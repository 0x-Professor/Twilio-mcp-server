"""FastAPI webhook server for inbound Twilio callbacks."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from .config import get_settings
from .store import init_db, store_inbound, update_delivery_status

logger = logging.getLogger(__name__)


def _validation_url(request: Request) -> str:
    settings = get_settings()
    if settings.public_webhook_base_url:
        query = f"?{request.url.query}" if request.url.query else ""
        return f"{settings.public_webhook_base_url}{request.url.path}{query}"
    return str(request.url)


def _validate_twilio_request(request: Request, form_data: dict[str, str]) -> bool:
    settings = get_settings()
    if not settings.validate_webhook_signatures:
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(settings.effective_webhook_auth_token)
    return validator.validate(_validation_url(request), form_data, signature)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Twilio SMS Webhook",
    docs_url=None,
    redoc_url=None,
    lifespan=_lifespan,
)


@app.post("/webhook/sms")
async def receive_sms(request: Request) -> Response:
    form_data = dict(await request.form())

    if not _validate_twilio_request(request, form_data):
        logger.warning("Rejected inbound SMS webhook with invalid Twilio signature.")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    store_inbound(form_data)
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
        status_code=200,
    )


@app.post("/webhook/status")
async def delivery_status(request: Request) -> Response:
    form_data = dict(await request.form())

    if not _validate_twilio_request(request, form_data):
        logger.warning("Rejected delivery status webhook with invalid Twilio signature.")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    update_delivery_status(form_data)
    return Response(status_code=204)


@app.get("/health")
@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def ready() -> dict[str, str]:
    init_db()
    return {"status": "ready"}
