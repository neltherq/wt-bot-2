# app/handlers/errors.py
import logging
from aiogram import Router
from aiogram.exceptions import TelegramBadRequest

router = Router()
logger = logging.getLogger(__name__)

@router.errors()
async def errors_handler(event: object, exception: Exception):
    # тихо игнорим частые "косметические" ошибки
    if isinstance(exception, TelegramBadRequest):
        msg = str(exception)
        if "message is not modified" in msg:
            logger.debug("Ignored: %s", msg)
            return True
        if "there is no text in the message to edit" in msg:
            logger.debug("Ignored (edit_text on media): %s", msg)
            return True

    # остальное логируем
    logger.exception("Unhandled exception: %r (event=%r)", exception, event)
    # можно оповестить пользователя если это callback
    try:
        from aiogram.types import CallbackQuery
        if hasattr(event, "answer") and isinstance(event, CallbackQuery):
            await event.answer("Ошибка. Попробуйте ещё раз.", show_alert=True)
    except Exception:
        pass
    return True  # считаем обработанным
