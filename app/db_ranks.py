# app/db_ranks.py
import os
import aiosqlite
from typing import Optional, Literal

# Разделы (ранги), с которыми работаем
Rank = Literal["8", "7", "6"]

# Пути к БД
# 8 rank хранится в основной БД (как и раньше), 7/6 — в отдельных файлах
MAIN_DB = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "db.sqlite3")
)
RANK7_DB = os.getenv(
    "RANK7_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "accounts_rank7.sqlite3")
)
RANK6_DB = os.getenv(
    "RANK6_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "accounts_rank6.sqlite3")
)


def _db_path_for_rank(rank: Rank) -> str:
    if rank == "8":
        # текущие лоты 8 ранга — в основной БД
        return MAIN_DB
    if rank == "7":
        return RANK7_DB
    if rank == "6":
        return RANK6_DB
    raise ValueError("Unsupported rank")


# ---------------------------------------------------------------------
# LIST / COUNT
# ---------------------------------------------------------------------
async def list_available(rank: Rank, limit: int = 10, offset: int = 0) -> list[dict]:
    """
    Список доступных (status='available') аккаунтов для ранга.
    Для 8 ранга это тоже сработает, но обычно вы используете функции из app.db.
    """
    path = _db_path_for_rank(rank)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, button_title, price_rub FROM accounts "
            "WHERE status='available' ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_available(rank: Rank) -> int:
    path = _db_path_for_rank(rank)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM accounts WHERE status='available'"
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


# ---------------------------------------------------------------------
# GET / MARK SOLD / INSERT
# ---------------------------------------------------------------------
async def get_account(rank: Rank, acc_id: int) -> Optional[dict]:
    path = _db_path_for_rank(rank)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE id=?", (int(acc_id),)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def mark_sold(rank: Rank, acc_id: int) -> None:
    path = _db_path_for_rank(rank)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE accounts SET status='sold' WHERE id=? AND status='available'",
            (int(acc_id),)
        )
        await db.commit()


async def insert_account(
    rank: Rank,
    *,
    button_title: str,
    creds: str,
    photo_file_id: str | None,
    caption: str | None,
    price_rub: int,
    category: str | None = None,
) -> int:
    path = _db_path_for_rank(rank)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "INSERT INTO accounts(category, button_title, creds, photo_file_id, caption, price_rub, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'available')",
            (category, button_title, creds, photo_file_id, caption, int(price_rub))
        )
        await db.commit()
        return cur.lastrowid


# ---------------------------------------------------------------------
# DELETE / UPDATE CAPTION  ← ЭТИХ ФУНКЦИЙ У ТЕБЯ НЕ ХВАТАЛО
# ---------------------------------------------------------------------
async def delete_account(rank: Rank, acc_id: int) -> bool:
    """
    Удаление аккаунта (hard delete) для 7/6 рангов.
    Для 8 ранга обычно используем app.db.delete_account, но тут тоже работает.
    """
    path = _db_path_for_rank(rank)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("DELETE FROM accounts WHERE id=?", (int(acc_id),))
        await db.commit()
        return cur.rowcount > 0


async def update_caption(rank: Rank, acc_id: int, caption: str) -> bool:
    """
    Обновление описания аккаунта для 7/6 рангов.
    Для 8 ранга обычно используем app.db.update_account_caption, но тут тоже работает.
    """
    path = _db_path_for_rank(rank)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "UPDATE accounts SET caption=? WHERE id=?",
            (caption, int(acc_id))
        )
        await db.commit()
        return cur.rowcount > 0
