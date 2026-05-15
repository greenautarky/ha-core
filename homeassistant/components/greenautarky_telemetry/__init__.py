"""Integration for greenautarky telemetry preferences (Privacy Tier model).

Implements the storage backend for the consent tiers documented in
ga-ihost-docs/PRIVACY_TIERS.md:

- Tier 0 (Vertragserfüllung + berechtigtes Interesse): NO toggle here
  — always-on at the OS layer. This integration tracks only the
  consent-gated tiers below.
- Tier 1 (berechtigtes Interesse): default ON, opt-out
- Tier 2 (Einwilligung): default OFF, opt-in
- Tier 3 (Einwilligung, zeitbegrenzt): not stored here — handled by
  case-management UI per-incident.

Storage schema v2 (this version):
    {
      "version": 2, "minor_version": 0,
      "data": {
        "policy_version_accepted": int,
        "tiers": {
          "tier1": {"value": bool, "accepted_at": iso8601, "policy_version": int},
          "tier2": {"value": bool, "accepted_at": iso8601, "policy_version": int}
        },
        "legacy": {"error_logs": bool, "metrics": bool}   # mirrored for back-compat
      }
    }

Schema v1 (legacy — auto-migrated on first read):
    {"version":1, "data":{"error_logs": bool, "metrics": bool}}

Migration rule: v1 values are preserved literally
  (error_logs → tier1, metrics → tier2).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

DOMAIN = "greenautarky_telemetry"
STORAGE_KEY = "greenautarky_telemetry"
STORAGE_VERSION = 2
STORAGE_MINOR_VERSION = 0

# OS-baked policy version (must match /etc/ga-policy-version in the OS image).
# Bump this only when the privacy policy text changes substantively (new
# data category, new legal basis, new retention duration). Cosmetic edits
# do NOT count.
POLICY_VERSION = 1

# Canonical tier keys
TIER_1 = "tier1"
TIER_2 = "tier2"

# Legacy aliases (kept for the consent UI's existing message schema)
LEGACY_TIER1_KEY = "error_logs"
LEGACY_TIER2_KEY = "metrics"

DEFAULT_PREFERENCES: dict[str, bool] = {
    TIER_1: True,    # Tier 1 default ON  — berechtigtes Interesse, opt-out
    TIER_2: False,   # Tier 2 default OFF — Einwilligung, opt-in
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_v2_record(
    values: dict[str, bool],
    *,
    policy_version: int = POLICY_VERSION,
    accepted_at: str | None = None,
) -> dict[str, Any]:
    """Build a v2 storage payload (the ``data`` part) from a flat values dict.

    ``policy_version`` records which version of the privacy policy the
    user was shown when they made this decision. Defaults to the current
    OS-baked ``POLICY_VERSION``, but migrations from v1 storage pass
    ``policy_version=1`` so a future bump correctly marks those users
    as having stale consent.
    """
    when = accepted_at or _now_iso()
    return {
        "policy_version_accepted": policy_version,
        "tiers": {
            TIER_1: {
                "value": bool(values.get(TIER_1, DEFAULT_PREFERENCES[TIER_1])),
                "accepted_at": when,
                "policy_version": policy_version,
            },
            TIER_2: {
                "value": bool(values.get(TIER_2, DEFAULT_PREFERENCES[TIER_2])),
                "accepted_at": when,
                "policy_version": policy_version,
            },
        },
        "legacy": {
            LEGACY_TIER1_KEY: bool(values.get(TIER_1, DEFAULT_PREFERENCES[TIER_1])),
            LEGACY_TIER2_KEY: bool(values.get(TIER_2, DEFAULT_PREFERENCES[TIER_2])),
        },
    }


def _is_stale(record: dict[str, Any]) -> bool:
    """Whether the recorded consent predates the current policy version.

    Returns ``False`` when ``policy_version_accepted`` is ``None`` (fresh
    device, never onboarded — the panel handles that case separately).
    Returns ``True`` when an explicit older version is recorded.
    """
    accepted = record.get("policy_version_accepted")
    if accepted is None:
        return False
    return int(accepted) < POLICY_VERSION


def _flatten_v2(data: dict[str, Any]) -> dict[str, bool]:
    """Extract a flat values dict from a v2 storage payload.

    Used for the websocket get response and internal consumers that
    still expect a flat structure.
    """
    tiers = (data or {}).get("tiers", {}) or {}
    return {
        TIER_1: bool(tiers.get(TIER_1, {}).get("value", DEFAULT_PREFERENCES[TIER_1])),
        TIER_2: bool(tiers.get(TIER_2, {}).get("value", DEFAULT_PREFERENCES[TIER_2])),
    }


class TelemetryStore(Store[dict[str, Any]]):
    """Subclassed Store that knows how to migrate v1 → v2 on first read."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Migrate older schema versions to the current v2 shape."""
        if old_major_version == 1:
            # v1 was flat: {"error_logs": bool, "metrics": bool}. The user
            # accepted v1 of the policy, so we preserve policy_version=1
            # — a future POLICY_VERSION bump will then mark this as stale
            # and trigger a re-consent prompt.
            return _build_v2_record(
                {
                    TIER_1: bool(old_data.get(LEGACY_TIER1_KEY, DEFAULT_PREFERENCES[TIER_1])),
                    TIER_2: bool(old_data.get(LEGACY_TIER2_KEY, DEFAULT_PREFERENCES[TIER_2])),
                },
                policy_version=1,
            )
        # Unknown future-older version (shouldn't happen) — fall through to
        # rebuilding from defaults.
        return _build_v2_record(DEFAULT_PREFERENCES)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up greenautarky telemetry."""
    store = TelemetryStore(
        hass,
        STORAGE_VERSION,
        STORAGE_KEY,
        minor_version=STORAGE_MINOR_VERSION,
    )
    data = await store.async_load()

    if data is None:
        # No prior consent decision recorded → seed with defaults.
        # Note: we DO NOT auto-save here — the user must actively complete
        # onboarding for any consent to count. Defaults are returned to
        # the UI to show as initial toggle state.
        #
        # policy_version_accepted=None signals "not yet onboarded" — the
        # frontend treats this distinctly from "stale" (consent given but
        # under an older policy version).
        data = _build_v2_record(DEFAULT_PREFERENCES)
        data["policy_version_accepted"] = None
        for tier in (TIER_1, TIER_2):
            data["tiers"][tier]["policy_version"] = None
            data["tiers"][tier]["accepted_at"] = None

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
    """Return greenautarky telemetry preferences.

    Response format intentionally includes BOTH the v2 structured form
    AND a flat compat view, so old UI code that expects
    ``{"error_logs": bool, "metrics": bool}`` keeps working.
    """
    raw = hass.data[DOMAIN]["preferences"]
    flat = _flatten_v2(raw)
    response = {
        # v2 structured (preferred for new clients)
        "policy_version_accepted": raw.get("policy_version_accepted"),
        "current_policy_version": POLICY_VERSION,
        "consent_is_stale": _is_stale(raw),
        "tiers": raw.get("tiers", {}),
        # Flat compat view for legacy clients
        TIER_1: flat[TIER_1],
        TIER_2: flat[TIER_2],
        LEGACY_TIER1_KEY: flat[TIER_1],
        LEGACY_TIER2_KEY: flat[TIER_2],
    }
    connection.send_result(msg["id"], response)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "greenautarky_telemetry/set",
        # Canonical tier keys
        vol.Optional(TIER_1): bool,
        vol.Optional(TIER_2): bool,
        # Legacy aliases (still accepted from old UI clients)
        vol.Optional(LEGACY_TIER1_KEY): bool,
        vol.Optional(LEGACY_TIER2_KEY): bool,
    }
)
@websocket_api.async_response
async def websocket_set_preferences(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set greenautarky telemetry preferences.

    Accepts both the canonical tier keys (``tier1``/``tier2``) and the
    legacy aliases (``error_logs``/``metrics``). Canonical keys win if
    both are present in the same message.
    """
    raw = hass.data[DOMAIN]["preferences"]
    current = _flatten_v2(raw)

    # Apply legacy aliases first (lower precedence)
    if LEGACY_TIER1_KEY in msg:
        current[TIER_1] = bool(msg[LEGACY_TIER1_KEY])
    if LEGACY_TIER2_KEY in msg:
        current[TIER_2] = bool(msg[LEGACY_TIER2_KEY])

    # Canonical keys override
    if TIER_1 in msg:
        current[TIER_1] = bool(msg[TIER_1])
    if TIER_2 in msg:
        current[TIER_2] = bool(msg[TIER_2])

    new_record = _build_v2_record(current)
    hass.data[DOMAIN]["preferences"] = new_record

    store: TelemetryStore = hass.data[DOMAIN]["store"]
    await store.async_save(new_record)

    # Echo response in the same shape as `get`
    connection.send_result(
        msg["id"],
        {
            "policy_version_accepted": new_record["policy_version_accepted"],
            "current_policy_version": POLICY_VERSION,
            "consent_is_stale": _is_stale(new_record),
            "tiers": new_record["tiers"],
            TIER_1: current[TIER_1],
            TIER_2: current[TIER_2],
            LEGACY_TIER1_KEY: current[TIER_1],
            LEGACY_TIER2_KEY: current[TIER_2],
        },
    )
