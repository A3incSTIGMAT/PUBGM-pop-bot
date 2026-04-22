#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 5.2.2-fixed
# ОПИСАНИЕ: NEXUS Chat Manager — ИСПРАВЛЕН ПОРЯДОК ХЕНДЛЕРОВ
# ============================================

import asyncio
import logging
import sys
import signal
from datetime import datetime
from typing import Optional, Set

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()

# ==================== КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("nexus_bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ==================== ИМПОРТ КОНФИГУРАЦИИ ====================

from config import BOT_TOKEN, START_BALANCE, ADMIN_IDS, SUPER_ADMIN_IDS

if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN not set!")
    sys.exit(1)

logger.info(f"🔧 ADMIN_IDS: {ADMIN_IDS}")
logger.info(f"🔧 SUPER_ADMIN_IDS: {SUPER_ADMIN_IDS}")

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

_background_tasks: Set[asyncio.Task] = set()
_shutdown_event = asyncio.Event()


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu(user_id: int) -> InlineKeyboardMarkup:
    """Создает главное меню бота."""
    is_admin = user_id in ADMIN_IDS or user_id in SUPER_ADMIN_IDS
    
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


# ==================== УСТАНОВКА БОТА ДЛЯ МОДУЛЕЙ ====================

def setup_bot_for_modules() -> None:
    """Централизованная установка экземпляра бота для модулей."""
    modules_to_setup = [
        ("handlers.tictactoe", "set_bot"),
        ("handlers.smart_commands", "set_bot"),
    ]
    
    for module_name, func_name in modules_to_setup:
        try:
            module = __import__(module_name, fromlist=[func_name])
            setup_func = getattr(module, func_name, None)
            if setup_func and bot:
                setup_func(bot)
                logger.info(f"✅ Bot set for {module_name}")
        except ImportError:
            logger.warning(f"Module {module_name} not available")
        except Exception as e:
            logger.error(f"Failed to set bot for {module_name}: {e}")


setup_bot_for_modules()


# ==================== ЗАГРУЗКА РОУТЕРОВ (СНАЧАЛА!) ====================

def load_routers() -> None:
    """Загружает все роутеры."""
    router_modules = [
        ("handlers.start", "router"),
        ("handlers.profile", "router"),
        ("handlers.economy", "router"),
        ("handlers.tictactoe", "router"),
        ("handlers.stats", "router"),
        ("handlers.vip", "router"),
        ("handlers.tag", "router"),
        ("handlers.admin", "router"),
        ("handlers.rating", "router"),
        ("handlers.smart_commands", "router"),
        ("handlers.referral", "router"),
        ("handlers.tag_categories", "router"),
        ("handlers.tag_admin", "router"),
        ("handlers.tag_user", "router"),
        ("handlers.tag_trigger", "router"),
        ("handlers.ranks", "router"),
    ]
    
    loaded = 0
    failed = 0
    
    for module_name, attr_name in router_modules:
        try:
            module = __import__(module_name, fromlist=[attr_name])
            router = getattr(module, attr_name, None)
            if router:
                dp.include_router(router)
                loaded += 1
                logger.info(f"✅ Loaded router: {module_name}")
            else:
                logger.warning(f"No router in {module_name}")
                failed += 1
        except ImportError as e:
            logger.warning(f"Module {module_name} not found: {e}")
            failed += 1
        except Exception as e:
            logger.error(f"Error loading {module_name}: {e}")
            failed += 1
    
    logger.info(f"📦 Routers loaded: {loaded}, skipped: {failed}")


# ЗАГРУЖАЕМ РОУТЕРЫ ПЕРВЫМИ!
load_routers()


# ==================== ОТЛАДОЧНЫЙ ХЕНДЛЕР (ПОСЛЕ РОУТЕРОВ) ====================

@dp.message()
async def debug_unhandled_messages(message: types.Message):
    """Логирует НЕОБРАБОТАННЫЕ сообщения."""
    text_preview = message.text[:100] if message.text else (
        "📷 ФОТО" if message.photo else "🎥 ВИДЕО" if message.video else "ДРУГОЕ"
    )
    
    logger.warning(f"⚠️ UNHANDLED: chat={message.chat.id} user={message.from_user.id} content={text_preview}")


# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ====================

from database import db, DatabaseError

async def init_database() -> bool:
    try:
        await db.initialize()
        logger.info("✅ Database initialized successfully")
        return True
    except DatabaseError as e:
        logger.critical(f"❌ Database initialization failed: {e}")
        return False
    except Exception as e:
        logger.critical(f"❌ Unexpected database error: {e}", exc_info=True)
        return False


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

async def auto_register_all_chat_members() -> None:
    try:
        from utils.auto_delete import _active_chats
        
        if not _active_chats:
            return
            
        registered = 0
        for chat_id in list(_active_chats):
            if _shutdown_event.is_set():
                break
            try:
                members = await bot.get_chat_administrators(chat_id)
                for member in members:
                    if member.user.is_bot:
                        continue
                    user_id = member.user.id
                    user = await db.get_user(user_id)
                    if not user:
                        await db.create_user(user_id, member.user.username, member.user.first_name, START_BALANCE)
                        registered += 1
            except Exception as e:
                logger.warning(f"Error registering from {chat_id}: {e}")
            await asyncio.sleep(0.5)
        
        if registered > 0:
            logger.info(f"✅ Auto-registered {registered} new users")
    except Exception as e:
        logger.error(f"Error in auto_register: {e}")


async def schedule_streak_updates() -> None:
    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(3600)
            if _shutdown_event.is_set():
                break
            from handlers.stats import update_all_streaks
            await update_all_streaks()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Streak update error: {e}")
            await asyncio.sleep(60)


async def load_custom_rp_on_startup() -> None:
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        logger.info("✅ Custom RP commands loaded")
    except Exception as e:
        logger.warning(f"Failed to load custom RP: {e}")


async def cleanup_bot_data() -> None:
    try:
        bot_me = await bot.get_me()
        if bot_me:
            await db.cleanup_bot_from_all_tables(bot_me.id)
            logger.info(f"✅ Bot {bot_me.id} data cleaned")
    except Exception as e:
        logger.warning(f"Error cleaning bot data: {e}")


async def init_tag_categories() -> None:
    try:
        from handlers.tag_categories import init_categories
        await init_categories()
        logger.info("✅ Tag categories initialized")
    except Exception as e:
        logger.warning(f"Tag categories init failed: {e}")


def create_background_task(coro, name: str) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(lambda t: _background_tasks.discard(t))
    logger.debug(f"Background task '{name}' started")


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

async def on_startup() -> None:
    logger.info("🚀 Starting NEXUS Bot v5.2.2-fixed...")
    
    if not await init_database():
        sys.exit(1)
    
    await asyncio.gather(
        init_tag_categories(),
        load_custom_rp_on_startup(),
        return_exceptions=True
    )
    
    await cleanup_bot_data()
    
    create_background_task(auto_register_all_chat_members(), "auto_register")
    create_background_task(schedule_streak_updates(), "streak_updates")
    
    try:
        from utils.auto_delete import schedule_morning_cleanup
        create_background_task(schedule_morning_cleanup(bot), "morning_cleanup")
        logger.info("✅ Morning cleanup scheduler started")
    except Exception as e:
        logger.warning(f"Morning cleanup failed: {e}")
    
    try:
        from handlers.stats import update_all_streaks
        await update_all_streaks()
    except Exception as e:
        logger.warning(f"Initial streak update failed: {e}")
    
    logger.info("✅ NEXUS Bot v5.2.2-fixed successfully started!")


async def on_shutdown() -> None:
    logger.info("🛑 Shutting down...")
    _shutdown_event.set()
    
    for task in _background_tasks:
        task.cancel()
    
    if _background_tasks:
        await asyncio.wait(_background_tasks, timeout=5.0)
    
    try:
        await db.close()
    except Exception:
        pass
    
    try:
        await bot.session.close()
    except Exception:
        pass
    
    logger.info("👋 NEXUS Bot stopped.")


def handle_sigterm():
    logger.info("Received SIGTERM...")
    _shutdown_event.set()


async def main() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
        loop.add_signal_handler(signal.SIGINT, handle_sigterm)
    except NotImplementedError:
        pass
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("📡 Starting long-polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
