import asyncio
import logging
import psutil
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_IDS
from handlers import admin, user, games, economy, report, instructions, callbacks, roles
from database.db import init_db
from utils.logger import log_info, log_attack
from utils.antispam import cleanup_old_data

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Создаем бота и диспетчер
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Передаем бота в модули
admin.bot = bot
user.bot = bot
report.bot = bot
callbacks.bot = bot
roles.set_bot(bot)  # Устанавливаем бота для модуля ролей

# Инициализируем базу данных
init_db()

# Регистрируем обработчики
dp.include_router(admin.router)
dp.include_router(user.router)
dp.include_router(games.router)
dp.include_router(economy.router)
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)

async def monitor_resources():
    """Фоновый мониторинг ресурсов"""
    while True:
        await asyncio.sleep(60)
        
        cpu_percent = psutil.cpu_percent(interval=1)
        mem_percent = psutil.virtual_memory().percent
        mem_used = psutil.virtual_memory().used / (1024 * 1024)
        
        if cpu_percent > 80 or mem_percent > 80:
            log_attack(f"⚠️ ВЫСОКАЯ НАГРУЗКА! CPU={cpu_percent}%, RAM={mem_percent}% ({mem_used:.0f}MB)")
            if ADMIN_IDS:
                await bot.send_message(
                    ADMIN_IDS[0],
                    f"⚠️ **ВНИМАНИЕ! Высокая нагрузка на сервер!**\n\n"
                    f"📊 CPU: {cpu_percent}%\n"
                    f"💾 RAM: {mem_percent}% ({mem_used:.0f}MB)\n\n"
                    f"Возможна DDoS-атака или перегрузка бота."
                )
        elif cpu_percent > 50 or mem_percent > 50:
            log_info(f"📊 Нагрузка: CPU={cpu_percent}%, RAM={mem_percent}% ({mem_used:.0f}MB)")

async def main():
    log_info("🤖 NEXUS-bot запущен!")
    log_info("🛡 Режим защиты активен: Rate limiting, Anti-spam, Temp bans")
    log_info("🛡 Анонимные репорты: включены")
    log_info("👮 Система ролей: глобальный админ, владелец чата, админ, модератор")
    
    asyncio.create_task(monitor_resources())
    asyncio.create_task(cleanup_old_data())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
