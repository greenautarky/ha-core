"""Constants for greenautarky onboarding."""

DOMAIN = "greenautarky_onboarding"
STORAGE_KEY = "greenautarky_onboarding"
STORAGE_VERSION = 2

# Steps in the onboarding wizard
STEP_ACCOUNT = "account"
STEP_GDPR = "gdpr"
STEP_TELEMETRY = "telemetry"
STEP_INFO = "info"
STEP_COMPLETE = "complete"

# Consent types and their current required versions.
# Bump the version number to trigger re-consent for all users.
CONSENT_TYPES: dict[str, int] = {
    "gdpr": 1,
}

# Human-readable titles for consent types (German)
CONSENT_TITLES: dict[str, str] = {
    "gdpr": "Datenschutzerklärung",
}
