"""HTTP views for greenautarky onboarding.

All views are unauthenticated (like stock HA onboarding) but gated by the
completion state — once onboarding is done, the endpoints return 403.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Load the HTML template once at import time
_PAGE_HTML = (Path(__file__).parent / "page.html").read_text(encoding="utf-8")


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
    """Serve the standalone onboarding wizard page."""

    url = "/greenautarky-setup"
    name = "greenautarky_onboarding:page"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Serve the onboarding wizard HTML page."""
        hass: HomeAssistant = request.app["hass"]
        state = _get_state(hass)
        if state.get("completed"):
            # Redirect to dashboard if already done
            raise web.HTTPFound("/")
        return web.Response(text=_PAGE_HTML, content_type="text/html")


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


class GAOnboardingCreateTenantView(HomeAssistantView):
    """Create a tenant (normal) user during re-onboarding."""

    url = "/api/greenautarky_onboarding/create_tenant"
    name = "api:greenautarky_onboarding:create_tenant"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Create a new tenant user with normal (non-admin) privileges."""
        hass: HomeAssistant = request.app["hass"]
        if err := _check_not_completed(hass):
            return err

        # Only allow in tenant mode
        state = _get_state(hass)
        if not state.get("tenant_mode"):
            return web.json_response(
                {"message": "Not in tenant mode"}, status=403
            )

        body = await request.json()
        name = body.get("name", "").strip()
        username = body.get("username", "").strip()
        password = body.get("password", "")

        if not name or not username or not password:
            return self.json_message(
                "name, username, and password are required", status_code=400
            )

        # Create user in normal user group (not admin)
        tenant_user = await hass.auth.async_create_user(
            name, group_ids=[GROUP_ID_USER]
        )

        # Create credentials (homeassistant auth provider)
        provider = hass.auth.auth_providers[0]
        await provider.async_initialize()
        await hass.async_add_executor_job(
            provider.data.add_auth, username, password
        )
        credentials = await provider.async_get_or_create_credentials(
            {"username": username}
        )
        await hass.auth.async_link_user(tenant_user, credentials)

        # Mark account step as done
        store = _get_store(hass)
        if "account" not in state.get("steps_done", []):
            state.setdefault("steps_done", []).append("account")
            await store.async_save(state)

        _LOGGER.info("Created tenant user: %s", name)

        return self.json({"status": "ok", "user_id": tenant_user.id})
