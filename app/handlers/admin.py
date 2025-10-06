# app/handlers/admin.py
import os
import logging
import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from app.db import get_user_by_username, add_balance_rub_by_username

# Грузим .env прямо тут, чтобы не зависеть от порядка импортов
load_dotenv()

logger = logging.getLogger(__name__)
router = Router()

def _get_admin_unames() -> set[str]:
    """Читает ADMIN_USERNAMES из окружения каждый раз (регистронезависимо)."""
    raw = os.getenv("ADMIN_USERNAMES", "") or ""
    # допускаем разделение запятой и/или пробелами
    parts = re.split(r"[,\s]+", raw.strip())
    return {p.lower() for p in parts if p}

def _is_admin(msg: Message) -> bool:
    admins = _get_admin_unames()
    if not admins:
        # ПУСТО — никому нельзя
        logger.error("ADMIN_USERNAMES пуст — админ-команды ЗАПРЕЩЕНЫ для всех.")
        return False
    uname = (msg.from_user.username or "").lower()
    return uname in admins

def _parse_text_args(text: str):
    # Форматы: "дать username 100" или "забрать @username 50"
    m = re.match(r"^\s*(?:дать|забрать)\s+@?([A-Za-z0-9_]{5,32})\s+(\d+)\s*$", text, flags=re.IGNORECASE)
    if not m:
        return None, None
    uname = m.group(1)
    amount = int(m.group(2))
    return uname, amount

# ---------- /give ----------
@router.message(Command("give"))
async def cmd_give(message: Message):
    if not _is_admin(message):
        return await message.reply("⛔ Нет доступа. Настрой ADMIN_USERNAMES в .env")
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply("Использование: /give <username> <amount>\nНапр.: /give @user 100")
    uname = parts[1].lstrip("@")
    try:
        amount = int(parts[2])
        if amount <= 0:
            raise ValueError
    except ValueError:
        return await message.reply("Сумма должна быть целым числом > 0")

    user = await get_user_by_username(uname)
    if not user:
        return await message.reply(f"Пользователь @{uname} не найден (не писал боту).")

    new_balance, applied = await add_balance_rub_by_username(uname, amount)
    await message.reply(f"✅ Выдал @{uname} +{applied} ₽\nНовый баланс: {new_balance} ₽")

# ---------- /take ----------
@router.message(Command("take"))
async def cmd_take(message: Message):
    if not _is_admin(message):
        return await message.reply("⛔ Нет доступа. Настрой ADMIN_USERNAMES в .env")
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply("Использование: /take <username> <amount>\nНапр.: /take user 50")
    uname = parts[1].lstrip("@")
    try:
        amount = int(parts[2])
        if amount <= 0:
            raise ValueError
    except ValueError:
        return await message.reply("Сумма должна быть целым числом > 0")

    user = await get_user_by_username(uname)
    if not user:
        return await message.reply(f"Пользователь @{uname} не найден (не писал боту).")

    new_balance, applied = await add_balance_rub_by_username(uname, -amount)  # applied отрицательный
    await message.reply(f"✅ Забрал у @{uname} {-applied} ₽\nНовый баланс: {new_balance} ₽")

# ---------- Текст «дать ...» ----------
@router.message(F.text.regexp(re.compile(r"(?i)^дать\s+@?[A-Za-z0-9_]{5,32}\s+\d+$")))
async def txt_give(message: Message):
    if not _is_admin(message):
        return await message.reply("⛔ Нет доступа. Настрой ADMIN_USERNAMES в .env")
    uname, amount = _parse_text_args(message.text)
    if not uname:
        return await message.reply("Использование: дать <username> <amount>\nНапр.: дать @user 100")

    user = await get_user_by_username(uname)
    if not user:
        return await message.reply(f"Пользователь @{uname} не найден (не писал боту).")

    new_balance, applied = await add_balance_rub_by_username(uname, amount)
    await message.reply(f"✅ Выдал @{uname} +{applied} ₽\nНовый баланс: {new_balance} ₽")

# ---------- Текст «забрать ...» ----------
@router.message(F.text.regexp(re.compile(r"(?i)^забрать\s+@?[A-Za-z0-9_]{5,32}\s+\d+$")))
async def txt_take(message: Message):
    if not _is_admin(message):
        return await message.reply("⛔ Нет доступа. Настрой ADMIN_USERNAMES в .env")
    uname, amount = _parse_text_args(message.text)
    if not uname:
        return await message.reply("Использование: забрать <username> <amount>\nНапр.: забрать user 50")

    user = await get_user_by_username(uname)
    if not user:
        return await message.reply(f"Пользователь @{uname} не найден (не писал боту).")

    new_balance, applied = await add_balance_rub_by_username(uname, -amount)
    await message.reply(f"✅ Забрал у @{uname} {-applied} ₽\nНовый баланс: {new_balance} ₽")
