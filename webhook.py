"""
FastAPI webhook server.

Twilio calls this server when:
  1. A new SMS arrives at your Twilio number  →  POST /webhook/sms
  2. A delivery status update fires           →  POST /webhook/status

Run alongside the MCP server inside the Docker container.
"""

from fastapi import FastAPI, Request, Response, HTTPException
from twilio.request_validator import RequestValidator

from .config import settings
from .store import store_inbound, update_delivery_status

app = FastAPI(title="Twilio SMS Webhook", docs_url=None, redoc_url=None)

_validator = RequestValidator(settings.auth_token)


def _validate_twilio_request(request: Request, form_data: dict) -> bool:
    """Verify the request genuinely came from Twilio using signature validation."""
    if not settings.webhook_auth_token:
        # Skip validation in local dev if token not set — warn loudly
        return True
    sig = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    return _validator.validate(url, form_data, sig)


@app.post("/webhook/sms")
async def receive_sms(request: Request):
    """
    Twilio calls this endpoint when an SMS arrives at your number.
    Responds with TwiML 200 OK (no auto-reply).
    Configure this URL in: Twilio Console → Phone Numbers → your number → Messaging → Webhook.
    """
    form_data = dict(await request.form())

    if not _validate_twilio_request(request, form_data):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    store_inbound(form_data)

    # Empty TwiML response — no auto-reply
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
        status_code=200,
    )


@app.post("/webhook/status")
async def delivery_status(request: Request):
    """
    Twilio calls this endpoint with delivery status updates (sent, delivered, failed).
    Configure this URL in: Twilio Console → Phone Numbers → your number → Messaging → Status Callback URL.
    """
    form_data = dict(await request.form())

    if not _validate_twilio_request(request, form_data):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    update_delivery_status(form_data)
    return Response(status_code=204)


@app.get("/health")
async def health():
    return {"status": "ok"}
