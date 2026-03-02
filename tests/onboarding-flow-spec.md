# Onboarding Flow - Test Specification

## Overview

Custom onboarding flow for the greenautarky iHost (Sonoff iHost, RV1126 armv7).
Based on Home Assistant Core 2025.11.0 / Frontend 20251105.0.

## Onboarding Steps

| # | Step            | Auth Required | API Endpoint                      | Description                              |
|---|-----------------|---------------|-----------------------------------|------------------------------------------|
| 1 | Welcome (init)  | No            | —                                 | Branding page, "Mein iHost einrichten"   |
| 2 | GDPR            | No            | POST /api/onboarding/gdpr         | Datenschutz akzeptieren (Checkbox)       |
| 3 | User            | No            | POST /api/onboarding/users        | E-Mail + Passwort, Konto erstellen       |
| 4 | Custom Pages    | Yes           | POST /api/onboarding/custom_pages | Info + Hilfe Seiten (Wizard)             |
| 5 | Analytics       | Yes           | POST /api/onboarding/analytics    | Standard HA Analytics On/Off             |

## Test Cases

### TC-01: Welcome Page

**Precondition:** Fresh install, no onboarding completed (`config/.storage/onboarding` deleted).

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | Navigate to `http://<host>:8123`        | Redirect to `/onboarding.html`                       |
| 2    | Page loads                              | GA logo (green circle + "GA") is visible             |
| 3    | —                                       | Heading: "Willkommen auf deinem iHost"               |
| 4    | —                                       | Subtext: "Lass uns dein Smart Home einrichten..."    |
| 5    | —                                       | Button: "Mein iHost einrichten" is visible           |
| 6    | —                                       | Language picker shows "Deutsch" (default)            |
| 7    | —                                       | Progress bar at 0%                                   |
| 8    | Click "Mein iHost einrichten"           | Proceeds to GDPR step                               |

### TC-02: GDPR/Datenschutz Page

**Precondition:** Welcome step completed.

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | Page loads                              | Heading: "Datenschutz"                               |
| 2    | —                                       | Privacy text visible in scrollable box               |
| 3    | —                                       | Sections: "Datenverarbeitung", "Deine Rechte"        |
| 4    | —                                       | Checkbox: "Ich akzeptiere die Datenschutzerklaerung" |
| 5    | —                                       | "Weiter" button is **disabled**                      |
| 6    | Check the checkbox                      | "Weiter" button becomes **enabled**                  |
| 7    | Uncheck the checkbox                    | "Weiter" button becomes **disabled** again           |
| 8    | Check checkbox, click "Weiter"          | POST /api/onboarding/gdpr `{"accepted": true}` → 200|
| 9    | —                                       | Proceeds to User creation step                       |

**API Edge Cases:**
| Test | Request                                 | Expected Response                                    |
|------|-----------------------------------------|------------------------------------------------------|
| A    | POST /api/onboarding/gdpr `{"accepted": false}` | 400 Bad Request                               |
| B    | POST /api/onboarding/gdpr `{"accepted": true}`  | 200 OK, step marked done                      |
| C    | POST /api/onboarding/gdpr (repeat)              | 403 Forbidden (step already done)              |

### TC-03: User Creation Page

**Precondition:** GDPR step completed.

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | Page loads                              | Heading: "Benutzerkonto erstellen"                   |
| 2    | —                                       | Subtext: "Erstelle ein Benutzerkonto..."             |
| 3    | —                                       | Fields: E-Mail-Adresse, Passwort, Passwort bestätigen|
| 4    | —                                       | No "Name" or "Username" fields visible               |
| 5    | —                                       | "Konto erstellen" button is **disabled**             |
| 6    | Fill email only                         | Button remains disabled                              |
| 7    | Fill email + password                   | Button remains disabled                              |
| 8    | Fill all three fields, passwords match  | Button becomes **enabled**                           |
| 9    | Enter mismatched passwords              | Error: "Passwörter stimmen nicht überein"            |
| 10   | Fix passwords, click "Konto erstellen"  | POST /api/onboarding/users → 200                    |
| 11   | —                                       | Username = email address                             |
| 12   | —                                       | Display name = part before @ (e.g. "test")           |
| 13   | —                                       | Auth token returned, connection established          |
| 14   | —                                       | Proceeds to Custom Pages step                        |

