"""Tests for the greenautarky_telemetry integration (Privacy Tier model).

Schema v2 + tier-aware behavior, see:
  ga-ihost-docs/PRIVACY_TIERS.md
  homeassistant/components/greenautarky_telemetry/PRIVACY.md
"""

from typing import Any

from homeassistant.components.greenautarky_telemetry import (
    DOMAIN,
    LEGACY_TIER1_KEY,
    LEGACY_TIER2_KEY,
    POLICY_VERSION,
    STORAGE_KEY,
    STORAGE_VERSION,
    TIER_1,
    TIER_2,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.typing import WebSocketGenerator


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


async def test_setup_creates_tier_defaults(hass: HomeAssistant) -> None:
    """No prior storage → defaults match the Tier model (tier1 ON, tier2 OFF)."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert DOMAIN in hass.data
    prefs = hass.data[DOMAIN]["preferences"]
    # v2 structured form
    assert prefs["tiers"][TIER_1]["value"] is True
    assert prefs["tiers"][TIER_2]["value"] is False
    # Policy version stamped
    assert prefs["policy_version_accepted"] == POLICY_VERSION


async def test_default_tier_legal_basis_alignment(hass: HomeAssistant) -> None:
    """The default tier values must match the documented legal-basis rules.

    Tier 1 default ON is defensible under berechtigtes Interesse (Art. 6 f).
    Tier 2 default OFF requires explicit Einwilligung (Art. 6 a).
    Drifting from this would change our legal posture — block silently
    via this test rather than accept incompatible defaults.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    prefs = hass.data[DOMAIN]["preferences"]
    assert prefs["tiers"][TIER_1]["value"] is True, (
        "Tier 1 must default ON (berechtigtes Interesse)"
    )
    assert prefs["tiers"][TIER_2]["value"] is False, (
        "Tier 2 must default OFF (Einwilligung required)"
    )


# ---------------------------------------------------------------------------
# v1 → v2 migration
# ---------------------------------------------------------------------------


async def test_migrates_v1_storage_preserving_values(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """v1 flat schema is migrated to v2 nested form, values preserved."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {LEGACY_TIER1_KEY: True, LEGACY_TIER2_KEY: True},
    }

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    prefs = hass.data[DOMAIN]["preferences"]
    # v1 error_logs=True → tier1=True
    assert prefs["tiers"][TIER_1]["value"] is True
    # v1 metrics=True → tier2=True
    assert prefs["tiers"][TIER_2]["value"] is True
    # Legacy mirror present for OS-side gate-script back-compat
    assert prefs["legacy"][LEGACY_TIER1_KEY] is True
    assert prefs["legacy"][LEGACY_TIER2_KEY] is True


async def test_migrates_v1_storage_with_partial_values(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """v1 with one True one False → preserves both literally."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {LEGACY_TIER1_KEY: True, LEGACY_TIER2_KEY: False},
    }

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    prefs = hass.data[DOMAIN]["preferences"]
    assert prefs["tiers"][TIER_1]["value"] is True
    assert prefs["tiers"][TIER_2]["value"] is False


# ---------------------------------------------------------------------------
# Websocket: GET
# ---------------------------------------------------------------------------


async def test_ws_get_returns_both_canonical_and_legacy_keys(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Response shape includes tier1/tier2 (canonical) AND error_logs/metrics
    (legacy aliases) so old UI code keeps working during transition."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "greenautarky_telemetry/get"})
    msg = await client.receive_json()

    assert msg["success"]
    r = msg["result"]
    # v2 structured fields
    assert "tiers" in r
    assert "policy_version_accepted" in r
    assert "current_policy_version" in r
    # Flat canonical
    assert r[TIER_1] is True
    assert r[TIER_2] is False
    # Flat legacy aliases (same values as canonical)
    assert r[LEGACY_TIER1_KEY] is True
    assert r[LEGACY_TIER2_KEY] is False


# ---------------------------------------------------------------------------
# Websocket: SET
# ---------------------------------------------------------------------------


async def test_ws_set_with_legacy_keys(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Legacy error_logs/metrics keys still accepted by set endpoint."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1, "type": "greenautarky_telemetry/set",
        LEGACY_TIER1_KEY: False,
        LEGACY_TIER2_KEY: True,
    })
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"][TIER_1] is False
    assert msg["result"][TIER_2] is True


async def test_ws_set_with_canonical_keys(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Canonical tier1/tier2 keys work."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1, "type": "greenautarky_telemetry/set",
        TIER_1: False,
        TIER_2: True,
    })
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"][TIER_1] is False
    assert msg["result"][TIER_2] is True


