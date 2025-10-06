# app/handlers/warthunder.py
import logging
from math import ceil

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InputMediaPhoto,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest

from app.keyboards.wt import wt_ranks_keyboard
from app.keyboards.accounts import MAX_ROWS  # используем лимит строк как per_page

from app.db import (
    ensure_user,
    get_balance_rub,
    add_balance_rub,
    get_account_by_id as get_account_rank8,
    purchase_account as purchase_rank8,
    list_accounts as list_rank8_accounts,
    count_accounts as count_rank8_accounts,
)
from app.db_ranks import (
    list_available as list_rank_accounts,
    count_available as count_rank_accounts,
    get_account as get_rank_account,
    mark_sold as mark_rank_sold,
)

logger = logging.getLogger(__name__)
router = Router(name="warthunder")

PER_PAGE = MAX_ROWS


# ──────────────────────────────────────────────────────────────
# Вход из главного меню
# ──────────────────────────────────────────────────────────────
@router.message(F.text == "🎮 WarThunder")
async def wt_entry(msg: Message):
    await ensure_user(msg.from_user.id, msg.from_user.username)
    await msg.answer("Выберите раздел WarThunder:", reply_markup=wt_ranks_keyboard())


# ──────────────────────────────────────────────────────────────
# Выбор ранга → первая страница
# ──────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("wt:rank:"))
async def wt_rank_select(cb: CallbackQuery):
    _, _, rank = cb.data.split(":")
    await _render_list(cb, rank=rank, page=1)


# ──────────────────────────────────────────────────────────────
# Переход по страницам
# ──────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("wt:page:"))
async def wt_page(cb: CallbackQuery):
    _, _, rank, page_str = cb.data.split(":")
    page = int(page_str)
    await _render_list(cb, rank=rank, page=page)


# ──────────────────────────────────────────────────────────────
# Назад к выбору рангов
# ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "wt:back")
async def wt_back(cb: CallbackQuery):
    try:
        if (cb.message.text or "") == "Выберите раздел WarThunder:":
            await cb.message.edit_reply_markup(reply_markup=wt_ranks_keyboard())
        else:
            await cb.message.edit_text("Выберите раздел WarThunder:", reply_markup=wt_ranks_keyboard())
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await cb.answer()


# ──────────────────────────────────────────────────────────────
# Карточка товара
# ──────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("wt:item:"))
async def wt_item(cb: CallbackQuery):
    _, _, rank, acc_id_str, *rest = cb.data.split(":")
    acc_id = int(acc_id_str)

    row = await (get_account_rank8(acc_id) if rank == "8" else get_rank_account(rank, acc_id))
    if not row or row.get("status") != "available":
        await cb.answer("Лот недоступен", show_alert=True)
        return

    caption_lines = [
        row.get("caption") or "",
        "",
        f"Цена: {row['price_rub']}₽",
        f"ID: {row['id']}",
        f"Rank: {rank}",
    ]
    caption = "\n".join(caption_lines)

    back_cb = f"wt:rank:{rank}" if not rest else f"wt:page:{rank}:{rest[0]}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить", callback_data=f"wt:buy:{rank}:{row['id']}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)],
    ])

    try:
        if row.get("photo_file_id"):
            try:
                await cb.message.edit_media(InputMediaPhoto(media=row["photo_file_id"], caption=caption), reply_markup=kb)
            except TelegramBadRequest:
                await cb.message.edit_text(caption, reply_markup=kb)
        else:
            await cb.message.edit_text(caption, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await cb.answer()


# ──────────────────────────────────────────────────────────────
# Покупка
# ──────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("wt:buy:"))
async def wt_buy(cb: CallbackQuery):
    _, _, rank, acc_id_str = cb.data.split(":")
    acc_id = int(acc_id_str)

    if rank == "8":
        result = await purchase_rank8(cb.from_user.id, acc_id)
        status = result.get("status")
        if status == "ok":
            await cb.message.answer(f"Покупка успешна!\nДанные:\n<code>{result['creds']}</code>", parse_mode="HTML")
            await cb.answer()
            return
        if status == "insufficient":
            await cb.answer("Недостаточно средств.", show_alert=True)
            return
        if status == "not_available":
            await cb.answer("Лот недоступен", show_alert=True)
            return

        logger.error("purchase_rank8 failed: %r", result)
        await cb.answer("Ошибка при покупке. Попробуйте позже.", show_alert=True)
        return

    # 7/6 ранги
    row = await get_rank_account(rank, acc_id)
    if not row or row.get("status") != "available":
        await cb.answer("Лот недоступен", show_alert=True)
        return

    price = int(row["price_rub"])
    balance = await get_balance_rub(cb.from_user.id)
    if balance < price:
        await cb.answer("Недостаточно средств.", show_alert=True)
        return

    await add_balance_rub(cb.from_user.id, -price)
    await mark_rank_sold(rank, acc_id)

    await cb.message.answer(f"Покупка успешна!\nДанные:\n<code>{row['creds']}</code>", parse_mode="HTML")
    await cb.answer()


# ──────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ
# ──────────────────────────────────────────────────────────────
async def _render_list(cb: CallbackQuery, *, rank: str, page: int):
    """Показать страницу со списком лотов выбранного ранга."""
    per_page = PER_PAGE if PER_PAGE > 0 else 10
    page = max(1, page)

    if rank == "8":
        total = await count_rank8_accounts("WarThunder")
        items = await list_rank8_accounts("WarThunder", limit=per_page, offset=(page - 1) * per_page)
    else:
        total = await count_rank_accounts(rank)
        items = await list_rank_accounts(rank, limit=per_page, offset=(page - 1) * per_page)

    pages = max(1, ceil(total / per_page)) if total else 1
    if page > pages:
        await cb.answer(f"☹️ Страницы {page} не существует", show_alert=True)
        return

    if not items:
        await cb.answer(f"Пока нет доступных лотов для {rank} rank.", show_alert=True)
        return

    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        title = it.get("button_title")
        price = it.get("price_rub")
        acc_id = it.get("id")
        rows.append([InlineKeyboardButton(
            text=f"{title} — {price}₽",
            callback_data=f"wt:item:{rank}:{acc_id}:{page}"
        )])

    # Навигация
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"wt:page:{rank}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="wt:nop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"wt:page:{rank}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="wt:back")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    header = f"Секция: {rank} rank ({total} шт.)"
    try:
        # если текущее сообщение текстовое — редактируем
        if (cb.message.text or ""):
            if cb.message.text == header:
                await cb.message.edit_reply_markup(reply_markup=kb)
            else:
                await cb.message.edit_text(header, reply_markup=kb)
        else:
            # если текущее сообщение было с фото — создаём новое
            await cb.message.answer(header, reply_markup=kb)
    except TelegramBadRequest as e:
        msg = str(e)
        if "message is not modified" in msg:
            pass
        elif "there is no text in the message to edit" in msg:
            await cb.message.answer(header, reply_markup=kb)
        else:
            raise
    await cb.answer()
