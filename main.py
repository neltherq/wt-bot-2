# main.py
import os
import asyncio
import logging
from dotenv import load_dotenv
from app.handlers.accounts_admin import router as accounts_admin_router
from app.handlers.warthunder import router as warthunder_router
from app.handlers.change_admin import router as change_admin_router

# 1) Сначала грузим .env, чтобы ADMIN_USERNAMES и прочее подхватилось в хендлерах
load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand  # 👈 добавили

from app.db import init_db
from app.middlewares.debounce import DebounceMiddleware

# Импортируем роутеры напрямую, чтобы не зависеть от __init__.py
from app.handlers.menu import router as menu_router
from app.handlers.profile import router as profile_router
from app.handlers.balance import router as balance_router
from app.handlers.deposit import router as deposit_router
from app.handlers.admin import router as admin_router
from app.handlers.errors import router as errors_router
from app.handlers.stats_admin import router as stats_admin_router

# ------------------ Логирование ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)

# ------------------ Бот / Диспетчер ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Дебаунс: отвечаем только на самый свежий апдейт от пользователя в коротком окне
dp.update.middleware(DebounceMiddleware(window_ms=600))  # подбери 400–800 мс по ощущениям

# Подключаем роутеры
dp.include_router(menu_router)     # главное меню и магазин
dp.include_router(profile_router)  # профиль
dp.include_router(balance_router)  # баланс
dp.include_router(deposit_router)  # пополнение (lolz)
dp.include_router(admin_router)    # админ-команды (дать/забрать)
dp.include_router(errors_router)   # глобальный обработчик ошибок
dp.include_router(accounts_admin_router)
dp.include_router(warthunder_router)
dp.include_router(change_admin_router)
dp.include_router(stats_admin_router)

# ------------------ Команды бота (кнопка меню) ------------------
async def set_default_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Restart bot 🤖"),
        # если захочешь, можно добавить:
        # BotCommand(command="menu", description="Главное меню"),
        # BotCommand(command="balance", description="Проверить баланс"),
    ]
    await bot.set_my_commands(commands)

# ------------------ Точка входа ------------------
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден в .env")

    await init_db()

    # Установим команды для кнопки меню
    await set_default_commands(bot)

    # Вариант радикальный (удалит ВСЕ накопившиеся апдейты у Telegram-сервера):
    # await bot.delete_webhook(drop_pending_updates=True)

    # Некоторые версии aiogram 3 поддерживают skip_updates=True (пропустить очередь при старте):
    # await dp.start_polling(bot, skip_updates=True)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
