"""FastAPI webhook server for inbound Twilio callbacks."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from . import __version__
from .config import get_settings
from .store import init_db, store_inbound, update_delivery_status

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter: max requests per IP per window.
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 120  # requests per window
_request_counts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is within the rate limit."""
    now = time.monotonic()
    timestamps = _request_counts[client_ip]
    # Evict old entries
    _request_counts[client_ip] = [ts for ts in timestamps if now - ts < _RATE_LIMIT_WINDOW]
    if len(_request_counts[client_ip]) >= _RATE_LIMIT_MAX:
        return False
    _request_counts[client_ip].append(now)
    return True


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
    version=__version__,
    docs_url=None,
    redoc_url=None,
    lifespan=_lifespan,
)


@app.post("/webhook/sms")
async def receive_sms(request: Request) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        logger.warning("Rate limit exceeded for %s on /webhook/sms", client_ip)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    form_data = dict(await request.form())

    if not _validate_twilio_request(request, form_data):
        logger.warning("Rejected inbound SMS webhook with invalid Twilio signature from %s.", client_ip)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    store_inbound(form_data)
    logger.info("Stored inbound SMS %s from %s", form_data.get("MessageSid", "?"), form_data.get("From", "?"))
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
        status_code=200,
    )


@app.post("/webhook/status")
async def delivery_status(request: Request) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        logger.warning("Rate limit exceeded for %s on /webhook/status", client_ip)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    form_data = dict(await request.form())

    if not _validate_twilio_request(request, form_data):
        logger.warning("Rejected delivery status webhook with invalid Twilio signature from %s.", client_ip)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    update_delivery_status(form_data)
    return Response(status_code=204)


@app.get("/health")
@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def ready() -> dict[str, str]:
    init_db()
    return {"status": "ready", "version": __version__}
