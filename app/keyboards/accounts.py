# app/keyboards/accounts.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from math import ceil

MAX_ROWS = 10  # максимум 10 рядов на страницу (по одному аккаунту в ряд)

def _trim(text: str, limit: int = 64) -> str:
    return (text[: limit - 1] + "…") if len(text) > limit else text

def accounts_list_kb(category: str, items: list[dict], total: int, page: int, per_page: int = MAX_ROWS) -> InlineKeyboardMarkup:
    """
    items: [{id, button_title, price_rub}]
    В callback аккаунта кладём текущую страницу, чтобы «Назад» вернул туда же.
    """
    rows: list[list[InlineKeyboardButton]] = []

    for it in items:
        label = f"{it['button_title']} — {it['price_rub']} ₽"
        rows.append([InlineKeyboardButton(text=_trim(label), callback_data=f"acc:pick:{it['id']}:{page}")])

    # пагинация
    pages = max(1, ceil(total / per_page)) if per_page else 1
    if pages > 1:
        prev_p = max(1, page - 1)
        next_p = min(pages, page + 1)
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"acc:page:{prev_p}"))
        nav.append(InlineKeyboardButton(text=f"Стр. {page}/{pages}", callback_data="acc:nop"))
        if page < pages:
            nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"acc:page:{next_p}"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def account_card_kb(acc_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить", callback_data=f"acc:buy:{acc_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"acc:page:{page}")],
    ])
