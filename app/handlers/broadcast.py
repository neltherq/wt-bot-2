# app/handlers/broadcast.py
import asyncio
import logging
from typing import Iterable

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

from app.states.broadcast import BroadcastStates
from app.db_broadcast import (
    is_admin,
    get_all_recipient_ids,
    upsert_recipient,
    create_broadcast,
    finalize_broadcast,
    update_progress,
    add_delivery_result,
)

router = Router()
log = logging.getLogger(__name__)

def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Отправить", callback_data="broadcast:send")],
        [InlineKeyboardButton(text="❌ Отмена",   callback_data="broadcast:cancel")],
    ])

# — рекомендуем вызывать где-то в /start, чтобы записывать пользователей как получателей:
@router.message(Command("start"))
async def track_recipient_on_start(message: Message):
    # не ломаем твой основной /start — просто отмечаем юзера как получателя рассылки
    try:
        await upsert_recipient(message.from_user.id, active=True)
    except Exception:
        log.exception("failed to upsert recipient")

@router.message(Command("send"))
async def cmd_send(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return await message.reply("Команда доступна только админам.")
    await state.set_state(BroadcastStates.waiting_content)
    await message.answer(
        "Отправь сюда **сообщение для рассылки** (текст/фото/видео/документ/гиф/голос/альбом).\n"
        "После этого я покажу превью и попрошу подтверждение.",
        parse_mode="Markdown"
    )

@router.message(BroadcastStates.waiting_content)
async def got_content(message: Message, state: FSMContext):
    # сохраняем «источник» для копирования
    await state.update_data(src_chat_id=message.chat.id, src_msg_id=message.message_id)
    await state.set_state(BroadcastStates.confirm)

    # превью — просто копируем сообщение администратору
    try:
        await message.copy_to(chat_id=message.chat.id)
    except Exception:
        pass

    await message.answer("Это превью рассылки. Отправляем?", reply_markup=_confirm_kb())

@router.callback_query(BroadcastStates.confirm, F.data == "broadcast:cancel")
async def cancel_broadcast(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.edit_text("Рассылка отменена.")
    await cq.answer()

@router.callback_query(BroadcastStates.confirm, F.data == "broadcast:send")
async def do_broadcast(cq: CallbackQuery, state: FSMContext):
    if not await is_admin(cq.from_user.id):
        return await cq.answer("Только для админов", show_alert=True)

    data = await state.get_data()
    src_chat_id = data["src_chat_id"]
    src_msg_id  = data["src_msg_id"]

    # собираем адресатов
    user_ids: Iterable[int] = await get_all_recipient_ids(only_active=True)
    total = len(user_ids)
    if total == 0:
        await cq.answer("Нет получателей", show_alert=True)
        return

    # запись о рассылке
    bcast_id = await create_broadcast(
        author_id=cq.from_user.id, src_chat_id=src_chat_id, src_msg_id=src_msg_id
    )

    await cq.answer("Стартую рассылку…")
    await cq.message.edit_text(f"Рассылка запущена для {total} получателей…")

    sent = failed = 0
    sem = asyncio.Semaphore(20)  # ограничим параллелизм

    async def _send_one(uid: int):
        nonlocal sent, failed
        try:
            async with sem:
                await cq.bot.copy_message(chat_id=uid, from_chat_id=src_chat_id, message_id=src_msg_id)
            sent += 1
            await update_progress(bcast_id, sent_inc=1)
            await add_delivery_result(bcast_id, uid, status="ok")
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            return await _send_one(uid)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            failed += 1
            await update_progress(bcast_id, fail_inc=1)
            await add_delivery_result(bcast_id, uid, status="fail", error=str(e)[:500])
        except Exception as e:
            log.exception("broadcast fail user=%s: %s", uid, e)
            failed += 1
            await update_progress(bcast_id, fail_inc=1)
            await add_delivery_result(bcast_id, uid, status="fail", error=str(e)[:500])

    tasks = [asyncio.create_task(_send_one(uid)) for uid in user_ids]
    await asyncio.gather(*tasks)

    await finalize_broadcast(bcast_id, total=total, status="done")
    await state.clear()
    await cq.message.edit_text(f"Готово. Разослано: {sent}/{total}. Ошибок: {failed}.")
