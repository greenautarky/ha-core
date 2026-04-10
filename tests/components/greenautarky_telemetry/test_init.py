"""Tests for the greenautarky_telemetry integration."""

from typing import Any

from homeassistant.components.greenautarky_telemetry import (
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.typing import WebSocketGenerator


async def test_setup_creates_defaults(hass: HomeAssistant) -> None:
    """Test that setup initializes default preferences."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert DOMAIN in hass.data
    prefs = hass.data[DOMAIN]["preferences"]
    assert prefs["error_logs"] is False
    assert prefs["metrics"] is False


async def test_setup_loads_existing_storage(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Test that setup loads existing preferences from storage."""
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {"error_logs": True, "metrics": True},
    }

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    prefs = hass.data[DOMAIN]["preferences"]
    assert prefs["error_logs"] is True
    assert prefs["metrics"] is True


async def test_ws_get_defaults(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test websocket get returns default preferences."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    await client.send_json({"id": 1, "type": "greenautarky_telemetry/get"})
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"] == {"error_logs": False, "metrics": False}


async def test_ws_set_error_logs(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test websocket set updates error_logs preference."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    await client.send_json(
        {"id": 1, "type": "greenautarky_telemetry/set", "error_logs": True}
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is True
    assert msg["result"]["metrics"] is False


async def test_ws_set_metrics(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test websocket set updates metrics preference."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    await client.send_json(
        {"id": 1, "type": "greenautarky_telemetry/set", "metrics": True}
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is False
    assert msg["result"]["metrics"] is True


async def test_ws_set_both(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test websocket set updates both preferences at once."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    await client.send_json(
        {
            "id": 1,
            "type": "greenautarky_telemetry/set",
            "error_logs": True,
            "metrics": True,
        }
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is True
    assert msg["result"]["metrics"] is True


async def test_ws_set_persists(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test that set preferences persist and can be retrieved."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    # Set preferences
    await client.send_json(
        {
            "id": 1,
            "type": "greenautarky_telemetry/set",
            "error_logs": True,
            "metrics": True,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]

    # Get preferences and verify they persisted
    await client.send_json({"id": 2, "type": "greenautarky_telemetry/get"})
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is True
    assert msg["result"]["metrics"] is True


async def test_ws_set_partial_update(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test that partial updates only change specified fields."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    # Enable error_logs
    await client.send_json(
        {"id": 1, "type": "greenautarky_telemetry/set", "error_logs": True}
    )
    msg = await client.receive_json()
    assert msg["success"]

    # Enable metrics without touching error_logs
    await client.send_json(
        {"id": 2, "type": "greenautarky_telemetry/set", "metrics": True}
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is True
    assert msg["result"]["metrics"] is True


async def test_ws_set_disable(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test disabling previously enabled preferences."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    # Enable both
    await client.send_json(
        {
            "id": 1,
            "type": "greenautarky_telemetry/set",
            "error_logs": True,
            "metrics": True,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]

    # Disable error_logs
    await client.send_json(
        {"id": 2, "type": "greenautarky_telemetry/set", "error_logs": False}
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is False
    assert msg["result"]["metrics"] is True


async def test_ws_set_empty_message_succeeds(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Test set with no preference fields keeps existing values."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    # Set with no fields — should succeed and return current defaults
    await client.send_json({"id": 1, "type": "greenautarky_telemetry/set"})
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is False
    assert msg["result"]["metrics"] is False


async def test_ws_get_after_restart_with_storage(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test preferences survive component reload (loaded from storage)."""
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {"error_logs": True, "metrics": False},
    }

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "greenautarky_telemetry/get"})
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["error_logs"] is True
    assert msg["result"]["metrics"] is False


async def test_storage_format_matches_os_gate(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test that storage format matches what ga-telemetry-gate expects on the OS.

    The OS-level ga-telemetry-gate script parses the JSON with sed and expects:
      "error_logs" : true   or   "metrics" : false
    inside a {"key":...,"version":...,"data":{...}} wrapper.
    Verify the HA Store writes in this format.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)

    await client.send_json(
        {
            "id": 1,
            "type": "greenautarky_telemetry/set",
            "error_logs": True,
            "metrics": False,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]

    # Verify the storage dict matches the expected structure
    stored = hass_storage.get(STORAGE_KEY)
    assert stored is not None
    assert stored["version"] == STORAGE_VERSION
    assert stored["key"] == STORAGE_KEY
    assert "data" in stored
    assert stored["data"]["error_logs"] is True
    assert stored["data"]["metrics"] is False


async def test_default_is_opt_out_safe(hass: HomeAssistant) -> None:
    """Test that defaults are False — GDPR-safe opt-in.

    The OS telemetry gate (ga-telemetry-gate) blocks services when values
    are False or missing. This test ensures HA defaults are safe so that
    services never run without explicit user consent.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    prefs = hass.data[DOMAIN]["preferences"]
    assert prefs["error_logs"] is False, "error_logs must default to False (opt-in)"
    assert prefs["metrics"] is False, "metrics must default to False (opt-in)"
