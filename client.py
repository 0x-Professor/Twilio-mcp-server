"""Async Twilio REST client wrapper."""

import asyncio
from typing import Any, Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from .config import settings

# Twilio SDK is synchronous — we run it in a thread pool so we don't block the event loop
_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.account_sid, settings.auth_token)
    return _client


async def _run(fn, *args, **kwargs) -> Any:
    """Run a synchronous Twilio SDK call in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ── Message operations ───────────────────────────────────────────────────────

async def send_message(
    to: str,
    body: str,
    media_url: Optional[list[str]] = None,
    schedule_time: Optional[str] = None,
) -> dict[str, Any]:
    """Send an SMS (or MMS if media_url provided). Returns message dict."""
    client = get_client()
    params: dict[str, Any] = {"to": to, "body": body}

    if settings.messaging_service_sid:
        params["messaging_service_sid"] = settings.messaging_service_sid
    else:
        params["from_"] = settings.from_number

    if media_url:
        params["media_url"] = media_url

    if schedule_time:
        params["send_at"] = schedule_time
        params["schedule_type"] = "fixed"
        if not settings.messaging_service_sid:
            raise ValueError("Scheduling requires TWILIO_MESSAGING_SERVICE_SID to be set.")

    msg = await _run(client.messages.create, **params)
    return _message_to_dict(msg)


async def fetch_message(sid: str) -> dict[str, Any]:
    """Fetch a single message by SID."""
    client = get_client()
    msg = await _run(client.messages(sid).fetch)
    return _message_to_dict(msg)


async def list_messages(
    to: Optional[str] = None,
    from_: Optional[str] = None,
    limit: int = 20,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """List messages from Twilio — sent and received."""
    client = get_client()
    kwargs: dict[str, Any] = {"limit": limit, "page_size": page_size}
    if to:
        kwargs["to"] = to
    if from_:
        kwargs["from_"] = from_
    msgs = await _run(client.messages.list, **kwargs)
    return [_message_to_dict(m) for m in msgs]


async def cancel_message(sid: str) -> dict[str, Any]:
    """Cancel a scheduled message (status must be 'scheduled')."""
    client = get_client()
    msg = await _run(client.messages(sid).update, status="canceled")
    return _message_to_dict(msg)


async def delete_message(sid: str) -> bool:
    """Delete a message record. Returns True on success."""
    client = get_client()
    await _run(client.messages(sid).delete)
    return True


# ── Phone number operations ──────────────────────────────────────────────────

async def list_phone_numbers() -> list[dict[str, Any]]:
    """List all Twilio phone numbers on this account."""
    client = get_client()
    numbers = await _run(client.incoming_phone_numbers.list)
    return [
        {
            "sid": n.sid,
            "phone_number": n.phone_number,
            "friendly_name": n.friendly_name,
            "capabilities": {
                "sms": n.capabilities.get("sms"),
                "mms": n.capabilities.get("mms"),
                "voice": n.capabilities.get("voice"),
            },
            "sms_url": n.sms_url,
            "date_created": str(n.date_created),
        }
        for n in numbers
    ]


async def lookup_number(phone_number: str) -> dict[str, Any]:
    """Lookup carrier and line type info for a phone number."""
    client = get_client()
    result = await _run(
        client.lookups.v2.phone_numbers(phone_number).fetch,
        fields="line_type_intelligence",
    )
    return {
        "phone_number": result.phone_number,
        "country_code": result.country_code,
        "national_format": result.national_format,
        "valid": result.valid,
        "line_type_intelligence": result.line_type_intelligence,
    }


async def get_account_info() -> dict[str, Any]:
    """Fetch account balance and status."""
    client = get_client()
    account = await _run(client.api.accounts(settings.account_sid).fetch)
    balance = await _run(client.balance.fetch)
    return {
        "account_sid": account.sid,
        "friendly_name": account.friendly_name,
        "status": account.status,
        "type": account.type,
        "balance": balance.balance,
        "currency": balance.currency,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _message_to_dict(msg) -> dict[str, Any]:
    return {
        "sid": msg.sid,
        "to": msg.to,
        "from": msg.from_,
        "body": msg.body,
        "status": msg.status,
        "direction": msg.direction,
        "num_segments": msg.num_segments,
        "num_media": msg.num_media,
        "price": str(msg.price) if msg.price else None,
        "price_unit": msg.price_unit,
        "date_created": str(msg.date_created),
        "date_sent": str(msg.date_sent) if msg.date_sent else None,
        "date_updated": str(msg.date_updated) if msg.date_updated else None,
        "error_code": msg.error_code,
        "error_message": msg.error_message,
        "uri": msg.uri,
    }


def handle_error(e: Exception) -> str:
    """Convert exceptions to clear, actionable agent-readable messages."""
    if isinstance(e, TwilioRestException):
        code = e.code
        if code == 20003:
            return "Error: Authentication failed. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
        if code == 21211:
            return "Error: Invalid 'to' phone number. Use E.164 format: +[country_code][number] e.g. +12025551234."
        if code == 21214:
            return "Error: 'to' number is not a mobile number capable of receiving SMS."
        if code == 21408:
            return "Error: Permission to send to this region is not enabled. Enable it in the Twilio Console → Messaging → Geographic Permissions."
        if code == 21610:
            return "Error: This number has opted out (STOP). Twilio blocks messages to opted-out numbers automatically."
        if code == 21612:
            return "Error: The 'from' number cannot send to the 'to' number. They may be on the same carrier's domestic network, which blocks A2P."
        if code == 21617:
            return "Error: Message body exceeds 1,600 character limit. Shorten the message."
        if code == 30006:
            return "Error: Landline or unreachable carrier. The destination number cannot receive SMS."
        if e.status == 429:
            return "Error: Rate limit hit. Twilio limits messages per second per number — wait and retry."
        return f"Error: Twilio error {code} — {e.msg}. See https://www.twilio.com/docs/errors/{code}"
    if isinstance(e, ValueError):
        return f"Error: {e}"
    return f"Error: Unexpected error — {type(e).__name__}: {e}"
