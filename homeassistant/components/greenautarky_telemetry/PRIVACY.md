# greenautarky_telemetry — Privacy Tier Implementation Notes

**Canonical doc**: [`ga-ihost-docs/PRIVACY_TIERS.md`](https://github.com/greenautarky/ga-ihost-docs/blob/main/PRIVACY_TIERS.md)
**Roadmap**: [`ga-ihost-docs/PRIVACY_IMPLEMENTATION_ROADMAP.md`](https://github.com/greenautarky/ga-ihost-docs/blob/main/PRIVACY_IMPLEMENTATION_ROADMAP.md)

This file documents the HA Core side of the privacy tier refactor.
Short by design — most of the substance is in the canonical doc.

## What this component does

`greenautarky_telemetry` persists consent state to HA's storage:
`.storage/greenautarky_telemetry`. The sibling component
`greenautarky_onboarding` provides the UI panel that drives this.

The boot-time `ga-telemetry-gate` service on the OS reads this
storage file and creates marker files that systemd uses to gate
fluent-bit + telegraf.

## Phase C — Tier 1 default ON

**Goal**: error_logs starts ON for new onboardings (was OFF).

**Code change** (consent.py / __init__.py):

```python
# was:
DEFAULT_CONSENT = {"error_logs": False, "metrics": False}

# becomes:
DEFAULT_CONSENT = {
    "tier1": True,    # default ON, legal basis: berechtigtes Interesse
    "tier2": False,   # default OFF, legal basis: Einwilligung
    "legacy": {       # back-compat for v1 storage readers
        "error_logs": True,
        "metrics": False,
    },
}
```

**Storage schema bump** (consent.py — Phase E concerns):

```python
# v1 schema (current):
# {"version": 1, "minor_version": 1, "data": {"error_logs": bool, "metrics": bool}}

# v2 schema (target):
# {
#   "version": 2, "minor_version": 0,
#   "data": {
#     "policy_version_accepted": int,
#     "tiers": {
#       "tier1": {"value": bool, "accepted_at": iso8601, "policy_version": int},
#       "tier2": {"value": bool, "accepted_at": iso8601, "policy_version": int}
#     },
#     "legacy": {"error_logs": bool, "metrics": bool}  # mirror for gate-script back-compat
#   }
# }
```

Migration: on first load, v1 → v2 with policy_version=1, both
accepted_at = file's mtime.

## Phase E — Versioning

The `policy_version` is a small integer baked into the integration
constants. We bump it whenever the privacy policy text changes
substantively. On boot, `ga-telemetry-gate` reads the OS-baked
`/etc/ga-policy-version` and compares against
`data.policy_version_accepted` — if user's accepted version is
lower, marker files are NOT written → consent panel re-shows on
next browser visit.

Substantive change examples (bump policy_version):
- New data category added (e.g. "we now collect kernel panic timestamps")
- New legal basis ("we now process under Art. 6 (c)")
- New retention duration

Non-substantive (DO NOT bump):
- Typo fixes in the German text
- HTML markup changes
- Translation additions

## Phase F — Consent UI redesign

Owned by sibling integration `greenautarky_onboarding` —
`consent_page.html` template + view classes. This component
(`greenautarky_telemetry`) is just the backend.

The UI redesign keeps the storage schema stable (this component
doesn't need redesign-time changes). UI just hits the existing
`/api/greenautarky_onboarding/telemetry` POST.

## Touch points (when implementation starts)

1. `__init__.py` — DEFAULT_CONSENT + v2 schema migration
2. `const.py` — POLICY_VERSION constant
3. (separately) `greenautarky_onboarding/consent_page.html` — UI redesign

## Test coverage required

In `tests/components/greenautarky_telemetry/`:

- [ ] Test v1 → v2 migration preserves consent values
- [ ] Test default values match the spec (tier1=True, tier2=False)
- [ ] Test policy_version_accepted tracks per-tier acceptance correctly
- [ ] Test schema validation rejects malformed input
