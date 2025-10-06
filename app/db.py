# app/db.py
import os
import aiosqlite
from typing import Optional

# Путь к базе: по умолчанию ../db.sqlite3 от этого файла; можно переопределить через .env (DB_PATH)
DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "db.sqlite3")
)

# -------------------- INIT --------------------

async def init_db():
    """
    Инициализация БД и таблиц.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # users
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance_rub INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(lower(username))")
        
                # sales (история покупок)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                price_rub INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )


        # payments (для пополнений по comment)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                method TEXT NOT NULL,
                amount_rub INTEGER NOT NULL,
                comment TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,             -- pending / success / failed
                ext_operation_id INTEGER,         -- id операции на стороне провайдера
                raw_json TEXT,                    -- полный ответ провайдера
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")

        # accounts (товары)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,            -- например, 'WarThunder'
                button_title TEXT NOT NULL,        -- текст кнопки (название)
                creds TEXT NOT NULL,               -- "login:password"
                photo_file_id TEXT,                -- file_id фото из Telegram (опционально)
                caption TEXT,                      -- описание (подпись к фото)
                price_rub INTEGER NOT NULL,        -- цена в рублях
                status TEXT DEFAULT 'available',   -- available / sold / hidden
                created_by INTEGER,                -- Telegram user_id админа
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_cat_status ON accounts(category, status, id)")
        await db.commit()

# -------------------- USERS --------------------

async def ensure_user(user_id: int, username: Optional[str]) -> None:
    """
    Создать пользователя, если нет. Обновить username при необходимости.
    """
    uname = (username or "").lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users(user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                updated_at=datetime('now')
            """,
            (user_id, uname)
        )
        await db.commit()

async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_user_by_username(username: str) -> Optional[dict]:
    """Найти пользователя по username (без @), регистронезависимо."""
    uname = (username or "").lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE lower(username) = ?", (uname,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_balance_rub(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance_rub FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

async def add_balance_rub(user_id: int, delta_rub: int) -> int:
    """
    Изменить баланс по user_id. Возвращает новый баланс.
    Списания не опускают ниже 0.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance_rub FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            current = int(row[0]) if row else 0
        if delta_rub >= 0:
            new_balance = current + delta_rub
        else:
            new_balance = max(0, current + delta_rub)
        await db.execute(
            "UPDATE users SET balance_rub = ?, updated_at = datetime('now') WHERE user_id = ?",
            (new_balance, user_id)
        )
        await db.commit()
        return new_balance

async def add_balance_rub_by_username(username: str, delta_rub: int) -> tuple[Optional[int], int]:
    """
    Изменить баланс по username. Возвращает (new_balance, applied_delta).
    Если delta отрицательная — не уходим ниже 0 (кэпим).
    """
    uname = (username or "").lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, balance_rub FROM users WHERE lower(username)=?", (uname,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None, 0
            user_id = row["user_id"]
            current = int(row["balance_rub"])

        if delta_rub >= 0:
            new_balance = current + delta_rub
            applied = delta_rub
        else:
            applied = -min(current, -delta_rub)
            new_balance = current + applied

        await db.execute(
            "UPDATE users SET balance_rub = ?, updated_at = datetime('now') WHERE user_id = ?",
            (new_balance, user_id)
        )
        await db.commit()
        return new_balance, applied

# -------------------- PAYMENTS --------------------

async def create_payment(user_id: int, method: str, amount_rub: int,
                         comment: str, status: str, raw_json: Optional[str]) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO payments(user_id, method, amount_rub, comment, status, raw_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, method, amount_rub, comment, status, raw_json)
        )
        await db.commit()
        return cur.lastrowid

async def get_payment_by_comment(comment: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE comment = ?", (comment,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def mark_payment_success(comment: str, ext_operation_id: int, raw_json: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE payments
            SET status='success',
                ext_operation_id=?,
                raw_json=?,
                updated_at=datetime('now')
            WHERE comment=?
            """,
            (ext_operation_id, raw_json, comment)
        )
        await db.commit()

# -------------------- ACCOUNTS (товары) --------------------

