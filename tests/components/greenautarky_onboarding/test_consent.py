"""Test consent management for greenautarky onboarding."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.greenautarky_onboarding.consent import (
    async_check_and_create_issues,
    async_record_consent,
    get_outdated_consents,
)
from homeassistant.components.greenautarky_onboarding.const import CONSENT_TYPES, DOMAIN
from homeassistant.core import HomeAssistant


class TestGetOutdatedConsents:
    """Tests for get_outdated_consents()."""

    def test_empty_state_all_outdated(self) -> None:
        """No consents stored → all types returned as outdated."""
        state: dict[str, Any] = {"consents": {}}
        result = get_outdated_consents(state)
        assert result == CONSENT_TYPES

    def test_no_consents_key_all_outdated(self) -> None:
        """Missing consents key entirely → all types outdated."""
        state: dict[str, Any] = {}
        result = get_outdated_consents(state)
        assert result == CONSENT_TYPES

    def test_current_consent_not_outdated(self) -> None:
        """Stored version matches required → empty dict."""
        state: dict[str, Any] = {
            "consents": {
                "gdpr": {
                    "version": CONSENT_TYPES["gdpr"],
                    "accepted_at": "2026-01-01T00:00:00+00:00",
                },
                "ethernet": {
                    "version": CONSENT_TYPES["ethernet"],
                    "accepted_at": "2026-01-01T00:00:00+00:00",
                },
            },
        }
        result = get_outdated_consents(state)
        assert result == {}

    def test_stale_consent_is_outdated(self) -> None:
        """Stored version < required → that type returned."""
        state: dict[str, Any] = {
            "consents": {
                "gdpr": {
                    "version": 0,
                    "accepted_at": "2025-01-01T00:00:00+00:00",
                },
            },
        }
        result = get_outdated_consents(state)
        assert "gdpr" in result
        assert result["gdpr"] == CONSENT_TYPES["gdpr"]


class TestAsyncRecordConsent:
    """Tests for async_record_consent()."""

    async def test_records_consent_and_clears_issue(self, hass: HomeAssistant) -> None:
        """Record consent, save to store, delete repair issue."""
        store = MagicMock()
        store.async_save = AsyncMock()
        state: dict[str, Any] = {"consents": {}}

        with patch(
            "homeassistant.components.greenautarky_onboarding.consent.ir"
        ) as mock_ir:
            result = await async_record_consent(hass, store, state, "gdpr")

        assert result is True
        assert "gdpr" in state["consents"]
        assert state["consents"]["gdpr"]["version"] == CONSENT_TYPES["gdpr"]
        assert "accepted_at" in state["consents"]["gdpr"]
        store.async_save.assert_called_once_with(state)
        mock_ir.async_delete_issue.assert_called_once_with(
            hass, DOMAIN, "consent_outdated_gdpr"
        )

    async def test_unknown_type_returns_false(self, hass: HomeAssistant) -> None:
        """Unknown consent type → returns False, no state change."""
        store = MagicMock()
        store.async_save = AsyncMock()
        state: dict[str, Any] = {"consents": {}}

        result = await async_record_consent(hass, store, state, "bogus")

        assert result is False
        assert "bogus" not in state["consents"]
        store.async_save.assert_not_called()


class TestCheckAndCreateIssues:
    """Tests for async_check_and_create_issues()."""

    def test_creates_issue_for_outdated(self, hass: HomeAssistant) -> None:
        """Create repair issue when consent is outdated."""
        state: dict[str, Any] = {"consents": {}}

        with patch(
            "homeassistant.components.greenautarky_onboarding.consent.ir"
        ) as mock_ir:
            async_check_and_create_issues(hass, state)

        # Both gdpr and ethernet issues should be created (no consents recorded)
        assert mock_ir.async_create_issue.call_count == 2
        keys = [
            c.kwargs["translation_key"]
            for c in mock_ir.async_create_issue.call_args_list
        ]
        assert "consent_outdated_gdpr" in keys
        assert "consent_outdated_ethernet" in keys
        for c in mock_ir.async_create_issue.call_args_list:
            assert c.kwargs["is_fixable"] is True

    def test_deletes_issue_for_current(self, hass: HomeAssistant) -> None:
        """Delete repair issue when consent is current."""
        state: dict[str, Any] = {
            "consents": {
                "gdpr": {
                    "version": CONSENT_TYPES["gdpr"],
                    "accepted_at": "2026-01-01T00:00:00+00:00",
                },
                "ethernet": {
                    "version": CONSENT_TYPES["ethernet"],
                    "accepted_at": "2026-01-01T00:00:00+00:00",
                },
            },
        }

        with patch(
            "homeassistant.components.greenautarky_onboarding.consent.ir"
        ) as mock_ir:
            async_check_and_create_issues(hass, state)

        mock_ir.async_create_issue.assert_not_called()
        assert mock_ir.async_delete_issue.call_count == 2
