"""HTTP views for greenautarky onboarding."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


def _get_store(hass: HomeAssistant) -> Store[dict[str, Any]]:
    """Get the storage store."""
    return hass.data[DOMAIN]["store"]


def _get_state(hass: HomeAssistant) -> dict[str, Any]:
    """Get the current onboarding state."""
    return hass.data[DOMAIN]["state"]


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
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Accept GDPR consent."""
        hass: HomeAssistant = request.app["hass"]
        state = _get_state(hass)
        store = _get_store(hass)

        body = await request.json()
        state["gdpr_accepted"] = bool(body.get("accepted", False))
        state["steps_done"].append("gdpr")
        await store.async_save(state)

        return self.json({"status": "ok"})


class GAOnboardingTelemetryView(HomeAssistantView):
    """Handle telemetry preferences."""

    url = "/api/greenautarky_onboarding/telemetry"
    name = "api:greenautarky_onboarding:telemetry"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Save telemetry preferences."""
        hass: HomeAssistant = request.app["hass"]
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

        state["steps_done"].append("telemetry")
        await store.async_save(state)

        return self.json({"status": "ok"})


class GAOnboardingCompleteView(HomeAssistantView):
    """Mark onboarding as complete."""

    url = "/api/greenautarky_onboarding/complete"
    name = "api:greenautarky_onboarding:complete"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Complete the GA onboarding."""
        hass: HomeAssistant = request.app["hass"]
        state = _get_state(hass)
        store = _get_store(hass)

        state["steps_done"].append("complete")
        state["completed"] = True
        await store.async_save(state)

        # Remove the panel so user goes to normal dashboard
        from homeassistant.components import frontend

        from .const import PANEL_URL_PATH

        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)

        _LOGGER.info("greenautarky onboarding completed")

        return self.json({"status": "ok", "redirect": "/"})


class GAOnboardingCreateTenantView(HomeAssistantView):
    """Create a tenant (normal) user during re-onboarding."""

    url = "/api/greenautarky_onboarding/create_tenant"
    name = "api:greenautarky_onboarding:create_tenant"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Create a new tenant user with normal (non-admin) privileges."""
        hass: HomeAssistant = request.app["hass"]
        user = request["hass_user"]

        # Only admin can create tenants
        if not user.is_owner:
            return self.json_message("Unauthorized", status_code=403)

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
        state = _get_state(hass)
        store = _get_store(hass)
        if "account" not in state.get("steps_done", []):
            state.setdefault("steps_done", []).append("account")
            await store.async_save(state)

        _LOGGER.info("Created tenant user: %s", name)

        return self.json({"status": "ok", "user_id": tenant_user.id})
