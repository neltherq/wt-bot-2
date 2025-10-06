# app/keyboards/main_menu.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="🛍 Магазин")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🛒 Корзина"), KeyboardButton(text="📦 Мои покупки")],
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="📞 Поддержка")],
        ]
    )
