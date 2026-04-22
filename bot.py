#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 5.1.0-production
# ОПИСАНИЕ: NEXUS Chat Manager — Точка входа
# ИСПРАВЛЕНИЯ: Полная совместимость с aiosqlite, graceful shutdown, фоновые задачи
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

# Загрузка переменных окружения
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

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Глобальные переменные для управления жизненным циклом
_background_tasks: Set[asyncio.Task] = set()
_shutdown_event = asyncio.Event()


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu(user_id: int) -> InlineKeyboardMarkup:
    """
    Создает главное меню бота.
    
    Args:
        user_id: ID пользователя для проверки прав администратора
        
    Returns:
        InlineKeyboardMarkup с кнопками меню
    """
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


# ==================== ТЕСТОВЫЕ КОМАНДЫ ====================

@dp.message(lambda msg: msg.text and msg.text.lower() == "/ping")
async def cmd_ping(message: types.Message) -> None:
    """Проверка работоспособности бота."""
    if message is None:
        return
    await message.answer("🏓 PONG! Бот работает!")


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
                logger.debug(f"✅ Bot set for {module_name}")
        except ImportError:
            logger.debug(f"Module {module_name} not available")
        except Exception as e:
            logger.warning(f"Failed to set bot for {module_name}: {e}")


setup_bot_for_modules()


# ==================== ИМПОРТ РОУТЕРОВ (с fallback) ====================

def load_routers() -> None:
    """
    Загружает все роутеры с обработкой отсутствующих модулей.
    """
    router_modules = [
        "handlers.start",
        "handlers.profile",
        "handlers.economy",
        "handlers.tictactoe",
        "handlers.stats",
        "handlers.vip",
        "handlers.tag",
        "handlers.admin",  # Админ-панель
        "handlers.ai_assistant",
        "handlers.referral",
        "handlers.tag_admin",
        "handlers.tag_user",
        "handlers.tag_trigger",
        "handlers.ranks",
        "handlers.rating",
        "handlers.smart_commands",
    ]
    
    loaded = 0
    failed = 0
    
    for module_name in router_modules:
        try:
            module = __import__(module_name, fromlist=["router"])
            router = getattr(module, "router", None)
            if router:
                dp.include_router(router)
                loaded += 1
                logger.debug(f"✅ Loaded router: {module_name}")
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


# Загружаем роутеры
load_routers()


# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ====================

from database import db, DatabaseError

async def init_database() -> bool:
    """
    Инициализация базы данных с обработкой ошибок.
    
    Returns:
        True если успешно, иначе False
    """
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
    """Автоматическая регистрация всех участников чатов (в фоне)."""
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
            
            await asyncio.sleep(0.5)  # Защита от флуда
        
        if registered > 0:
            logger.info(f"✅ Auto-registered {registered} new users")
            
    except Exception as e:
        logger.error(f"Error in auto_register_all_chat_members: {e}")


async def schedule_streak_updates() -> None:
    """Периодическое обновление стриков (каждый час)."""
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
    except Exception as e:
        logger.warning(f"Tag categories init failed: {e}")


async def init_rp_tables_safe() -> None:
    """Безопасная инициализация РП таблиц."""
    try:
        from handlers.rp_tables import init_rp_tables
        await init_rp_tables()
        logger.info("✅ RP tables initialized")
    except ImportError:
        logger.debug("rp_tables module not found")
    except Exception as e:
        logger.warning(f"RP tables init failed: {e}")


def create_background_task(coro, name: str) -> None:
    """
    Создает фоновую задачу с отслеживанием.
    
    Args:
        coro: Корутина для выполнения
        name: Имя задачи для логирования
    """
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
    logger.info("🚀 Starting NEXUS Bot v5.1...")
    
    # 1. Инициализация БД (КРИТИЧЕСКИ)
    if not await init_database():
        logger.critical("Cannot start without database")
        sys.exit(1)
    
    # 2. Параллельная инициализация некритических компонентов
    init_tasks = [
        init_tag_categories(),
        init_rp_tables_safe(),
        load_custom_rp_on_startup(),
    ]
    await asyncio.gather(*init_tasks, return_exceptions=True)
    
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
    
    logger.info("✅ NEXUS Bot v5.1 successfully started!")


async def on_shutdown() -> None:
    """Действия при остановке бота."""
    logger.info("🛑 Shutting down NEXUS Bot...")
    
    # Сигнализируем фоновым задачам о завершении
    _shutdown_event.set()
    
    # Отменяем все фоновые задачи
    for task in _background_tasks:
        task.cancel()
        logger.debug(f"Cancelled task: {task.get_name()}")
    
    # Ждем завершения задач (с таймаутом)
    if _background_tasks:
        done, pending = await asyncio.wait(
            _background_tasks,
            timeout=5.0
        )
        for task in pending:
            logger.warning(f"Task {task.get_name()} did not finish in time")
    
    # Закрываем соединения
    try:
        await db.close()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.warning(f"Error closing database: {e}")
    
    try:
        await bot.session.close()
        logger.info("✅ Bot session closed")
    except Exception as e:
        logger.warning(f"Error closing bot session: {e}")
    
    logger.info("👋 NEXUS Bot stopped. Goodbye!")


# ==================== ОБРАБОТКА СИГНАЛОВ ====================

def handle_sigterm():
    """Обработчик SIGTERM для корректного завершения."""
    logger.info("Received SIGTERM, initiating shutdown...")
    _shutdown_event.set()


# ==================== ТОЧКА ВХОДА ====================

async def main() -> None:
    """Главная функция запуска бота."""
    # Регистрируем обработчики сигналов
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
        loop.add_signal_handler(signal.SIGINT, handle_sigterm)
    except NotImplementedError:
        # Windows не поддерживает add_signal_handler
        pass
    
    # Регистрируем startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("📡 Starting long-polling...")
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    except asyncio.CancelledError:
        logger.info("Polling cancelled")
    except Exception as e:
        logger.critical(f"💥 Fatal error in polling: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except SystemExit:
        logger.info("👋 System exit")
    except Exception as e:
        logger.critical(f"💥 Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
