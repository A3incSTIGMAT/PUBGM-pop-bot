#!/usr/bin/env python3
"""
NEXUS Chat Manager v5.0 — Точка входа
Запуск на платформе Amvera
"""

import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загрузка переменных окружения ДО импорта config
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Проверка токена
from config import BOT_TOKEN
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set in environment!")
    sys.exit(1)

# ========== ИМПОРТ БАЗЫ ДАННЫХ ==========
from database import db

# Создание директории для данных Amvera
os.makedirs("/data", exist_ok=True)

# Инициализация бота и диспетчера
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

# Новые модули умного тегирования
from handlers.tag_admin import router as tag_admin_router
from handlers.tag_user import router as tag_user_router
from handlers.tag_trigger import router as tag_trigger_router

# ==================== РЕГИСТРАЦИЯ РОУТЕРОВ ====================
dp.include_routers(
    start_router,
    smart_commands_router,
    profile_router,
    economy_router,
    games_router,
    vip_router,
    ai_assistant_router,
    referral_router,
    tag_admin_router,
    tag_user_router,
    tag_trigger_router,
    tag_router,
)

logger.info("✅ Все роутеры успешно загружены")


# ==================== ЖИЗНЕННЫЙ ЦИКЛ БОТА ====================

async def on_startup():
    """Инициализация при запуске"""
    logger.info("🚀 Запуск NEXUS Bot v5.0...")
    
    # 1. Инициализация БД
    try:
        if asyncio.iscoroutinefunction(db.init):
            await db.init()
        else:
            await asyncio.to_thread(db.init)
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.critical(f"❌ Ошибка инициализации БД: {e}")
        sys.exit(1)
    
    # 2. Инициализация категорий тегов
    try:
        from handlers.tag_categories import init_categories
        await init_categories()
        logger.info("✅ Категории тегов инициализированы")
    except ImportError:
        logger.warning("⚠️ Модуль tag_categories не найден, пропускаем")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации категорий: {e}")
    
    # 3. Проверка окружения
    data_dir = os.getenv("DATA_DIR", "/data")
    os.makedirs(data_dir, exist_ok=True)
    logger.info(f"📁 Data directory: {data_dir}")
    
    logger.info("✅ NEXUS Bot v5.0 успешно запущен на Amvera!")


async def on_shutdown():
    """Очистка при остановке"""
    logger.info("🛑 Остановка бота...")
    
    try:
        if asyncio.iscoroutinefunction(db.close):
            await db.close()
        else:
            await asyncio.to_thread(db.close)
        logger.info("✅ База данных закрыта")
    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии БД: {e}")
    
    await bot.session.close()
    logger.info("👋 NEXUS Bot v5.0 остановлен")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    logger.info("📡 Запуск long-polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Прервано пользователем")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}")
        sys.exit(1)
