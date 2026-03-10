"""Comprehensive tests for all 16 MCP tools with mocked Twilio API."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(
    sid: str = "SM" + "a" * 32,
    to: str = "+12025559999",
    from_: str = "+12025550100",
    body: str = "hello",
    status: str = "queued",
    direction: str = "outbound-api",
    num_segments: str = "1",
    num_media: str = "0",
    price: str | None = None,
    price_unit: str = "USD",
    date_created: str = "2025-01-01T00:00:00+00:00",
    date_sent: str | None = None,
    date_updated: str | None = None,
    error_code: int | None = None,
    error_message: str | None = None,
    uri: str = "/2010-04-01/Accounts/AC/Messages/SM.json",
) -> SimpleNamespace:
    return SimpleNamespace(
        sid=sid,
        to=to,
        from_=from_,
        body=body,
        status=status,
        direction=direction,
        num_segments=num_segments,
        num_media=num_media,
        price=price,
        price_unit=price_unit,
        date_created=date_created,
        date_sent=date_sent,
        date_updated=date_updated,
        error_code=error_code,
        error_message=error_message,
        uri=uri,
    )


def _parse(result) -> dict[str, Any]:
    """Extract JSON payload from an MCP tool call result."""
    return json.loads(result.content[0].text)


def _twilio_error(code: int = 20003, status: int = 401, msg: str = "Auth failed"):
    from twilio.base.exceptions import TwilioRestException
    return TwilioRestException(status=status, uri="/test", msg=msg, code=code)


# ===========================================================================
# 1. sms_send
# ===========================================================================


class TestSmsSend:
    """Tests for the sms_send tool."""

    @patch("twilio_sms_mcp.client.send_message", new_callable=AsyncMock)
    async def test_send_success(self, mock_send):
        from twilio_sms_mcp.server import mcp

        mock_send.return_value = {
            "sid": "SM" + "a" * 32,
            "to": "+12025559999",
            "from": "+12025550100",
            "status": "queued",
            "num_segments": "1",
            "date_created": "2025-01-01T00:00:00+00:00",
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_send", {
                "params": {"to": "+12025559999", "body": "Hello World"}
            })

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["sid"] == "SM" + "a" * 32
        mock_send.assert_called_once_with(to="+12025559999", body="Hello World", media_url=None)

    @patch("twilio_sms_mcp.client.send_message", new_callable=AsyncMock)
    async def test_send_with_media(self, mock_send):
        from twilio_sms_mcp.server import mcp

        mock_send.return_value = {
            "sid": "SM" + "b" * 32,
            "to": "+12025559999",
            "from": "+12025550100",
            "status": "queued",
            "num_segments": "1",
            "date_created": "2025-01-01T00:00:00+00:00",
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_send", {
                "params": {
                    "to": "+12025559999",
                    "body": "Check this out",
                    "media_urls": ["https://example.com/image.png"],
                }
            })

        payload = _parse(result)
        assert payload["success"] is True
        mock_send.assert_called_once_with(
            to="+12025559999",
            body="Check this out",
            media_url=["https://example.com/image.png"],
        )

    @patch("twilio_sms_mcp.client.send_message", new_callable=AsyncMock)
    async def test_send_twilio_error(self, mock_send):
        from twilio_sms_mcp.server import mcp

        mock_send.side_effect = _twilio_error(21211, 400, "Invalid number")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_send", {
                "params": {"to": "+12025559999", "body": "Hi"}
            })

        payload = _parse(result)
        assert payload["success"] is False
        assert "Invalid" in payload["error"]

    async def test_send_invalid_phone_number(self):
        from twilio_sms_mcp.server import mcp

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_send", {
                    "params": {"to": "not-a-number", "body": "Hi"}
                })

    async def test_send_empty_body(self):
        from twilio_sms_mcp.server import mcp

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_send", {
                    "params": {"to": "+12025559999", "body": ""}
                })


# ===========================================================================
# 2. sms_send_bulk
# ===========================================================================


class TestSmsSendBulk:
    """Tests for the sms_send_bulk tool."""

    @patch("twilio_sms_mcp.client.send_message", new_callable=AsyncMock)
    async def test_bulk_send_all_success(self, mock_send):
        from twilio_sms_mcp.server import mcp

        mock_send.side_effect = [
            {"sid": f"SM{'c' * 32}", "to": "+12025559901", "from": "+12025550100", "status": "queued"},
            {"sid": f"SM{'d' * 32}", "to": "+12025559902", "from": "+12025550100", "status": "queued"},
        ]

        async with Client(mcp) as client:
            result = await client.call_tool("sms_send_bulk", {
                "params": {
                    "to": ["+12025559901", "+12025559902"],
                    "body": "Bulk message",
                }
            })

        payload = _parse(result)
        assert payload["total"] == 2
        assert payload["succeeded"] == 2
        assert payload["failed"] == 0

    @patch("twilio_sms_mcp.client.send_message", new_callable=AsyncMock)
    async def test_bulk_send_partial_failure(self, mock_send):
        from twilio_sms_mcp.server import mcp

        mock_send.side_effect = [
            {"sid": f"SM{'e' * 32}", "to": "+12025559901", "from": "+12025550100", "status": "queued"},
            _twilio_error(21211, 400, "Invalid number"),
        ]

        async with Client(mcp) as client:
            result = await client.call_tool("sms_send_bulk", {
                "params": {
                    "to": ["+12025559901", "+12025559902"],
                    "body": "Bulk message",
                }
            })

        payload = _parse(result)
        assert payload["succeeded"] == 1
        assert payload["failed"] == 1

    async def test_bulk_send_duplicate_recipients(self):
        from twilio_sms_mcp.server import mcp

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_send_bulk", {
                    "params": {
                        "to": ["+12025559901", "+12025559901"],
                        "body": "Dup",
                    }
                })


# ===========================================================================
# 3. sms_schedule
# ===========================================================================


class TestSmsSchedule:
    """Tests for the sms_schedule tool."""

    @patch("twilio_sms_mcp.client.send_message", new_callable=AsyncMock)
    async def test_schedule_success(self, mock_send):
        from twilio_sms_mcp.server import mcp

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_send.return_value = {
            "sid": f"SM{'f' * 32}",
            "to": "+12025559999",
            "from": "+12025550100",
            "status": "scheduled",
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_schedule", {
                "params": {
                    "to": "+12025559999",
                    "body": "Scheduled msg",
                    "send_at": future.isoformat(),
                }
            })

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["status"] == "scheduled"

    async def test_schedule_too_soon(self):
        from twilio_sms_mcp.server import mcp

        too_soon = datetime.now(timezone.utc) + timedelta(minutes=5)

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_schedule", {
                    "params": {
                        "to": "+12025559999",
                        "body": "Too soon",
                        "send_at": too_soon.isoformat(),
                    }
                })

    async def test_schedule_too_far(self):
        from twilio_sms_mcp.server import mcp

        too_far = datetime.now(timezone.utc) + timedelta(days=40)

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_schedule", {
                    "params": {
                        "to": "+12025559999",
                        "body": "Too far",
                        "send_at": too_far.isoformat(),
                    }
                })

    async def test_schedule_no_timezone(self):
        from twilio_sms_mcp.server import mcp

        naive = datetime.now() + timedelta(hours=1)

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_schedule", {
                    "params": {
                        "to": "+12025559999",
                        "body": "Naive dt",
                        "send_at": naive.isoformat(),
                    }
                })

    @patch("twilio_sms_mcp.client.send_message", new_callable=AsyncMock)
    async def test_schedule_twilio_error(self, mock_send):
        from twilio_sms_mcp.server import mcp

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_send.side_effect = ValueError("Scheduling requires TWILIO_MESSAGING_SERVICE_SID to be set.")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_schedule", {
                "params": {
                    "to": "+12025559999",
                    "body": "No service sid",
                    "send_at": future.isoformat(),
                }
            })

        payload = _parse(result)
        assert payload["success"] is False
        assert "MESSAGING_SERVICE" in payload["error"].upper() or "Scheduling" in payload["error"]


# ===========================================================================
# 4. sms_cancel_scheduled
# ===========================================================================


class TestSmsCancelScheduled:
    """Tests for the sms_cancel_scheduled tool."""

    @patch("twilio_sms_mcp.client.cancel_message", new_callable=AsyncMock)
    async def test_cancel_success(self, mock_cancel):
        from twilio_sms_mcp.server import mcp

        sid = f"SM{'1' * 32}"
        mock_cancel.return_value = {"sid": sid, "status": "canceled"}

        async with Client(mcp) as client:
            result = await client.call_tool("sms_cancel_scheduled", {
                "params": {"sid": sid}
            })

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["status"] == "canceled"

    @patch("twilio_sms_mcp.client.cancel_message", new_callable=AsyncMock)
    async def test_cancel_error(self, mock_cancel):
        from twilio_sms_mcp.server import mcp

        mock_cancel.side_effect = _twilio_error(20404, 404, "Not found")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_cancel_scheduled", {
                "params": {"sid": f"SM{'2' * 32}"}
            })

        payload = _parse(result)
        assert payload["success"] is False

    async def test_cancel_invalid_sid(self):
        from twilio_sms_mcp.server import mcp

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_cancel_scheduled", {
                    "params": {"sid": "INVALID_SID"}
                })


# ===========================================================================
# 5. sms_list_sent
# ===========================================================================


class TestSmsListSent:
    """Tests for the sms_list_sent tool."""

    @patch("twilio_sms_mcp.client.list_sent_messages", new_callable=AsyncMock)
    async def test_list_sent_success(self, mock_list):
        from twilio_sms_mcp.server import mcp

        mock_list.return_value = [
            {"sid": f"SM{'3' * 32}", "to": "+12025559999", "status": "delivered", "direction": "outbound-api"},
        ]

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_sent", {
                "params": {"limit": 10}
            })

        payload = _parse(result)
        assert payload["count"] == 1
        assert payload["messages"][0]["status"] == "delivered"

    @patch("twilio_sms_mcp.client.list_sent_messages", new_callable=AsyncMock)
    async def test_list_sent_with_filters(self, mock_list):
        from twilio_sms_mcp.server import mcp

        mock_list.return_value = []

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_sent", {
                "params": {"to": "+12025559999", "from": "+12025550100", "limit": 5}
            })

        payload = _parse(result)
        assert payload["count"] == 0
        mock_list.assert_called_once_with(to="+12025559999", from_="+12025550100", limit=5)

    @patch("twilio_sms_mcp.client.list_sent_messages", new_callable=AsyncMock)
    async def test_list_sent_error(self, mock_list):
        from twilio_sms_mcp.server import mcp

        mock_list.side_effect = _twilio_error(20003, 401, "Auth failed")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_sent", {
                "params": {"limit": 10}
            })

        payload = _parse(result)
        assert payload["success"] is False
        assert "Authentication" in payload["error"] or "Auth" in payload["error"]


# ===========================================================================
# 6. sms_get_message
# ===========================================================================


class TestSmsGetMessage:
    """Tests for the sms_get_message tool."""

    @patch("twilio_sms_mcp.client.fetch_message", new_callable=AsyncMock)
    async def test_get_message_success(self, mock_fetch):
        from twilio_sms_mcp.server import mcp

        sid = f"SM{'4' * 32}"
        mock_fetch.return_value = {
            "sid": sid,
            "to": "+12025559999",
            "from": "+12025550100",
            "body": "Test message",
            "status": "delivered",
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_get_message", {
                "params": {"sid": sid}
            })

        payload = _parse(result)
        assert payload["sid"] == sid
        assert payload["body"] == "Test message"

    @patch("twilio_sms_mcp.client.fetch_message", new_callable=AsyncMock)
    async def test_get_message_with_delivery_status(self, mock_fetch):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        sid = f"SM{'5' * 32}"
        store.init_db()
        store.update_delivery_status({
            "MessageSid": sid,
            "MessageStatus": "delivered",
            "ErrorCode": "",
        })

        mock_fetch.return_value = {
            "sid": sid,
            "to": "+12025559999",
            "from": "+12025550100",
            "body": "Tracked msg",
            "status": "delivered",
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_get_message", {
                "params": {"sid": sid}
            })

        payload = _parse(result)
        assert payload["sid"] == sid
        assert payload["latest_delivery_status"]["status"] == "delivered"

    @patch("twilio_sms_mcp.client.fetch_message", new_callable=AsyncMock)
    async def test_get_message_not_found(self, mock_fetch):
        from twilio_sms_mcp.server import mcp

        mock_fetch.side_effect = _twilio_error(20404, 404, "Not found")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_get_message", {
                "params": {"sid": f"SM{'6' * 32}"}
            })

        payload = _parse(result)
        assert payload["success"] is False


# ===========================================================================
# 7. sms_delete_message
# ===========================================================================


class TestSmsDeleteMessage:
    """Tests for the sms_delete_message tool."""

    @patch("twilio_sms_mcp.client.delete_message", new_callable=AsyncMock)
    async def test_delete_success(self, mock_delete):
        from twilio_sms_mcp.server import mcp

        sid = f"SM{'7' * 32}"
        mock_delete.return_value = True

        async with Client(mcp) as client:
            result = await client.call_tool("sms_delete_message", {
                "params": {"sid": sid}
            })

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["deleted"] is True

    @patch("twilio_sms_mcp.client.delete_message", new_callable=AsyncMock)
    async def test_delete_error(self, mock_delete):
        from twilio_sms_mcp.server import mcp

        mock_delete.side_effect = _twilio_error(20404, 404, "Not found")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_delete_message", {
                "params": {"sid": f"SM{'8' * 32}"}
            })

        payload = _parse(result)
        assert payload["success"] is False


# ===========================================================================
# 8. sms_redact_message
# ===========================================================================


class TestSmsRedactMessage:
    """Tests for the sms_redact_message tool."""

    @patch("twilio_sms_mcp.client.redact_message", new_callable=AsyncMock)
    async def test_redact_success(self, mock_redact):
        from twilio_sms_mcp.server import mcp

        sid = f"SM{'9' * 32}"
        mock_redact.return_value = {"sid": sid, "body": "", "status": "delivered"}

        async with Client(mcp) as client:
            result = await client.call_tool("sms_redact_message", {
                "params": {"sid": sid}
            })

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["body"] == ""

    @patch("twilio_sms_mcp.client.redact_message", new_callable=AsyncMock)
    async def test_redact_error(self, mock_redact):
        from twilio_sms_mcp.server import mcp

        mock_redact.side_effect = _twilio_error(20404, 404, "Message not found")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_redact_message", {
                "params": {"sid": f"SM{'0' * 32}"}
            })

        payload = _parse(result)
        assert payload["success"] is False


# ===========================================================================
# 9. sms_list_inbox
# ===========================================================================


class TestSmsListInbox:
    """Tests for the sms_list_inbox tool."""

    async def test_list_inbox_default(self):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        store.store_inbound({
            "MessageSid": f"SM{'aa' * 16}",
            "From": "+12025550111",
            "To": "+12025550100",
            "Body": "Inbox test",
            "NumMedia": "0",
        })

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_inbox", {"params": {}})

        payload = _parse(result)
        assert payload["count"] == 1
        assert payload["unread_total"] == 1
        assert payload["messages"][0]["body"] == "Inbox test"

    async def test_list_inbox_filtered_by_sender(self):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        store.store_inbound({
            "MessageSid": f"SM{'bb' * 16}",
            "From": "+12025550111",
            "To": "+12025550100",
            "Body": "From 111",
            "NumMedia": "0",
        })
        store.store_inbound({
            "MessageSid": f"SM{'cc' * 16}",
            "From": "+12025550222",
            "To": "+12025550100",
            "Body": "From 222",
            "NumMedia": "0",
        })

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_inbox", {
                "params": {"from_number": "+12025550111"}
            })

        payload = _parse(result)
        assert payload["count"] == 1
        assert payload["messages"][0]["body"] == "From 111"

    async def test_list_inbox_unread_only(self):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        sid1 = f"SM{'dd' * 16}"
        store.store_inbound({
            "MessageSid": sid1,
            "From": "+12025550111",
            "To": "+12025550100",
            "Body": "Read msg",
            "NumMedia": "0",
        })
        store.store_inbound({
            "MessageSid": f"SM{'ee' * 16}",
            "From": "+12025550111",
            "To": "+12025550100",
            "Body": "Unread msg",
            "NumMedia": "0",
        })
        store.mark_read(sid1)

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_inbox", {
                "params": {"unread_only": True}
            })

        payload = _parse(result)
        assert payload["count"] == 1
        assert payload["messages"][0]["body"] == "Unread msg"

    async def test_list_inbox_pagination(self):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        for i in range(5):
            store.store_inbound({
                "MessageSid": f"SM{str(i) * 32}",
                "From": "+12025550111",
                "To": "+12025550100",
                "Body": f"Msg {i}",
                "NumMedia": "0",
            })

        async with Client(mcp) as client:
            r1 = await client.call_tool("sms_list_inbox", {"params": {"limit": 2, "offset": 0}})
            r2 = await client.call_tool("sms_list_inbox", {"params": {"limit": 2, "offset": 2}})

        p1 = _parse(r1)
        p2 = _parse(r2)
        assert p1["count"] == 2
        assert p2["count"] == 2
        assert p1["has_more"] is True
        sids1 = {m["sid"] for m in p1["messages"]}
        sids2 = {m["sid"] for m in p2["messages"]}
        assert sids1.isdisjoint(sids2)


# ===========================================================================
# 10. sms_get_conversation
# ===========================================================================


class TestSmsGetConversation:
    """Tests for the sms_get_conversation tool."""

    @patch("twilio_sms_mcp.client.list_conversation", new_callable=AsyncMock)
    async def test_conversation_merges_local_and_remote(self, mock_conv):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        store.store_inbound({
            "MessageSid": f"SM{'f1' * 16}",
            "From": "+12025550333",
            "To": "+12025550100",
            "Body": "local inbound",
            "NumMedia": "0",
        })

        mock_conv.return_value = [
            {
                "sid": f"SM{'f2' * 16}",
                "to": "+12025550333",
                "from": "+12025550100",
                "body": "remote outbound",
                "status": "delivered",
                "direction": "outbound-api",
                "date_sent": "2025-01-01T12:00:00+00:00",
            },
        ]

        async with Client(mcp) as client:
            result = await client.call_tool("sms_get_conversation", {
                "params": {"number": "+12025550333"}
            })

        payload = _parse(result)
        assert payload["count"] == 2

    @patch("twilio_sms_mcp.client.list_conversation", new_callable=AsyncMock)
    async def test_conversation_remote_error_fallback(self, mock_conv):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        store.store_inbound({
            "MessageSid": f"SM{'f3' * 16}",
            "From": "+12025550444",
            "To": "+12025550100",
            "Body": "local only",
            "NumMedia": "0",
        })

        mock_conv.side_effect = _twilio_error(20003, 401, "Auth")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_get_conversation", {
                "params": {"number": "+12025550444"}
            })

        payload = _parse(result)
        assert payload["count"] >= 1
        assert "warning" in payload

    @patch("twilio_sms_mcp.client.list_conversation", new_callable=AsyncMock)
    async def test_conversation_empty(self, mock_conv):
        from twilio_sms_mcp.server import mcp

        mock_conv.return_value = []

        async with Client(mcp) as client:
            result = await client.call_tool("sms_get_conversation", {
                "params": {"number": "+12025550555"}
            })

        payload = _parse(result)
        assert payload["count"] == 0


# ===========================================================================
# 11. sms_mark_read
# ===========================================================================


class TestSmsMarkRead:
    """Tests for the sms_mark_read tool."""

    async def test_mark_read_by_sid(self):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        sid = f"SM{'11' * 16}"
        store.store_inbound({
            "MessageSid": sid,
            "From": "+12025550111",
            "To": "+12025550100",
            "Body": "Mark me",
            "NumMedia": "0",
        })
        assert store.count_unread() == 1

        async with Client(mcp) as client:
            result = await client.call_tool("sms_mark_read", {
                "params": {"sid": sid}
            })

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["marked"] == 1
        assert store.count_unread() == 0

    async def test_mark_read_by_from_number(self):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        for i in range(3):
            store.store_inbound({
                "MessageSid": f"SM{str(i + 20) * 16}{str(i + 20) * 16}",
                "From": "+12025550666",
                "To": "+12025550100",
                "Body": f"msg {i}",
                "NumMedia": "0",
            })
        assert store.count_unread() == 3

        async with Client(mcp) as client:
            result = await client.call_tool("sms_mark_read", {
                "params": {"from_number": "+12025550666"}
            })

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["marked"] == 3

    async def test_mark_all_read(self):
        from twilio_sms_mcp import store
        from twilio_sms_mcp.server import mcp

        store.init_db()
        for i in range(2):
            store.store_inbound({
                "MessageSid": f"SM{str(i + 30) * 16}{str(i + 30) * 16}",
                "From": "+12025550777",
                "To": "+12025550100",
                "Body": f"all {i}",
                "NumMedia": "0",
            })

        async with Client(mcp) as client:
            result = await client.call_tool("sms_mark_read", {"params": {}})

        payload = _parse(result)
        assert payload["success"] is True
        assert payload["marked"] == 2

    async def test_mark_read_both_sid_and_from_rejects(self):
        from twilio_sms_mcp.server import mcp

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("sms_mark_read", {
                    "params": {
                        "sid": f"SM{'a' * 32}",
                        "from_number": "+12025550100",
                    }
                })


# ===========================================================================
# 12. sms_list_numbers
# ===========================================================================


class TestSmsListNumbers:
    """Tests for the sms_list_numbers tool."""

    @patch("twilio_sms_mcp.client.list_phone_numbers", new_callable=AsyncMock)
    async def test_list_numbers_success(self, mock_list):
        from twilio_sms_mcp.server import mcp

        mock_list.return_value = [
            {
                "sid": "PN" + "1" * 32,
                "phone_number": "+12025550100",
                "friendly_name": "Main Line",
                "capabilities": {"sms": True, "mms": True, "voice": True},
                "sms_url": "https://example.com/sms",
                "status_callback": None,
                "date_created": "2025-01-01",
            }
        ]

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_numbers", {})

        payload = _parse(result)
        assert payload["count"] == 1
        assert payload["numbers"][0]["phone_number"] == "+12025550100"

    @patch("twilio_sms_mcp.client.list_phone_numbers", new_callable=AsyncMock)
    async def test_list_numbers_error(self, mock_list):
        from twilio_sms_mcp.server import mcp

        mock_list.side_effect = _twilio_error(20003, 401, "Auth failed")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_list_numbers", {})

        payload = _parse(result)
        assert payload["success"] is False


# ===========================================================================
# 13. sms_lookup_number
# ===========================================================================


class TestSmsLookupNumber:
    """Tests for the sms_lookup_number tool."""

    @patch("twilio_sms_mcp.client.lookup_number", new_callable=AsyncMock)
    async def test_lookup_success(self, mock_lookup):
        from twilio_sms_mcp.server import mcp

        mock_lookup.return_value = {
            "phone_number": "+12025550123",
            "country_code": "US",
            "national_format": "(202) 555-0123",
            "valid": True,
            "line_type_intelligence": {"type": "mobile"},
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_lookup_number", {
                "params": {"phone_number": "+12025550123"}
            })

        payload = _parse(result)
        assert payload["valid"] is True
        assert payload["country_code"] == "US"

    @patch("twilio_sms_mcp.client.lookup_number", new_callable=AsyncMock)
    async def test_lookup_invalid_number(self, mock_lookup):
        from twilio_sms_mcp.server import mcp

        mock_lookup.side_effect = _twilio_error(20404, 404, "Number not valid")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_lookup_number", {
                "params": {"phone_number": "+10000000000"}
            })

        payload = _parse(result)
        assert payload["success"] is False


# ===========================================================================
# 14. sms_format_number
# ===========================================================================


class TestSmsFormatNumber:
    """Tests for the sms_format_number tool."""

    @patch("twilio_sms_mcp.client.format_number", new_callable=AsyncMock)
    async def test_format_success(self, mock_fmt):
        from twilio_sms_mcp.server import mcp

        mock_fmt.return_value = {
            "phone_number": "+12025550123",
            "country_code": "US",
            "national_format": "(202) 555-0123",
            "valid": True,
            "calling_country_code": "1",
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_format_number", {
                "params": {"phone_number": "2025550123"}
            })

        payload = _parse(result)
        assert payload["valid"] is True
        assert payload["phone_number"] == "+12025550123"

    @patch("twilio_sms_mcp.client.format_number", new_callable=AsyncMock)
    async def test_format_error(self, mock_fmt):
        from twilio_sms_mcp.server import mcp

        mock_fmt.side_effect = _twilio_error(20404, 404, "Not found")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_format_number", {
                "params": {"phone_number": "badnumber"}
            })

        payload = _parse(result)
        assert payload["success"] is False


# ===========================================================================
# 15. sms_usage_stats
# ===========================================================================


class TestSmsUsageStats:
    """Tests for the sms_usage_stats tool."""

    @patch("twilio_sms_mcp.client.get_usage_records", new_callable=AsyncMock)
    async def test_usage_stats_success(self, mock_usage):
        from twilio_sms_mcp.server import mcp

        mock_usage.return_value = [
            {
                "category": "sms",
                "start_date": "2025-01-01",
                "end_date": "2025-01-01",
                "count": "10",
                "count_unit": "messages",
                "price": "0.50",
                "price_unit": "USD",
                "usage": "10",
                "usage_unit": "messages",
            },
            {
                "category": "sms",
                "start_date": "2025-01-02",
                "end_date": "2025-01-02",
                "count": "5",
                "count_unit": "messages",
                "price": "0.25",
                "price_unit": "USD",
                "usage": "5",
                "usage_unit": "messages",
            },
        ]

        async with Client(mcp) as client:
            result = await client.call_tool("sms_usage_stats", {
                "params": {"category": "sms", "days": 7}
            })

        payload = _parse(result)
        assert payload["total_messages"] == 15
        assert payload["total_cost"] == "0.7500"
        assert len(payload["daily_records"]) == 2

    @patch("twilio_sms_mcp.client.get_usage_records", new_callable=AsyncMock)
    async def test_usage_stats_empty(self, mock_usage):
        from twilio_sms_mcp.server import mcp

        mock_usage.return_value = []

        async with Client(mcp) as client:
            result = await client.call_tool("sms_usage_stats", {
                "params": {"category": "mms", "days": 1}
            })

        payload = _parse(result)
        assert payload["total_messages"] == 0

    @patch("twilio_sms_mcp.client.get_usage_records", new_callable=AsyncMock)
    async def test_usage_stats_error(self, mock_usage):
        from twilio_sms_mcp.server import mcp

        mock_usage.side_effect = _twilio_error(20003, 401, "Auth failed")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_usage_stats", {
                "params": {}
            })

        payload = _parse(result)
        assert payload["success"] is False


# ===========================================================================
# 16. sms_account_info
# ===========================================================================


class TestSmsAccountInfo:
    """Tests for the sms_account_info tool."""

    @patch("twilio_sms_mcp.client.get_account_info", new_callable=AsyncMock)
    async def test_account_info_success(self, mock_info):
        from twilio_sms_mcp.server import mcp

        mock_info.return_value = {
            "account_sid": "AC" + "1" * 32,
            "friendly_name": "Test Account",
            "status": "active",
            "type": "Full",
            "balance": "100.00",
            "currency": "USD",
        }

        async with Client(mcp) as client:
            result = await client.call_tool("sms_account_info", {})

        payload = _parse(result)
        assert payload["account_sid"] == "AC" + "1" * 32
        assert payload["status"] == "active"
        assert payload["balance"] == "100.00"

    @patch("twilio_sms_mcp.client.get_account_info", new_callable=AsyncMock)
    async def test_account_info_error(self, mock_info):
        from twilio_sms_mcp.server import mcp

        mock_info.side_effect = _twilio_error(20003, 401, "Auth failed")

        async with Client(mcp) as client:
            result = await client.call_tool("sms_account_info", {})

        payload = _parse(result)
        assert payload["success"] is False
        assert "Authentication" in payload["error"]
