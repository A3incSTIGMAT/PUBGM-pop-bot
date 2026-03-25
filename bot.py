import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import (
    admin, user, economy, balance_handler, report,
    instructions, callbacks, roles, birthday_calendar, games_interactive,
    menu_handler, rp_commands, vip, ai_agent
)
from handlers.shop import router as shop_router  # ← импорт напрямую
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
menu_handler.set_bot(bot)
ai_agent.set_bot(bot)

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
dp.include_router(shop_router)  # ← shop
dp.include_router(rp_commands.router)
dp.include_router(vip.router)
dp.include_router(ai_agent.router)

print("✅ Все роутеры зарегистрированы")
print(f"   - menu_handler: {menu_handler.router}")
print(f"   - shop: {shop_router}")
print(f"   - rp_commands: {rp_commands.router}")
print(f"   - vip: {vip.router}")
print(f"   - ai_agent: {ai_agent.router}")

async def main():
    print("\n🤖 NEXUS-bot запущен!")
    print("📋 Команды:")
    print("   • /menu — главное меню")
    print("   • /ai — AI-ассистент (диалог)")
    print("   • /ask [вопрос] — быстрый вопрос AI")
    print("   • /balance — баланс")
    print("   • /daily — бонус (00:00 UTC)")
    print("   • /shop — магазин подарков")
    print("   • /hug, /kiss, /slap — РП-команды")
    print("   • /vip — VIP-статус")
    print("   • /rps, /roulette — игры")
    print("   • /setbirthday — календарь")
    print("   • /all — отметить всех (админ)")
    print("   • /ban, /mute — модерация")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
