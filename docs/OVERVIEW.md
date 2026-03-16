# greenautarky iHost - System architecture

Complete documentation of how all repositories, images, and build pipelines
come together for the Sonoff iHost hardware.

## Target hardware

- **Device:** Sonoff iHost (Smart Home Hub)
- **SoC:** Rockchip RV1126, ARM Cortex-A7
- **Architecture:** armv7 (32-bit)
- **OS:** Custom HA OS via Buildroot
- **Machine name:** `tinker`

## Repository map

| Repository | Purpose | Branch | Upstream |
|-----------|---------|--------|----------|
| [greenautarky/ha-core](https://github.com/greenautarky/ha-core) | HA Core + custom integrations | `ga/custom-onboarding` | `home-assistant/core` @ `2025.11.0` |
| [greenautarky/frontend](https://github.com/greenautarky/frontend) | HA Frontend (Lit/TypeScript) | `ga/custom-onboarding` | `home-assistant/frontend` @ `20251105.0` |
| [greenautarky/ha-supervisor](https://github.com/greenautarky/ha-supervisor) | Supervisor (container orchestrator) | `ga/custom-version-url` | `iHost-Open-Source-Project/ha-supervisor` @ `ihost-2025.11.4` |
| [greenautarky/ha-operating-system](https://github.com/greenautarky/ha-operating-system) | HA OS (Buildroot image) | `main` | `iHost-Open-Source-Project/ha-operating-system` |
| [greenautarky/haos-version](https://github.com/greenautarky/haos-version) | Version manifest (`stable.json`) | `main` | `iHost-Open-Source-Project/haos-version` |

### Local development paths

```
/home/user/git/homeassisant_core/       # ha-core
/home/user/git/homeassistant_frontend/  # frontend
/tmp/ga-supervisor/                     # ha-supervisor (cloned on demand)
```

## Container images

All custom images are published to `ghcr.io/greenautarky/`.

| Component | Image | Tag format | Built from |
|-----------|-------|------------|------------|
| **HA Core** | `ghcr.io/greenautarky/tinker-homeassistant` | `2025.11.3-ga.1` | `ha-core` + `frontend` |
| **Supervisor** | `ghcr.io/greenautarky/armv7-hassio-supervisor` | `2025.11.4-ga.1` | `ha-supervisor` |
| CLI | `ghcr.io/home-assistant/armv7-hassio-cli` | `2025.09.0` | Stock upstream |
| DNS | `ghcr.io/home-assistant/armv7-hassio-dns` | `2025.08.0` | Stock upstream |
| Audio | `ghcr.io/home-assistant/armv7-hassio-audio` | `2025.08.0` | Stock upstream |
| Observer | `ghcr.io/home-assistant/armv7-hassio-observer` | `2025.02.0` | Stock upstream |
| Multicast | `ghcr.io/home-assistant/armv7-hassio-multicast` | `2025.08.0` | Stock upstream |

### Version tag convention

- Release: `2025.11.3-ga.1` (base HA version + `-ga.` + GA revision)
- Dev/CI: `2025.11.3-ga.dev-abc1234` (auto-generated on push)
- The `latest` tag always points to the most recent build

### Docker image labels (critical)

The Supervisor reads `io.hass.version` from Docker image labels to determine
which version of HA Core is running. Without correct labels, updates and
container management break.

The `build-ga-core.yml` workflow sets:
```
io.hass.version=2025.11.3-ga.1
io.hass.type=homeassistant
io.hass.arch=armv7
io.hass.machine=tinker
```

## Build pipelines

### HA Core image (`build-ga-core.yml`)

Four-gate pipeline — `:latest` is only promoted after all gates pass:

```
Trigger: push to ga/custom-onboarding OR workflow_dispatch

  ┌─────────────────────────────┐
  │  test                        │  Unit + consistency tests (GA components)
  │  pytest greenautarky_*       │
  └────────────┬────────────────┘
               │
  ┌────────────▼────────────────┐
  │  build                       │  Checkout frontend, build JS, wheel
  │  Docker build (armv7)        │  Verify wheel contains GA pages
  │  Push :ci-{sha} (staging)    │  Upload wheel artifact
  └────────────┬────────────────┘
               │
  ┌────────────▼────────────────┐
  │  test-e2e                    │  Download wheel, pip-install HA on amd64
  │  Playwright GA onboarding    │  Seed Phase 1 via stock onboarding API
  │  (5-step full flow)          │  Run Playwright against live HA instance
  └────────────┬────────────────┘
               │
  ┌────────────▼────────────────┐
  │  promote                     │  Pull :ci-{sha}
  │  Tag + push final images     │  Promote to :latest :landingpage :tag :HA_VERSION
  └─────────────────────────────┘

Output: ghcr.io/greenautarky/tinker-homeassistant:{tag}
```

**Key design decisions:**
- `build` pushes a staging `:ci-{sha}` tag — never `:latest` directly
- `test-e2e` uses pip-installed HA on amd64 (no QEMU/ARM emulation — fast, reliable)
- `promote` only runs after both `build` AND `test-e2e` succeed
- Playwright artifacts (screenshots, video, traces) uploaded on test failure

### Supervisor image (`build-ga-supervisor.yml`)

```
Trigger: push to ga/custom-version-url OR workflow_dispatch
         ┌─────────────────────────────────────────┐
         │  1. Checkout ha-supervisor               │
         │  2. Docker build (armv7 cross-compile)   │
         │  3. Push to GHCR with version labels     │
         └─────────────────────────────────────────┘
Output: ghcr.io/greenautarky/armv7-hassio-supervisor:{tag}
```

### HA OS image (Buildroot)

Built via `ha-operating-system` Buildroot. During the OS build:
1. `hassio.mk` fetches `stable.json` from `greenautarky/haos-version`
2. Downloads all container images (core, supervisor, cli, dns, audio, etc.)
3. Bakes them into the OS data partition
4. Output: `.img` file flashable to iHost eMMC

## Version manifest (`stable.json`)

Located at `greenautarky/haos-version/stable.json`. This is the **single source
of truth** for which image versions the Supervisor pulls.

Key fields for iHost (tinker/armv7):

```json
{
  "supervisor": "2025.11.4-ga.1",
  "homeassistant": {
    "tinker": "2025.11.3-ga.1"
  },
  "images": {
    "core": "ghcr.io/greenautarky/{machine}-homeassistant",
    "supervisor": "ghcr.io/greenautarky/{arch}-hassio-supervisor"
  },
  "core": "2025.11.3-ga.1"
}
```

The Supervisor reads this file on every startup via `URL_HASSIO_VERSION` in
`supervisor/const.py`. Our fork points this to `greenautarky/haos-version`
instead of the upstream.

## Boot and update flow

```
┌──────────────────────────────────────────────────────────┐
│  iHost powers on                                         │
│  ├── HA OS boots (Buildroot Linux)                       │
│  ├── Docker starts                                       │
│  ├── Supervisor container starts                         │
│  │   ├── Reads URL_HASSIO_VERSION (greenautarky/haos-    │
│  │   │   version/stable.json)                            │
│  │   ├── Caches image refs in updater.json               │
│  │   ├── Compares running version vs stable.json         │
│  │   └── If update available: pulls new image, restarts  │
│  ├── HA Core container starts                            │
│  │   ├── Loads configuration.yaml                        │
│  │   ├── Loads greenautarky_telemetry integration        │
│  │   ├── Loads greenautarky_onboarding integration       │
│  │   │   ├── Checks .storage/greenautarky_onboarding     │
│  │   │   ├── If not completed: registers /greenautarky-  │
│  │   │   │   setup page + sidebar panel                  │
│  │   │   └── If completed: views still registered but    │
│  │   │       redirect to /                               │
│  │   └── Starts HTTP server on :8123                     │
│  └── Add-on containers start (zigbee2mqtt, mosquitto...) │
└──────────────────────────────────────────────────────────┘
```

## Custom integrations

### greenautarky_onboarding

Standalone Phase 2 onboarding wizard. Phase 1 (stock HA onboarding) runs
automatically during provisioning and creates the admin account. Phase 2 runs
when the end customer first opens the device, creates their own non-admin
account, accepts GDPR, and configures analytics. Zero modifications to upstream
onboarding code.

**Location:** `homeassistant/components/greenautarky_onboarding/`

**Files:**
- `__init__.py` — Setup: registers HTTP views + sidebar panel; `_async_register_panel()` re-registers after reset
- `http.py` — All HTTP API endpoints
- `const.py` — Constants, step definitions, consent types
- `consent.py` — Consent version tracking, triggers repair issues on outdated consents
- `repairs.py` — Repair flow for outdated consents
- `manifest.json` — Integration metadata
- `translations/en.json` — English translations (required by HA test framework)
- `strings.json` — Translation strings source (keep in sync with `translations/en.json`)

**Endpoints:**
| Method | Auth | Path | Purpose |
|--------|------|------|---------|
| GET | none | `/greenautarky-setup` | Redirect to `/greenautarky-setup.html` |
| GET | none | `/api/greenautarky_onboarding/status` | Current state: `{completed, gdpr_accepted, steps_done}` |
| POST | none | `/api/greenautarky_onboarding/gdpr` | Accept GDPR, persist consent |
| POST | none | `/api/greenautarky_onboarding/create_user` | Create non-admin user, return `auth_code` |
| POST | bearer | `/api/greenautarky_onboarding/telemetry` | Save GA telemetry prefs (best-effort) |
| POST | bearer | `/api/greenautarky_onboarding/complete` | Mark wizard done, redirect to `/` |
| POST | admin | `/api/greenautarky_onboarding/reset` | Reset state for QA re-testing (admin only) |

**Reset endpoint (QA use):**
The reset endpoint clears `completed`, `gdpr_accepted`, and `steps_done` while
preserving stored consents. It also re-registers the sidebar panel so the
wizard is accessible again without reflashing. Requires admin Bearer token:
```bash
# Get token
TOKEN=$(curl -s -X POST http://DEVICE:8123/auth/token \
  -d "grant_type=password&client_id=http://DEVICE:8123&username=admin&password=changeme" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Reset
curl -X POST http://DEVICE:8123/api/greenautarky_onboarding/reset \
  -H "Authorization: Bearer $TOKEN"
# → {"status": "ok"}
```

**Wizard steps (Phase 2 — end customer flow):**
1. **Welcome** — Branding/intro screen
2. **GDPR** — Privacy consent (persisted to backend)
3. **Create user** — Non-admin account creation (returns `auth_code` for auth flow)
4. **Info pages** — Product overview, first steps, app links
5. **Analytics** — GA telemetry preferences (HA system analytics removed — requires admin)

**Why HA system analytics was removed from the wizard:**
The HA `analytics/preferences` WebSocket command requires admin rights. The GA
wizard creates a `GROUP_ID_USER` (non-admin) account, so calling that endpoint
always returned "Unauthorized". The analytics step now only saves GA-specific
telemetry preferences via `greenautarky_telemetry/set` (best-effort — non-fatal
if it fails).

**Trigger mechanisms:**
- Included in `DEFAULT_CONFIG` (`homeassistant/config.py`) for new installs
- Provisioning sets up the admin account via Phase 1 (stock HA onboarding API)

### greenautarky_telemetry

Telemetry preferences integration (error reports, metrics).

**Location:** `homeassistant/components/greenautarky_telemetry/`

## Testing strategy

Three layers of automated testing cover the GA onboarding flow:

### Layer 1 — Backend unit tests (pytest)

```bash
# From homeassistant_core/
python -m pytest tests/components/greenautarky_onboarding/ -v
python -m pytest tests/components/greenautarky_telemetry/ -v
```

Key test files:
- `test_views.py` — All HTTP endpoints including reset, GDPR, create_user
- `test_consent.py` — Consent versioning and repair issues
- `test_build_consistency.py` — Frontend version pinned in all 3 locations
- `test_version_consistency.py` — Version format validation

### Layer 2 — CI Playwright e2e tests (in `build-ga-core.yml`)

Runs on every push. Installs HA from pip + built frontend wheel on amd64 (no
ARM emulation). Seeds Phase 1 via the stock HA onboarding API, then drives the
full 5-step wizard through a real Chromium browser.

Test file: `tests/e2e/ga_onboarding.spec.ts`
Config: `tests/e2e/playwright.config.ts`

Key regression test:
```
"analytics step completes without Unauthorized error"
```
This catches the bug where `setAnalyticsPreferences` (admin-only WS) was called
after creating a non-admin user, causing "Failed to save: Unauthorized".

### Layer 3 — Physical device test (ga-flasher stage 90)

Runs on real iHost hardware after full provisioning. Uses
`work/ha-onboarding/ga-onboarding.py` (Python Playwright):

```bash
# Manual run against a provisioned device
./work/ha-onboarding/ga-onboarding.py 192.168.101.100 \
  --admin-username admin --admin-password changeme --headless
```

Stage 90 (`stages.d/90-final-check.sh`):
1. Pre-checks: device reachable, GA API available, page serves HTTP 200
2. Calls `ga-onboarding.py` with credentials from `stage-env.sh`
3. Script resets onboarding state (via reset endpoint), runs wizard, verifies backend completion
4. Stage exits 1 (blocks further stages) if wizard fails

## Flasher integration

The `ga-flasher-py` tool (separate repo) handles device provisioning:

1. Flashes HA OS to iHost eMMC
2. Runs stock HA onboarding via API (creates admin user, sets locale) — Phase 1
3. Restarts HA Core
4. Stage 90: verifies GA Phase 2 onboarding works end-to-end on the real device

## Release checklist

To release a new version:

1. **Build HA Core image:**
   ```bash
   gh workflow run build-ga-core.yml -R greenautarky/ha-core \
     -f tag="2025.11.3-ga.2"
   ```

2. **Build Supervisor image** (only if supervisor code changed):
   ```bash
   gh workflow run build-ga-supervisor.yml -R greenautarky/ha-supervisor \
     --ref ga/custom-version-url -f version="2025.11.4-ga.1"
   ```

3. **Update `stable.json`** in `greenautarky/haos-version`:
   - Set `homeassistant.tinker` to new core tag
   - Set `core` to new core tag
   - Set `supervisor` to new supervisor tag (if changed)

4. **Existing devices** will auto-update on next Supervisor check
   (or manually: `ha core update` via SSH)

5. **New OS builds** will bake in the latest images from `stable.json`

## Device access

- **NetBird VPN IP:** `100.126.140.48`
- **SSH:** `ssh -i HomeassistantGreen0.pem -p 22222 root@100.126.140.48`
- **HA Web UI:** `http://100.126.140.48:8123`
- **SSH key:** `/home/user/Nextcloud2/GreenAutarky/security_store/HomeassistantGreen0.pem`

## Known issues

- **Recorder DB schema mismatch:** iHost DB has schema v52 but HA 2025.11.x
  expects v51. Workaround: delete `home-assistant_v2.db` for fresh start,
  or upgrade base HA version.
- **armv7 end-of-life:** HA dropped armv7 support after 2025.11.x. This is
  the last supportable version for iHost hardware.
- **Supervisor restart overwrites config:** The Supervisor re-fetches
  `stable.json` on every restart and overwrites local `updater.json` and
  `homeassistant.json`. This is by design — `stable.json` is the source
  of truth.
