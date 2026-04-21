"""Test the greenautarky onboarding HTTP views."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.greenautarky_onboarding.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import mock_storage

from tests.common import register_auth_provider
from tests.typing import ClientSessionGenerator


@pytest.fixture(autouse=True)
async def auth_active(hass: HomeAssistant) -> None:
    """Ensure auth is always active."""
    await register_auth_provider(hass, {"type": "homeassistant"})


@pytest.fixture
def default_state() -> dict[str, Any]:
    """Return a fresh default state."""
    return {
        "completed": False,
        "gdpr_accepted": False,
        "steps_done": [],
        "consents": {},
    }


async def _setup_component(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> None:
    """Set up the greenautarky_onboarding component with optional state."""
    if state is not None:
        mock_storage(hass_storage, state)

    # Set up the auth component so create_auth_code works in create_user tests.
    assert await async_setup_component(hass, "auth", {})

    # Mark frontend/panel_custom as already set up so HA does not try to import
    # hass_frontend (the built wheel, not available in the test environment).
    hass.config.components.add("frontend")
    hass.config.components.add("panel_custom")

    # Mock panel registration to avoid needing the panel dist directory
    with patch(
        "homeassistant.components.greenautarky_onboarding._async_register_panel"
    ):
        assert await async_setup_component(
            hass, DOMAIN, {DOMAIN: {}}
        )
    await hass.async_block_till_done()


class TestStatusView:
    """Tests for GET /api/greenautarky_onboarding/status."""

    async def test_status_returns_state(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test status returns the current onboarding state."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get("/api/greenautarky_onboarding/status")
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert data["completed"] is False
        assert data["gdpr_accepted"] is False
        assert data["steps_done"] == []

    async def test_status_after_gdpr(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test status reflects GDPR acceptance."""
        state = {
            "completed": False,
            "gdpr_accepted": True,
            "steps_done": ["gdpr"],
            "consents": {},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.get("/api/greenautarky_onboarding/status")
        data = await resp.json()
        assert data["gdpr_accepted"] is True
        assert "gdpr" in data["steps_done"]


class TestGDPRView:
    """Tests for POST /api/greenautarky_onboarding/gdpr."""

    async def test_accept_gdpr(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test accepting GDPR consent."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/gdpr",
            json={"accepted": True},
        )
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert data["status"] == "ok"

        # Verify state was updated
        state = hass.data[DOMAIN]["state"]
        assert state["gdpr_accepted"] is True
        assert "gdpr" in state["steps_done"]

    async def test_gdpr_rejected_when_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test GDPR endpoint returns 403 when onboarding completed."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "account", "complete"],
            "consents": {"gdpr": {"version": 1, "accepted_at": "2026-01-01"}},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/gdpr",
            json={"accepted": True},
        )
        assert resp.status == HTTPStatus.FORBIDDEN


