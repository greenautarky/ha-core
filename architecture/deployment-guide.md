# greenautarky KI-Butler — Deployment Guide

## Repositories

| Repo | Branch | Purpose |
|------|--------|---------|
| `greenautarky/ha-core` | `ga/custom-onboarding` | HA Core + `greenautarky_telemetry` component |
| `greenautarky/frontend` | `ga/custom-onboarding` | Custom onboarding UI (German, KI-Butler branding) |
| `greenautarky/ha-operating-system` | `ga/custom-core-image` | HAOS with custom version URL |
| `greenautarky/haos-version` | `main` | Version manifest (`stable.json`) pointing to custom image |

## Architecture Diagram

Open [build-pipeline.drawio](build-pipeline.drawio) in draw.io for the visual overview.

---

## Build Pipeline

### What happens on `git push`

```
Frontend repo                    Core repo
(ga/custom-onboarding)           (ga/custom-onboarding)
        │                                │
        │   ┌────────────────────────────┤
        │   │ build-ga-core.yml triggers │
        │   │ on push to branch          │
        ▼   ▼                            │
   ┌─────────────┐                       │
   │ GitHub Actions                      │
   │  1. checkout core + frontend        │
   │  2. yarn install + build_frontend   │
   │  3. python3 -m build → .whl         │
   │  4. QEMU + Buildx (armv7)          │
   │  5. docker build + push             │
   └──────────┬──────────────────────────┘
              │
              ▼
   ghcr.io/greenautarky/tinker-homeassistant:{tag}
```

### Trigger types

| Trigger | Tag format | When |
|---------|-----------|------|
| Push to `ga/custom-onboarding` | `dev-<sha7>` + `latest` | Every commit to core branch |
| `workflow_dispatch` | User-specified (e.g. `2025.11.0-ga.2`) + `latest` | Manual release |

> **Note**: Frontend changes alone don't trigger the build. You must either push to ha-core or trigger manually.

---

## How to Update Each Artifact

### 1. Frontend changes (UI, branding, onboarding steps)

**Files**: `greenautarky/frontend` → `src/onboarding/`

```bash
cd ~/git/homeassistant_frontend
# Make changes...
git add -A && git commit -m "feat: description"
git push origin ga/custom-onboarding
```

