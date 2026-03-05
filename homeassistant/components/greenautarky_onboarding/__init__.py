"""Integration for greenautarky post-onboarding setup wizard."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PANEL_URL_PATH, STORAGE_KEY, STORAGE_VERSION, URL_BASE
from .http import (
    GAOnboardingCompleteView,
    GAOnboardingCreateTenantView,
    GAOnboardingGDPRView,
    GAOnboardingStatusView,
    GAOnboardingTelemetryView,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_STATE: dict[str, Any] = {
    "completed": False,
    "gdpr_accepted": False,
    "steps_done": [],
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up greenautarky onboarding."""
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    state = await store.async_load()

    if state is None:
        state = {**DEFAULT_STATE, "steps_done": []}

    hass.data[DOMAIN] = {"store": store, "state": state}

    # Register HTTP API views
    hass.http.register_view(GAOnboardingStatusView())
    hass.http.register_view(GAOnboardingGDPRView())
    hass.http.register_view(GAOnboardingTelemetryView())
    hass.http.register_view(GAOnboardingCompleteView())
    hass.http.register_view(GAOnboardingCreateTenantView())

    # If onboarding not completed, register the setup wizard panel
    if not state.get("completed"):
        await _async_register_panel(hass)
        _LOGGER.info("greenautarky onboarding panel registered")

    return True


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the GA onboarding wizard panel."""
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
