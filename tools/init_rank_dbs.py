import sqlite3
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    button_title TEXT NOT NULL,
    creds TEXT NOT NULL,
    photo_file_id TEXT,
    caption TEXT,
    price_rub INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
'''

def init_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    base = Path("data")
    init_db(base / "accounts_rank7.sqlite3")
    init_db(base / "accounts_rank6.sqlite3")
    print("Initialized: data/accounts_rank7.sqlite3, data/accounts_rank6.sqlite3")
