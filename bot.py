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

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Передаем бота во все модули
admin.set_bot(bot)
user.set_bot(bot)
report.set_bot(bot)
callbacks.set_bot(bot)
roles.set_bot(bot)

dp = Dispatcher()
init_db()

dp.include_router(admin.router)
dp.include_router(user.router)
dp.include_router(games.router)
dp.include_router(economy.router)
dp.include_router(report.router)
dp.include_router(instructions.router)
dp.include_router(callbacks.router)

async def monitor_resources():
    while True:
        await asyncio.sleep(60)
        cpu_percent = psutil.cpu_percent(interval=1)
        mem_percent = psutil.virtual_memory().percent
        if cpu_percent > 80 or mem_percent > 80:
            log_attack(f"⚠️ ВЫСОКАЯ НАГРУЗКА! CPU={cpu_percent}%, RAM={mem_percent}%")
            if ADMIN_IDS:
                await bot.send_message(
                    ADMIN_IDS[0],
                    f"⚠️ **Высокая нагрузка!**\nCPU: {cpu_percent}%\nRAM: {mem_percent}%"
                )

async def main():
    log_info("🤖 NEXUS-bot запущен!")
    log_info("🛡 Защита активна: Rate limiting, Anti-spam")
    log_info("🛡 Анонимные репорты: включены")
    log_info("👮 Система ролей: глобальный админ, владелец чата, админ, модератор")
    
    asyncio.create_task(monitor_resources())
    asyncio.create_task(cleanup_old_data())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
