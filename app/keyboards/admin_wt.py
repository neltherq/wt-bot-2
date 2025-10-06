from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_choose_rank_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="8 rank", callback_data="admin:add:rank:8")],
        [InlineKeyboardButton(text="7 rank", callback_data="admin:add:rank:7")],
        [InlineKeyboardButton(text="6 rank", callback_data="admin:add:rank:6")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:add:cancel")]
    ])
