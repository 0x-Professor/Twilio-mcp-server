from __future__ import annotations

from fastapi.testclient import TestClient


def test_webhook_persists_inbound_message():
    from twilio_sms_mcp import store
    from twilio_sms_mcp.webhook import app

    client = TestClient(app)
    sid = f"SM{'2' * 32}"
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

    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
