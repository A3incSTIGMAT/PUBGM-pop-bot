import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import admin, user, economy, games_interactive, birthday_calendar, menu_handler
from handlers.shop import router as shop_router
from handlers.rp_commands import router as rp_router
from handlers.vip import router as vip_router
from handlers.ai_agent import router as ai_router, set_bot as set_ai_bot
from handlers.report import router as report_router
from handlers.instructions import router as instructions_router
from handlers.callbacks import router as callbacks_router
from handlers.balance_handler import router as balance_router
from handlers.roles import set_bot as set_roles_bot
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
set_roles_bot(bot)
menu_handler.set_bot(bot)
set_ai_bot(bot)

dp = Dispatcher()
init_db()

# РЕГИСТРАЦИЯ ВСЕХ РОУТЕРОВ
dp.include_router(economy.router)
dp.include_router(games_interactive.router)
dp.include_router(birthday_calendar.router)
dp.include_router(user.router)
dp.include_router(admin.router)
dp.include_router(report_router)
dp.include_router(instructions_router)
dp.include_router(callbacks_router)
dp.include_router(menu_handler.router)
dp.include_router(shop_router)
dp.include_router(rp_router)
dp.include_router(vip_router)
dp.include_router(ai_router)
dp.include_router(balance_router)

print("✅ Все роутеры зарегистрированы")
print(f"   - economy: {economy.router}")
print(f"   - games: {games_interactive.router}")
print(f"   - user: {user.router}")
print(f"   - admin: {admin.router}")
print(f"   - menu: {menu_handler.router}")
print(f"   - shop: {shop_router}")
print(f"   - rp: {rp_router}")
print(f"   - vip: {vip_router}")
print(f"   - ai: {ai_router}")

async def main():
    print("\n🤖 NEXUS-bot запущен!")
    print("📋 Команды: /menu, /balance, /daily, /rps, /roulette, /shop, /hug, /kiss, /vip, /ask, /ai")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
