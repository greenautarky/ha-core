"""Integration for greenautarky post-onboarding setup wizard.

Serves a standalone unauthenticated page at /greenautarky-setup AND registers
a HA panel so the wizard is accessible from the mobile app too.
In tenant mode, also handles account creation.

After onboarding, manages consent re-confirmation via HA repairs system.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .consent import async_check_and_create_issues
from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .http import (
    GAConsentAcceptView,
    GAConsentPageView,
    GAConsentStatusView,
    GAOnboardingCompleteView,
    GAOnboardingCreateTenantView,
    GAOnboardingGDPRView,
    GAOnboardingPageView,
    GAOnboardingStatusView,
    GAOnboardingTelemetryView,
)

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/greenautarky_onboarding_static"
PANEL_URL_PATH = "greenautarky-setup-panel"

DEFAULT_STATE: dict[str, Any] = {
    "completed": False,
    "gdpr_accepted": False,
    "steps_done": [],
    "consents": {},
}


def _migrate_v1_to_v2(state: dict[str, Any]) -> dict[str, Any]:
    """Migrate storage from v1 to v2: add consents dict.

    If GDPR was already accepted during onboarding, seed consents.gdpr
    with version 1 so the user isn't immediately prompted to re-confirm.
    """
    if "consents" not in state:
        state["consents"] = {}
    if state.get("gdpr_accepted") and "gdpr" not in state["consents"]:
        state["consents"]["gdpr"] = {
            "version": 1,
            "accepted_at": "migrated-from-v1",
        }
    return state


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up greenautarky onboarding."""
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    state = await store.async_load()

    if state is None:
        state = {**DEFAULT_STATE, "steps_done": [], "consents": {}}
    else:
        # Migrate from v1 if needed
        if "consents" not in state:
            state = _migrate_v1_to_v2(state)
            await store.async_save(state)

    hass.data[DOMAIN] = {"store": store, "state": state}

    # Register onboarding HTTP views (always — status check needs to work)
    hass.http.register_view(GAOnboardingPageView())
    hass.http.register_view(GAOnboardingStatusView())
    hass.http.register_view(GAOnboardingGDPRView())
    hass.http.register_view(GAOnboardingTelemetryView())
    hass.http.register_view(GAOnboardingCompleteView())
    hass.http.register_view(GAOnboardingCreateTenantView())

    # Register consent HTTP views (authenticated, always available)
    hass.http.register_view(GAConsentPageView())
    hass.http.register_view(GAConsentStatusView())
    hass.http.register_view(GAConsentAcceptView())

    # If onboarding not completed, also register a panel for the HA app
    if not state.get("completed"):
        await _async_register_panel(hass)
        _LOGGER.info("greenautarky onboarding available at /greenautarky-setup")

    # Check for outdated consents and create repair issues if needed
    if state.get("completed"):
        async_check_and_create_issues(hass, state)

    return True


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the panel so the wizard is accessible from the HA app."""
    panel_dir = Path(__file__).parent / "panel" / "dist"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(panel_dir), cache_headers=False)]
    )

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="ga-onboarding-panel",
        sidebar_title="Einrichtung",
        sidebar_icon="mdi:rocket-launch",
        module_url=f"{URL_BASE}/entrypoint.js",
        embed_iframe=False,
        require_admin=False,
    )
