"""Test the greenautarky onboarding HTTP views."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from unittest.mock import patch

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


class TestPageView:
    """Tests for GET /greenautarky-setup."""

    async def test_page_serves_html_when_not_completed(
        self,
        hass: HomeAssistant,
        hass_storage: dict[str, Any],
        hass_client: ClientSessionGenerator,
        default_state: dict[str, Any],
    ) -> None:
        """Test setup page is served when not completed."""
        await _setup_component(hass, hass_storage, default_state)
        client = await hass_client()

        resp = await client.get("/greenautarky-setup", allow_redirects=False)
        assert resp.status == HTTPStatus.OK
        assert "text/html" in resp.content_type

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
