import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import (
    admin, user, games, economy, balance_handler, report,
    instructions, callbacks, roles, birthday_calendar, games_interactive
)
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
# Сначала команды (чтобы иметь приоритет над универсальным обработчиком)
dp.include_router(economy.router)               # /balance, /daily, /gift, /top
dp.include_router(games.router)                 # старые игры (заглушки)
dp.include_router(games_interactive.router)     # интерактивные игры с кнопками
dp.include_router(birthday_calendar.router)     # интерактивный календарь дня рождения
# Потом остальные
dp.include_router(user.router)                  # /start, /help, /stats, /myrole
dp.include_router(admin.router)                 # /all, /ban, /mute, /setup и т.д.
dp.include_router(report.router)                # /report, /reports_stats
dp.include_router(instructions.router)          # /admin_guide
dp.include_router(callbacks.router)             # обработка callback-запросов

print("✅ Все роутеры зарегистрированы")
print(f"   - economy: {economy.router}")
print(f"   - games: {games.router}")
print(f"   - games_interactive: {games_interactive.router}")
print(f"   - birthday_calendar: {birthday_calendar.router}")
print(f"   - user: {user.router}")
print(f"   - admin: {admin.router}")

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    print("\n🤖 NEXUS-bot запущен!")
    print("📋 Доступные команды:")
    print("   • /start — приветствие")
    print("   • /help — справка")
    print("   • /balance — баланс NCoin")
    print("   • /daily — ежедневный бонус")
    print("   • /gift — подарить NCoin")
    print("   • /top — топ богачей")
    print("   • /rps — камень-ножницы-бумага (интерактивно)")
    print("   • /roulette — рулетка (интерактивно)")
    print("   • /setbirthday — установить день рождения (интерактивно)")
    print("   • /stats — статистика пользователя")
    print("   • /myrole — моя роль")
    print("   • /report — анонимная жалоба")
    print("   • /all — отметить всех (админ)")
    print("   • /ban — забанить (админ)")
    print("   • /mute — заглушить (админ)")
    print("   • /setup — мастер настройки (админ)")
    print("   • /setlogchannel — установить лог-канал (админ)")
    print("   • /setwelcome — настроить приветствие (админ)")
    print("   • /addmod — назначить модератора (админ)")
    print("   • /removemod — удалить модератора (админ)")
    print("   • /mods — список модераторов (админ)")
    print("⏳ Ожидание сообщений...\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен вручную")
    finally:
        print("🔓 Бот завершен")
