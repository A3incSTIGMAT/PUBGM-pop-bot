import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import admin, user, games, economy, balance_handler, report, instructions, callbacks, roles, birthday_handler
from database.db import init_db
from utils.lock import acquire_lock

logging.basicConfig(level=logging.INFO)

if not acquire_lock():
    print("❌ Бот уже запущен!")
    sys.exit(0)

print("🔒 Блокировка захвачена. Бот запускается...")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

admin.set_bot(bot)
user.set_bot(bot)
report.set_bot(bot)
callbacks.set_bot(bot)
roles.set_bot(bot)

dp = Dispatcher()
init_db()

# Регистрация роутеров
dp.include_router(economy.router)
dp.include_router(games.router)
dp.include_router(birthday_handler.router)  # ← НОВЫЙ
dp.include_router(user.router)
dp.include_router(admin.router)
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)

print("✅ Все роутеры зарегистрированы")
print(f"   - birthday_handler: {birthday_handler.router}")

async def main():
    print("\n🤖 NEXUS-bot запущен!")
    print("📋 Команды: /start, /help, /balance, /daily, /rps, /roulette, /setbirthday")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