### TC-04: Custom Pages (Info + Help)

**Precondition:** User created, auth established.

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | Page loads                              | Heading: "Ueber dein Geraet"                         |
| 2    | —                                       | Page indicator: "1 / 2"                              |
| 3    | —                                       | Content about iHost (Zigbee, local, etc.)            |
| 4    | —                                       | Only "Naechste" button visible (no "Zurueck")        |
| 5    | Click "Naechste"                        | Page 2 loads                                         |
| 6    | —                                       | Heading: "Erste Schritte"                            |
| 7    | —                                       | Page indicator: "2 / 2"                              |
| 8    | —                                       | Help content with links to HA docs                   |
| 9    | —                                       | Both "Zurueck" and "Weiter" buttons visible          |
| 10   | Click "Zurueck"                         | Returns to page 1                                    |
| 11   | Click "Naechste" then "Weiter"          | POST /api/onboarding/custom_pages → 200              |
| 12   | —                                       | Proceeds to Analytics step                           |

### TC-05: Analytics Page

**Precondition:** Custom pages completed.

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | Page loads                              | Standard HA analytics page                           |
| 2    | —                                       | Toggles: Basic analytics, Usage, Statistics, Diagnostics |
| 3    | —                                       | All toggles off by default                           |
| 4    | Click "Next"/"Weiter"                   | POST /api/onboarding/analytics → 200                 |
| 5    | —                                       | Auth revoked, redirect to login page                 |
| 6    | —                                       | Login page shows "Welcome home!" / username+password |

### TC-06: Full Flow Regression

**Precondition:** Fresh install.

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | GET /api/onboarding                     | 4 steps, all `done: false`                           |
| 2    | Complete Welcome → GDPR → User → Pages → Analytics | Each step marked done sequentially      |
| 3    | GET /api/onboarding after completion    | All 4 steps `done: true`                             |
| 4    | Navigate to /onboarding.html            | Redirects to / (onboarding complete)                 |
| 5    | Login with email + password             | Dashboard loads successfully                         |

### TC-07: Language Selection

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | Default language on fresh install       | "Deutsch" selected                                   |
| 2    | Change to English via picker            | UI text switches to English (where available)        |
| 3    | Change back to Deutsch                  | UI text switches back to German                      |
| 4    | Refresh page                            | Language selection persists (localStorage)            |

### TC-08: Onboarding Reset

| Step | Action                                  | Expected Result                                      |
|------|-----------------------------------------|------------------------------------------------------|
| 1    | Delete `config/.storage/onboarding`     | —                                                    |
| 2    | Restart HA Core                         | —                                                    |
| 3    | Navigate to host                        | Onboarding starts fresh from Welcome page            |

## Files Under Test

### Backend (HA Core)
| File | Purpose |
|------|---------|
| `homeassistant/components/onboarding/const.py` | Step definitions and order |
| `homeassistant/components/onboarding/views.py` | API endpoint handlers |
| `homeassistant/components/onboarding/__init__.py` | Initialization, storage migration |

### Frontend
| File | Purpose |
|------|---------|
| `src/onboarding/ha-onboarding.ts` | Main orchestrator, step routing |
| `src/onboarding/onboarding-welcome.ts` | Welcome page with GA branding |
| `src/onboarding/onboarding-gdpr.ts` | GDPR acceptance page |
| `src/onboarding/onboarding-create-user.ts` | Email + password user creation |
| `src/onboarding/onboarding-custom-pages.ts` | Custom pages wizard framework |
| `src/onboarding/custom-pages/page-info.ts` | Device info page |
| `src/onboarding/custom-pages/page-help.ts` | Getting started help page |
| `src/onboarding/ga-branding.ts` | Logo, colors, shared styles |
| `src/data/onboarding.ts` | API types and fetch functions |
