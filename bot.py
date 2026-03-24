import asyncio
import logging
import psutil
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_IDS
from handlers import admin, user, games, economy, report, instructions, callbacks, roles
from database.db import init_db
from utils.logger import log_info, log_attack
from utils.antispam import cleanup_old_data
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

# ========== ПЕРЕДАЧА БОТА ВО ВСЕ МОДУЛИ ==========
admin.set_bot(bot)
user.set_bot(bot)
report.set_bot(bot)
callbacks.set_bot(bot)
roles.set_bot(bot)

# ========== СОЗДАНИЕ ДИСПЕТЧЕРА ==========
dp = Dispatcher()

# ========== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ==========
init_db()

# ========== РЕГИСТРАЦИЯ ВСЕХ РОУТЕРОВ ==========
dp.include_router(admin.router)
dp.include_router(user.router)
dp.include_router(games.router)
dp.include_router(economy.router)
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)

# ========== ПРОВЕРКА РЕГИСТРАЦИИ ==========
print("✅ Зарегистрированы роутеры:")
print(f"   - admin: {admin.router}")
print(f"   - user: {user.router}")
print(f"   - games: {games.router}")
print(f"   - economy: {economy.router}")
print(f"   - report: {report.router}")
print(f"   - instructions: {instructions.router}")
print(f"   - callbacks: {callbacks.router}")

# ========== МОНИТОРИНГ РЕСУРСОВ ==========
async def monitor_resources():
    while True:
        await asyncio.sleep(60)
        cpu_percent = psutil.cpu_percent(interval=1)
        mem_percent = psutil.virtual_memory().percent
        mem_used = psutil.virtual_memory().used / (1024 * 1024)
        
        if cpu_percent > 80 or mem_percent > 80:
            log_attack(f"⚠️ ВЫСОКАЯ НАГРУЗКА! CPU={cpu_percent}%, RAM={mem_percent}%")
            if ADMIN_IDS:
                await bot.send_message(
                    ADMIN_IDS[0],
                    f"⚠️ Высокая нагрузка!\nCPU: {cpu_percent}%\nRAM: {mem_percent}%"
                )

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    log_info("🤖 NEXUS-bot запущен!")
    log_info("🛡 Защита активна: Rate limiting, Anti-spam")
    log_info("🔒 Защита от дублирующихся процессов: активна")
    log_info("📋 Доступные команды: /start, /help, /balance, /daily, /rps, /roulette, /stats, /myrole, /gift, /top")
    
    asyncio.create_task(monitor_resources())
    asyncio.create_task(cleanup_old_data())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
