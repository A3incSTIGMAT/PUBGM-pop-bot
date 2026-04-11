#!/usr/bin/env python3
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from config import BOT_TOKEN
from database import db
from utils.auto_delete import track_and_delete

load_dotenv()

os.makedirs("/data", exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set!")
    exit(1)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Импорт роутеров
from handlers.start import router as start_router
from handlers.profile import router as profile_router
from handlers.economy import router as economy_router
from handlers.games import router as games_router
from handlers.tag import router as tag_router
from handlers.ai_assistant import router as ai_assistant_router
from handlers.vip import router as vip_router
from handlers.referral import router as referral_router

dp.include_routers(
    start_router,
    profile_router,
    economy_router,
    games_router,
    tag_router,
    ai_assistant_router,
    vip_router,
    referral_router,
)


# Middleware для автоудаления сообщений
@dp.message()
async def auto_delete_middleware(message: types.Message):
    """Автоматическое удаление сообщений (кроме команд)"""
    # Пропускаем команды, которые не нужно удалять
    if message.text and message.text.startswith('/'):
        return
    
    # Для остальных сообщений удаляем через 30 секунд
    asyncio.create_task(track_and_delete(bot, message.chat.id, message.from_user.id, message.message_id, 30))


async def on_startup():
    await db.init()
    logger.info("✅ NEXUS Bot v5.0 запущен на Amvera!")


async def on_shutdown():
    await db.close()
    logger.info("👋 Бот остановлен")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
