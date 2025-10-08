# app/db_broadcast.py
import aiosqlite
from typing import Optional, Iterable, Tuple

DB_PATH = "broadcast.db"

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS admins(
  user_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS recipients(
  user_id   INTEGER PRIMARY KEY,
  is_active INTEGER NOT NULL DEFAULT 1,
  last_seen TEXT     DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS broadcasts(
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
  author_id   INTEGER,
  src_chat_id INTEGER,
  src_msg_id  INTEGER,
  total       INTEGER DEFAULT 0,
  sent        INTEGER DEFAULT 0,
  failed      INTEGER DEFAULT 0,
  status      TEXT    DEFAULT 'running'  -- running|done|canceled
);

CREATE TABLE IF NOT EXISTS deliveries(
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  broadcast_id  INTEGER NOT NULL,
  user_id       INTEGER NOT NULL,
  status        TEXT,   -- ok|fail|skip
  error         TEXT,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(broadcast_id) REFERENCES broadcasts(id)
);
"""

# ---------- lifecycle ----------
async def init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

# ---------- admins ----------
async def add_admin(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (user_id,))
        await db.commit()

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row is not None

# ---------- recipients ----------
async def upsert_recipient(user_id: int, active: bool = True) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO recipients(user_id, is_active) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET is_active=excluded.is_active, last_seen=CURRENT_TIMESTAMP",
            (user_id, 1 if active else 0),
        )
        await db.commit()

async def get_all_recipient_ids(only_active: bool = True) -> list[int]:
    sql = "SELECT user_id FROM recipients"
    if only_active:
        sql += " WHERE is_active=1"
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(sql)
        rows = await cur.fetchall()
        return [r[0] for r in rows]

# ---------- broadcasts / logs ----------
async def create_broadcast(author_id: int, src_chat_id: int, src_msg_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO broadcasts(author_id, src_chat_id, src_msg_id) VALUES(?,?,?)",
            (author_id, src_chat_id, src_msg_id),
        )
        await db.commit()
        return cur.lastrowid

async def update_progress(broadcast_id: int, sent_inc: int = 0, fail_inc: int = 0) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE broadcasts SET sent = sent + ?, failed = failed + ? WHERE id = ?",
            (sent_inc, fail_inc, broadcast_id),
        )
        await db.commit()

async def finalize_broadcast(broadcast_id: int, total: int, status: str = "done") -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE broadcasts SET total=?, status=? WHERE id=?",
            (total, status, broadcast_id),
        )
        await db.commit()

async def add_delivery_result(broadcast_id: int, user_id: int, status: str, error: Optional[str] = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO deliveries(broadcast_id, user_id, status, error) VALUES(?,?,?,?)",
            (broadcast_id, user_id, status, error),
        )
        await db.commit()
