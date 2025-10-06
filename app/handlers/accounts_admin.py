# app/handlers/accounts_admin.py
import os
import re
import logging
from dotenv import load_dotenv

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.states.accounts import AddAccountStates
from app.db import add_account  # для 8 rank (основная БД)
from app.keyboards.admin_wt import admin_choose_rank_kb
from app.db_ranks import insert_account as insert_account_rank  # для 7/6 rank

# Подхватываем .env сразу (важно для ADMIN_USERNAMES)
load_dotenv()

logger = logging.getLogger(__name__)
router = Router(name="accounts_admin")

# -------------------- Вспомогательные --------------------

def _admin_unames() -> set[str]:
    raw = os.getenv("ADMIN_USERNAMES", "") or ""
    parts = re.split(r"[\s,]+", raw.strip())
    return {p.lower() for p in parts if p}

def _is_admin(msg: Message) -> bool:
    admins = _admin_unames()
    if not admins:
        logger.error("ADMIN_USERNAMES пуст — админ-добавление аккаунтов запрещено.")
        return False
    uname = (msg.from_user.username or "").lower()
    return uname in admins

# -------------------- Старт: выбор раздела (rank) --------------------

@router.message(Command("addacc"))
@router.message(F.text.regexp(r"^/addacc(\s|$)"))
async def cmd_addacc(message: Message, state: FSMContext):
    logger.info("Got /addacc from user=%s uname=%s", message.from_user.id, message.from_user.username)
    if not _is_admin(message):
        return await message.reply("⛔ Нет доступа. Настрой ADMIN_USERNAMES в .env")
    await state.clear()
    await state.set_state(AddAccountStates.waiting_rank)
    await message.reply("Выбери раздел (rank) для нового аккаунта:", reply_markup=admin_choose_rank_kb())

@router.callback_query(F.data.startswith("admin:add:rank:"))
async def admin_pick_rank(cb: CallbackQuery, state: FSMContext):
    rank = cb.data.split(":")[-1]  # '8' | '7' | '6'
    category = "WarThunder" if rank == "8" else f"{rank} rank"
    await state.update_data(rank=rank, category=category)
    await state.set_state(AddAccountStates.waiting_creds)
    await cb.message.edit_text("Отправь логин и пароль в формате: <code>login:password</code>", parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "admin:add:cancel")
async def admin_add_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await cb.answer()

# -------------------- Шаг 1: логин:пароль --------------------

@router.message(AddAccountStates.waiting_creds)
async def addacc_creds(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if ":" not in text or len(text.split(":", 1)) < 2:
        return await message.reply("Некорректно. Формат: <code>login:password</code>")
    await state.update_data(creds=text)
    await message.reply("Теперь отправь НАЗВАНИЕ для кнопки (коротко).")
    await state.set_state(AddAccountStates.waiting_button_title)

# -------------------- Шаг 2: название кнопки --------------------

@router.message(AddAccountStates.waiting_button_title)
async def addacc_button_title(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        return await message.reply("Название не может быть пустым. Введи ещё раз.")
    await state.update_data(button_title=name)
    await message.reply("Теперь отправь 📷 ФОТО с описанием в подписи (одно сообщение).")
    await state.set_state(AddAccountStates.waiting_photo)

# -------------------- Шаг 3: фото с подписью --------------------

@router.message(AddAccountStates.waiting_photo, F.photo)
async def addacc_photo(message: Message, state: FSMContext):
    caption = message.caption or ""
    photo_sizes = message.photo or []
    file_id = photo_sizes[-1].file_id if photo_sizes else None
    await state.update_data(photo_file_id=file_id, caption=caption)
    await message.reply("Укажи цену товара в рублях (целое число):")
    await state.set_state(AddAccountStates.waiting_price)

@router.message(AddAccountStates.waiting_photo)
async def addacc_photo_required(message: Message, state: FSMContext):
    await message.reply("Нужно прислать именно фото с подписью (одним сообщением).")

# -------------------- Шаг 4: цена --------------------

@router.message(AddAccountStates.waiting_price)
async def addacc_price(message: Message, state: FSMContext):
    try:
        price = int((message.text or "").strip())
        if price <= 0:
            raise ValueError
    except Exception:
        return await message.reply("Цена должна быть целым числом больше 0. Введи ещё раз.")

    data = await state.get_data()
    rank = data.get("rank", "8")
    category = data.get("category", "WarThunder")
    creds = data.get("creds")
    button_title = data.get("button_title")
    photo_file_id = data.get("photo_file_id")
    caption = data.get("caption")

    logger.info("Creating account: rank=%s cat=%s title=%r price=%s by=%s",
                rank, category, button_title, price, message.from_user.id)

    if rank == "8":
        acc_id = await add_account(
            category=category,
            button_title=button_title,
            creds=creds,
            photo_file_id=photo_file_id,
            caption=caption,
            price_rub=price,
            created_by=message.from_user.id
        )
    else:
        acc_id = await insert_account_rank(
            rank,
            button_title=button_title,
            creds=creds,
            photo_file_id=photo_file_id,
            caption=caption,
            price_rub=price,
            category=category
        )

    await state.clear()
    await message.reply(
        "✅ Аккаунт добавлен.\n"
        f"ID: <code>{acc_id}</code>\n"
        f"Раздел: <b>{rank} rank</b>\n"
        f"Категория: <b>{category}</b>\n"
        f"Название: <b>{button_title}</b>\n"
        f"Цена: <b>{price} ₽</b>"
    )
