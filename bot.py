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

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# ========== ЗАЩИТА ОТ ДУБЛИРУЮЩИХСЯ ПРОЦЕССОВ ==========
if not acquire_lock():
    print("❌ Бот уже запущен! Завершаем этот процесс.")
    sys.exit(0)

print("🔒 Блокировка захвачена. Бот запускается...")

# ========== СОЗДАНИЕ БОТА ==========
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

print("✅ Бот создан")

# ========== ПЕРЕДАЧА БОТА ВО ВСЕ МОДУЛИ ==========
admin.set_bot(bot)
user.set_bot(bot)
report.set_bot(bot)
callbacks.set_bot(bot)
roles.set_bot(bot)

print("✅ Бот передан во все модули")

# ========== СОЗДАНИЕ ДИСПЕТЧЕРА ==========
dp = Dispatcher()
print("✅ Диспетчер создан")

# ========== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ==========
init_db()
print("✅ База данных инициализирована")

# ========== РЕГИСТРАЦИЯ ВСЕХ РОУТЕРОВ ==========
dp.include_router(admin.router)
dp.include_router(user.router)
dp.include_router(games.router)
dp.include_router(economy.router)
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)

print("✅ Все роутеры зарегистрированы")
print(f"   - economy router: {economy.router}")
print(f"   - games router: {games.router}")

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    print("\n🤖 NEXUS-bot запущен!")
    print("📋 Доступные команды: /start, /help, /balance, /daily, /rps, /roulette, /stats, /myrole, /gift, /top")
    print("⏳ Ожидание сообщений...\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен вручную")
    finally:
        print("🔓 Бот завершен")
