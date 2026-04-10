import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database import db

DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не задан в переменных окружения!")
    exit(1)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==================== ИМПОРТЫ РОУТЕРОВ ====================
# Существующие роутеры
from handlers.start import router as start_router
from handlers.profile import router as profile_router
from handlers.economy import router as economy_router
from handlers.games import router as games_router
from handlers.moderation import router as moderation_router
from handlers.ai_assistant import router as ai_assistant_router
from handlers.smart_commands import router as smart_commands_router

# НОВЫЙ роутер для чат-менеджера
from handlers.chat_manager import router as chat_manager_router

# ==================== ПОДКЛЮЧЕНИЕ РОУТЕРОВ ====================
dp.include_routers(
    start_router,
    profile_router,
    economy_router,
    games_router,
    moderation_router,
    ai_assistant_router,
    smart_commands_router,
    chat_manager_router,  # <-- ДОБАВЛЕНО
)

logger.info("✅ Все роутеры загружены")

async def on_startup():
    await db.init()
    logger.info("✅ Nexus Bot v5.0 успешно запущен на Amvera!")

async def on_shutdown():
    await db.close()
    logger.info("👋 Nexus Bot v5.0 остановлен")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
