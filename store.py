"""SQLite store for inbound SMS messages received via Twilio webhooks."""

import sqlite3
import json
from datetime import datetime
from typing import Optional
from .config import settings


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables on startup."""
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inbox (
                sid           TEXT PRIMARY KEY,
                from_number   TEXT NOT NULL,
                to_number     TEXT NOT NULL,
                body          TEXT,
                num_media     INTEGER DEFAULT 0,
                media_urls    TEXT,
                received_at   TEXT NOT NULL,
                read          INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS delivery_status (
                sid           TEXT NOT NULL,
                status        TEXT NOT NULL,
                error_code    TEXT,
                updated_at    TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_inbox_from ON inbox(from_number);
            CREATE INDEX IF NOT EXISTS idx_inbox_ts   ON inbox(received_at);
            CREATE INDEX IF NOT EXISTS idx_status_sid ON delivery_status(sid);
        """)


def store_inbound(data: dict) -> None:
    """Persist an inbound message from Twilio's webhook POST."""
    media_urls = []
    num_media = int(data.get("NumMedia", 0))
    for i in range(num_media):
        url = data.get(f"MediaUrl{i}")
        if url:
            media_urls.append(url)

    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO inbox
               (sid, from_number, to_number, body, num_media, media_urls, received_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                data.get("MessageSid", ""),
                data.get("From", ""),
                data.get("To", ""),
                data.get("Body", ""),
                num_media,
                json.dumps(media_urls),
                datetime.utcnow().isoformat(),
            ),
        )


def update_delivery_status(data: dict) -> None:
    """Store a delivery status callback."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO delivery_status (sid, status, error_code, updated_at) VALUES (?,?,?,?)",
            (
                data.get("MessageSid", ""),
                data.get("MessageStatus", ""),
                data.get("ErrorCode", ""),
                datetime.utcnow().isoformat(),
            ),
        )


def get_inbox(
    from_number: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    query = "SELECT * FROM inbox WHERE 1=1"
    params: list = []
    if from_number:
        query += " AND from_number = ?"
        params.append(from_number)
    if unread_only:
        query += " AND read = 0"
    query += " ORDER BY received_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        d["media_urls"] = json.loads(d.get("media_urls") or "[]")
        result.append(d)
    return result


def count_unread() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM inbox WHERE read=0").fetchone()[0]


def mark_read(sid: str) -> None:
    with _conn() as conn:
        conn.execute("UPDATE inbox SET read=1 WHERE sid=?", (sid,))


def mark_all_read(from_number: Optional[str] = None) -> int:
    if from_number:
        with _conn() as conn:
            cur = conn.execute(
                "UPDATE inbox SET read=1 WHERE from_number=? AND read=0", (from_number,)
            )
            return cur.rowcount
    else:
        with _conn() as conn:
            cur = conn.execute("UPDATE inbox SET read=1 WHERE read=0")
            return cur.rowcount


def get_conversation(number: str, limit: int = 50) -> list[dict]:
    """Return all messages to/from a number, chronological order."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM inbox WHERE from_number=? OR to_number=? ORDER BY received_at ASC LIMIT ?",
            (number, number, limit),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["media_urls"] = json.loads(d.get("media_urls") or "[]")
        result.append(d)
    return result


def get_latest_delivery_status(sid: str) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM delivery_status WHERE sid=? ORDER BY updated_at DESC LIMIT 1", (sid,)
        ).fetchone()
    return dict(row) if row else None