class TestCreateUserView:
    """Tests for POST /api/greenautarky_onboarding/create_user."""

    async def test_create_user_returns_auth_code(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation returns an auth_code."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "Test User",
                "username": "testuser",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert "auth_code" in data
        assert isinstance(data["auth_code"], str)
        assert len(data["auth_code"]) > 0

        # Verify account step was marked done
        state = hass.data[DOMAIN]["state"]
        assert "account" in state["steps_done"]

    async def test_create_user_missing_fields(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation fails without required fields."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "name": "Test User",
                # missing client_id, username, password
            },
        )
        assert resp.status == HTTPStatus.BAD_REQUEST

    async def test_create_user_rejected_when_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test user creation fails when onboarding is completed."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "account", "complete"],
            "consents": {"gdpr": {"version": 1, "accepted_at": "2026-01-01"}},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "Test User",
                "username": "testuser",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.FORBIDDEN

    async def test_created_user_is_not_admin(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test that created user has normal (non-admin) privileges."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "Normal User",
                "username": "normaluser",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.OK

        # Find the created user
        users = await hass.auth.async_get_users()
        created = [u for u in users if u.name == "Normal User"]
        assert len(created) == 1
        assert not created[0].is_admin


    async def test_create_user_with_email_as_username(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation with an email address as username (email mode)."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "thomas",
                "username": "thomas@greenautarky.com",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert "auth_code" in data

        # Verify the user was created with the email as username
        users = await hass.auth.async_get_users()
        created = [u for u in users if u.name == "thomas"]
        assert len(created) == 1
        assert not created[0].is_admin

    async def test_create_user_with_plain_username(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation with a plain username (no email, username mode)."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "kibutler-user",
                "username": "kibutler-user",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert "auth_code" in data

        # Verify user was created with name matching username
        users = await hass.auth.async_get_users()
        created = [u for u in users if u.name == "kibutler-user"]
        assert len(created) == 1
        assert not created[0].is_admin

    async def test_create_user_empty_password(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation fails with empty password."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "Test User",
                "username": "testuser",
                "password": "",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.BAD_REQUEST

    async def test_create_user_empty_username(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation fails with empty username."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "Test User",
                "username": "",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.BAD_REQUEST

    async def test_create_user_empty_name(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation fails with empty name."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "",
                "username": "testuser",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.BAD_REQUEST

    async def test_create_user_empty_client_id(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation fails with empty client_id."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "",
                "name": "Test User",
                "username": "testuser",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.BAD_REQUEST

    async def test_create_user_whitespace_only_fields(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation fails when fields are whitespace-only (stripped)."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "   ",
                "username": "   ",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp.status == HTTPStatus.BAD_REQUEST

    async def test_create_user_default_language(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test user creation succeeds without explicit language (defaults to de)."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "Lang User",
                "username": "languser",
                "password": "SecurePass1!",
            },
        )
        assert resp.status == HTTPStatus.OK
        data = await resp.json()
        assert "auth_code" in data

    async def test_create_user_auth_code_is_unique(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test that each user creation returns a unique auth_code."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp1 = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "User One",
                "username": "userone",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        data1 = await resp1.json()

        # Reset to allow second creation
        hass.data[DOMAIN]["state"]["steps_done"] = []

        resp2 = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "User Two",
                "username": "usertwo",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        data2 = await resp2.json()

        assert data1["auth_code"] != data2["auth_code"]

    async def test_create_two_users_different_modes(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test creating users with both email and plain username yields distinct users."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        # First user: email mode
        resp1 = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "emailuser",
                "username": "emailuser@example.com",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp1.status == HTTPStatus.OK

        # Reset steps_done so we can create another user
        hass.data[DOMAIN]["state"]["steps_done"] = []

        # Second user: username mode
        resp2 = await client.post(
            "/api/greenautarky_onboarding/create_user",
            json={
                "client_id": "http://localhost:8123/",
                "name": "plainuser",
                "username": "plainuser",
                "password": "SecurePass1!",
                "language": "de",
            },
        )
        assert resp2.status == HTTPStatus.OK

        # Both users exist
        users = await hass.auth.async_get_users()
        names = {u.name for u in users}
        assert "emailuser" in names
        assert "plainuser" in names


class TestCompleteView:
    """Tests for POST /api/greenautarky_onboarding/complete."""

    async def test_complete_onboarding(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test completing the onboarding."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post("/api/greenautarky_onboarding/complete")
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert data["status"] == "ok"
        assert data["redirect"] == "/"

        # Verify state
        state = hass.data[DOMAIN]["state"]
        assert state["completed"] is True
        assert "complete" in state["steps_done"]

    async def test_complete_rejected_when_already_done(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test completing fails when already completed."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["complete"],
            "consents": {"gdpr": {"version": 1, "accepted_at": "2026-01-01"}},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post("/api/greenautarky_onboarding/complete")
        assert resp.status == HTTPStatus.FORBIDDEN


class TestTelemetryView:
    """Tests for POST /api/greenautarky_onboarding/telemetry."""

    async def test_save_telemetry_preferences(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test saving telemetry preferences records the step."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/telemetry",
            json={"error_logs": True, "metrics": False},
        )
        assert resp.status == HTTPStatus.OK

        state = hass.data[DOMAIN]["state"]
        assert "telemetry" in state["steps_done"]

    async def test_telemetry_forwarded_to_integration(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test telemetry prefs are forwarded to greenautarky_telemetry data store."""
        await _setup_component(hass, hass_storage, default_state)

        # Simulate greenautarky_telemetry being loaded
        tel_store = MagicMock()
        tel_store.async_save = AsyncMock()
        tel_prefs = {"error_logs": False, "metrics": False}
        hass.data["greenautarky_telemetry"] = {
            "preferences": tel_prefs,
            "store": tel_store,
        }

        client = await hass_client()
        resp = await client.post(
            "/api/greenautarky_onboarding/telemetry",
            json={"error_logs": True, "metrics": True},
        )
        assert resp.status == HTTPStatus.OK

        assert tel_prefs["error_logs"] is True
        assert tel_prefs["metrics"] is True
        tel_store.async_save.assert_called_once_with(tel_prefs)

    async def test_telemetry_without_integration(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test telemetry works when greenautarky_telemetry is not loaded."""
        await _setup_component(hass, hass_storage, default_state)
        # Do NOT set hass.data["greenautarky_telemetry"]
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/telemetry",
            json={"error_logs": True, "metrics": False},
        )
        assert resp.status == HTTPStatus.OK

        state = hass.data[DOMAIN]["state"]
        assert "telemetry" in state["steps_done"]

    async def test_telemetry_rejected_when_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test telemetry endpoint returns 403 when onboarding completed."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "account", "complete"],
            "consents": {"gdpr": {"version": 1, "accepted_at": "2026-01-01"}},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/telemetry",
            json={"error_logs": True, "metrics": True},
        )
        assert resp.status == HTTPStatus.FORBIDDEN


class TestConsentViews:
    """Tests for consent HTTP endpoints (authenticated, post-onboarding)."""

    async def test_consent_page_serves_html(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test GET /greenautarky-consent serves HTML page."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get("/greenautarky-consent")
        assert resp.status == HTTPStatus.OK
        assert "text/html" in resp.content_type

    async def test_consent_status_returns_outdated(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test consent status lists outdated consents."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "complete"],
            "consents": {},  # No consent versions → all outdated
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.get("/api/greenautarky_onboarding/consent/status")
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert "gdpr" in data["outdated"]

    async def test_consent_status_current(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test consent status returns empty outdated when all current."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "complete"],
            "consents": {
                "gdpr": {"version": 1, "accepted_at": "2026-01-01"},
                "ethernet": {"version": 1, "accepted_at": "2026-01-01"},
            },
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.get("/api/greenautarky_onboarding/consent/status")
        assert resp.status == HTTPStatus.OK

        data = await resp.json()
        assert data["outdated"] == []

    async def test_consent_accept_records(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test accepting a consent type records it in state."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "complete"],
            "consents": {},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/consent/accept",
            json={"type": "gdpr"},
        )
        assert resp.status == HTTPStatus.OK

        onboarding_state = hass.data[DOMAIN]["state"]
        assert "gdpr" in onboarding_state["consents"]
        assert onboarding_state["consents"]["gdpr"]["version"] == 1

    async def test_consent_accept_unknown_type(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test accepting unknown consent type returns 400."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "complete"],
            "consents": {},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/consent/accept",
            json={"type": "bogus"},
        )
        assert resp.status == HTTPStatus.BAD_REQUEST

    async def test_consent_accept_missing_type(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test accepting consent with missing type field returns 400."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "complete"],
            "consents": {},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/consent/accept",
            json={},
        )
        assert resp.status == HTTPStatus.BAD_REQUEST


class TestStorageMigration:
    """Tests for v1→v2 storage migration."""

    async def test_v1_to_v2_with_gdpr_accepted(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
    ) -> None:
        """v1 state with gdpr_accepted=True → adds consents.gdpr."""
        from homeassistant.components.greenautarky_onboarding import (
            _migrate_v1_to_v2,
        )

        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "complete"],
        }
        result = _migrate_v1_to_v2(state)
        assert "consents" in result
        assert "gdpr" in result["consents"]
        assert result["consents"]["gdpr"]["version"] == 1
        assert result["consents"]["gdpr"]["accepted_at"] == "migrated-from-v1"

    async def test_v1_to_v2_without_gdpr(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
    ) -> None:
        """v1 state with gdpr_accepted=False → adds empty consents."""
        from homeassistant.components.greenautarky_onboarding import (
            _migrate_v1_to_v2,
        )

        state = {
            "completed": False,
            "gdpr_accepted": False,
            "steps_done": [],
        }
        result = _migrate_v1_to_v2(state)
        assert "consents" in result
        assert result["consents"] == {}

    async def test_setup_with_v1_storage_triggers_migration(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
    ) -> None:
        """Component setup with v1 storage (no consents key) → migrates."""
        from homeassistant.components.greenautarky_onboarding.const import (
            STORAGE_KEY,
        )

        # v1 storage: no consents key
        hass_storage[STORAGE_KEY] = {
            "version": 2,
            "data": {
                "completed": True,
                "gdpr_accepted": True,
                "steps_done": ["gdpr", "complete"],
                # no "consents" key
            },
        }

        hass.config.components.add("frontend")
        hass.config.components.add("panel_custom")
        with patch(
            "homeassistant.components.greenautarky_onboarding._async_register_panel"
        ):
            assert await async_setup_component(
                hass, DOMAIN, {DOMAIN: {}}
            )
        await hass.async_block_till_done()

        state = hass.data[DOMAIN]["state"]
        assert "consents" in state
        assert "gdpr" in state["consents"]


class TestPageView:
    """Tests for GET /greenautarky-setup."""

    async def test_page_redirects_to_built_html_when_not_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test /greenautarky-setup redirects to the built Lit panel HTML."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get("/greenautarky-setup", allow_redirects=False)
        assert resp.status == HTTPStatus.FOUND
        assert resp.headers["Location"] == "/greenautarky-setup.html"

    async def test_page_redirects_when_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test setup page redirects to / when completed."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["complete"],
            "consents": {"gdpr": {"version": 1, "accepted_at": "2026-01-01"}},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.get("/greenautarky-setup", allow_redirects=False)
        assert resp.status == HTTPStatus.FOUND
        assert resp.headers["Location"] == "/"


class TestResetView:
    """Tests for POST /api/greenautarky_onboarding/reset.

    The reset endpoint is used by the ga-flasher (stage 90) to re-run the
    GA onboarding wizard on a provisioned device without reflashing.
    It requires admin authentication.
    """

    async def test_reset_clears_onboarding_state(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test reset clears completed state and steps, preserves consents."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "account", "telemetry", "complete"],
            "consents": {"gdpr": {"version": 1, "accepted_at": "2026-01-01"}},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        resp = await client.post("/api/greenautarky_onboarding/reset")
        assert resp.status == HTTPStatus.OK
        data = await resp.json()
        assert data["status"] == "ok"

        # State is reset
        current = hass.data[DOMAIN]["state"]
        assert current["completed"] is False
        assert current["gdpr_accepted"] is False
        assert current["steps_done"] == []
        # Consents are preserved
        assert "gdpr" in current["consents"]

    async def test_reset_allows_onboarding_to_run_again(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Test that after reset, onboarding endpoints accept requests again."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["complete"],
            "consents": {},
        }
        await _setup_component(hass, hass_storage, state)
        client = await hass_client()

        # GDPR endpoint is blocked while completed
        resp = await client.post(
            "/api/greenautarky_onboarding/gdpr", json={"accepted": True}
        )
        assert resp.status == HTTPStatus.FORBIDDEN

        # Reset
        resp = await client.post("/api/greenautarky_onboarding/reset")
        assert resp.status == HTTPStatus.OK

        # GDPR endpoint works again
        resp = await client.post(
            "/api/greenautarky_onboarding/gdpr", json={"accepted": True}
        )
        assert resp.status == HTTPStatus.OK

    async def test_reset_requires_auth(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client_no_auth: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test reset returns 401 without authentication."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client_no_auth()

        resp = await client.post("/api/greenautarky_onboarding/reset")
        assert resp.status == HTTPStatus.UNAUTHORIZED

    async def test_reset_requires_admin(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        hass_access_token: str,
        default_state: dict[str, Any],
    ) -> None:
        """Test reset returns 403 for non-admin users."""
        from homeassistant.auth.const import GROUP_ID_USER

        await _setup_component(hass, hass_storage, default_state)

        # Create a non-admin user and get their token
        user_group = await hass.auth.async_get_group(GROUP_ID_USER)
        from tests.common import MockUser

        regular_user = MockUser(groups=[user_group]).add_to_hass(hass)
        refresh_token = await hass.auth.async_create_refresh_token(
            regular_user, "http://localhost/"
        )
        user_token = hass.auth.async_create_access_token(refresh_token)

        client = await hass_client(user_token)
        resp = await client.post("/api/greenautarky_onboarding/reset")
        assert resp.status == HTTPStatus.FORBIDDEN


class TestPinVerifyView:
    """Tests for POST /api/greenautarky_onboarding/verify_pin.

    The PIN endpoint verifies a 6-digit code printed on the device sticker
    to prove physical access. Exponential backoff prevents brute-force.
    """

    async def test_pin_not_required_when_no_file(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test status shows pin_required=false when no PIN file exists."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get("/api/greenautarky_onboarding/status")
        assert resp.status == HTTPStatus.OK
        data = await resp.json()
        assert data["pin_required"] is False
        assert data["pin_verified"] is False

    async def test_pin_required_when_file_exists(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test status shows pin_required=true when PIN file exists."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.get("/api/greenautarky_onboarding/status")
            data = await resp.json()
            assert data["pin_required"] is True
            assert data["pin_verified"] is False

    async def test_verify_pin_correct(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test correct PIN returns ok and sets pin_verified."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "847293"},
            )
            assert resp.status == HTTPStatus.OK
            data = await resp.json()
            assert data["status"] == "ok"

            # Verify status reflects verification
            resp = await client.get("/api/greenautarky_onboarding/status")
            data = await resp.json()
            assert data["pin_verified"] is True
            assert "pin" in data["steps_done"]

    async def test_verify_pin_wrong(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test wrong PIN returns error."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "000000"},
            )
            assert resp.status == HTTPStatus.UNAUTHORIZED
            data = await resp.json()
            assert data["status"] == "error"
            assert data["attempts"] == 1

    async def test_verify_pin_dash_format(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test PIN with dash format (847-293) is accepted."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "847-293"},
            )
            assert resp.status == HTTPStatus.OK
            data = await resp.json()
            assert data["status"] == "ok"

    async def test_verify_pin_exponential_backoff(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test exponential backoff on repeated failures."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            # First attempt — no delay
            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "111111"},
            )
            data = await resp.json()
            assert data["retry_after"] == 0
            assert data["attempts"] == 1

            # Second attempt — 5s delay
            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "222222"},
            )
            data = await resp.json()
            assert data["retry_after"] == 5
            assert data["attempts"] == 2

            # Third attempt — should be locked (429)
            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "333333"},
            )
            assert resp.status == HTTPStatus.TOO_MANY_REQUESTS
            data = await resp.json()
            assert data["status"] == "locked"
            assert data["retry_after"] > 0

    async def test_verify_pin_idempotent_after_success(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test verify_pin returns ok if already verified."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            # First verify
            await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "847293"},
            )

            # Second call — still ok
            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "847293"},
            )
            assert resp.status == HTTPStatus.OK
            data = await resp.json()
            assert data["status"] == "ok"

    async def test_verify_pin_rejected_when_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        tmp_path,
    ) -> None:
        """Test verify_pin returns 403 when onboarding is already completed."""
        state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["pin", "gdpr", "account"],
            "consents": {},
        }

        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "847293"},
            )
            assert resp.status == HTTPStatus.FORBIDDEN

    async def test_gdpr_blocked_before_pin_verified(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test GDPR endpoint returns 403 when PIN not yet verified."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/gdpr",
                json={"accepted": True},
            )
            assert resp.status == HTTPStatus.FORBIDDEN
            data = await resp.json()
            assert "PIN" in data["error"]

    async def test_gdpr_allowed_after_pin_verified(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test GDPR endpoint works after PIN is verified."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            # Verify PIN first
            await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "847293"},
            )

            # GDPR should now work
            resp = await client.post(
                "/api/greenautarky_onboarding/gdpr",
                json={"accepted": True},
            )
            assert resp.status == HTTPStatus.OK

    async def test_no_pin_file_gdpr_not_blocked(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test GDPR works normally when no PIN file exists (backward compat)."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/gdpr",
            json={"accepted": True},
        )
        assert resp.status == HTTPStatus.OK


# ---------------------------------------------------------------------------
# Password reset (PIN-based, unauthenticated)
# ---------------------------------------------------------------------------


class TestPasswordResetViews:
    """Tests for PIN-based password reset endpoints."""

    async def test_reset_page_loads(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test password reset page returns HTML."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get("/greenautarky-password-reset")
        assert resp.status == HTTPStatus.OK
        text = await resp.text()
        assert "Passwort" in text

    async def test_users_requires_pin(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test user list requires correct PIN."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset/users",
                json={"pin": "000000"},
            )
            assert resp.status == HTTPStatus.UNAUTHORIZED
            data = await resp.json()
            assert data["status"] == "error"

    async def test_users_returns_tenant_only(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test user list returns only GROUP_ID_USER, not admin."""
        from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER

        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)

            provider = None
            for prv in hass.auth.auth_providers:
                if prv.type == "homeassistant":
                    provider = prv
                    break
            await provider.async_initialize()
            await provider.async_add_auth("admin_user", "admin_pass")
            admin = await hass.auth.async_create_user(
                "Admin", group_ids=[GROUP_ID_ADMIN]
            )
            cred_admin = await provider.async_get_or_create_credentials(
                {"username": "admin_user"}
            )
            await hass.auth.async_link_user(admin, cred_admin)

            await provider.async_add_auth("tenant_user", "tenant_pass")
            tenant = await hass.auth.async_create_user(
                "Tenant Max", group_ids=[GROUP_ID_USER]
            )
            cred_tenant = await provider.async_get_or_create_credentials(
                {"username": "tenant_user"}
            )
            await hass.auth.async_link_user(tenant, cred_tenant)

            client = await hass_client()
            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset/users",
                json={"pin": "847293"},
            )
            assert resp.status == HTTPStatus.OK
            data = await resp.json()
            usernames = [u["username"] for u in data["users"]]
            assert "tenant_user" in usernames
            assert "admin_user" not in usernames

    async def test_reset_changes_password(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test password reset actually changes the password."""
        from homeassistant.auth.const import GROUP_ID_USER
        from homeassistant.auth.providers.homeassistant import InvalidAuth

        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)

            provider = None
            for prv in hass.auth.auth_providers:
                if prv.type == "homeassistant":
                    provider = prv
                    break
            await provider.async_initialize()
            await provider.async_add_auth("mieter", "old_password_123")
            user = await hass.auth.async_create_user(
                "Mieter", group_ids=[GROUP_ID_USER]
            )
            cred = await provider.async_get_or_create_credentials(
                {"username": "mieter"}
            )
            await hass.auth.async_link_user(user, cred)

            client = await hass_client()
            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset",
                json={
                    "pin": "847293",
                    "username": "mieter",
                    "new_password": "new_secure_password_456",
                },
            )
            assert resp.status == HTTPStatus.OK
            data = await resp.json()
            assert data["status"] == "ok"

            # New password works
            await provider.async_validate_login("mieter", "new_secure_password_456")

            # Old password fails
            with pytest.raises(InvalidAuth):
                await provider.async_validate_login("mieter", "old_password_123")

    async def test_reset_wrong_pin(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test reset with wrong PIN returns 401."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset",
                json={
                    "pin": "000000",
                    "username": "mieter",
                    "new_password": "anything",
                },
            )
            assert resp.status == HTTPStatus.UNAUTHORIZED
            data = await resp.json()
            assert data["attempts"] == 1

    async def test_reset_rate_limited(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test exponential backoff on repeated wrong PINs."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            # First wrong attempt — no delay
            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset/users",
                json={"pin": "000000"},
            )
            assert resp.status == HTTPStatus.UNAUTHORIZED
            data = await resp.json()
            assert data["retry_after"] == 0

            # Second wrong attempt — 5s delay
            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset/users",
                json={"pin": "000000"},
            )
            assert resp.status == HTTPStatus.UNAUTHORIZED
            data = await resp.json()
            assert data["retry_after"] == 5

            # Now locked — 429
            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset/users",
                json={"pin": "847293"},
            )
            assert resp.status == HTTPStatus.TOO_MANY_REQUESTS

    async def test_reset_no_pin_file(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test reset returns 404 when no PIN file exists."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.post(
            "/api/greenautarky_onboarding/password_reset/users",
            json={"pin": "123456"},
        )
        assert resp.status == HTTPStatus.NOT_FOUND

    async def test_reset_admin_blocked(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test reset rejects admin users."""
        from homeassistant.auth.const import GROUP_ID_ADMIN

        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)

            provider = None
            for prv in hass.auth.auth_providers:
                if prv.type == "homeassistant":
                    provider = prv
                    break
            await provider.async_initialize()
            await provider.async_add_auth("admin_user", "admin_pass")
            admin = await hass.auth.async_create_user(
                "Admin", group_ids=[GROUP_ID_ADMIN]
            )
            cred = await provider.async_get_or_create_credentials(
                {"username": "admin_user"}
            )
            await hass.auth.async_link_user(admin, cred)

            client = await hass_client()
            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset",
                json={
                    "pin": "847293",
                    "username": "admin_user",
                    "new_password": "new_admin_pw",
                },
            )
            assert resp.status == HTTPStatus.NOT_FOUND

    async def test_reset_separate_pin_state(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test password reset PIN state is separate from onboarding PIN."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            # Fail password reset PIN
            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset/users",
                json={"pin": "000000"},
            )
            assert resp.status == HTTPStatus.UNAUTHORIZED

            # Onboarding PIN should still work
            resp = await client.post(
                "/api/greenautarky_onboarding/verify_pin",
                json={"pin": "847293"},
            )
            assert resp.status == HTTPStatus.OK

    async def test_reset_missing_fields(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
        tmp_path,
    ) -> None:
        """Test reset returns 400 when username or password missing."""
        pin_file = tmp_path / "ga-onboarding-pin"
        pin_file.write_text("847293")

        with patch(
            "homeassistant.components.greenautarky_onboarding.http._pin_file_path",
            return_value=pin_file,
        ):
            await _setup_component(hass, hass_storage, default_state)
            client = await hass_client()

            resp = await client.post(
                "/api/greenautarky_onboarding/password_reset",
                json={"pin": "847293", "username": "", "new_password": ""},
            )
            assert resp.status == HTTPStatus.BAD_REQUEST


class TestAdminBypass:
    """Tests for the ga_bypass=1 admin escape hatch.

    The bypass lets admins reach the normal HA login without completing the
    GA onboarding wizard. It works via either a `?ga_bypass=1` query param
    or a `ga_bypass=1` cookie. The status endpoint must report
    `completed=true` when the cookie is set so the client-side authorize.ts
    skips its redirect to /greenautarky-setup.html.
    """

    async def test_status_without_cookie_reports_actual_state(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Normal customer (no bypass cookie) sees the real onboarding state."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get("/api/greenautarky_onboarding/status")
        assert resp.status == HTTPStatus.OK
        data = await resp.json()
        assert data["completed"] is False

    async def test_status_with_bypass_cookie_reports_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Admin with bypass cookie sees completed=true so client-side skips redirect."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get(
            "/api/greenautarky_onboarding/status",
            cookies={"ga_bypass": "1"},
        )
        assert resp.status == HTTPStatus.OK
        data = await resp.json()
        assert data["completed"] is True

    async def test_status_with_bypass_cookie_does_not_mutate_state(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Bypass is per-request: server state must stay not-completed."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        # Request with cookie
        await client.get(
            "/api/greenautarky_onboarding/status",
            cookies={"ga_bypass": "1"},
        )

        # Server-side state is still not completed
        assert hass.data[DOMAIN]["state"]["completed"] is False

        # Request without cookie returns real state
        resp = await client.get("/api/greenautarky_onboarding/status")
        data = await resp.json()
        assert data["completed"] is False

    async def test_status_with_wrong_cookie_value_no_bypass(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Only ga_bypass=1 triggers bypass; any other value is ignored."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        for bad in ("0", "true", "yes", ""):
            resp = await client.get(
                "/api/greenautarky_onboarding/status",
                cookies={"ga_bypass": bad},
            )
            data = await resp.json()
            assert data["completed"] is False, f"bad cookie value {bad!r} leaked bypass"

    async def test_status_with_bypass_cookie_when_actually_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Cookie is harmless when onboarding is genuinely completed."""
        completed_state = {
            "completed": True,
            "gdpr_accepted": True,
            "steps_done": ["gdpr", "account", "complete"],
            "consents": {},
        }
        await _setup_component(hass, hass_storage, completed_state)
        client = await hass_client()

        resp = await client.get(
            "/api/greenautarky_onboarding/status",
            cookies={"ga_bypass": "1"},
        )
        data = await resp.json()
        assert data["completed"] is True
