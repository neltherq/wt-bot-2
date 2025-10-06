# app/handlers/stats_admin.py
import os, re, logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.db import (
    count_users_total,
    count_users_this_week,
    count_users_this_month,
)

logger = logging.getLogger(__name__)
router = Router(name="stats_admin")

def _admin_unames() -> set[str]:
    raw = os.getenv("ADMIN_USERNAMES", "") or ""
    parts = re.split(r"[\s,]+", raw.strip())
    return {p.lower() for p in parts if p}

def _is_admin(msg: Message) -> bool:
    admins = _admin_unames()
    if not admins:
        logger.error("ADMIN_USERNAMES пуст — /getstats недоступна.")
        return False
    uname = (msg.from_user.username or "").lower()
    return uname in admins

@router.message(Command("getstats"))
async def getstats_cmd(message: Message):
    if not _is_admin(message):
        return await message.reply("⛔ Нет доступа.")
    total = await count_users_total()
    week  = await count_users_this_week()
    month = await count_users_this_month()

    text = (
        "<b>Статистика пользователей</b>\n"
        f"• Всего: <b>{total}</b>\n"
        f"• За 7 дней: <b>{week}</b>\n"
        f"• В этом месяце: <b>{month}</b>\n"
    )
    await message.reply(text)
