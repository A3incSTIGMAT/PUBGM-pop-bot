#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 5.3.0-production
# ОПИСАНИЕ: NEXUS Chat Manager — ИСПРАВЛЕНА ЗАГРУЗКА РОУТЕРОВ
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
    logger.critical("❌ BOT_TOKEN not set in .env file!")
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


# ==================== ЗАГРУЗКА РОУТЕРОВ ====================

def load_routers() -> None:
    """Загружает все роутеры с подробным логированием."""
    router_modules = [
        # КРИТИЧЕСКИ ВАЖНЫЕ - загружаем первыми
        ("handlers.start", "router"),
        ("handlers.smart_commands", "router"),
        ("handlers.economy", "router"),
        ("handlers.tictactoe", "router"),
        ("handlers.stats", "router"),
        ("handlers.profile", "router"),
        ("handlers.vip", "router"),
        ("handlers.tag", "router"),
        ("handlers.admin", "router"),
        ("handlers.rating", "router"),
        
        # Реферальная система
        ("handlers.referral", "router"),
        
        # Система тегов (если есть ошибки - не критично)
        ("handlers.tag_admin", "router"),
        ("handlers.tag_user", "router"),
        ("handlers.tag_trigger", "router"),
        
        # Ранги
        ("handlers.ranks", "router"),
    ]
    
    # Проблемные модули - пробуем загрузить но не падаем при ошибке
    optional_modules = [
        ("handlers.tag_categories", "router"),
    ]
    
    loaded = 0
    failed = 0
    
    logger.info("=" * 50)
    logger.info("📦 STARTING ROUTER LOADING...")
    logger.info("=" * 50)
    
    for module_name, attr_name in router_modules:
        try:
            logger.info(f"🔄 Loading: {module_name}...")
            module = __import__(module_name, fromlist=[attr_name])
            router = getattr(module, attr_name, None)
            if router:
                dp.include_router(router)
                loaded += 1
                logger.info(f"   ✅ SUCCESS: {module_name}")
            else:
                logger.error(f"   ❌ No router attribute '{attr_name}' in {module_name}")
                failed += 1
        except ImportError as e:
            logger.error(f"   ❌ IMPORT ERROR: {module_name} - {e}")
            failed += 1
        except AttributeError as e:
            logger.error(f"   ❌ ATTRIBUTE ERROR: {module_name} - {e}")
            failed += 1
        except Exception as e:
            logger.error(f"   ❌ UNKNOWN ERROR: {module_name} - {e}", exc_info=True)
            failed += 1
    
    # Пробуем загрузить опциональные модули
    for module_name, attr_name in optional_modules:
        try:
            logger.info(f"🔄 Loading optional: {module_name}...")
            module = __import__(module_name, fromlist=[attr_name])
            router = getattr(module, attr_name, None)
            if router:
                dp.include_router(router)
                loaded += 1
                logger.info(f"   ✅ OPTIONAL SUCCESS: {module_name}")
        except Exception as e:
            logger.warning(f"   ⚠️ Optional module {module_name} skipped: {e}")
    
    logger.info("=" * 50)
    logger.info(f"📦 ROUTERS LOADED: {loaded} | FAILED: {failed}")
    logger.info("=" * 50)


# Загружаем роутеры
load_routers()


# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ====================

from database import db, DatabaseError

async def init_database() -> bool:
    """Инициализация базы данных."""
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
    """Автоматическая регистрация участников чатов."""
    try:
        from utils.auto_delete import _active_chats
        
        if not _active_chats:
            logger.debug("No active chats to register")
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
                        await db.create_user(
                            user_id,
                            member.user.username,
                            member.user.first_name,
                            START_BALANCE
                        )
                        registered += 1
                        logger.debug(f"Auto-registered: {user_id} from chat {chat_id}")
                        
            except TelegramAPIError as e:
                logger.debug(f"Telegram API error for chat {chat_id}: {e}")
            except Exception as e:
                logger.warning(f"Error registering members from {chat_id}: {e}")
            
            await asyncio.sleep(0.5)
        
        if registered > 0:
            logger.info(f"✅ Auto-registered {registered} new users")
            
    except Exception as e:
        logger.error(f"Error in auto_register_all_chat_members: {e}")


async def schedule_streak_updates() -> None:
    """Периодическое обновление стриков."""
    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(3600)
            if _shutdown_event.is_set():
                break
                
            from handlers.stats import update_all_streaks
            await update_all_streaks()
            logger.debug("✅ Streaks updated")
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Streak update error: {e}")
            await asyncio.sleep(60)


async def load_custom_rp_on_startup() -> None:
    """Загрузка кастомных РП команд."""
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        logger.info("✅ Custom RP commands loaded")
    except ImportError:
        logger.debug("smart_commands module not available")
    except Exception as e:
        logger.warning(f"Failed to load custom RP: {e}")


