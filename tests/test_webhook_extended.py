"""Extended webhook tests — rate limiting, signature validation, edge cases."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestWebhookRateLimiting:
    """Tests for in-memory rate limiter."""

    def test_rate_limit_triggers_after_max(self):
        from twilio_sms_mcp.webhook import app, _request_counts, _RATE_LIMIT_MAX

        _request_counts.clear()

        with TestClient(app) as client:
            # Fill up the rate limit window
            for i in range(_RATE_LIMIT_MAX):
                resp = client.post("/webhook/sms", data={
                    "MessageSid": f"SM{str(i).zfill(32)}",
                    "From": "+12025550123",
                    "To": "+12025550100",
                    "Body": f"msg {i}",
                    "NumMedia": "0",
                })
                assert resp.status_code == 200, f"Request {i} should succeed"

            # Next request should be rate-limited
            resp = client.post("/webhook/sms", data={
                "MessageSid": f"SM{'z' * 32}",
                "From": "+12025550123",
                "To": "+12025550100",
                "Body": "over limit",
                "NumMedia": "0",
            })
            assert resp.status_code == 429

        _request_counts.clear()

    def test_rate_limit_on_status_endpoint(self):
        from twilio_sms_mcp.webhook import app, _request_counts, _RATE_LIMIT_MAX

        _request_counts.clear()

        with TestClient(app) as client:
            for i in range(_RATE_LIMIT_MAX):
                resp = client.post("/webhook/status", data={
                    "MessageSid": f"SM{str(i).zfill(32)}",
                    "MessageStatus": "delivered",
                    "ErrorCode": "",
                })
                assert resp.status_code == 204

            resp = client.post("/webhook/status", data={
                "MessageSid": f"SM{'y' * 32}",
                "MessageStatus": "delivered",
                "ErrorCode": "",
            })
            assert resp.status_code == 429

        _request_counts.clear()


class TestWebhookSignatureValidation:
    """Tests for Twilio request signature validation."""

    def test_invalid_signature_rejected(self, monkeypatch):
        monkeypatch.setenv("TWILIO_VALIDATE_WEBHOOK_SIGNATURES", "true")
        from twilio_sms_mcp.config import reset_settings_cache
        reset_settings_cache()
        from twilio_sms_mcp.webhook import app, _request_counts

        _request_counts.clear()

        with TestClient(app) as client:
            resp = client.post(
                "/webhook/sms",
                data={
                    "MessageSid": f"SM{'x' * 32}",
                    "From": "+12025550123",
                    "To": "+12025550100",
                    "Body": "bad sig",
                    "NumMedia": "0",
                },
                headers={"X-Twilio-Signature": "invalid-signature"},
            )
            assert resp.status_code == 403

        _request_counts.clear()


class TestWebhookEdgeCases:
    """Edge case tests for webhook endpoints."""

    def test_sms_webhook_missing_fields(self):
        from twilio_sms_mcp.webhook import app, _request_counts

        _request_counts.clear()

        with TestClient(app) as client:
            # Minimal payload — should still be accepted (store_inbound handles missing keys)
            resp = client.post("/webhook/sms", data={
                "MessageSid": f"SM{'m' * 32}",
                "From": "+12025550123",
                "To": "+12025550100",
            })
            assert resp.status_code == 200

        _request_counts.clear()

    def test_health_is_get_only(self):
        from twilio_sms_mcp.webhook import app

        with TestClient(app) as client:
            resp = client.post("/healthz")
            assert resp.status_code == 405

    def test_status_webhook_returns_204(self):
        from twilio_sms_mcp.webhook import app, _request_counts

        _request_counts.clear()

        with TestClient(app) as client:
            resp = client.post("/webhook/status", data={
                "MessageSid": f"SM{'n' * 32}",
                "MessageStatus": "sent",
                "ErrorCode": "",
            })
            assert resp.status_code == 204
            assert resp.content == b""

        _request_counts.clear()
