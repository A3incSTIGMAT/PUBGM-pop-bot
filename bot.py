import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import admin, user, games, economy, balance_handler, report, instructions, callbacks, roles
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

# ========== ВАЖНО: ПОРЯДОК РЕГИСТРАЦИИ ==========
# Сначала регистрируем команды (чтобы они имели приоритет)
dp.include_router(economy.router)      # /balance, /daily, /gift, /top
dp.include_router(games.router)        # /rps, /roulette
# Потом регистрируем user (в нём есть универсальный обработчик)
dp.include_router(user.router)         # /start, /help, /stats, /myrole, универсальный
# Затем остальные
dp.include_router(admin.router)
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)

print("✅ Все роутеры зарегистрированы")
print(f"   - economy router: {economy.router}")
print(f"   - games router: {games.router}")
print(f"   - user router: {user.router}")

async def main():
    print("\n🤖 NEXUS-bot запущен!")
    print("📋 Команды: /balance, /daily, /rps, /roulette, /start, /stats")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
