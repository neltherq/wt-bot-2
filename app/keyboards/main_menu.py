from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="🎮 WarThunder")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="📞 Поддержка")],
        ]
    )

def main_kb() -> ReplyKeyboardMarkup:
    return main_menu_kb()

__all__ = ["main_menu_kb", "main_kb"]
