"""Integration for greenautarky telemetry preferences."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

DOMAIN = "greenautarky_telemetry"
STORAGE_KEY = "greenautarky_telemetry"
STORAGE_VERSION = 1

DEFAULT_PREFERENCES: dict[str, bool] = {
    "error_logs": False,
    "metrics": False,
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up greenautarky telemetry."""
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    data = await store.async_load()

    if data is None:
        data = {**DEFAULT_PREFERENCES}

    hass.data[DOMAIN] = {"store": store, "preferences": data}

    websocket_api.async_register_command(hass, websocket_get_preferences)
    websocket_api.async_register_command(hass, websocket_set_preferences)

    return True


@callback
@websocket_api.websocket_command(
    {vol.Required("type"): "greenautarky_telemetry/get"}
)
def websocket_get_preferences(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return greenautarky telemetry preferences."""
    connection.send_result(msg["id"], hass.data[DOMAIN]["preferences"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "greenautarky_telemetry/set",
        vol.Optional("error_logs"): bool,
        vol.Optional("metrics"): bool,
    }
)
@websocket_api.async_response
async def websocket_set_preferences(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set greenautarky telemetry preferences."""
    preferences: dict[str, bool] = hass.data[DOMAIN]["preferences"]

    for key in ("error_logs", "metrics"):
        if key in msg:
            preferences[key] = msg[key]

    store: Store = hass.data[DOMAIN]["store"]
    await store.async_save(preferences)

    connection.send_result(msg["id"], preferences)
