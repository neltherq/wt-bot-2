# app/middlewares/debounce.py
import asyncio
import logging
from typing import Any, Callable, Dict, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery

logger = logging.getLogger(__name__)

class DebounceMiddleware(BaseMiddleware):
    """
    Пропускает апдейты от одного пользователя, если за короткое окно пришёл более новый апдейт.
    Идеально для ситуации, когда бот был оффлайн, а юзер натыкал кучу кнопок.
    Работает так:
      - на каждый апдейт ждём небольшое окно (по умолчанию 500мс),
      - если за это время пришёл более новый апдейт от того же юзера — текущий игнорим.
    """

    def __init__(self, window_ms: int = 500):
        super().__init__()
        self.window = window_ms / 1000.0
        self._last_seen_id: Dict[int, int] = {}  # user_id -> last update_id

    def _get_user_and_update_id(self, update: Update) -> tuple[Optional[int], Optional[int]]:
        uid = None
        if isinstance(update.event, Message) and update.event.from_user:
            uid = update.event.from_user.id
        elif isinstance(update.event, CallbackQuery) and update.event.from_user:
            uid = update.event.from_user.id
        # update.update_id доступен у Update как атрибут
        up_id = getattr(update, "update_id", None)
        return uid, up_id

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        uid, up_id = self._get_user_and_update_id(event)
        if uid is None or up_id is None:
            # системные/служебные апдейты — пропускаем без дебаунса
            return await handler(event, data)

        # сохраняем «текущий как последний увиденный»
        prev = self._last_seen_id.get(uid)
        self._last_seen_id[uid] = max(up_id, prev or up_id)

        # даём окну времени «накопиться» более новым апдейтам
        await asyncio.sleep(self.window)

        # если за окно появился более новый — игнорируем этот апдейт
        latest = self._last_seen_id.get(uid, up_id)
        if up_id < latest:
            # тихо пропускаем без ответа
            logger.info("Debounce: skip update %s for user %s (latest=%s)", up_id, uid, latest)
            return None

        # это самый свежий апдейт пользователя — обрабатываем
        return await handler(event, data)
