# app/bot.py
import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    User
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.db import init_db, ensure_user, get_user, get_balance_rub, add_balance_rub

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# === reply-клавиатура (нижняя панель) ===
def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="💰 Баланс")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

# === inline-кнопки для экрана баланса ===
def balance_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="balance:back"),
            InlineKeyboardButton(text="➕ Пополнить", callback_data="balance:deposit"),
        ]
    ])

# === inline-кнопки выбора метода оплаты ===
def pay_methods_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 lolz", callback_data="pay:method:lolz")]
    ])

def fmt_username(u: User) -> str:
    parts = []
    if getattr(u, "first_name", None):
        parts.append(u.first_name)
    if getattr(u, "last_name", None):
        parts.append(u.last_name)
    name = " ".join(parts) if parts else (u.username or f"id{u.id}")
    if u.username:
        name = f"{name} (@{u.username})"
    return name

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Привет! Это панель управления.\n"
        "— Нажми «👤 Мой профиль» чтобы посмотреть данные.\n"
        "— Нажми «💰 Баланс» чтобы увидеть баланс и пополнение.",
        reply_markup=main_kb(),
    )

@dp.message(Command("profile"))
@dp.message(F.text == "👤 Мой профиль")
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

# === Экран баланса (одним сообщением + две inline-кнопки снизу) ===
@dp.message(Command("balance"))
@dp.message(F.text == "💰 Баланс")
async def show_balance(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    bal = await get_balance_rub(message.from_user.id)
    await message.answer(
        f"💰 <b>Баланс</b>: {bal} ₽",
        reply_markup=balance_actions_kb()
    )

# Назад — удаляем сообщение баланса
@dp.callback_query(F.data == "balance:back")
async def cb_balance_back(cq):
    await cq.answer("Назад")
    try:
        await cq.message.delete()
    except Exception:
        # если вдруг нельзя удалить (нет прав/уже удалено) — просто скрываем кнопки
        await cq.message.edit_reply_markup(reply_markup=None)

# Пополнить — показываем выбор метода оплаты
@dp.callback_query(F.data == "balance:deposit")
async def cb_balance_deposit(cq):
    await cq.answer()
    await cq.message.edit_text(
        "Выберите метод оплаты:",
        reply_markup=pay_methods_kb()
    )

# Нажали «lolz» — пока заглушка
@dp.callback_query(F.data == "pay:method:lolz")
async def cb_pay_method_lolz(cq):
    await cq.answer("Метод оплаты: lolz (скоро подключим)")
    # можно оставить то же сообщение, либо дополнить:
    # await cq.message.edit_text("Метод оплаты: lolz\n(интеграция скоро будет)", reply_markup=None)

# Временная команда пополнения для тестов (оставляем как было)
@dp.message(Command("deposit"))
async def cmd_deposit(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("Укажи сумму в рублях, например: /deposit 100", reply_markup=main_kb())

    try:
        delta_rub = int(parts[1])
        if delta_rub <= 0:
            return await message.reply("Сумма должна быть больше 0.", reply_markup=main_kb())
    except ValueError:
        return await message.reply("Укажи целое число рублей. Пример: /deposit 150", reply_markup=main_kb())

    await add_balance_rub(message.from_user.id, delta_rub)
    bal = await get_balance_rub(message.from_user.id)
    await message.answer(f"Зачислено: {delta_rub} ₽\nТекущий баланс: {bal} ₽", reply_markup=main_kb())

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден в .env")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
