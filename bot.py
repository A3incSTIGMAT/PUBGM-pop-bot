#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import logging
import sys
import signal
from typing import Set

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

from config import BOT_TOKEN, START_BALANCE, ADMIN_IDS, SUPER_ADMIN_IDS, BOT_USERNAME

if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN not set!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==================== ПРЯМОЙ ХЕНДЛЕР КОМАНД ====================

@dp.message(Command("start"))
async def direct_start_handler(message: types.Message, command: CommandObject):
    """ПРЯМОЙ ОБРАБОТЧИК /start"""
    logger.info(f"🔥🔥🔥 DIRECT HANDLER TRIGGERED! User={message.from_user.id} Chat={message.chat.id} Text={message.text}")
    
    from database import db
    from utils.keyboards import main_menu
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    
    try:
        await db.initialize()
    except:
        pass
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
        
        balance = await db.get_balance(user_id)
        vip_level = user.get('vip_level', 0) if user else 0
        
        is_admin = user_id in ADMIN_IDS or user_id in SUPER_ADMIN_IDS
        
        text = (
            f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
            f"👋 Привет, <b>{first_name}</b>!\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n\n"
            f"👇 Выберите действие:"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_menu(is_admin=is_admin))
        logger.info(f"✅ MENU SENT to {user_id}")
        
    except Exception as e:
        logger.error(f"Start handler error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("ping"))
async def ping_handler(message: types.Message):
    await message.answer("🏓 PONG!")


@dp.message()
async def fallback_handler(message: types.Message):
    """Ловит ВСЕ необработанные сообщения"""
    logger.warning(f"⚠️ UNHANDLED: chat={message.chat.id} user={message.from_user.id} text={message.text}")


# ==================== ЗАГРУЗКА ОСТАЛЬНЫХ МОДУЛЕЙ ====================

try:
    from handlers.smart_commands import router as smart_router
    dp.include_router(smart_router)
    logger.info("✅ smart_commands loaded")
except Exception as e:
    logger.warning(f"smart_commands: {e}")

try:
    from handlers.economy import router as economy_router
    dp.include_router(economy_router)
    logger.info("✅ economy loaded")
except Exception as e:
    logger.warning(f"economy: {e}")

try:
    from handlers.tictactoe import router as xo_router
    dp.include_router(xo_router)
    logger.info("✅ tictactoe loaded")
except Exception as e:
    logger.warning(f"tictactoe: {e}")

try:
    from handlers.stats import router as stats_router
    dp.include_router(stats_router)
    logger.info("✅ stats loaded")
except Exception as e:
    logger.warning(f"stats: {e}")

try:
    from handlers.vip import router as vip_router
    dp.include_router(vip_router)
    logger.info("✅ vip loaded")
except Exception as e:
    logger.warning(f"vip: {e}")

try:
    from handlers.tag import router as tag_router
    dp.include_router(tag_router)
    logger.info("✅ tag loaded")
except Exception as e:
    logger.warning(f"tag: {e}")

try:
    from handlers.admin import router as admin_router
    dp.include_router(admin_router)
    logger.info("✅ admin loaded")
except Exception as e:
    logger.warning(f"admin: {e}")

try:
    from handlers.profile import router as profile_router
    dp.include_router(profile_router)
    logger.info("✅ profile loaded")
except Exception as e:
    logger.warning(f"profile: {e}")

try:
    from handlers.rating import router as rating_router
    dp.include_router(rating_router)
    logger.info("✅ rating loaded")
except Exception as e:
    logger.warning(f"rating: {e}")

# ==================== УСТАНОВКА БОТА ====================

try:
    from handlers.tictactoe import set_bot
    set_bot(bot)
except:
    pass

try:
    from handlers.smart_commands import set_bot as set_smart_bot
    set_smart_bot(bot)
except:
    pass


# ==================== ЗАПУСК ====================

async def on_startup():
    logger.info("🚀 Bot starting...")
    try:
        from database import db
        await db.initialize()
        logger.info("✅ DB initialized")
    except Exception as e:
        logger.error(f"DB error: {e}")
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        logger.info("✅ Custom RP loaded")
    except Exception as e:
        logger.warning(f"Custom RP: {e}")
    
    logger.info("✅ Bot started! Ready for /start@NEXUS_Manager_Official_bot")


async def on_shutdown():
    logger.info("🛑 Stopping...")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("📡 Starting polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted")
    except Exception as e:
        logger.critical(f"💥 Fatal: {e}", exc_info=True)
        sys.exit(1)