async def add_account(category: str, button_title: str, creds: str,
                      photo_file_id: Optional[str], caption: Optional[str],
                      price_rub: int, created_by: Optional[int]) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO accounts(category, button_title, creds, photo_file_id, caption, price_rub, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, 'available', ?)
            """,
            (category, button_title, creds, photo_file_id, caption, int(price_rub), created_by)
        )
        await db.commit()
        return cur.lastrowid

async def list_accounts(category: str, limit: int, offset: int = 0) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, button_title, price_rub
            FROM accounts
            WHERE category = ? AND status = 'available'
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (category, limit, offset)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

async def count_accounts(category: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM accounts WHERE category = ? AND status = 'available'",
            (category,)
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

async def get_account_by_id(acc_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM accounts WHERE id = ?", (int(acc_id),)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def purchase_account(user_id: int, acc_id: int) -> dict:
    """
    Атомарная покупка:
      - проверяет, что аккаунт доступен
      - проверяет баланс пользователя
      - списывает price и помечает аккаунт как sold
      - пишет запись в sales
    Возвращает dict: {"status": "ok", "creds": "...", "price_rub": 123, "title": "..."} |
                      {"status": "insufficient"} |
                      {"status": "not_available"} |
                      {"status": "error", "reason": "..."}
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")  # блокируем для гонок

            # тянем аккаунт
            async with db.execute("SELECT * FROM accounts WHERE id = ?", (acc_id,)) as cur:
                acc = await cur.fetchone()
            if not acc or acc["status"] != "available":
                await db.execute("ROLLBACK")
                return {"status": "not_available"}

            price = int(acc["price_rub"])
            title = acc["button_title"]
            creds = acc["creds"]

            # баланс пользователя
            async with db.execute("SELECT balance_rub FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
            balance = int(row[0]) if row else 0

            if balance < price:
                await db.execute("ROLLBACK")
                return {"status": "insufficient"}

            # списываем и отмечаем SOLD
            new_balance = balance - price
            await db.execute("UPDATE users SET balance_rub=?, updated_at=datetime('now') WHERE user_id=?", (new_balance, user_id))
            # доп.защита от гонки: статус меняем только если ещё available
            await db.execute("UPDATE accounts SET status='sold' WHERE id=? AND status='available'", (acc_id,))
            # запись о продаже
            await db.execute("INSERT INTO sales(user_id, account_id, price_rub) VALUES (?, ?, ?)", (user_id, acc_id, price))

            await db.commit()
            return {"status": "ok", "creds": creds, "price_rub": price, "title": title}
    except Exception as e:
        try:
            async with aiosqlite.connect(DB_PATH) as db2:
                await db2.execute("ROLLBACK")
        except Exception:
            pass
        return {"status": "error", "reason": str(e)}

# ---------------------------------------------------------------------
# УДАЛЕНИЕ АККАУНТА (8 rank)
# ---------------------------------------------------------------------
async def delete_account(acc_id: int) -> bool:
    """
    Удаляет аккаунт из основной (8 rank) базы.
    Возвращает True, если запись реально удалена.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM accounts WHERE id=?", (int(acc_id),))
        await db.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------
# ОБНОВЛЕНИЕ ОПИСАНИЯ (8 rank)
# ---------------------------------------------------------------------
async def update_account_caption(acc_id: int, caption: str) -> bool:
    """
    Обновляет описание (caption) для аккаунта в основной базе.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE accounts SET caption=?, updated_at=datetime('now') WHERE id=?",
            (caption, int(acc_id))
        )
        await db.commit()
        return cur.rowcount > 0
    
# --- STATS: users ---

async def count_users_total() -> int:
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


async def count_users_this_week() -> int:
    """
    Считает пользователей, зарегистрированных за последние 7 дней (включая сегодня).
    Поле регистрации: created_at (UTC), по умолчанию datetime('now') в init_db.
    """
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        # >= DATE('now','-6 days')  → сегодня и 6 предыдущих дней = 7 дней
        async with db.execute("""
            SELECT COUNT(*) FROM users
            WHERE DATE(created_at) >= DATE('now','-6 days')
        """) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


async def count_users_this_month() -> int:
    """
    Считает пользователей, зарегистрированных с начала текущего месяца (UTC).
    """
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) FROM users
            WHERE DATE(created_at) >= DATE('now','start of month')
        """) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0
