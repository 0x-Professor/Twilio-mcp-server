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
