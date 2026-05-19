"""Tests for the greenautarky_onboarding component."""

from homeassistant.components.greenautarky_onboarding.const import (
    DOMAIN as DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)


def mock_storage(hass_storage, data):
    """Mock the greenautarky onboarding storage."""
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": data,
    }
