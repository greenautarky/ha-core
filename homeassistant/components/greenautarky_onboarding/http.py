"""HTTP views for greenautarky onboarding.

Onboarding views are unauthenticated (like stock HA onboarding) but gated by
the completion state — once onboarding is done, the endpoints return 403.

Consent views are authenticated and available after onboarding is complete.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.auth.providers.homeassistant import HassAuthProvider
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .consent import async_record_consent, get_outdated_consents
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _async_get_hass_provider(hass: HomeAssistant) -> HassAuthProvider:
    """Get the Home Assistant auth provider."""
    for prv in hass.auth.auth_providers:
        if prv.type == "homeassistant":
            return prv
    raise RuntimeError("Home Assistant auth provider not found")

# Load HTML templates once at import time
_CONSENT_HTML = (Path(__file__).parent / "consent_page.html").read_text(encoding="utf-8")


def _get_store(hass: HomeAssistant) -> Store[dict[str, Any]]:
    """Get the storage store."""
    return hass.data[DOMAIN]["store"]


def _get_state(hass: HomeAssistant) -> dict[str, Any]:
    """Get the current onboarding state."""
    return hass.data[DOMAIN]["state"]


def _check_not_completed(hass: HomeAssistant) -> web.Response | None:
    """Return a 403 response if onboarding is already completed."""
    state = _get_state(hass)
    if state.get("completed"):
        return web.json_response(
            {"message": "Onboarding already completed"}, status=403
        )
    return None


class GAOnboardingPageView(HomeAssistantView):
    """Redirect to the built greenautarky-setup.html page.

    The actual HTML is built by the frontend build pipeline and served as a
    static file by the frontend component (just like onboarding.html).
    """

    url = "/greenautarky-setup"
    name = "greenautarky_onboarding:page"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Redirect to the built frontend page."""
        hass: HomeAssistant = request.app["hass"]
        state = _get_state(hass)
        if state.get("completed"):
            raise web.HTTPFound("/")
        raise web.HTTPFound("/greenautarky-setup.html")


class GAOnboardingStatusView(HomeAssistantView):
    """Return current onboarding status."""

    url = "/api/greenautarky_onboarding/status"
    name = "api:greenautarky_onboarding:status"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return onboarding status."""
        hass: HomeAssistant = request.app["hass"]
        state = _get_state(hass)
        return self.json(state)


class GAOnboardingGDPRView(HomeAssistantView):
    """Handle GDPR consent."""

    url = "/api/greenautarky_onboarding/gdpr"
    name = "api:greenautarky_onboarding:gdpr"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Accept GDPR consent."""
        hass: HomeAssistant = request.app["hass"]
        if err := _check_not_completed(hass):
            return err

        state = _get_state(hass)
        store = _get_store(hass)

        body = await request.json()
        state["gdpr_accepted"] = bool(body.get("accepted", False))
        if "gdpr" not in state["steps_done"]:
            state["steps_done"].append("gdpr")
        await store.async_save(state)

        return self.json({"status": "ok"})


class GAOnboardingTelemetryView(HomeAssistantView):
    """Handle telemetry preferences."""

    url = "/api/greenautarky_onboarding/telemetry"
    name = "api:greenautarky_onboarding:telemetry"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Save telemetry preferences."""
        hass: HomeAssistant = request.app["hass"]
        if err := _check_not_completed(hass):
            return err

        state = _get_state(hass)
        store = _get_store(hass)

        body = await request.json()

        # Forward to greenautarky_telemetry integration
        telemetry_data = hass.data.get("greenautarky_telemetry")
        if telemetry_data:
            prefs = telemetry_data["preferences"]
            prefs["error_logs"] = bool(body.get("error_logs", False))
            prefs["metrics"] = bool(body.get("metrics", False))
            telemetry_store: Store = telemetry_data["store"]
            await telemetry_store.async_save(prefs)

        if "telemetry" not in state["steps_done"]:
            state["steps_done"].append("telemetry")
        await store.async_save(state)

        return self.json({"status": "ok"})


class GAOnboardingCompleteView(HomeAssistantView):
    """Mark onboarding as complete."""

    url = "/api/greenautarky_onboarding/complete"
    name = "api:greenautarky_onboarding:complete"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Complete the GA onboarding."""
        hass: HomeAssistant = request.app["hass"]
        if err := _check_not_completed(hass):
            return err

        state = _get_state(hass)
        store = _get_store(hass)

        if "complete" not in state["steps_done"]:
            state["steps_done"].append("complete")
        state["completed"] = True
        await store.async_save(state)

        # Remove the sidebar panel (for app users)
        from homeassistant.components import frontend

        frontend.async_remove_panel(
            hass, "greenautarky-setup-panel", warn_if_unknown=False
        )

        _LOGGER.info("greenautarky onboarding completed")

        return self.json({"status": "ok", "redirect": "/"})


