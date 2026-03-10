"""Tests for the client module — retry logic, error handling, and edge cases."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from twilio.base.exceptions import TwilioRestException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(**overrides) -> SimpleNamespace:
    defaults = dict(
        sid="SM" + "a" * 32,
        to="+12025559999",
        from_="+12025550100",
        body="hello",
        status="queued",
        direction="outbound-api",
        num_segments="1",
        num_media="0",
        price=None,
        price_unit="USD",
        date_created="2025-01-01T00:00:00+00:00",
        date_sent=None,
        date_updated=None,
        error_code=None,
        error_message=None,
        uri="/test",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _twilio_exc(code: int = 20003, status: int = 401, msg: str = "err") -> TwilioRestException:
    return TwilioRestException(status=status, uri="/test", msg=msg, code=code)


# ===========================================================================
# Retry logic
# ===========================================================================


def _override_retry(monkeypatch, attempts: int, delay: float = 0.1):
    """Helper to override retry settings via env and reset the settings cache."""
    monkeypatch.setenv("TWILIO_API_RETRY_ATTEMPTS", str(attempts))
    monkeypatch.setenv("TWILIO_API_RETRY_DELAY", str(delay))
    from twilio_sms_mcp.config import reset_settings_cache
    reset_settings_cache()


class TestRetryLogic:
    """Tests for exponential backoff retry in _run_with_retry."""

    async def test_retry_on_429(self, monkeypatch):
        _override_retry(monkeypatch, attempts=2)
        from twilio_sms_mcp.client import _run_with_retry

        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TwilioRestException(status=429, uri="/test", msg="Rate limit", code=20429)
            return "ok"

        result = await _run_with_retry(flaky)
        assert result == "ok"
        assert call_count == 3

    async def test_retry_exhausted(self, monkeypatch):
        _override_retry(monkeypatch, attempts=1)
        from twilio_sms_mcp.client import _run_with_retry

        def always_fail():
            raise TwilioRestException(status=500, uri="/test", msg="Server Error", code=20500)

        with pytest.raises(TwilioRestException):
            await _run_with_retry(always_fail)

    async def test_no_retry_on_non_retryable_error(self, monkeypatch):
        _override_retry(monkeypatch, attempts=3)
        from twilio_sms_mcp.client import _run_with_retry

        call_count = 0

        def non_retryable():
            nonlocal call_count
            call_count += 1
            raise TwilioRestException(status=400, uri="/test", msg="Bad request", code=21211)

        with pytest.raises(TwilioRestException):
            await _run_with_retry(non_retryable)
        assert call_count == 1  # No retries for 400-level client errors

    async def test_retry_on_connection_error(self, monkeypatch):
        _override_retry(monkeypatch, attempts=1)
        from twilio_sms_mcp.client import _run_with_retry

        call_count = 0

        def network_flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection reset")
            return "recovered"

        result = await _run_with_retry(network_flaky)
        assert result == "recovered"
        assert call_count == 2

    async def test_zero_retries_no_retry(self):
        # conftest already sets TWILIO_API_RETRY_ATTEMPTS=0
        from twilio_sms_mcp.client import _run_with_retry

        call_count = 0

        def fail_once():
            nonlocal call_count
            call_count += 1
            raise TwilioRestException(status=500, uri="/test", msg="fail", code=20500)

        with pytest.raises(TwilioRestException):
            await _run_with_retry(fail_once)
        assert call_count == 1


# ===========================================================================
# Error handler
# ===========================================================================


class TestHandleError:
    """Tests for handle_error returning user-friendly messages."""

    def test_auth_error(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(20003, 401, "Auth failed")
        msg = handle_error(err)
        assert "Authentication" in msg

    def test_invalid_number_error(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(21211, 400, "Invalid number")
        msg = handle_error(err)
        assert "Invalid" in msg and "phone number" in msg

    def test_not_sms_capable(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(21214, 400, "Not SMS capable")
        msg = handle_error(err)
        assert "SMS-capable" in msg

    def test_geo_permissions(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(21408, 403, "Geo block")
        msg = handle_error(err)
        assert "Geographic" in msg or "geographic" in msg

    def test_opted_out(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(21610, 400, "Opted out")
        msg = handle_error(err)
        assert "opted out" in msg or "STOP" in msg

    def test_sender_blocked(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(21612, 400, "Cannot message")
        msg = handle_error(err)
        assert "sender" in msg or "destination" in msg

    def test_body_too_long(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(21617, 400, "Too long")
        msg = handle_error(err)
        assert "1,600" in msg or "character" in msg

    def test_carrier_rejected(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(30006, 400, "Carrier rejected")
        msg = handle_error(err)
        assert "carrier" in msg or "rejected" in msg

    def test_rate_limit_error(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(20429, 429, "Rate limit")
        msg = handle_error(err)
        assert "rate limit" in msg.lower()

    def test_generic_twilio_error(self):
        from twilio_sms_mcp.client import handle_error

        err = _twilio_exc(99999, 400, "Unknown issue")
        msg = handle_error(err)
        assert "99999" in msg

    def test_value_error(self):
        from twilio_sms_mcp.client import handle_error

        msg = handle_error(ValueError("Bad input"))
        assert "Bad input" in msg

    def test_unexpected_error(self):
        from twilio_sms_mcp.client import handle_error

        msg = handle_error(RuntimeError("Something broke"))
        assert "RuntimeError" in msg


# ===========================================================================
# message_to_dict
# ===========================================================================


class TestMessageToDict:
    """Tests for _message_to_dict conversion."""

    def test_basic_conversion(self):
        from twilio_sms_mcp.client import _message_to_dict

        msg = _make_message(price="0.0075", date_sent="2025-01-01T00:00:00+00:00")
        d = _message_to_dict(msg)
        assert d["sid"] == msg.sid
        assert d["price"] == "0.0075"
        assert d["date_sent"] == "2025-01-01T00:00:00+00:00"

    def test_null_price(self):
        from twilio_sms_mcp.client import _message_to_dict

        msg = _make_message(price=None)
        d = _message_to_dict(msg)
        assert d["price"] is None

    def test_null_dates(self):
        from twilio_sms_mcp.client import _message_to_dict

        msg = _make_message(date_sent=None, date_updated=None)
        d = _message_to_dict(msg)
        assert d["date_sent"] is None
        assert d["date_updated"] is None


# ===========================================================================
# message_sort_key
# ===========================================================================


class TestMessageSortKey:
    """Tests for the _message_sort_key ordering function."""

    def test_sorts_by_date_sent(self):
        from twilio_sms_mcp.client import _message_sort_key

        msg = {"date_sent": "2025-06-15T10:00:00+00:00"}
        ts = _message_sort_key(msg)
        assert ts.year == 2025 and ts.month == 6

    def test_falls_back_to_date_created(self):
        from twilio_sms_mcp.client import _message_sort_key

        msg = {"date_sent": None, "date_created": "2025-03-01T08:00:00+00:00"}
        ts = _message_sort_key(msg)
        assert ts.month == 3

    def test_no_dates_returns_min(self):
        from twilio_sms_mcp.client import _message_sort_key

        ts = _message_sort_key({})
        assert ts == datetime.min.replace(tzinfo=timezone.utc)

    def test_handles_z_suffix(self):
        from twilio_sms_mcp.client import _message_sort_key

        msg = {"date_sent": "2025-01-01T00:00:00Z"}
        ts = _message_sort_key(msg)
        assert ts.tzinfo is not None


# ===========================================================================
# get_client singleton
# ===========================================================================


class TestGetClient:
    """Tests for the Twilio client singleton."""

    def test_creates_client_once(self):
        from twilio_sms_mcp import client as mod

        mod._client = None
        c1 = mod.get_client()
        c2 = mod.get_client()
        assert c1 is c2

    def test_reset_client(self):
        from twilio_sms_mcp import client as mod

        mod._client = None
        c1 = mod.get_client()
        mod._client = None
        c2 = mod.get_client()
        assert c1 is not c2
