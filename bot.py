import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import (
    admin, user, economy, games_interactive, birthday_calendar,
    menu_handler, shop, rp_commands, vip, report, instructions, callbacks, roles,
    smart_parser
)
from payments.ozon import router as ozon_router
from database.db import init_db
from utils.lock import acquire_lock

logging.basicConfig(level=logging.INFO)

if not acquire_lock():
    print("❌ Бот уже запущен!")
    sys.exit(0)

print("🔒 NEXUS AI — ЗАПУСКАЕТСЯ...")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Передаём бота во все модули
admin.set_bot(bot)
user.set_bot(bot)
report.set_bot(bot)
callbacks.set_bot(bot)
roles.set_bot(bot)
menu_handler.set_bot(bot)
shop.set_bot(bot)
smart_parser.set_bot(bot)

dp = Dispatcher()
init_db()

# Регистрация роутеров
dp.include_router(economy.router)
dp.include_router(games_interactive.router)
dp.include_router(birthday_calendar.router)
dp.include_router(user.router)
dp.include_router(admin.router)
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)
dp.include_router(menu_handler.router)
dp.include_router(shop.router)
dp.include_router(rp_commands.router)
dp.include_router(vip.router)
dp.include_router(ozon_router)
dp.include_router(smart_parser.router)

print("✅ Все роутеры зарегистрированы")
print("🧠 Умный парсер активирован")
print("🚀 NEXUS AI готов к работе!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
