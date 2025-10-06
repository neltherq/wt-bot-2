# app/handlers/balance.py
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.db import ensure_user, get_balance_rub
from app.keyboards.balance import balance_actions_kb

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("balance"))
@router.message(F.text == "💰 Баланс")
async def show_balance(message: Message):
    try:
        await ensure_user(message.from_user.id, message.from_user.username)
        bal = await get_balance_rub(message.from_user.id)
        await message.answer(f"💰 <b>Баланс</b>: {bal} ₽", reply_markup=balance_actions_kb())
    except Exception:
        logger.exception("show_balance failed")

@router.callback_query(F.data == "balance:back")
async def cb_balance_back(cq: CallbackQuery):
    try:
        await cq.answer("Назад")
        try:
            await cq.message.delete()
        except Exception:
            await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("balance:back handler failed")
