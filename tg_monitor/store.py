import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from .paths import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS mentions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_message_id   INTEGER NOT NULL,
  chat_id         INTEGER NOT NULL,
  chat_title      TEXT NOT NULL,
  chat_username   TEXT,
  sender_id       INTEGER NOT NULL,
  sender_name     TEXT NOT NULL,
  sender_username TEXT,
  text            TEXT NOT NULL,
  kind            TEXT NOT NULL,
  matched_keyword TEXT,
  received_at     INTEGER NOT NULL,
  seen_at         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_mentions_received ON mentions(received_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mentions_dedup ON mentions(chat_id, tg_message_id);
"""


@dataclass
class Mention:
    id: int
    tg_message_id: int
    chat_id: int
    chat_title: str
    chat_username: Optional[str]
    sender_id: int
    sender_name: str
    sender_username: Optional[str]
    text: str
    kind: str
    matched_keyword: Optional[str]
    received_at: int
    seen_at: Optional[int]


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns for older databases that predate the WS-sync feature."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(mentions)").fetchall()}
    if not existing:
        return  # fresh DB; SCHEMA below will create the full set
    if "chat_username" not in existing:
        conn.execute("ALTER TABLE mentions ADD COLUMN chat_username TEXT")
    if "sender_username" not in existing:
        conn.execute("ALTER TABLE mentions ADD COLUMN sender_username TEXT")


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


class Store:
    def __init__(self) -> None:
        self.conn = _connect()

    def insert(
        self,
        *,
        tg_message_id: int,
        chat_id: int,
        chat_title: str,
        sender_id: int,
        sender_name: str,
        text: str,
        kind: str,
        matched_keyword: Optional[str],
        chat_username: Optional[str] = None,
        sender_username: Optional[str] = None,
    ) -> Optional[int]:
        try:
            cur = self.conn.execute(
                """INSERT INTO mentions
                   (tg_message_id, chat_id, chat_title, chat_username,
                    sender_id, sender_name, sender_username,
                    text, kind, matched_keyword, received_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tg_message_id,
                    chat_id,
                    chat_title,
                    chat_username,
                    sender_id,
                    sender_name,
                    sender_username,
                    text,
                    kind,
                    matched_keyword,
                    int(time.time()),
                ),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def recent(self, limit: int = 20) -> List[Mention]:
        rows = self.conn.execute(
            "SELECT * FROM mentions ORDER BY received_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_mention(r) for r in rows]

    def get(self, mention_id: int) -> Optional[Mention]:
        row = self.conn.execute(
            "SELECT * FROM mentions WHERE id = ?", (mention_id,)
        ).fetchone()
        return _row_to_mention(row) if row else None

    def mark_seen(self, mention_id: int) -> None:
        self.conn.execute(
            "UPDATE mentions SET seen_at = ? WHERE id = ? AND seen_at IS NULL",
            (int(time.time()), mention_id),
        )

    def mark_all_seen(self) -> None:
        self.conn.execute(
            "UPDATE mentions SET seen_at = ? WHERE seen_at IS NULL",
            (int(time.time()),),
        )

    def clear_all(self) -> None:
        self.conn.execute("DELETE FROM mentions")

    def unseen_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM mentions WHERE seen_at IS NULL"
        ).fetchone()
        return int(row["c"])


def _row_to_mention(r: sqlite3.Row) -> Mention:
    keys = r.keys()
    return Mention(
        id=r["id"],
        tg_message_id=r["tg_message_id"],
        chat_id=r["chat_id"],
        chat_title=r["chat_title"],
        chat_username=r["chat_username"] if "chat_username" in keys else None,
        sender_id=r["sender_id"],
        sender_name=r["sender_name"],
        sender_username=r["sender_username"] if "sender_username" in keys else None,
        text=r["text"],
        kind=r["kind"],
        matched_keyword=r["matched_keyword"],
        received_at=r["received_at"],
        seen_at=r["seen_at"],
    )
