# app/handlers/warthunder.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from app.keyboards.wt import wt_ranks_keyboard
from app.keyboards.accounts import MAX_ROWS  # используем лимит строк на страницу как общий per_page

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

# ---------------------------------------------------------------------
# ВХОД: кнопка "🎮 WarThunder" в главном меню
# ---------------------------------------------------------------------
@router.message(F.text == "🎮 WarThunder")
async def wt_entry(msg: Message):
    await ensure_user(msg.from_user.id, msg.from_user.username)
    await msg.answer("Выберите раздел WarThunder:", reply_markup=wt_ranks_keyboard())

# ---------------------------------------------------------------------
# ВЫБОР РАНГА
# ---------------------------------------------------------------------
@router.callback_query(F.data.startswith("wt:rank:"))
async def wt_rank_select(cb: CallbackQuery):
    _, _, rank = cb.data.split(":")  # '8'|'7'|'6'
    page = 1
    per_page = MAX_ROWS

    # Загружаем список лотов для выбранного ранга
    if rank == "8":
        total = await count_rank8_accounts("WarThunder")
        items = await list_rank8_accounts("WarThunder", limit=per_page, offset=(page - 1) * per_page)
    else:
        total = await count_rank_accounts(rank)
        items = await list_rank_accounts(rank, limit=per_page, offset=(page - 1) * per_page)

    if not items:
        new_text = f"Пока пусто в {rank} rank."
        try:
            if (cb.message.text or "") == new_text:
                await cb.message.edit_reply_markup(reply_markup=wt_ranks_keyboard())
            else:
                await cb.message.edit_text(new_text, reply_markup=wt_ranks_keyboard())
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
        await cb.answer()
        return

    # Строим простой список без пагинации (по MAX_ROWS строк)
    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        title = it.get("button_title")
        price = it.get("price_rub")
        acc_id = it.get("id")
        rows.append([InlineKeyboardButton(text=f"{title} — {price}₽", callback_data=f"wt:item:{rank}:{acc_id}")])

    # Добавим «назад»
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="wt:back")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    header = f"Секция: {rank} rank ({total} шт.)"
    try:
        if (cb.message.text or "") == header:
            await cb.message.edit_reply_markup(reply_markup=kb)
        else:
            await cb.message.edit_text(header, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await cb.answer()

# ---------------------------------------------------------------------
# НАЗАД К ВЫБОРУ РАНГОВ
# ---------------------------------------------------------------------
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

# ---------------------------------------------------------------------
# ОТКРЫТИЕ КАРТОЧКИ ТОВАРА
# ---------------------------------------------------------------------
@router.callback_query(F.data.startswith("wt:item:"))
async def wt_item(cb: CallbackQuery):
    _, _, rank, acc_id_str = cb.data.split(":")
    acc_id = int(acc_id_str)

    # Получаем лот из нужной БД
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

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить", callback_data=f"wt:buy:{rank}:{row['id']}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wt:rank:{rank}")],
    ])

    try:
        if row.get("photo_file_id"):
            try:
                await cb.message.edit_media(InputMediaPhoto(media=row["photo_file_id"], caption=caption), reply_markup=kb)
            except TelegramBadRequest:
                # если было текстовое сообщение — заменим на текст
                await cb.message.edit_text(caption, reply_markup=kb)
        else:
            await cb.message.edit_text(caption, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await cb.answer()

# ---------------------------------------------------------------------
# ПОКУПКА
# ---------------------------------------------------------------------
@router.callback_query(F.data.startswith("wt:buy:"))
async def wt_buy(cb: CallbackQuery):
    _, _, rank, acc_id_str = cb.data.split(":")
    acc_id = int(acc_id_str)

    if rank == "8":
        # Стандартная покупка через основную БД
        result = await purchase_rank8(cb.from_user.id, acc_id)
        status = result.get("status")
        if status == "ok":
            creds = result["creds"]
            await cb.message.answer(f"Покупка успешна!\nДанные:\n<code>{creds}</code>", parse_mode="HTML")
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

    # 7/6 ранги — покупка через внешние БД
    row = await get_rank_account(rank, acc_id)
    if not row or row.get("status") != "available":
        await cb.answer("Лот недоступен", show_alert=True)
        return

    price = int(row["price_rub"])
    balance = await get_balance_rub(cb.from_user.id)

    if balance < price:
        await cb.answer("Недостаточно средств.", show_alert=True)
        return

    # списываем в основной БД
    await add_balance_rub(cb.from_user.id, -price)
    # помечаем проданным в rank-БД
    await mark_rank_sold(rank, acc_id)

    # отдаём доступы
    creds = row["creds"]
    await cb.message.answer(f"Покупка успешна!\nДанные:\n<code>{creds}</code>", parse_mode="HTML")
    await cb.answer()
