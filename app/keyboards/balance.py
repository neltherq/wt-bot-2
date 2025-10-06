# app/keyboards/balance.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def balance_actions_kb() -> InlineKeyboardMarkup:
    # Кнопки по одной в строке → широкие
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="balance:back")],
        [InlineKeyboardButton(text="➕ Пополнить", callback_data="balance:deposit")],
    ])

def back_kb(callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback)]
    ])

def pay_methods_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 lolz", callback_data="pay:method:lolz")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="pay:back")]
    ])

def pay_lolz_kb(pay_url: str, comment: str) -> InlineKeyboardMarkup:
    # URL-кнопка «Оплатить в lolz» + «Проверить оплату» (по comment) + «Назад»
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить в lolz", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"pay:check:{comment}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="pay:back")],
    ])
