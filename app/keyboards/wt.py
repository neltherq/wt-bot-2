from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def wt_ranks_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="8 rank", callback_data="wt:rank:8")],
        [InlineKeyboardButton(text="7 rank", callback_data="wt:rank:7")],
        [InlineKeyboardButton(text="6 rank", callback_data="wt:rank:6")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main:menu")]
    ])
