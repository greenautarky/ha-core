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
            "consents": {"gdpr": {"version": 1, "accepted_at": "2026-01-01"}},
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
