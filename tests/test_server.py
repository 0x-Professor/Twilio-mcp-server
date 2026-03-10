from __future__ import annotations

import json

from fastmcp import Client


async def test_mcp_lists_expected_tools_and_reads_inbox():
    from twilio_sms_mcp import store
    from twilio_sms_mcp.server import mcp

    store.init_db()
    store.store_inbound(
        {
            "MessageSid": f"SM{'3' * 32}",
            "From": "+12025550123",
            "To": "+12025550100",
            "Body": "hello from mcp",
            "NumMedia": "0",
        }
    )

    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        assert tool_names == {
            "sms_send",
            "sms_send_bulk",
            "sms_schedule",
            "sms_cancel_scheduled",
            "sms_list_sent",
            "sms_get_message",
            "sms_delete_message",
            "sms_redact_message",
            "sms_list_inbox",
            "sms_get_conversation",
            "sms_mark_read",
            "sms_list_numbers",
            "sms_lookup_number",
            "sms_format_number",
            "sms_usage_stats",
            "sms_account_info",
        }

        result = await client.call_tool("sms_list_inbox", {"params": {"limit": 10}})
        payload = json.loads(result.content[0].text)
        assert payload["count"] == 1
        assert payload["messages"][0]["body"] == "hello from mcp"


async def test_mcp_exposes_prompts():
    from twilio_sms_mcp.server import mcp

    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        prompt_names = {p.name for p in prompts}
        assert "draft_sms" in prompt_names
        assert "summarize_conversation" in prompt_names


async def test_mcp_exposes_resources():
    from twilio_sms_mcp.server import mcp

    async with Client(mcp) as client:
        resources = await client.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        assert any("twilio://account" in uri for uri in resource_uris)
