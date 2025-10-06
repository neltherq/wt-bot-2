from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def shop_menu_kb() -> InlineKeyboardMarkup:
    # оставили только Каталог и Назад
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Каталог", callback_data="shop:catalog")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:back")],
    ])

def categories_kb() -> InlineKeyboardMarkup:
    # категории заглушки — как было
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Аккаунты", callback_data="cat:accounts")],
        [InlineKeyboardButton(text="🪙 Подписки", callback_data="cat:subs")],
        [InlineKeyboardButton(text="🔑 Ключи", callback_data="cat:keys")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:menu")],
    ])

def back_kb(cb: str = "shop:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=cb)]
    ])
