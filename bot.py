import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import admin, user, games, economy, report, instructions, callbacks, roles
from database.db import init_db
from utils.lock import acquire_lock

logging.basicConfig(level=logging.INFO)

if not acquire_lock():
    print("❌ Бот уже запущен!")
    sys.exit(0)

print("🔒 Бот запускается...")

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

# РЕГИСТРАЦИЯ ВСЕХ РОУТЕРОВ
dp.include_router(admin.router)
dp.include_router(user.router)
dp.include_router(games.router)
dp.include_router(economy.router)   # ← ЭТОТ ДОЛЖЕН БЫТЬ
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)

print("✅ Роутеры зарегистрированы:")
print(f"   - economy: {economy.router}")

async def main():
    print("🤖 NEXUS-bot запущен!")
    print("📋 Команды: /balance, /daily, /rps, /roulette")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
