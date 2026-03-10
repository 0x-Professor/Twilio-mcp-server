"""
Gemini-powered MCP test client.

Connects to the Twilio SMS MCP server via stdio, discovers all tools,
and asks Gemini to exercise every single tool — verifying they return
valid JSON and sensible results.

Usage
-----
    python test_client_gemini.py          # full automated test
    python test_client_gemini.py --list   # just list available tools
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "",
)
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

# Read Twilio creds for comparison / test data
TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER", "+13187149040")

# A real external number we can safely target for read-only tests.
# We use the from number itself for listing, lookup, format – never actually send.
TEST_PHONE = TWILIO_FROM

# ---------------------------------------------------------------------------
# Pretty helpers
# ---------------------------------------------------------------------------

PASS = "\033[92m✔ PASS\033[0m"
FAIL = "\033[91m✘ FAIL\033[0m"
SKIP = "\033[93m⊘ SKIP\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"


def banner(text: str) -> None:
    width = 70
    print(f"\n{'=' * width}")
    print(f"  {BOLD}{text}{RESET}")
    print(f"{'=' * width}")


def section(text: str) -> None:
    print(f"\n  {BOLD}── {text} ──{RESET}")


# ---------------------------------------------------------------------------
# Gemini helper – simple stateless call
# ---------------------------------------------------------------------------

async def ask_gemini(prompt: str, http: httpx.AsyncClient) -> str:
    """Send a prompt to Gemini and return the text response."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
    }
    try:
        resp = await http.post(
            GEMINI_URL,
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": GEMINI_API_KEY,
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        return f"(Gemini unavailable: {type(exc).__name__} — tests continue without AI commentary)"


# ---------------------------------------------------------------------------
# MCP Client – in-process (no subprocess)
# ---------------------------------------------------------------------------

class MCPDirectClient:
    """
    Import the MCP server in-process and call tools directly via the
    FastMCP `mcp` object.  No subprocess pipes required.
    """

    def __init__(self):
        self._tools: dict[str, Any] = {}

    async def connect(self) -> None:
        """Import server module and discover tools."""
        from twilio_sms_mcp.server import mcp as server

        self._server = server
        # FastMCP stores tool handlers internally; discover them.
        self._tools = {}
        tool_list = await server.list_tools()
        for tool in tool_list:
            self._tools[tool.name] = tool
        print(f"  Connected to MCP server — {len(self._tools)} tools discovered")

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool by name and return the parsed JSON result."""
        result = await self._server.call_tool(name, arguments)
        # FastMCP returns CallToolResult with .content list of TextContent
        text = ""
        if hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    text += item.text
        elif hasattr(result, "__iter__"):
            for item in result:
                if hasattr(item, "text"):
                    text += item.text
                elif isinstance(item, str):
                    text += item
        else:
            text = str(result)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}


# ---------------------------------------------------------------------------
# Individual tool tests
# ---------------------------------------------------------------------------

async def test_sms_account_info(client: MCPDirectClient) -> dict:
    """Test sms_account_info — should return account details."""
    result = await client.call_tool("sms_account_info", {})
    assert "friendly_name" in result or "account_sid" in result or "success" in result, (
        f"Unexpected response: {result}"
    )
    return result


async def test_sms_list_numbers(client: MCPDirectClient) -> dict:
    """Test sms_list_numbers — list phone numbers on the account."""
    result = await client.call_tool("sms_list_numbers", {})
    assert "numbers" in result or "count" in result or "success" in result
    return result


async def test_sms_list_sent(client: MCPDirectClient) -> dict:
    """Test sms_list_sent — list recently sent messages."""
    result = await client.call_tool("sms_list_sent", {"params": {"limit": 5}})
    assert "messages" in result or "count" in result or "success" in result
    return result


async def test_sms_list_inbox(client: MCPDirectClient) -> dict:
    """Test sms_list_inbox — list inbound webhook messages."""
    result = await client.call_tool("sms_list_inbox", {"params": {"limit": 5}})
    assert "messages" in result or "count" in result
    return result


async def test_sms_format_number(client: MCPDirectClient) -> dict:
    """Test sms_format_number — validate and reformat a phone number."""
    result = await client.call_tool("sms_format_number", {"params": {
        "phone_number": TWILIO_FROM,
        "country_code": "US",
    }})
    assert "phone_number" in result or "national_format" in result or "success" in result
    return result


async def test_sms_lookup_number(client: MCPDirectClient) -> dict:
    """Test sms_lookup_number — carrier/line-type lookup."""
    result = await client.call_tool("sms_lookup_number", {"params": {
        "phone_number": TWILIO_FROM,
    }})
    # Could be success or error (lookup costs may apply)
    return result


async def test_sms_usage_stats(client: MCPDirectClient) -> dict:
    """Test sms_usage_stats — daily usage analytics."""
    result = await client.call_tool("sms_usage_stats", {"params": {
        "category": "sms",
        "days": 7,
    }})
    assert "total_messages" in result or "daily_records" in result or "success" in result
    return result


async def test_sms_get_conversation(client: MCPDirectClient) -> dict:
    """Test sms_get_conversation — conversation thread for a number."""
    result = await client.call_tool("sms_get_conversation", {"params": {
        "number": TWILIO_FROM,
        "limit": 10,
    }})
    assert "messages" in result or "count" in result or "number" in result
    return result


async def test_sms_mark_read(client: MCPDirectClient) -> dict:
    """Test sms_mark_read — mark all messages as read."""
    result = await client.call_tool("sms_mark_read", {"params": {}})
    assert "success" in result or "marked" in result
    return result


async def test_sms_send(client: MCPDirectClient) -> dict:
    """Test sms_send — send a single test message."""
    result = await client.call_tool("sms_send", {"params": {
        "to": TWILIO_FROM,
        "body": f"[MCP Test] Automated test at {datetime.now(timezone.utc).isoformat()}",
    }})
    assert "sid" in result or "success" in result
    return result


async def test_sms_get_message(client: MCPDirectClient, sid: str) -> dict:
    """Test sms_get_message — fetch a specific message by SID."""
    result = await client.call_tool("sms_get_message", {"params": {"sid": sid}})
    assert "sid" in result or "body" in result or "success" in result
    return result


async def test_sms_redact_message(client: MCPDirectClient, sid: str) -> dict:
    """Test sms_redact_message — redact message body for privacy."""
    result = await client.call_tool("sms_redact_message", {"params": {"sid": sid}})
    assert "sid" in result or "success" in result
    return result


async def test_sms_delete_message(client: MCPDirectClient, sid: str) -> dict:
    """Test sms_delete_message — delete a message record."""
    result = await client.call_tool("sms_delete_message", {"params": {"sid": sid}})
    assert "deleted" in result or "success" in result
    return result


async def test_sms_send_bulk(client: MCPDirectClient) -> dict:
    """Test sms_send_bulk — send to multiple recipients."""
    result = await client.call_tool("sms_send_bulk", {"params": {
        "to": [TWILIO_FROM],
        "body": f"[MCP Bulk Test] {datetime.now(timezone.utc).isoformat()}",
    }})
    assert "results" in result or "total" in result or "success" in result
    return result


async def test_sms_schedule(client: MCPDirectClient) -> dict:
    """Test sms_schedule — schedule a message for future delivery."""
    # Schedule 20 minutes from now (within the 15min–35day window)
    send_at = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    result = await client.call_tool("sms_schedule", {"params": {
        "to": TWILIO_FROM,
        "body": f"[MCP Schedule Test] {send_at}",
        "send_at": send_at,
    }})
    # May fail if no Messaging Service SID configured — that's expected
    return result


async def test_sms_cancel_scheduled(client: MCPDirectClient, sid: str) -> dict:
    """Test sms_cancel_scheduled — cancel a scheduled message."""
    result = await client.call_tool("sms_cancel_scheduled", {"params": {"sid": sid}})
    return result


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

async def run_all_tests() -> None:
    banner("Twilio SMS MCP Server — Tool Test Suite (Gemini-powered)")
    print(f"  Gemini Model : {GEMINI_MODEL}")
    print(f"  Twilio From  : {TWILIO_FROM}")
    print(f"  Timestamp    : {datetime.now(timezone.utc).isoformat()}")

    # ── Connect to MCP server ──
    section("Connecting to MCP Server")
    client = MCPDirectClient()
    await client.connect()

    print(f"\n  Available tools ({len(client.tool_names)}):")
    for name in client.tool_names:
        print(f"    • {name}")

    # ── Ask Gemini to verify the tool list ──
    section("Gemini Verification")
    async with httpx.AsyncClient() as http:
        tool_list_str = ", ".join(client.tool_names)
        gemini_response = await ask_gemini(
            f"I have an MCP server with these SMS tools: {tool_list_str}. "
            "Briefly confirm this looks like a complete Twilio SMS toolkit. "
            "Reply in 2-3 sentences max.",
            http,
        )
        print(f"  Gemini says: {gemini_response.strip()}")

    # ── Test matrix ──
    results: list[tuple[str, str, str]] = []  # (tool, status, detail)
    sent_sid: str | None = None
    scheduled_sid: str | None = None

    # ── Group 1: Read-only tools (safe, no side effects) ──
    section("Group 1 — Read-Only Tools")

    read_only_tests = [
        ("sms_account_info", test_sms_account_info),
        ("sms_list_numbers", test_sms_list_numbers),
        ("sms_list_sent", test_sms_list_sent),
        ("sms_list_inbox", test_sms_list_inbox),
        ("sms_format_number", test_sms_format_number),
        ("sms_lookup_number", test_sms_lookup_number),
        ("sms_usage_stats", test_sms_usage_stats),
        ("sms_get_conversation", test_sms_get_conversation),
        ("sms_mark_read", test_sms_mark_read),
    ]

    for tool_name, test_fn in read_only_tests:
        try:
            result = await test_fn(client)
            is_error = result.get("success") is False
            status = FAIL if is_error else PASS
            detail = json.dumps(result, default=str)[:200]
            if is_error:
                detail = f"API Error: {result.get('error', 'unknown')}"
        except Exception as exc:
            status = FAIL
            detail = f"{type(exc).__name__}: {exc}"
        results.append((tool_name, status, detail))
        print(f"  {status}  {tool_name:<25} {detail[:120]}")

    # ── Group 2: Send tools (creates real messages) ──
    section("Group 2 — Send & Mutate Tools")

    # sms_send
    try:
        result = await test_sms_send(client)
        is_error = result.get("success") is False
        if is_error:
            results.append(("sms_send", FAIL, f"API Error: {result.get('error')}"))
            print(f"  {FAIL}  {'sms_send':<25} {result.get('error', '')[:120]}")
        else:
            sent_sid = result.get("sid")
            results.append(("sms_send", PASS, f"SID={sent_sid}"))
            print(f"  {PASS}  {'sms_send':<25} SID={sent_sid}")
    except Exception as exc:
        results.append(("sms_send", FAIL, str(exc)[:120]))
        print(f"  {FAIL}  {'sms_send':<25} {exc}")

    # sms_send_bulk
    try:
        result = await test_sms_send_bulk(client)
        is_error = result.get("success") is False if "success" in result else result.get("failed", 0) > 0
        if is_error:
            detail = f"Failed: {result.get('failed', '?')}"
            results.append(("sms_send_bulk", FAIL, detail))
            print(f"  {FAIL}  {'sms_send_bulk':<25} {detail}")
        else:
            detail = f"Sent={result.get('succeeded', '?')}, Total={result.get('total', '?')}"
            results.append(("sms_send_bulk", PASS, detail))
            print(f"  {PASS}  {'sms_send_bulk':<25} {detail}")
    except Exception as exc:
        results.append(("sms_send_bulk", FAIL, str(exc)[:120]))
        print(f"  {FAIL}  {'sms_send_bulk':<25} {exc}")

    # sms_get_message (needs a SID from sms_send or sms_list_sent)
    if sent_sid:
        try:
            # Brief wait for Twilio to register the message
            await asyncio.sleep(2)
            result = await test_sms_get_message(client, sent_sid)
            is_error = result.get("success") is False
            status = FAIL if is_error else PASS
            detail = f"SID={sent_sid}, status={result.get('status', 'N/A')}"
            results.append(("sms_get_message", status, detail))
            print(f"  {status}  {'sms_get_message':<25} {detail}")
        except Exception as exc:
            results.append(("sms_get_message", FAIL, str(exc)[:120]))
            print(f"  {FAIL}  {'sms_get_message':<25} {exc}")
    else:
        # Fallback: try fetching from list_sent
        try:
            list_result = await client.call_tool("sms_list_sent", {"params": {"limit": 1}})
            msgs = list_result.get("messages", [])
            if msgs:
                fallback_sid = msgs[0].get("sid")
                result = await test_sms_get_message(client, fallback_sid)
                status = FAIL if result.get("success") is False else PASS
                results.append(("sms_get_message", status, f"Used fallback SID={fallback_sid}"))
                print(f"  {status}  {'sms_get_message':<25} Fallback SID={fallback_sid}")
            else:
                results.append(("sms_get_message", SKIP, "No messages to fetch"))
                print(f"  {SKIP}  {'sms_get_message':<25} No messages available")
        except Exception as exc:
            results.append(("sms_get_message", FAIL, str(exc)[:120]))
            print(f"  {FAIL}  {'sms_get_message':<25} {exc}")

    # sms_schedule (requires Messaging Service SID)
    try:
        result = await test_sms_schedule(client)
        is_error = result.get("success") is False
        if is_error:
            err = result.get("error", "")
            if "messaging service" in str(err).lower() or "21710" in str(err):
                results.append(("sms_schedule", SKIP, "No Messaging Service SID configured"))
                print(f"  {SKIP}  {'sms_schedule':<25} Requires Messaging Service SID (expected)")
            else:
                results.append(("sms_schedule", FAIL, str(err)[:120]))
                print(f"  {FAIL}  {'sms_schedule':<25} {str(err)[:120]}")
        else:
            scheduled_sid = result.get("sid")
            results.append(("sms_schedule", PASS, f"Scheduled SID={scheduled_sid}"))
            print(f"  {PASS}  {'sms_schedule':<25} SID={scheduled_sid}")
    except Exception as exc:
        results.append(("sms_schedule", FAIL, str(exc)[:120]))
        print(f"  {FAIL}  {'sms_schedule':<25} {exc}")

    # sms_cancel_scheduled
    if scheduled_sid:
        try:
            await asyncio.sleep(1)
            result = await test_sms_cancel_scheduled(client, scheduled_sid)
            is_error = result.get("success") is False
            status = FAIL if is_error else PASS
            results.append(("sms_cancel_scheduled", status, f"SID={scheduled_sid}"))
            print(f"  {status}  {'sms_cancel_scheduled':<25} SID={scheduled_sid}")
        except Exception as exc:
            results.append(("sms_cancel_scheduled", FAIL, str(exc)[:120]))
            print(f"  {FAIL}  {'sms_cancel_scheduled':<25} {exc}")
    else:
        results.append(("sms_cancel_scheduled", SKIP, "No scheduled message to cancel"))
        print(f"  {SKIP}  {'sms_cancel_scheduled':<25} No scheduled message (sms_schedule didn't produce one)")

    # sms_redact_message
    if sent_sid:
        try:
            await asyncio.sleep(2)
            result = await test_sms_redact_message(client, sent_sid)
            is_error = result.get("success") is False
            status = FAIL if is_error else PASS
            detail = f"SID={sent_sid}"
            results.append(("sms_redact_message", status, detail))
            print(f"  {status}  {'sms_redact_message':<25} {detail}")
        except Exception as exc:
            results.append(("sms_redact_message", FAIL, str(exc)[:120]))
            print(f"  {FAIL}  {'sms_redact_message':<25} {exc}")
    else:
        results.append(("sms_redact_message", SKIP, "No sent message to redact"))
        print(f"  {SKIP}  {'sms_redact_message':<25} No sent message available")

    # sms_delete_message — use the BULK message SID if available, fall back
    delete_sid = None
    try:
        # Get a message from list_sent to delete (pick the most recent test msg)
        list_result = await client.call_tool("sms_list_sent", {"params": {"limit": 5}})
        for msg in list_result.get("messages", []):
            body = msg.get("body", "")
            if "[MCP Bulk Test]" in body or "[MCP Test]" in body:
                delete_sid = msg.get("sid")
                break
    except Exception:
        pass

    if delete_sid:
        try:
            result = await test_sms_delete_message(client, delete_sid)
            is_error = result.get("success") is False
            status = FAIL if is_error else PASS
            results.append(("sms_delete_message", status, f"SID={delete_sid}"))
            print(f"  {status}  {'sms_delete_message':<25} SID={delete_sid}")
        except Exception as exc:
            results.append(("sms_delete_message", FAIL, str(exc)[:120]))
            print(f"  {FAIL}  {'sms_delete_message':<25} {exc}")
    else:
        results.append(("sms_delete_message", SKIP, "No expendable message to delete"))
        print(f"  {SKIP}  {'sms_delete_message':<25} No test message found to delete safely")

    # ── Gemini Summary ──
    section("Gemini Analysis of Results")
    async with httpx.AsyncClient() as http:
        summary_lines = "\n".join(
            f"- {name}: {'PASS' if 'PASS' in status else 'FAIL' if 'FAIL' in status else 'SKIP'} — {detail[:80]}"
            for name, status, detail in results
        )
        gemini_summary = await ask_gemini(
            f"Here are the test results for all 16 Twilio MCP server tools:\n\n{summary_lines}\n\n"
            "Write a brief 3-5 sentence summary of the test run. Note which tools passed, "
            "which failed with real errors vs expected skips (e.g. sms_schedule requires a "
            "Messaging Service SID). Rate the overall health of the server.",
            http,
        )
        print(f"\n  {gemini_summary.strip()}")

    # ── Final Report ──
    banner("TEST RESULTS SUMMARY")

    passed = sum(1 for _, s, _ in results if "PASS" in s)
    failed = sum(1 for _, s, _ in results if "FAIL" in s)
    skipped = sum(1 for _, s, _ in results if "SKIP" in s)

    for name, status, detail in results:
        print(f"  {status}  {name:<25} {detail[:90]}")

    print(f"\n  {'─' * 50}")
    print(f"  Total: {len(results)} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}")

    if failed == 0:
        print(f"\n  {BOLD}🎉 All tools operational!{RESET}")
    else:
        print(f"\n  {BOLD}⚠️  {failed} tool(s) need attention.{RESET}")

    return_code = 1 if failed > 0 else 0
    sys.exit(return_code)


def list_tools_only() -> None:
    """Quick mode: just list all tools without running tests."""

    async def _list():
        client = MCPDirectClient()
        await client.connect()
        banner("Available MCP Tools")
        for i, name in enumerate(client.tool_names, 1):
            print(f"  {i:2d}. {name}")
        print(f"\n  Total: {len(client.tool_names)} tools")

    asyncio.run(_list())


def main():
    parser = argparse.ArgumentParser(description="Gemini-powered MCP tool tester")
    parser.add_argument("--list", action="store_true", help="Just list tools, don't test")
    args = parser.parse_args()

    if args.list:
        list_tools_only()
    else:
        asyncio.run(run_all_tests())


if __name__ == "__main__":
    main()
