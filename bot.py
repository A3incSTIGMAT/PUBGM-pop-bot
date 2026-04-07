import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN
from database import db
from handlers import start, profile, economy, games, moderation, stats, social, vip, ai_assistant, payments, shop, about, help, smart_commands

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

dp.include_routers(start.router, profile.router, economy.router, games.router, moderation.router, stats.router, social.router, vip.router, ai_assistant.router, payments.router, shop.router, about.router, help.router, smart_commands.router)

async def on_startup():
    await db.init()
    logger.info("✅ Nexus Bot v5.0 started")

async def on_shutdown():
    await db.close()
    logger.info("👋 Bot stopped")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