async def cleanup_bot_data() -> None:
    """Очистка данных бота из таблиц."""
    try:
        bot_me = await bot.get_me()
        if bot_me:
            await db.cleanup_bot_from_all_tables(bot_me.id)
            logger.info(f"✅ Bot {bot_me.id} data cleaned")
    except TelegramAPIError as e:
        logger.warning(f"Failed to get bot info: {e}")
    except Exception as e:
        logger.warning(f"Error cleaning bot data: {e}")


async def init_tag_categories() -> None:
    """Инициализация категорий тегов."""
    try:
        from handlers.tag_categories import init_categories
        await init_categories()
        logger.info("✅ Tag categories initialized")
    except ImportError:
        logger.debug("tag_categories module not available")
    except AttributeError as e:
        logger.warning(f"Tag categories init failed (old DB method): {e}")
    except Exception as e:
        logger.warning(f"Tag categories init failed: {e}")


def create_background_task(coro, name: str) -> None:
    """Создает фоновую задачу с отслеживанием."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(lambda t: _background_tasks.discard(t))
    task.add_done_callback(
        lambda t: logger.error(f"Background task '{name}' failed", exc_info=t.exception())
        if t.exception() else None
    )
    logger.debug(f"Background task '{name}' started")


# ==================== ЖИЗНЕННЫЙ ЦИКЛ БОТА ====================

async def on_startup() -> None:
    """Действия при запуске бота."""
    logger.info("🚀 Starting NEXUS Bot v5.3.0...")
    
    # 1. Инициализация БД
    if not await init_database():
        logger.critical("Cannot start without database")
        sys.exit(1)
    
    # 2. Параллельная инициализация
    await asyncio.gather(
        init_tag_categories(),
        load_custom_rp_on_startup(),
        return_exceptions=True
    )
    
    # 3. Очистка данных бота
    await cleanup_bot_data()
    
    # 4. Запуск фоновых задач
    create_background_task(auto_register_all_chat_members(), "auto_register")
    create_background_task(schedule_streak_updates(), "streak_updates")
    
    # 5. Запуск планировщика утренней очистки
    try:
        from utils.auto_delete import schedule_morning_cleanup
        create_background_task(schedule_morning_cleanup(bot), "morning_cleanup")
        logger.info("✅ Morning cleanup scheduler started")
    except ImportError:
        logger.debug("auto_delete module not available")
    except Exception as e:
        logger.warning(f"Morning cleanup scheduler failed: {e}")
    
    # 6. Обновление стриков при старте
    try:
        from handlers.stats import update_all_streaks
        await update_all_streaks()
        logger.info("✅ Initial streak update completed")
    except Exception as e:
        logger.warning(f"Initial streak update failed: {e}")
    
    logger.info("✅ NEXUS Bot v5.3.0 successfully started!")
    logger.info("📡 Bot is ready to receive messages!")


async def on_shutdown() -> None:
    """Действия при остановке бота."""
    logger.info("🛑 Shutting down NEXUS Bot...")
    
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


# ==================== ОБРАБОТКА СИГНАЛОВ ====================

def handle_sigterm():
    logger.info("Received SIGTERM, initiating shutdown...")
    _shutdown_event.set()


# ==================== ОТЛАДОЧНЫЙ ХЕНДЛЕР ====================

@dp.message()
async def debug_unhandled_messages(message: types.Message):
    """Логирует НЕОБРАБОТАННЫЕ сообщения."""
    text_preview = message.text[:100] if message.text else (
        "📷 ФОТО" if message.photo else "🎥 ВИДЕО" if message.video else "ДРУГОЕ"
    )
    
    logger.warning(f"⚠️ UNHANDLED: chat={message.chat.id} user={message.from_user.id} content={text_preview}")


# ==================== ТОЧКА ВХОДА ====================

async def main() -> None:
    """Главная функция."""
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
        loop.add_signal_handler(signal.SIGINT, handle_sigterm)
    except NotImplementedError:
        pass
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("📡 Starting long-polling...")
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.critical(f"💥 Fatal error in polling: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
# ==================== ЭКСТРЕННЫЙ ХЕНДЛЕР /start ====================
@dp.message(lambda msg: msg.text and "/start" in msg.text)
async def emergency_start(message: types.Message):
    """ЭКСТРЕННЫЙ ОБРАБОТЧИК /start"""
    logger.info(f"🚨 EMERGENCY /start from {message.from_user.id}")
    
    from config import START_BALANCE
    from database import db
    from utils.keyboards import main_menu
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    
    # Создаем пользователя если нет
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
        
        balance = await db.get_balance(user_id)
        vip_level = user.get('vip_level', 0) if user else 0
        
        text = (
            f"🚨 <b>ЭКСТРЕННЫЙ РЕЖИМ</b>\n\n"
            f"👋 Привет, <b>{first_name}</b>!\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n\n"
            f"👇 Выберите действие:"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_menu(is_admin=False))
    except Exception as e:
        logger.error(f"Emergency start error: {e}")
        await message.answer("❌ Ошибка. Попробуйте позже.")
