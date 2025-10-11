# send_message.py
import asyncio
import os
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("8218860438:AAH52lOmbzAzNpt5HEbJ_etVkjOk1jgJmcU", "")

# 🔹 Твой Telegram ID (или ID получателя)
ADMIN_ID = 904268457

async def main():
    bot = Bot(token=BOT_TOKEN)
    # просто текст
    await bot.send_message(ADMIN_ID, "🔥 Привет! Это тестовое рекламное сообщение от бота!")
    # или фото
    # await bot.send_photo(ADMIN_ID, "https://example.com/banner.jpg", caption="🛩 WarThunder Market!")
    await bot.session.close()

asyncio.run(main())
