#!/usr/bin/env python3
"""
NEXUS Chat Manager v5.0 — Точка входа
Запуск на платформе Amvera
ПОЛНОСТЬЮ ЗАЩИЩЕНО ОТ NULL
"""

import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from config import BOT_TOKEN, START_BALANCE
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню бота"""
    if is_admin is None:
        is_admin = False
        
    keyboard = [
        [InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="vip"),
         InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")],
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
         InlineKeyboardButton(text="🏆 РАНГ", callback_data="rank_menu")],
        [InlineKeyboardButton(text="🎮 КРЕСТИКИ-НОЛИКИ", callback_data="game_xo"),
         InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")],
        [InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="relationships_menu"),
         InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="groups_menu")],
        [InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="rp_menu"),
         InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="my_tags_menu")],
        [InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="top_chats"),
         InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help"),
         InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate")],
        [InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="feedback_menu")]
    ]
    
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ==================== ТЕСТОВЫЕ КОМАНДЫ ====================

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    if message is None:
        return
    await message.answer("🏓 PONG! Бот работает!")


# ==================== ИМПОРТЫ РОУТЕРОВ ====================
from database import db

try:
    from handlers.start import router as start_router
    from handlers.profile import router as profile_router
    from handlers.economy import router as economy_router
    from handlers.tictactoe import router as tictactoe_router
    from handlers.stats import router as stats_router
    from handlers.vip import router as vip_router
    from handlers.tag import router as tag_router
    from handlers.ai_assistant import router as ai_assistant_router
    from handlers.referral import router as referral_router
    from handlers.tag_admin import router as tag_admin_router
    from handlers.tag_user import router as tag_user_router
    from handlers.tag_trigger import router as tag_trigger_router
    from handlers.ranks import router as ranks_router
    from handlers.rating import router as rating_router
    from handlers.rp_commands import router as rp_commands_router
    from handlers.smart_commands import router as smart_commands_router
    
    dp.include_routers(
        start_router,
        profile_router,
        economy_router,
        tictactoe_router,
        stats_router,
        vip_router,
        tag_router,
        ai_assistant_router,
        referral_router,
        tag_admin_router,
        tag_user_router,
        tag_trigger_router,
        ranks_router,
        rating_router,
        rp_commands_router,
        smart_commands_router,
    )
    logger.info("✅ Все роутеры загружены")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки роутеров: {e}")
    sys.exit(1)


# ==================== ЖИЗНЕННЫЙ ЦИКЛ БОТА ====================

async def on_startup():
    logger.info("🚀 Запуск NEXUS Bot v5.0...")
    
    try:
        if db is not None:
            await db.init()
            logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.critical(f"❌ Ошибка инициализации БД: {e}")
        sys.exit(1)
    
    try:
        from handlers.tag_categories import init_categories
        await init_categories()
        logger.info("✅ Категории тегов инициализированы")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации категорий: {e}")
    
    # Запускаем периодическое обновление стриков
    try:
        asyncio.create_task(schedule_streak_updates())
    except:
        pass
    
    # Запускаем планировщик утренней очистки
    try:
        from utils.auto_delete import schedule_morning_cleanup
        asyncio.create_task(schedule_morning_cleanup(bot))
        logger.info("✅ Планировщик утренней очистки запущен")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка запуска планировщика очистки: {e}")
    
    logger.info("✅ NEXUS Bot v5.0 успешно запущен!")


async def schedule_streak_updates():
    """Периодическое обновление стриков (раз в час)"""
    while True:
        await asyncio.sleep(3600)
        try:
            from handlers.stats import update_all_streaks
            await update_all_streaks()
        except Exception as e:
            logger.error(f"Ошибка обновления стриков: {e}")


async def on_shutdown():
    logger.info("🛑 Остановка бота...")
    try:
        if db is not None:
            await db.close()
    except:
        pass
    try:
        await bot.session.close()
    except:
        pass
    logger.info("👋 NEXUS Bot v5.0 остановлен")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    logger.info("📡 Запуск long-polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Прервано пользователем")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
