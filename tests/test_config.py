"""Tests for configuration validation and setup_logging."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError


class TestSettingsValidation:
    """Tests for Settings field validation."""

    def test_valid_settings(self):
        from twilio_sms_mcp.config import Settings

        s = Settings(
            TWILIO_ACCOUNT_SID="AC" + "1" * 32,
            TWILIO_AUTH_TOKEN="tok",
            TWILIO_FROM_NUMBER="+12025550100",
        )
        assert s.account_sid == "AC" + "1" * 32
        assert s.from_number == "+12025550100"

    def test_invalid_account_sid(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError, match="ACCOUNT_SID"):
            Settings(
                TWILIO_ACCOUNT_SID="INVALID",
                TWILIO_AUTH_TOKEN="tok",
                TWILIO_FROM_NUMBER="+12025550100",
            )

    def test_invalid_from_number(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError, match="FROM_NUMBER"):
            Settings(
                TWILIO_ACCOUNT_SID="AC" + "1" * 32,
                TWILIO_AUTH_TOKEN="tok",
                TWILIO_FROM_NUMBER="not-e164",
            )

    def test_empty_auth_token(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError):
            Settings(
                TWILIO_ACCOUNT_SID="AC" + "1" * 32,
                TWILIO_AUTH_TOKEN="",
                TWILIO_FROM_NUMBER="+12025550100",
            )

    def test_blank_messaging_service_sid_becomes_none(self):
        from twilio_sms_mcp.config import Settings

        s = Settings(
            TWILIO_ACCOUNT_SID="AC" + "1" * 32,
            TWILIO_AUTH_TOKEN="tok",
            TWILIO_FROM_NUMBER="+12025550100",
            TWILIO_MESSAGING_SERVICE_SID="",
        )
        assert s.messaging_service_sid is None

    def test_valid_messaging_service_sid(self):
        from twilio_sms_mcp.config import Settings

        s = Settings(
            TWILIO_ACCOUNT_SID="AC" + "1" * 32,
            TWILIO_AUTH_TOKEN="tok",
            TWILIO_FROM_NUMBER="+12025550100",
            TWILIO_MESSAGING_SERVICE_SID="MG" + "a" * 32,
        )
        assert s.messaging_service_sid == "MG" + "a" * 32

    def test_invalid_messaging_service_sid(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError, match="MG"):
            Settings(
                TWILIO_ACCOUNT_SID="AC" + "1" * 32,
                TWILIO_AUTH_TOKEN="tok",
                TWILIO_FROM_NUMBER="+12025550100",
                TWILIO_MESSAGING_SERVICE_SID="INVALID",
            )

    def test_webhook_base_url_must_have_scheme(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError, match="http"):
            Settings(
                TWILIO_ACCOUNT_SID="AC" + "1" * 32,
                TWILIO_AUTH_TOKEN="tok",
                TWILIO_FROM_NUMBER="+12025550100",
                TWILIO_PUBLIC_WEBHOOK_BASE_URL="no-scheme.example.com",
            )

    def test_webhook_base_url_strips_trailing_slash(self):
        from twilio_sms_mcp.config import Settings

        s = Settings(
            TWILIO_ACCOUNT_SID="AC" + "1" * 32,
            TWILIO_AUTH_TOKEN="tok",
            TWILIO_FROM_NUMBER="+12025550100",
            TWILIO_PUBLIC_WEBHOOK_BASE_URL="https://example.com/hooks/",
        )
        assert s.public_webhook_base_url == "https://example.com/hooks"

    def test_invalid_log_level(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError, match="log_level"):
            Settings(
                TWILIO_ACCOUNT_SID="AC" + "1" * 32,
                TWILIO_AUTH_TOKEN="tok",
                TWILIO_FROM_NUMBER="+12025550100",
                TWILIO_LOG_LEVEL="VERBOSE",
            )

    def test_log_level_normalised_to_upper(self):
        from twilio_sms_mcp.config import Settings

        s = Settings(
            TWILIO_ACCOUNT_SID="AC" + "1" * 32,
            TWILIO_AUTH_TOKEN="tok",
            TWILIO_FROM_NUMBER="+12025550100",
            TWILIO_LOG_LEVEL="debug",
        )
        assert s.log_level == "DEBUG"

    def test_port_out_of_range(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError):
            Settings(
                TWILIO_ACCOUNT_SID="AC" + "1" * 32,
                TWILIO_AUTH_TOKEN="tok",
                TWILIO_FROM_NUMBER="+12025550100",
                WEBHOOK_PORT=99999,
            )

    def test_retry_attempts_out_of_range(self):
        from twilio_sms_mcp.config import Settings

        with pytest.raises(ValidationError):
            Settings(
                TWILIO_ACCOUNT_SID="AC" + "1" * 32,
                TWILIO_AUTH_TOKEN="tok",
                TWILIO_FROM_NUMBER="+12025550100",
                TWILIO_API_RETRY_ATTEMPTS=100,
            )

    def test_effective_webhook_auth_token_custom(self):
        from twilio_sms_mcp.config import Settings

        s = Settings(
            TWILIO_ACCOUNT_SID="AC" + "1" * 32,
            TWILIO_AUTH_TOKEN="main-token",
            TWILIO_FROM_NUMBER="+12025550100",
            TWILIO_WEBHOOK_AUTH_TOKEN="custom-webhook-token",
        )
        assert s.effective_webhook_auth_token == "custom-webhook-token"

    def test_effective_webhook_auth_token_fallback(self, monkeypatch):
        from twilio_sms_mcp.config import get_settings, reset_settings_cache

        # Ensure webhook auth token is NOT set so the fallback path is exercised.
        monkeypatch.delenv("TWILIO_WEBHOOK_AUTH_TOKEN", raising=False)
        reset_settings_cache()
        s = get_settings()
        assert s.webhook_auth_token is None
        assert s.effective_webhook_auth_token == s.auth_token.get_secret_value()


class TestSetupLogging:
    """Tests for the setup_logging helper."""

    def test_sets_root_logger_level(self):
        from twilio_sms_mcp.config import setup_logging

        setup_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_quiets_noisy_libraries(self):
        from twilio_sms_mcp.config import setup_logging

        setup_logging("DEBUG")
        assert logging.getLogger("httpx").level >= logging.WARNING
        assert logging.getLogger("httpcore").level >= logging.WARNING

    def test_invalid_level_defaults_to_info(self):
        from twilio_sms_mcp.config import setup_logging

        setup_logging("NONEXISTENT")
        assert logging.getLogger().level == logging.INFO


class TestGetSettings:
    """Tests for get_settings / reset_settings_cache."""

    def test_cached(self):
        from twilio_sms_mcp.config import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset_cache(self):
        from twilio_sms_mcp.config import get_settings, reset_settings_cache

        s1 = get_settings()
        reset_settings_cache()
        s2 = get_settings()
        assert s1 is not s2