Then trigger the core build (frontend push alone won't trigger CI):

```bash
gh workflow run build-ga-core.yml \
  --ref ga/custom-onboarding \
  -f tag=2025.11.0-ga.X \
  -R greenautarky/ha-core
```

### 2. Core changes (Python components, config, manifest)

**Files**: `greenautarky/ha-core` → `homeassistant/components/`

```bash
cd ~/git/homeassisant_core
# Make changes...
git add -A && git commit -m "feat: description"
git push origin ga/custom-onboarding
# CI triggers automatically on push
```

### 3. Version manifest (update which image tag HAOS pulls)

**File**: `greenautarky/haos-version` → `stable.json`

```bash
# Update the version tag in stable.json:
#   "homeassistant.tinker": "2025.11.0-ga.X"
#   "core": "2025.11.0-ga.X"
git push origin main
```

### 4. HAOS build config (version URL, system-level changes)

**File**: `greenautarky/ha-operating-system` → `buildroot-external/package/hassio/hassio.mk`

Only needed if changing the version URL endpoint or system packages. Requires a full HAOS rebuild + flash.

---

## Deployment Methods

### Method A: Manual testing (retag on stock HAOS)

For testing on an iHost still running stock HAOS:

```bash
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
     -o LogLevel=ERROR -p 22222 \
     -i ~/Nextcloud2/GreenAutarky/security_store/HomeassistantGreen0.pem \
     root@<DEVICE_IP>"

# 1. Pull the new image
$SSH "docker pull ghcr.io/greenautarky/tinker-homeassistant:latest"

# 2. Retag to match what the Supervisor expects
$SSH "docker tag \
  ghcr.io/greenautarky/tinker-homeassistant:latest \
  ghcr.io/home-assistant/tinker-homeassistant:2025.11.3"

# 3. Force container recreation from the new image
$SSH "ha core rebuild"

# 4. (Optional) Reset onboarding to test from scratch
#    ⚠ This deletes ALL user accounts and auth data!
#    You will need to re-create the admin user (email + password)
#    during the onboarding user-creation step.
$SSH "docker exec homeassistant sh -c '\
  rm -f /config/.storage/onboarding \
        /config/.storage/auth \
        /config/.storage/auth_provider.homeassistant \
        /config/.storage/person'"
$SSH "ha core restart"
```

> **Important**: After a full reset, all user accounts are gone. The onboarding
> will prompt you to create a new admin account (step 3). There is no way to
> preserve existing login credentials across an onboarding reset — the admin
> user and password must be re-created each time.

### Method B: Production (HAOS auto-pulls)

On a device flashed with greenautarky HAOS:

1. CI builds and pushes image with tag `2025.11.0-ga.X`
2. Update `greenautarky/haos-version/stable.json` with the new tag
3. Supervisor automatically pulls the new image on next update check
4. User clicks "Update" in HA UI, or it auto-updates

No retagging needed — the Supervisor natively resolves `ghcr.io/greenautarky/tinker-homeassistant`.

---

## Full Release Checklist

```
[ ] 1. Make & test frontend changes locally
[ ] 2. Commit + push frontend to greenautarky/frontend (ga/custom-onboarding)
[ ] 3. Make & test core changes locally
[ ] 4. Commit + push core to greenautarky/ha-core (ga/custom-onboarding)
      → or trigger workflow_dispatch with release tag
[ ] 5. Wait for CI build (~24 min)
      → gh run list --workflow=build-ga-core.yml -R greenautarky/ha-core
[ ] 6. Deploy to test device (Method A)
[ ] 7. Verify all onboarding steps + telemetry
[ ] 8. Take screenshots for documentation
[ ] 9. Update greenautarky/haos-version/stable.json with release tag
[ ] 10. Tag the release in both repos
```

---

## Key File Locations

### In the Docker image

| Path | Content |
|------|---------|
| `/usr/local/lib/python3.13/site-packages/hass_frontend/` | Built frontend (JS bundles) |
| `/usr/src/homeassistant/homeassistant/components/` | HA Core components |
| `/usr/src/homeassistant/homeassistant/components/greenautarky_telemetry/` | Telemetry component |
| `/usr/src/homeassistant/homeassistant/components/onboarding/` | Onboarding backend |
| `/config/` | User config (mounted volume, persists across rebuilds) |
| `/config/.storage/` | HA internal storage (auth, onboarding state, telemetry prefs) |

### On the iHost (HAOS)

| Path | Content |
|------|---------|
| `/mnt/data/supervisor/` | Supervisor data |
| `/mnt/data/homeassistant/` | HA config (→ mounted as `/config/` in container) |
| `/mnt/data/docker/` | Docker data root |

---

## Troubleshooting

### Container still shows old code after rebuild

The Supervisor caches container layers. Use `ha core rebuild` (not `ha core restart`). If that doesn't work:

```bash
# Nuclear option: remove and re-pull
docker rmi ghcr.io/home-assistant/tinker-homeassistant:2025.11.3
docker tag ghcr.io/greenautarky/tinker-homeassistant:latest \
           ghcr.io/home-assistant/tinker-homeassistant:2025.11.3
ha core rebuild
```

### "Unknown command" on telemetry save

The `greenautarky_telemetry` component isn't loaded. Check:
1. `configuration.yaml` has `greenautarky_telemetry:` entry
2. Manifest has `integration_type: "service"` (not `"system"`)
3. `config.py` DEFAULT_CONFIG includes `greenautarky_telemetry:`

### Supervisor auto-updates to stock image

The Supervisor checks its version URL periodically. If running stock HAOS, it will overwrite the retagged image. Solutions:
- Use greenautarky HAOS build (points to our version URL)
- Or disable auto-updates: Settings → System → Updates → toggle off
