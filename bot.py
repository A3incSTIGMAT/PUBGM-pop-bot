import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN
from database import db
from handlers import (
    start, profile, economy, games, moderation, stats, 
    social, vip, ai_assistant, payments, shop, about, 
    help, smart_commands
)

# Создаём папку для данных Amvera
DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Регистрация роутеров
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

async def on_startup():
    """Запуск бота"""
    await db.init()
    logger.info("✅ Nexus Bot v5.0 успешно запущен на Amvera!")

async def on_shutdown():
    """Остановка бота"""
    await db.close()
    logger.info("👋 Nexus Bot v5.0 остановлен")

async def main():
    """Главная функция"""
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запускаем поллинг
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