async def test_ws_set_canonical_wins_over_legacy(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """If both canonical AND legacy key are in the same message, canonical wins.

    Defensive against confused clients that send both due to migration.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1, "type": "greenautarky_telemetry/set",
        TIER_1: True,
        LEGACY_TIER1_KEY: False,    # contradicts canonical, should be ignored
    })
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"][TIER_1] is True
    assert msg["result"][LEGACY_TIER1_KEY] is True   # mirror reflects canonical


async def test_ws_set_persists_v2_storage(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Set writes a v2-structured storage payload (with tiers + legacy mirror)."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1, "type": "greenautarky_telemetry/set",
        TIER_1: True,
        TIER_2: True,
    })
    msg = await client.receive_json()
    assert msg["success"]

    stored = hass_storage[STORAGE_KEY]
    assert stored["version"] == STORAGE_VERSION
    assert stored["key"] == STORAGE_KEY
    # v2 structured
    assert stored["data"]["tiers"][TIER_1]["value"] is True
    assert stored["data"]["tiers"][TIER_2]["value"] is True
    assert stored["data"]["tiers"][TIER_1]["policy_version"] == POLICY_VERSION
    # Legacy mirror preserved for OS-side gate-script back-compat
    assert stored["data"]["legacy"][LEGACY_TIER1_KEY] is True
    assert stored["data"]["legacy"][LEGACY_TIER2_KEY] is True


async def test_ws_set_records_accepted_at_iso8601(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Each tier records an accepted_at timestamp in ISO 8601 UTC format."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1, "type": "greenautarky_telemetry/set",
        TIER_1: True, TIER_2: False,
    })
    msg = await client.receive_json()
    assert msg["success"]

    accepted_at = msg["result"]["tiers"][TIER_1]["accepted_at"]
    # ISO 8601 UTC with Z suffix, e.g. "2026-05-15T15:00:00Z"
    assert accepted_at.endswith("Z")
    assert "T" in accepted_at
    assert len(accepted_at) == 20


async def test_ws_set_records_policy_version(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """policy_version is captured per-tier on every save."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1, "type": "greenautarky_telemetry/set",
        TIER_1: True,
    })
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["tiers"][TIER_1]["policy_version"] == POLICY_VERSION


async def test_ws_set_partial_update_preserves_other_tier(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Setting only tier1 doesn't reset tier2 — partial updates preserve."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    # Enable tier2 (default is off)
    await client.send_json({
        "id": 1, "type": "greenautarky_telemetry/set",
        TIER_2: True,
    })
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"][TIER_2] is True

    # Now disable tier1 — tier2 should stay True
    await client.send_json({
        "id": 2, "type": "greenautarky_telemetry/set",
        TIER_1: False,
    })
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"][TIER_1] is False
    assert msg["result"][TIER_2] is True


async def test_ws_set_empty_message_keeps_existing_values(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Empty set message is a no-op on values but still saves (refreshes accepted_at)."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "greenautarky_telemetry/set"})
    msg = await client.receive_json()

    assert msg["success"]
    # Defaults preserved
    assert msg["result"][TIER_1] is True
    assert msg["result"][TIER_2] is False
