#!/usr/bin/env python3
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from config import BOT_TOKEN
from database import db

load_dotenv()

os.makedirs("/data", exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set!")
    exit(1)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==================== ИМПОРТЫ РОУТЕРОВ ====================
from handlers.start import router as start_router
from handlers.profile import router as profile_router
from handlers.economy import router as economy_router
from handlers.games import router as games_router
from handlers.vip import router as vip_router
from handlers.tag import router as tag_router
from handlers.ai_assistant import router as ai_assistant_router
from handlers.referral import router as referral_router
from handlers.smart_commands import router as smart_commands_router

# ========== НОВЫЕ МОДУЛИ УМНОГО ТЭГА ==========
from handlers.tag_admin import router as tag_admin_router
from handlers.tag_user import router as tag_user_router
from handlers.tag_trigger import router as tag_trigger_router

# ==================== ПОДКЛЮЧЕНИЕ РОУТЕРОВ ====================
dp.include_routers(
    start_router,
    profile_router,
    economy_router,
    games_router,
    vip_router,
    tag_router,
    ai_assistant_router,
    referral_router,
    smart_commands_router,
    tag_admin_router,      # ← ДОБАВЛЕНО
    tag_user_router,       # ← ДОБАВЛЕНО
    tag_trigger_router,    # ← ДОБАВЛЕНО
)

logger.info("✅ Все роутеры загружены")

# ==================== ЗАПУСК И ОСТАНОВКА ====================
async def on_startup():
    await db.init()
    
    # Инициализация категорий тегов
    try:
        from handlers.tag_categories import init_categories
        await init_categories()
        logger.info("✅ Категории тегов инициализированы")
    except Exception as e:
        logger.warning(f"Ошибка инициализации категорий: {e}")
    
    logger.info("✅ NEXUS Bot v5.0 успешно запущен на Amvera!")

async def on_shutdown():
    await db.close()
    logger.info("👋 NEXUS Bot v5.0 остановлен")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
