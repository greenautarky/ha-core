"""Integration for greenautarky post-onboarding setup wizard.

Serves a standalone unauthenticated page at /greenautarky-setup that guides
the user through GDPR consent, telemetry preferences, and device info.
In tenant mode, also handles account creation.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .http import (
    GAOnboardingCompleteView,
    GAOnboardingCreateTenantView,
    GAOnboardingGDPRView,
    GAOnboardingPageView,
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

    # Register HTTP views (always — status check needs to work even when done)
    hass.http.register_view(GAOnboardingPageView())
    hass.http.register_view(GAOnboardingStatusView())
    hass.http.register_view(GAOnboardingGDPRView())
    hass.http.register_view(GAOnboardingTelemetryView())
    hass.http.register_view(GAOnboardingCompleteView())
    hass.http.register_view(GAOnboardingCreateTenantView())

    if not state.get("completed"):
        _LOGGER.info("greenautarky onboarding available at /greenautarky-setup")

    return True
