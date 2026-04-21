#!/usr/bin/env python3
# ============================================
# ФАЙЛ: bot.py
# ОПИСАНИЕ: NEXUS Chat Manager v5.0 — Точка входа
# ИСПРАВЛЕНО: Загрузка кастомных РП команд, защита от NULL
# ============================================

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
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

from config import BOT_TOKEN, START_BALANCE, ADMIN_IDS
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==================== УСТАНОВКА БОТА ДЛЯ МОДУЛЕЙ ====================
try:
    from handlers.tictactoe import set_bot
    if bot is not None:
        set_bot(bot)
        logger.info("✅ Bot instance set for tictactoe")
except Exception as e:
    logger.warning(f"⚠️ Could not set bot for tictactoe: {e}")

try:
    from handlers.smart_commands import set_bot as set_smart_bot
    if bot is not None:
        set_smart_bot(bot)
        logger.info("✅ Bot instance set for smart_commands")
except Exception as e:
    logger.warning(f"⚠️ Could not set bot for smart_commands: {e}")


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
        smart_commands_router,
    )
    logger.info("✅ Все роутеры загружены")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки роутеров: {e}")
    sys.exit(1)


# ==================== ЖИЗНЕННЫЙ ЦИКЛ БОТА ====================

async def on_startup():
    logger.info("🚀 Запуск NEXUS Bot v5.0...")
    
    # 1. Инициализация БД
    try:
        if db is not None:
            await db.init()
            logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.critical(f"❌ Ошибка инициализации БД: {e}")
        sys.exit(1)
    
    # 2. Инициализация категорий тегов
    try:
        from handlers.tag_categories import init_categories
        if init_categories is not None:
            await init_categories()
            logger.info("✅ Категории тегов инициализированы")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации категорий: {e}")
    
    # 3. Запуск планировщика стриков
    try:
        asyncio.create_task(schedule_streak_updates())
        logger.info("✅ Планировщик стриков запущен")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка запуска планировщика стриков: {e}")
    
    # 4. Запуск планировщика утренней очистки
    try:
        from utils.auto_delete import schedule_morning_cleanup
        if schedule_morning_cleanup is not None and bot is not None:
            asyncio.create_task(schedule_morning_cleanup(bot))
            logger.info("✅ Планировщик утренней очистки запущен")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка запуска планировщика очистки: {e}")
    
    # 5. Авторегистрация участников чатов
    try:
        await auto_register_all_chat_members()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка авторегистрации участников: {e}")
    
    # 6. Очистка данных бота
    try:
        if bot is not None:
            bot_me = await bot.get_me()
            if bot_me is not None:
                bot_id = bot_me.id
                if db is not None:
                    await db.cleanup_bot_from_all_tables(bot_id)
                    logger.info(f"✅ Данные бота {bot_id} очищены")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка очистки данных бота: {e}")
    
    # 7. Инициализация РП таблиц
    try:
        from handlers.rp_tables import init_rp_tables
        if init_rp_tables is not None:
            await init_rp_tables()
            logger.info("✅ РП таблицы инициализированы")
    except ImportError:
        logger.debug("rp_tables module not found, skipping")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации РП таблиц: {e}")
    
    # 8. 🔥 ЗАГРУЗКА КАСТОМНЫХ РП КОМАНД
    try:
        from handlers.smart_commands import load_custom_rp_commands
        if load_custom_rp_commands is not None:
            await load_custom_rp_commands()
            logger.info("✅ Кастомные РП команды загружены")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки кастомных РП команд: {e}")
    
    # 9. 🔥 ЗАГРУЗКА СТАТИСТИКИ
    try:
        from handlers.stats import update_all_streaks
        if update_all_streaks is not None:
            await update_all_streaks()
            logger.info("✅ Стрики активности обновлены при старте")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка обновления стриков при старте: {e}")
    
    logger.info("✅ NEXUS Bot v5.0 успешно запущен!")


async def auto_register_all_chat_members():
    """Автоматическая регистрация всех участников чатов (КРОМЕ БОТОВ)"""
    try:
        from utils.auto_delete import _active_chats
        
        if _active_chats is None:
            logger.debug("No active chats to register")
            return
            
        registered = 0
        for chat_id in list(_active_chats):
            if chat_id is None:
                continue
            try:
                if bot is None:
                    continue
                members = await bot.get_chat_administrators(chat_id)
                if members is None:
                    continue
                    
                for member in members:
                    if member is None or member.user is None:
                        continue
                    if member.user.is_bot:
                        continue
                        
                    user_id = member.user.id
                    username = member.user.username
                    first_name = member.user.first_name
                    
                    if db is None:
                        continue
                    user = await db.get_user(user_id)
                    if not user:
                        await db.create_user(user_id, username, first_name, START_BALANCE)
                        registered += 1
                        logger.info(f"Auto-registered user {user_id} (@{username}) from chat {chat_id}")
            except Exception as e:
                logger.debug(f"Could not register members from chat {chat_id}: {e}")
        
        if registered > 0:
            logger.info(f"✅ Auto-registered {registered} users from all chats")
    except Exception as e:
        logger.error(f"Error in auto_register_all_chat_members: {e}")


async def schedule_streak_updates():
    """Периодическое обновление стриков (раз в час)"""
    while True:
        await asyncio.sleep(3600)
        try:
            from handlers.stats import update_all_streaks
            if update_all_streaks is not None:
                await update_all_streaks()
                logger.debug("✅ Стрики обновлены")
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
        if bot is not None:
            await bot.session.close()
    except:
        pass
    logger.info("👋 NEXUS Bot v5.0 остановлен")


async def main():
    if dp is None:
        logger.error("❌ Dispatcher is None!")
        sys.exit(1)
        
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    logger.info("📡 Запуск long-polling...")
    
    if bot is None:
        logger.error("❌ Bot is None!")
        sys.exit(1)
        
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Прервано пользователем")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
