from __future__ import annotations

from fastapi.testclient import TestClient


def test_webhook_persists_inbound_message():
    from twilio_sms_mcp import store
    from twilio_sms_mcp.webhook import app

    sid = f"SM{'2' * 32}"
    with TestClient(app) as client:
        response = client.post(
            "/webhook/sms",
            data={
                "MessageSid": sid,
                "From": "+12025550123",
                "To": "+12025550100",
                "Body": "hi from webhook",
                "NumMedia": "0",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")

    inbox = store.get_inbox()
    assert len(inbox) == 1
    assert inbox[0]["sid"] == sid


def test_health_endpoints():
    from twilio_sms_mcp.webhook import app

    with TestClient(app) as client:
        health = client.get("/healthz").json()
        assert health["status"] == "ok"
        assert "version" in health

        ready = client.get("/readyz").json()
        assert ready["status"] == "ready"
        assert "version" in ready


def test_delivery_status_callback():
    from twilio_sms_mcp import store
    from twilio_sms_mcp.webhook import app

    sid = f"SM{'4' * 32}"
    with TestClient(app) as client:
        response = client.post(
            "/webhook/status",
            data={
                "MessageSid": sid,
                "MessageStatus": "delivered",
                "ErrorCode": "",
            },
        )
        assert response.status_code == 204

    store.init_db()
    status = store.get_latest_delivery_status(sid)
    assert status is not None
    assert status["status"] == "delivered"
