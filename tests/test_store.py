from __future__ import annotations


def test_store_round_trip():
    from twilio_sms_mcp import store

    sid = f"SM{'1' * 32}"
    store.init_db()
    store.store_inbound(
        {
            "MessageSid": sid,
            "From": "+12025550123",
            "To": "+12025550100",
            "Body": "hello",
            "NumMedia": "1",
            "MediaUrl0": "https://example.com/image.png",
        }
    )

    inbox = store.get_inbox()
    assert len(inbox) == 1
    assert inbox[0]["sid"] == sid
    assert inbox[0]["media_urls"] == ["https://example.com/image.png"]
    assert store.count_unread() == 1
    assert store.mark_read(sid) == 1
    assert store.count_unread() == 0


def test_store_conversation_returns_both_directions():
    from twilio_sms_mcp import store

    store.init_db()
    for i, (from_num, to_num) in enumerate(
        [("+12025550123", "+12025550100"), ("+12025550100", "+12025550123")]
    ):
        store.store_inbound(
            {
                "MessageSid": f"SM{str(i) * 32}",
                "From": from_num,
                "To": to_num,
                "Body": f"msg {i}",
                "NumMedia": "0",
            }
        )

    convo = store.get_conversation("+12025550123")
    assert len(convo) == 2


def test_mark_all_read():
    from twilio_sms_mcp import store

    store.init_db()
    for i in range(3):
        store.store_inbound(
            {
                "MessageSid": f"SM{str(i + 5) * 32}",
                "From": "+12025550123",
                "To": "+12025550100",
                "Body": f"msg {i}",
                "NumMedia": "0",
            }
        )
    assert store.count_unread() == 3
    marked = store.mark_all_read(from_number="+12025550123")
    assert marked == 3
    assert store.count_unread() == 0


def test_delivery_status_tracking():
    from twilio_sms_mcp import store

    sid = f"SM{'7' * 32}"
    store.init_db()
    store.update_delivery_status(
        {"MessageSid": sid, "MessageStatus": "sent", "ErrorCode": ""}
    )
    store.update_delivery_status(
        {"MessageSid": sid, "MessageStatus": "delivered", "ErrorCode": ""}
    )

    latest = store.get_latest_delivery_status(sid)
    assert latest is not None
    assert latest["status"] == "delivered"


def test_get_read_statuses():
    from twilio_sms_mcp import store

    store.init_db()
    sid_a = f"SM{'a' * 32}"
    sid_b = f"SM{'b' * 32}"
    store.store_inbound(
        {"MessageSid": sid_a, "From": "+12025550123", "To": "+12025550100", "Body": "a", "NumMedia": "0"}
    )
    store.store_inbound(
        {"MessageSid": sid_b, "From": "+12025550123", "To": "+12025550100", "Body": "b", "NumMedia": "0"}
    )
    store.mark_read(sid_a)

    statuses = store.get_read_statuses([sid_a, sid_b])
    assert statuses[sid_a] is True
    assert statuses[sid_b] is False


def test_inbox_pagination():
    from twilio_sms_mcp import store

    store.init_db()
    for i in range(5):
        store.store_inbound(
            {
                "MessageSid": f"SM{str(i + 10) * 16}{str(i + 10) * 16}",
                "From": "+12025550123",
                "To": "+12025550100",
                "Body": f"page {i}",
                "NumMedia": "0",
            }
        )

    page1 = store.get_inbox(limit=2, offset=0)
    page2 = store.get_inbox(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0]["sid"] != page2[0]["sid"]
