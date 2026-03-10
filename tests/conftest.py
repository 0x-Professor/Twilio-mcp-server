from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", f"AC{'1' * 32}")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+12025550100")
    monkeypatch.setenv("TWILIO_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TWILIO_VALIDATE_WEBHOOK_SIGNATURES", "false")
    monkeypatch.setenv("TWILIO_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("TWILIO_API_RETRY_ATTEMPTS", "0")
    monkeypatch.setenv("TWILIO_API_RETRY_DELAY", "0.1")

    from twilio_sms_mcp import client as twilio_client
    from twilio_sms_mcp.config import reset_settings_cache

    twilio_client._client = None
    reset_settings_cache()
    yield
    twilio_client._client = None
    reset_settings_cache()
