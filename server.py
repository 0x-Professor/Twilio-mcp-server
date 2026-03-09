"""
Twilio SMS MCP Server
=====================
Production-grade MCP server for Twilio Programmable Messaging.

Tools
-----
  sms_send              — Send a single SMS or MMS
  sms_send_bulk         — Send the same message to multiple numbers
  sms_schedule          — Schedule a message for future delivery
  sms_cancel_scheduled  — Cancel a scheduled message
  sms_list_sent         — List outbound messages (with filters)
  sms_get_message       — Fetch one message by SID
  sms_delete_message    — Delete a message record
  sms_list_inbox        — List inbound messages received via webhook
  sms_get_conversation  — Full conversation thread with a phone number
  sms_mark_read         — Mark inbox messages as read
  sms_list_numbers      — List your Twilio phone numbers
  sms_lookup_number     — Carrier + line-type lookup
  sms_account_info      — Account balance and status
"""

import json
import asyncio
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from fastmcp import FastMCP

from . import client as twilio_client
from . import store
from .config import settings

# ── Server init ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    "twilio_sms_mcp",
    instructions=(
        "You are connected to the Twilio SMS MCP server. "
        "Use sms_list_inbox to check received messages, sms_send to send messages, "
        "and sms_get_conversation to view a full thread with a contact. "
        "All phone numbers must be in E.164 format: +[country_code][number] e.g. +12025551234."
    ),
)

store.init_db()


# ── Input models ─────────────────────────────────────────────────────────────

E164_PATTERN = r"^\+[1-9]\d{7,14}$"


class SendInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    to: str = Field(
        ...,
        description="Recipient phone number in E.164 format. Example: '+12025551234'",
        pattern=E164_PATTERN,
    )
    body: str = Field(
        ...,
        description="Message text (up to 1,600 characters). Longer texts are auto-split into segments.",
        min_length=1,
        max_length=1600,
    )
    media_urls: Optional[list[str]] = Field(
        default=None,
        description="Optional list of public image URLs to attach (MMS). Max 10 URLs. Supported: jpeg, jpg, png, gif.",
        max_length=10,
    )


class SendBulkInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    to: list[str] = Field(
        ...,
        description="List of recipient phone numbers in E.164 format. Max 100.",
        min_length=1,
        max_length=100,
    )
    body: str = Field(..., description="Message text (up to 1,600 characters).", min_length=1, max_length=1600)


class ScheduleInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    to: str = Field(..., description="Recipient phone number in E.164 format.", pattern=E164_PATTERN)
    body: str = Field(..., description="Message text.", min_length=1, max_length=1600)
    send_at: str = Field(
        ...,
        description=(
            "ISO 8601 datetime with timezone for scheduled delivery. "
            "Must be at least 15 minutes in the future. Example: '2025-12-01T09:00:00Z'"
        ),
    )


class SidInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sid: str = Field(
        ...,
        description="Twilio Message SID starting with 'SM'. Example: 'SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'",
        pattern=r"^SM[a-f0-9]{32}$",
    )


class ListSentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: Optional[str] = Field(default=None, description="Filter by recipient number (E.164).")
    from_: Optional[str] = Field(default=None, alias="from", description="Filter by sender number (E.164).")
    limit: int = Field(default=20, description="Number of messages to return (1–100).", ge=1, le=100)


class ListInboxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_number: Optional[str] = Field(default=None, description="Filter by sender number.")
    unread_only: bool = Field(default=False, description="If true, only return unread messages.")
    limit: int = Field(default=20, description="Number of messages to return (1–100).", ge=1, le=100)
    offset: int = Field(default=0, description="Pagination offset.", ge=0)


class ConversationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    number: str = Field(
        ...,
        description="Phone number to retrieve conversation with (E.164).",
        pattern=E164_PATTERN,
    )
    limit: int = Field(default=50, description="Max messages to return.", ge=1, le=200)


class MarkReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sid: Optional[str] = Field(default=None, description="Mark a specific message SID as read. If omitted, marks ALL as read.")
    from_number: Optional[str] = Field(default=None, description="Mark all messages from this number as read.")


class LookupInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phone_number: str = Field(
        ...,
        description="Phone number to look up in E.164 format. Example: '+12025551234'",
        pattern=E164_PATTERN,
    )


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool(
    name="sms_send",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def sms_send(params: SendInput) -> str:
    """Send a single SMS or MMS message via Twilio.

    Sends from the configured TWILIO_FROM_NUMBER to the specified recipient.
    For MMS, include public image URLs in media_urls.
    Returns the message SID and initial delivery status.

    Args:
        params (SendInput): Validated input containing:
            - to (str): Recipient phone number in E.164 format
            - body (str): Message text up to 1,600 characters
            - media_urls (Optional[list[str]]): Public image URLs for MMS

    Returns:
        str: JSON with message SID, status, and cost information
    """
    try:
        msg = await twilio_client.send_message(
            to=params.to,
            body=params.body,
            media_url=params.media_urls,
        )
        return json.dumps({
            "success": True,
            "sid": msg["sid"],
            "to": msg["to"],
            "from": msg["from"],
            "status": msg["status"],
            "num_segments": msg["num_segments"],
            "date_created": msg["date_created"],
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_send_bulk",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def sms_send_bulk(params: SendBulkInput) -> str:
    """Send the same SMS message to multiple recipients concurrently.

    Fires all sends in parallel using asyncio.gather. Each result is
    reported individually — partial failures do not block successful sends.

    Args:
        params (SendBulkInput): Validated input containing:
            - to (list[str]): List of recipient phone numbers (max 100)
            - body (str): Message text

    Returns:
        str: JSON with per-recipient results including SIDs and any errors
    """
    async def _send_one(number: str) -> dict:
        try:
            msg = await twilio_client.send_message(to=number, body=params.body)
            return {"to": number, "success": True, "sid": msg["sid"], "status": msg["status"]}
        except Exception as e:
            return {"to": number, "success": False, "error": twilio_client.handle_error(e)}

    results = await asyncio.gather(*[_send_one(n) for n in params.to])
    succeeded = sum(1 for r in results if r["success"])
    return json.dumps({
        "total": len(params.to),
        "succeeded": succeeded,
        "failed": len(params.to) - succeeded,
        "results": list(results),
    }, indent=2)


@mcp.tool(
    name="sms_schedule",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def sms_schedule(params: ScheduleInput) -> str:
    """Schedule an SMS for future delivery at a specific date and time.

    Requires TWILIO_MESSAGING_SERVICE_SID to be configured.
    The scheduled time must be at least 15 minutes in the future.
    Use sms_cancel_scheduled to cancel before delivery.

    Args:
        params (ScheduleInput): Validated input containing:
            - to (str): Recipient phone number in E.164 format
            - body (str): Message text
            - send_at (str): ISO 8601 datetime e.g. '2025-12-01T09:00:00Z'

    Returns:
        str: JSON with message SID and scheduled time
    """
    try:
        msg = await twilio_client.send_message(
            to=params.to,
            body=params.body,
            schedule_time=params.send_at,
        )
        return json.dumps({
            "success": True,
            "sid": msg["sid"],
            "status": msg["status"],
            "scheduled_for": params.send_at,
            "to": msg["to"],
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_cancel_scheduled",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def sms_cancel_scheduled(params: SidInput) -> str:
    """Cancel a scheduled SMS before it is delivered.

    Only messages with status 'scheduled' can be cancelled.
    Once a message has status 'queued' or 'sent', it cannot be cancelled.

    Args:
        params (SidInput): Validated input containing:
            - sid (str): Message SID starting with 'SM'

    Returns:
        str: JSON confirming cancellation or explaining why it failed
    """
    try:
        msg = await twilio_client.cancel_message(params.sid)
        return json.dumps({"success": True, "sid": msg["sid"], "status": msg["status"]}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_list_sent",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def sms_list_sent(params: ListSentInput) -> str:
    """List outbound SMS messages from your Twilio account.

    Retrieves messages from the Twilio API with optional filtering by
    recipient or sender number. Results are ordered newest first.

    Args:
        params (ListSentInput): Validated input containing:
            - to (Optional[str]): Filter by recipient number
            - from (Optional[str]): Filter by sender number
            - limit (int): Number of messages (1–100, default 20)

    Returns:
        str: JSON array of message objects with SID, status, body, and timestamps
    """
    try:
        msgs = await twilio_client.list_messages(
            to=params.to,
            from_=params.from_,
            limit=params.limit,
        )
        return json.dumps({"count": len(msgs), "messages": msgs}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_get_message",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def sms_get_message(params: SidInput) -> str:
    """Fetch full details of a single message by its Twilio SID.

    Returns complete message data including delivery status, error codes,
    pricing, and media information.

    Args:
        params (SidInput): Validated input containing:
            - sid (str): Message SID starting with 'SM'

    Returns:
        str: JSON with complete message details
    """
    try:
        msg = await twilio_client.fetch_message(params.sid)
        return json.dumps(msg, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_delete_message",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def sms_delete_message(params: SidInput) -> str:
    """Delete a message record from Twilio's servers.

    This removes the message from Twilio's logs — it does NOT unsend
    a message that has already been delivered to the recipient.

    Args:
        params (SidInput): Validated input containing:
            - sid (str): Message SID starting with 'SM'

    Returns:
        str: JSON confirming deletion
    """
    try:
        await twilio_client.delete_message(params.sid)
        return json.dumps({"success": True, "sid": params.sid, "deleted": True}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_list_inbox",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def sms_list_inbox(params: ListInboxInput) -> str:
    """List inbound SMS messages received at your Twilio number.

    Messages are stored locally when Twilio calls your webhook endpoint.
    Requires the webhook server to be running and configured in Twilio Console.

    Args:
        params (ListInboxInput): Validated input containing:
            - from_number (Optional[str]): Filter by sender number
            - unread_only (bool): Only return unread messages (default false)
            - limit (int): Max messages to return (1–100, default 20)
            - offset (int): Pagination offset (default 0)

    Returns:
        str: JSON with unread count, messages list, and pagination info
    """
    msgs = store.get_inbox(
        from_number=params.from_number,
        unread_only=params.unread_only,
        limit=params.limit,
        offset=params.offset,
    )
    unread_count = store.count_unread()
    return json.dumps({
        "unread_total": unread_count,
        "count": len(msgs),
        "offset": params.offset,
        "has_more": len(msgs) == params.limit,
        "messages": msgs,
    }, indent=2)


@mcp.tool(
    name="sms_get_conversation",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def sms_get_conversation(params: ConversationInput) -> str:
    """Get the full message thread with a specific phone number.

    Returns all received messages to/from that number in chronological
    order from the local inbox store. Useful for reading conversation context.

    Args:
        params (ConversationInput): Validated input containing:
            - number (str): Phone number in E.164 format
            - limit (int): Max messages to return (1–200, default 50)

    Returns:
        str: JSON with ordered message thread
    """
    msgs = store.get_conversation(number=params.number, limit=params.limit)
    return json.dumps({
        "number": params.number,
        "count": len(msgs),
        "messages": msgs,
    }, indent=2)


@mcp.tool(
    name="sms_mark_read",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def sms_mark_read(params: MarkReadInput) -> str:
    """Mark inbox messages as read.

    Pass a specific SID to mark one message, a from_number to mark all
    from that sender, or omit both to mark everything as read.

    Args:
        params (MarkReadInput): Validated input containing:
            - sid (Optional[str]): Specific message SID to mark
            - from_number (Optional[str]): Mark all from this number

    Returns:
        str: JSON confirming how many messages were marked
    """
    if params.sid:
        store.mark_read(params.sid)
        return json.dumps({"success": True, "marked": 1, "sid": params.sid})
    else:
        count = store.mark_all_read(from_number=params.from_number)
        return json.dumps({"success": True, "marked": count})


@mcp.tool(
    name="sms_list_numbers",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def sms_list_numbers() -> str:
    """List all Twilio phone numbers on your account.

    Returns each number's SMS/MMS/Voice capabilities and current
    webhook configuration.

    Returns:
        str: JSON array of phone number objects
    """
    try:
        numbers = await twilio_client.list_phone_numbers()
        return json.dumps({"count": len(numbers), "numbers": numbers}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_lookup_number",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def sms_lookup_number(params: LookupInput) -> str:
    """Look up carrier and line-type information for a phone number.

    Validates whether a number is mobile (can receive SMS), landline,
    or VoIP. Useful before sending to avoid charges on undeliverable numbers.

    Args:
        params (LookupInput): Validated input containing:
            - phone_number (str): Number to look up in E.164 format

    Returns:
        str: JSON with country, carrier, line type, and validity information
    """
    try:
        result = await twilio_client.lookup_number(params.phone_number)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


@mcp.tool(
    name="sms_account_info",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def sms_account_info() -> str:
    """Get Twilio account balance and status.

    Returns current credit balance, currency, and account status.
    Useful for monitoring spend and ensuring the account is active.

    Returns:
        str: JSON with account SID, balance, currency, and status
    """
    try:
        info = await twilio_client.get_account_info()
        return json.dumps(info, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": twilio_client.handle_error(e)})


# ── Entry points ──────────────────────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
