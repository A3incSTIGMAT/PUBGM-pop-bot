import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Импорты конфига и БД
from config import BOT_TOKEN
from database import db

# Создаём папку для данных Amvera
DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Проверка токена
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не задан в переменных окружения!")
    exit(1)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Импорт роутеров (с проверкой наличия файлов)
try:
    from handlers import (
        start, profile, economy, games, moderation,
        stats, social, vip, ai_assistant, payments,
        shop, about, help, smart_commands
    )
    
    dp.include_routers(
        start.router,
        profile.router,
        economy.router,
        games.router,
        moderation.router,
        stats.router,
        social.router,
        vip.router,
        ai_assistant.router,
        payments.router,
        shop.router,
        about.router,
        help.router,
        smart_commands.router
    )
    logger.info("✅ Все роутеры загружены")
except ImportError as e:
    logger.error(f"❌ Ошибка импорта роутеров: {e}")
    exit(1)

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
