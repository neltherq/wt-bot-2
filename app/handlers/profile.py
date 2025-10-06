# app/handlers/profile.py
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from app.db import ensure_user, get_user, get_balance_rub
from app.keyboards.main_menu import main_kb
from app.utils.format import fmt_username

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Привет! Это панель управления.\n"
        "— Нажми «👤 Мой профиль» чтобы посмотреть данные.\n"
        "— Нажми «💰 Баланс» чтобы увидеть баланс и пополнение.",
        reply_markup=main_kb(),
    )

@router.message(Command("profile"))
@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    urec = await get_user(message.from_user.id)
    bal = await get_balance_rub(message.from_user.id)

    created = urec.get("created_at") if urec else "—"
    updated = urec.get("updated_at") if urec else "—"
    username = message.from_user.username or "—"

    text = (
        "🧾 <b>Профиль</b>\n"
        f"👤 Имя: {fmt_username(message.from_user)}\n"
        f"🆔 User ID: <code>{message.from_user.id}</code>\n"
        f"🔗 Username: @{username}\n"
        f"💰 Баланс: <b>{bal} ₽</b>\n"
        f"📅 Создан: {created}\n"
        f"♻️ Обновлён: {updated}\n"
    )
    await message.answer(text, reply_markup=main_kb())
