#!/usr/bin/env python3
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from config import BOT_TOKEN
from database import db  # ← импортируем db, а не init_db

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
from handlers import start, profile, economy, games, shop, vip, tag, ai_assistant

dp.include_routers(
    start.router,
    profile.router,
    economy.router,
    games.router,
    shop.router,
    vip.router,
    tag.router,
    ai_assistant.router,
)

async def on_startup():
    await db.init()  # ← вызываем db.init(), а не init_db()
    logger.info("✅ NEXUS Bot v5.0 запущен!")

async def on_shutdown():
    await db.close()
    logger.info("👋 Бот остановлен")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
