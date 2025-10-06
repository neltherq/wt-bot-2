# app/services/lolz.py
import os
import httpx
import logging
from urllib.parse import urlencode
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# --- Константы / ENV ---
LOLZ_USERNAME = "sainz"  # ← жёстко зашитый ник получателя
LOLZ_PAY_BASE_URL = os.getenv("LOLZ_PAY_BASE_URL", "https://lzt.market/balance/transfer")
BASE = "https://prod-api.lzt.market"  # API для проверки платежей (comment)

def _headers() -> dict:
    """
    Собираем заголовки для запросов к API.
    Если токен не задан, Authorization НЕ добавляем.
    """
    headers = {"accept": "application/json"}
    token = (os.getenv("LOLZ_API_TOKEN") or "").strip()
    if token:
        headers["authorization"] = f"Bearer {token}"
    else:
        logger.warning("LOLZ_API_TOKEN is empty – API requests will be unauthenticated")
    return headers

def build_pay_url(
    *,
    amount_rub: int,
    comment: str,
    currency: str = "rub",
    telegram_deal: bool = True,
    transfer_hold: bool = False,
) -> str:
    """
    Формируем ссылку оплаты строго по никнейму:
      https://lzt.market/balance/transfer?username=sainz&amount=...&comment=...
    """
    params = {
        "username": LOLZ_USERNAME,
        "amount": str(amount_rub),
        "currency": currency,
        "comment": comment,
        "telegram_deal": str(telegram_deal).lower(),
        "transfer_hold": str(transfer_hold).lower(),
    }
    url = f"{LOLZ_PAY_BASE_URL}?{urlencode(params)}"
    logger.info("LOLZ pay URL built (username=%s): %s", LOLZ_USERNAME, url)
    return url

async def find_payment_by_comment(comment: str) -> dict:
    """
    Проверка входящих платежей по комменту.
    Возвращает {"status_code": int, "json": dict}.
    Даже при 200 'payments' может быть пуст – значит, оплаты с таким comment нет.
    """
    url = f"{BASE}/user/payments?comment={comment}"
    logger.info("LOLZ payments check -> url=%s", url)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=_headers())
    except httpx.HTTPError as e:
        logger.exception("HTTP error while contacting lolz API")
        return {"status_code": 0, "json": {"error": str(e)}}

    try:
        data = r.json()
    except Exception:
        data = {"_raw": r.text[:500]}
    logger.info("LOLZ payments check <- status=%s keys=%s", r.status_code, list(data.keys()))
    return {"status_code": r.status_code, "json": data}

# ======= Сравнение сумм с точностью до копеек (строгое равенство) =======
def _to_decimal(val: str) -> Decimal | None:
    try:
        return Decimal(val)
    except (InvalidOperation, TypeError):
        return None

def extract_success_operation(data: dict, expected_amount_rub: int):
    """
    Ищем успешный входящий платёж с суммой ТОЧНО == expected_amount_rub (в рублях).
    Вернёт dict с operation_id и т.п. или None.
    """
    payments = (data or {}).get("payments") or {}
    expected = Decimal(expected_amount_rub)
    for _, pay in payments.items():
        if pay.get("payment_status") != "success_in":
            continue
        if pay.get("operation_type") != "receiving_money":
            continue

        inc_str = pay.get("incoming_sum") or pay.get("sum") or "0"
        inc = _to_decimal(inc_str)
        if inc is None:
            continue

        # строгое равенство — 5.01 или 4.99 не пройдут как 5
        if inc == expected:
            return {
                "operation_id": pay.get("operation_id"),
                "incoming_sum": inc,   # Decimal
                "raw": pay,
            }
    return None

def extract_any_success_amount(data: dict) -> str | None:
    """
    Если есть успешный входящий платёж по этому комменту, вернуть его сумму (строкой),
    даже если она НЕ совпадает с ожидаемой. Для сообщений о несоответствии.
    """
    payments = (data or {}).get("payments") or {}
    for _, pay in payments.items():
        if pay.get("payment_status") == "success_in" and pay.get("operation_type") == "receiving_money":
            return (pay.get("incoming_sum") or pay.get("sum") or "0")
    return None
