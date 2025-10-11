# tools/export_available_accounts.py
import os
import sqlite3
from datetime import datetime

# Попробуем взять путь к БД из .env (если есть), иначе используем db.sqlite3
DB_PATH = os.getenv("DB_PATH") or os.path.join(os.path.dirname(__file__), "..", "accounts_rank7.sqlite3")
DB_PATH = os.path.abspath(DB_PATH)

# Фильтры (нужно = True / False)
ONLY_CREDS = True          # если True — в файл попадут только логин:пароль (поле creds)
FILTER_CATEGORY = None     # например: "WarThunder"; или None чтобы не фильтровать

# Куда сохранять
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M")
out_path = os.path.abspath(os.path.join(EXPORT_DIR, f"available_accounts7_{ts}.txt"))

def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"[ERROR] База не найдена: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        sql = """
            SELECT id, category, button_title, price_rub, creds
            FROM accounts
            WHERE status='available'
        """
        params = []
        if FILTER_CATEGORY:
            sql += " AND category=?"
            params.append(FILTER_CATEGORY)
        sql += " ORDER BY id DESC"

        cur.execute(sql, params)
        rows = cur.fetchall()

        if not rows:
            print("[INFO] Нет доступных аккаунтов (status='available').")
            print(f"[INFO] DB: {DB_PATH}")
            return

        with open(out_path, "w", encoding="utf-8") as f:
            if ONLY_CREDS:
                # по одной строке: только данные для входа
                for r in rows:
                    creds = (r["creds"] or "").strip()
                    if creds:
                        f.write(creds + "\n")
            else:
                # расширенный формат: id | category | title | price | creds
                for r in rows:
                    line = f'{r["id"]}\t{r["category"]}\t{r["button_title"]}\t{r["price_rub"]} ₽\t{(r["creds"] or "").strip()}'
                    f.write(line + "\n")

        print(f"[OK] Выгружено: {len(rows)} записей")
        print(f"[OK] Файл: {out_path}")
        print(f"[OK] DB: {DB_PATH}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