class GAOnboardingCreateUserView(HomeAssistantView):
    """Create a user account during greenautarky onboarding.

    This endpoint is unauthenticated (the end user has no account yet).
    It creates a normal (non-admin) user and returns an auth_code so the
    frontend can authenticate and continue with authenticated steps.
    """

    url = "/api/greenautarky_onboarding/create_user"
    name = "api:greenautarky_onboarding:create_user"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Create a new user and return auth_code for frontend auth."""
        hass: HomeAssistant = request.app["hass"]
        if err := _check_not_completed(hass):
            return err

        body = await request.json()
        client_id = body.get("client_id", "").strip()
        name = body.get("name", "").strip()
        username = body.get("username", "").strip()
        password = body.get("password", "")
        language = body.get("language", "de")

        if not name or not username or not password or not client_id:
            return self.json_message(
                "client_id, name, username, and password are required",
                status_code=400,
            )

        # Create user in normal user group (not admin)
        user = await hass.auth.async_create_user(
            name, group_ids=[GROUP_ID_USER]
        )

        # Create credentials via homeassistant auth provider
        provider = _async_get_hass_provider(hass)
        await provider.async_initialize()
        await provider.async_add_auth(username, password)
        credentials = await provider.async_get_or_create_credentials(
            {"username": username}
        )
        await hass.auth.async_link_user(user, credentials)

        # Create person entity if available
        if "person" in hass.config.components:
            from homeassistant.components import person  # noqa: PLC0415

            await person.async_create_person(hass, name, user_id=user.id)

        # Mark account step as done
        state = _get_state(hass)
        store = _get_store(hass)
        if "account" not in state.get("steps_done", []):
            state.setdefault("steps_done", []).append("account")
            await store.async_save(state)

        # Return auth_code so frontend can authenticate
        from homeassistant.components.auth import create_auth_code  # noqa: PLC0415

        auth_code = create_auth_code(hass, client_id, credentials)

        _LOGGER.info("Created user via greenautarky onboarding: %s", name)

        return self.json({"auth_code": auth_code})


# ---------------------------------------------------------------------------
# Test/QA reset endpoint (admin-authenticated)
# ---------------------------------------------------------------------------


class GAOnboardingResetView(HomeAssistantView):
    """Reset GA onboarding state to allow re-running the wizard.

    Intended for QA and automated testing (e.g. ga-flasher stage 90).
    Requires admin authentication — the ga-flasher uses the admin token
    obtained during Phase 1 provisioning to call this endpoint.

    Resets: completed, gdpr_accepted, steps_done.
    Preserves: consents (version-tracked separately).
    """

    url = "/api/greenautarky_onboarding/reset"
    name = "api:greenautarky_onboarding:reset"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Reset onboarding state."""
        hass: HomeAssistant = request.app["hass"]

        # Require admin
        user = request["hass_user"]
        if not user.is_admin:
            return web.json_response({"message": "Admin required"}, status=403)

        state = _get_state(hass)
        store = _get_store(hass)

        # Reset wizard state, preserve consents
        state["completed"] = False
        state["gdpr_accepted"] = False
        state["steps_done"] = []
        await store.async_save(state)

        # Re-register the sidebar panel (removed on completion)
        from homeassistant.components.greenautarky_onboarding import (  # noqa: PLC0415
            _async_register_panel,
        )

        await _async_register_panel(hass)

        _LOGGER.info("greenautarky onboarding state reset by %s", user.name)
        return self.json({"status": "ok"})


# ---------------------------------------------------------------------------
# Consent views (authenticated — for post-onboarding consent re-confirmation)
# ---------------------------------------------------------------------------


class GAConsentPageView(HomeAssistantView):
    """Serve the standalone consent re-confirmation page."""

    url = "/greenautarky-consent"
    name = "greenautarky_onboarding:consent_page"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Serve the consent page HTML."""
        return web.Response(text=_CONSENT_HTML, content_type="text/html")


class GAConsentStatusView(HomeAssistantView):
    """Return which consents are outdated."""

    url = "/api/greenautarky_onboarding/consent/status"
    name = "api:greenautarky_onboarding:consent:status"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return consent status."""
        hass: HomeAssistant = request.app["hass"]
        state = _get_state(hass)
        outdated = get_outdated_consents(state)
        return self.json({
            "consents": state.get("consents", {}),
            "outdated": list(outdated.keys()),
        })


class GAConsentAcceptView(HomeAssistantView):
    """Accept a consent type."""

    url = "/api/greenautarky_onboarding/consent/accept"
    name = "api:greenautarky_onboarding:consent:accept"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Record consent acceptance."""
        hass: HomeAssistant = request.app["hass"]
        store = _get_store(hass)
        state = _get_state(hass)

        body = await request.json()
        consent_type = body.get("type", "")

        if not consent_type:
            return web.json_response(
                {"message": "Missing 'type' field"}, status=400
            )

        ok = await async_record_consent(hass, store, state, consent_type)
        if not ok:
            return web.json_response(
                {"message": f"Unknown consent type: {consent_type}"}, status=400
            )

        return self.json({"status": "ok"})
