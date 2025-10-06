# app/handlers/change_admin.py
import os
import re
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from app.keyboards.wt import wt_ranks_keyboard
from app.db import (
    list_accounts as list_rank8_accounts,
    count_accounts as count_rank8_accounts,
    get_account_by_id as get_rank8_account,
    delete_account as delete_rank8_account,
    update_account_caption as update_rank8_caption,
)
from app.db_ranks import (
    list_available as list_rank_accounts,
    count_available as count_rank_accounts,
    get_account as get_rank_account,
    delete_account as delete_rank_account,
    update_caption as update_rank_caption,
)
logger = logging.getLogger(__name__)
router = Router(name="change_admin")


# -------------------- FSM --------------------
class ChangeLotFSM(StatesGroup):
    waiting_rank = State()
    waiting_new_caption = State()


# -------------------- checks --------------------
def _admin_unames() -> set[str]:
    raw = os.getenv("ADMIN_USERNAMES", "") or ""
    parts = re.split(r"[\s,]+", raw.strip())
    return {p.lower() for p in parts if p}

def _is_admin(msg: Message) -> bool:
    admins = _admin_unames()
    if not admins:
        logger.error("ADMIN_USERNAMES пуст — /change недоступна.")
        return False
    uname = (msg.from_user.username or "").lower()
    return uname in admins


# -------------------- keyboards --------------------
def _lots_kb(rank: str, items: list[dict], page: int, pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        rows.append([InlineKeyboardButton(
            text=f"#{it['id']} — {it.get('button_title','')} — {it.get('price_rub','')}₽",
            callback_data=f"chg:item:{rank}:{it['id']}:{page}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"chg:page:{rank}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="chg:nop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"chg:page:{rank}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Ранги", callback_data="chg:ranks")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _lot_actions_kb(rank: str, acc_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"chg:editcap:{rank}:{acc_id}:{page}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"chg:del:{rank}:{acc_id}:{page}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chg:page:{rank}:{page}")]
    ])


# -------------------- entry --------------------
@router.message(Command("change"))
async def change_entry(msg: Message, state: FSMContext):
    if not _is_admin(msg):
        return await msg.reply("⛔ Нет доступа.")
    await state.set_state(ChangeLotFSM.waiting_rank)
    await msg.answer("Выбери раздел (rank) для редактирования:", reply_markup=wt_ranks_keyboard())


@router.callback_query(F.data == "chg:ranks")
async def back_to_ranks(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ChangeLotFSM.waiting_rank)
    try:
        await cb.message.edit_text("Выбери раздел (rank) для редактирования:", reply_markup=wt_ranks_keyboard())
    except TelegramBadRequest:
        await cb.message.answer("Выбери раздел (rank) для редактирования:", reply_markup=wt_ranks_keyboard())
    await cb.answer()


# -------------------- list pages --------------------
@router.callback_query(F.data.startswith("wt:rank:"), ChangeLotFSM.waiting_rank)
async def chg_pick_rank(cb: CallbackQuery, state: FSMContext):
    _, _, rank = cb.data.split(":")
    await state.update_data(rank=rank)
    await _render_list(cb, rank=rank, page=1)

@router.callback_query(F.data.startswith("chg:page:"))
async def chg_page(cb: CallbackQuery):
    _, _, rank, page_str = cb.data.split(":")
    await _render_list(cb, rank=rank, page=int(page_str))


async def _render_list(cb: CallbackQuery, *, rank: str, page: int):
    per_page = 10
    if rank == "8":
        total = await count_rank8_accounts("WarThunder")
        items = await list_rank8_accounts("WarThunder", limit=per_page, offset=(page-1)*per_page)
    else:
        total = await count_rank_accounts(rank)
        items = await list_rank_accounts(rank, limit=per_page, offset=(page-1)*per_page)

    if total == 0:
        await cb.answer(f"Раздел {rank} rank пуст.", show_alert=True)
        return

    pages = max(1, (total + per_page - 1)//per_page)
    if page > pages:
        await cb.answer(f"Страницы {page} не существует", show_alert=True)
        return

    kb = _lots_kb(rank, items, page, pages)
    header = f"Редактирование: {rank} rank ({total} шт.)"
    try:
        if (cb.message.text or ""):
            if cb.message.text == header:
                await cb.message.edit_reply_markup(reply_markup=kb)
            else:
                await cb.message.edit_text(header, reply_markup=kb)
        else:
            await cb.message.answer(header, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(header, reply_markup=kb)
    await cb.answer()


# -------------------- lot card with admin actions --------------------
@router.callback_query(F.data.startswith("chg:item:"))
async def chg_item(cb: CallbackQuery):
    _, _, rank, acc_id_str, page_str = cb.data.split(":")
    acc_id = int(acc_id_str)
    page = int(page_str)

    row = await (get_rank8_account(acc_id) if rank == "8" else get_rank_account(rank, acc_id))
    if not row:
        await cb.answer("Лот не найден.", show_alert=True)
        return

    caption = (row.get("caption") or "").strip()
    title = row.get("button_title") or ""
    price = row.get("price_rub")
    text = (
        f"<b>#{row['id']}</b> • {title}\n"
        f"Цена: {price}₽\n"
        f"Rank: {rank}\n\n"
        f"{caption or '<i>Описание отсутствует</i>'}"
    )
    kb = _lot_actions_kb(rank, acc_id, page)

    try:
        if (cb.message.text or ""):
            await cb.message.edit_text(text, reply_markup=kb)
        else:
            await cb.message.answer(text, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


# -------------------- delete --------------------
@router.callback_query(F.data.startswith("chg:del:"))
async def chg_delete(cb: CallbackQuery):
    _, _, rank, acc_id_str, page_str = cb.data.split(":")
    acc_id = int(acc_id_str)
    page = int(page_str)

    # реальное удаление (hard delete). Если хочешь soft — поменяй на статус hidden.
    if rank == "8":
        ok = await delete_rank8_account(acc_id)
    else:
        ok = await delete_rank_account(rank, acc_id)

    if not ok:
        await cb.answer("Не удалось удалить (возможно, уже удалён).", show_alert=True)
        return

    await cb.answer("Лот удалён.", show_alert=True)
    # перерисуем список
    await _render_list(cb, rank=rank, page=page)


# -------------------- edit caption --------------------
@router.callback_query(F.data.startswith("chg:editcap:"))
async def chg_edit_caption_start(cb: CallbackQuery, state: FSMContext):
    _, _, rank, acc_id_str, page_str = cb.data.split(":")
    await state.update_data(rank=rank, acc_id=int(acc_id_str), page=int(page_str))
    await state.set_state(ChangeLotFSM.waiting_new_caption)
    await cb.message.answer("Отправь новое описание (текст).")
    await cb.answer()

@router.message(ChangeLotFSM.waiting_new_caption)
async def chg_edit_caption_apply(msg: Message, state: FSMContext):
    data = await state.get_data()
    rank = data["rank"]
    acc_id = data["acc_id"]
    page = data["page"]
    new_caption = (msg.text or "").strip()

    if rank == "8":
        ok = await update_rank8_caption(acc_id, new_caption)
    else:
        ok = await update_rank_caption(rank, acc_id, new_caption)

    await state.clear()
    if not ok:
        return await msg.answer("Не удалось обновить описание.")
    await msg.answer("Описание обновлено ✅")
    # показать карточку снова
    fake_cb = CallbackQuery(id="0", from_user=msg.from_user, chat_instance="0", data=f"chg:item:{rank}:{acc_id}:{page}", message=msg)  # не будет использовано
