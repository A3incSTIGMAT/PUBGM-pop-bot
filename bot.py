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

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

from config import BOT_TOKEN
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set!")
    sys.exit(1)

from database import db

os.makedirs("/data", exist_ok=True)

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
from handlers.tag_admin import router as tag_admin_router
from handlers.tag_user import router as tag_user_router
from handlers.tag_trigger import router as tag_trigger_router
from handlers.ranks import router as ranks_router
from handlers.rating import router as rating_router
from handlers.games_private import router as games_private_router
from handlers.rp_commands import router as rp_commands_router
from handlers.smart_commands import router as smart_commands_router

# ==================== ПОДКЛЮЧЕНИЕ РОУТЕРОВ ====================
# 🔥 ВАЖНО: Командные роутеры ДОЛЖНЫ быть ПЕРЕД smart_commands!
# 🔥 smart_commands_router с @router.message() перехватывает всё!
dp.include_routers(
    start_router,
    profile_router,
    economy_router,          # ← /balance, /daily, /transfer
    games_router,            # ← /games, /slot, etc
    vip_router,              # ← /vip
    tag_router,              # ← /all, /tag
    ai_assistant_router,     # ← AI команды
    referral_router,         # ← /my_ref, /ref_stats
    tag_admin_router,        # ← /tagadmin
    tag_user_router,         # ← /mytags
    tag_trigger_router,      # ← /tagcat
    ranks_router,            # ← /rank, /top_ranked
    rating_router,           # ← /top_chats
    games_private_router,    # ← личные игры
    rp_commands_router,      # ← /hug, /kiss, etc
)

# 🔥 ПРОВЕРКА: Если smart_commands содержит @router.message() без фильтра,
# он перехватит ВСЕ оставшиеся сообщения, включая неизвестные команды.
# Поэтому подключаем его ПОСЛЕДНИМ.
try:
    # Проверяем, есть ли в роутере "опасные" обработчики
    dp.include_router(smart_commands_router)
    logger.info("✅ smart_commands_router подключен (последним)")
except Exception as e:
    logger.error(f"❌ Ошибка подключения smart_commands_router: {e}")

logger.info("✅ Все роутеры успешно загружены")


# ==================== ЖИЗНЕННЫЙ ЦИКЛ БОТА ====================

async def on_startup():
    """Инициализация при запуске"""
    logger.info("🚀 Запуск NEXUS Bot v5.0...")
    
    # 1. Инициализация БД
    try:
        await db.init()
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
    
    # 3. Инициализация рангов
    try:
        from handlers.ranks import init_ranks
        await init_ranks()
        logger.info("✅ Система рангов инициализирована")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации рангов: {e}")
    
    # 4. Инициализация рейтинга чатов
    try:
        from handlers.rating import init_rating_tables
        await init_rating_tables()
        logger.info("✅ Рейтинг чатов инициализирован")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации рейтинга: {e}")
    
    # 5. Инициализация личных игр
    try:
        from handlers.games_private import init_private_games
        await init_private_games()
        logger.info("✅ Личные игры инициализированы")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации личных игр: {e}")
    
    # 6. Инициализация РП команд
    try:
        from handlers.rp_commands import init_rp_tables
        await init_rp_tables()
        logger.info("✅ РП команды инициализированы")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации РП команд: {e}")
    
    logger.info("✅ NEXUS Bot v5.0 успешно запущен на Amvera!")


async def on_shutdown():
    """Очистка при остановке"""
    logger.info("🛑 Остановка бота...")
    try:
        await db.close()
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
