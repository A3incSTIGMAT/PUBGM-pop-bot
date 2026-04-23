#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 6.0.6-hardened
# ОПИСАНИЕ: NEXUS Chat Manager — ПРОДАКШН ВЕРСИЯ С ИСПРАВЛЕНИЯМИ
# ============================================

import asyncio
import logging
import sys
import time
from typing import Dict, Set, Optional, Any

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from dotenv import load_dotenv

load_dotenv()

# ==================== ЛОГИРОВАНИЕ ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГ ====================

from config import (
    BOT_TOKEN, START_BALANCE, ADMIN_IDS, SUPER_ADMIN_IDS, 
    BOT_USERNAME, GAME_COMMISSION, MORNING_CLEANUP_HOUR,
    DONATE_URL, DONATE_BANK, DONATE_RECEIVER
)

if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN not set!")
    sys.exit(1)

ADMIN_IDS = ADMIN_IDS if ADMIN_IDS is not None else []
SUPER_ADMIN_IDS = SUPER_ADMIN_IDS if SUPER_ADMIN_IDS is not None else []
START_BALANCE = START_BALANCE if START_BALANCE is not None else 1000

# 🔥 ВЛАДЕЛЕЦ — ЖЁСТКИЙ ХАРДКОД
OWNER_ID = 895844198

logger.info(f"🔧 Bot starting with OWNER_ID: {OWNER_ID}")

# ==================== БОТ ====================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Хранилище фоновых задач с автоочисткой
_background_tasks: Set[asyncio.Task] = set()
_cleanup_tasks: list[asyncio.Task] = []

# ==================== RATE LIMITER ====================

from utils.rate_limiter import (
    RateLimiter, 
    start_cleanup_task, 
    stop_cleanup_task
)

daily_limiter = RateLimiter(limit=1, period=10)
transfer_limiter = RateLimiter(limit=5, period=60)
game_limiter = RateLimiter(limit=10, period=60)
all_limiter = RateLimiter(limit=3, period=300)

# ==================== БАЗА ДАННЫХ ====================

from database import db, DatabaseError

_user_cache: Dict[int, Optional[dict]] = {}
_cache_time: Dict[int, float] = {}
CACHE_TTL = 30  # секунд для успешных запросов
CACHE_TTL_ERROR = 5  # секунд для ошибок/отсутствующих пользователей


async def get_user_cached(user_id: int) -> Optional[dict]:
    """
    Получение пользователя с кэшированием.
    🔥 Кэширует и ошибки/None с коротким TTL для защиты БД.
    """
    if user_id is None or db is None:
        return None
    
    now = time.time()
    
    # Проверяем кэш (включая закэшированные None)
    if user_id in _user_cache:
        if now - _cache_time.get(user_id, 0) < CACHE_TTL:
            return _user_cache[user_id]
    
    try:
        user = await db.get_user(user_id)
        # Кэшируем результат с соответствующим TTL
        ttl = CACHE_TTL if user else CACHE_TTL_ERROR
        _user_cache[user_id] = user
        _cache_time[user_id] = now
        return user
    except Exception as e:
        logger.warning(f"⚠️ DB error for user {user_id}: {e}")
        # Кэшируем ошибку на короткое время
        _user_cache[user_id] = None
        _cache_time[user_id] = now
        return None


async def get_balance_safe(user_id: int) -> int:
    """Безопасное получение баланса."""
    if user_id is None or db is None:
        return 0
    try:
        return await db.get_balance(user_id) or 0
    except Exception as e:
        logger.debug(f"Balance error for {user_id}: {e}")
        return 0


async def get_user_stats_safe(user_id: int) -> dict:
    """Безопасное получение статистики."""
    default_stats = {'wins': 0, 'games_played': 0, 'losses': 0}
    if user_id is None or db is None:
        return default_stats
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return {
                'wins': stats.get('wins', 0) or 0,
                'games_played': stats.get('games_played', 0) or 0,
                'losses': stats.get('losses', 0) or 0,
            }
    except Exception as e:
        logger.debug(f"Stats error for {user_id}: {e}")
    return default_stats


def safe_int(value: Any) -> int:
    """Безопасное преобразование в int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


# ==================== ПРОВЕРКА АДМИНА ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    """Проверка прав супер-админа."""
    if user_id is None:
        return False
    try:
        return int(user_id) == OWNER_ID or int(user_id) in SUPER_ADMIN_IDS
    except (ValueError, TypeError):
        return False


async def check_is_admin(user_id: int, chat_id: int) -> bool:
    """Проверка прав администратора."""
    if user_id is None:
        return False
    
    if is_super_admin(user_id):
        return True
    
    if user_id in ADMIN_IDS:
        return True
    
    if chat_id and bot:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return member.status in ['creator', 'administrator']
        except Exception:
            pass
    
    return False


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура главного меню."""
    keyboard = [
        [InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="menu_vip"),
         InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="menu_profile")],
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="menu_balance"),
         InlineKeyboardButton(text="🏆 РАНГ", callback_data="menu_rank")],
        [InlineKeyboardButton(text="🎮 КРЕСТИКИ-НОЛИКИ", callback_data="menu_xo"),
         InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="menu_stats")],
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="menu_all"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="menu_ref")],
        [InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="menu_relations"),
         InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="menu_groups")],
        [InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="menu_rp"),
         InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="menu_tags")],
        [InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="menu_topchats"),
         InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="menu_privacy")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="menu_help"),
         InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="menu_donate")],
        [InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="menu_feedback")]
    ]
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard(callback_data: str = "back_to_menu") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой «Назад»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])


async def safe_callback_edit(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    """
    Безопасное редактирование сообщения через callback.
    🔥 Гарантирует ответ клиенту Telegram в любой ситуации.
    """
    if not callback or not callback.message:
        return False
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        logger.warning(f"⚠️ Edit error: {e}")
        try:
            await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            return True
        except Exception as e2:
            logger.error(f"❌ Fallback send failed: {e2}")
            return False
    except Exception as e:
        logger.error(f"❌ Edit failed: {e}")
        return False


# ==================== УПРАВЛЕНИЕ ФОНОВЫМИ ЗАДАЧАМИ ====================

async def start_all_background_tasks():
    """Запуск всех фоновых задач с отслеживанием."""
    logger.info("🔄 Starting background tasks...")
    
    # 1. Rate limiter cleanup
    try:
        start_cleanup_task()
        logger.info("✅ Rate limiter cleanup started")
    except Exception as e:
        logger.warning(f"⚠️ Rate limiter cleanup error: {e}")
    
    # 2. Tictactoe background tasks
    try:
        from handlers.tictactoe import start_background_tasks as start_xo_tasks
        await start_xo_tasks()
        logger.info("✅ Tictactoe tasks started")
    except Exception as e:
        logger.warning(f"⚠️ Tictactoe tasks error: {e}")
    
    # 3. Morning cleanup (с автоочисткой задачи)
    try:
        from utils.auto_delete import schedule_morning_cleanup
        task = asyncio.create_task(schedule_morning_cleanup(bot))
        _cleanup_tasks.append(task)
        task.add_done_callback(lambda t: _cleanup_tasks.remove(t) if t in _cleanup_tasks else None)
        logger.info("✅ Morning cleanup scheduled")
    except Exception as e:
        logger.warning(f"⚠️ Morning cleanup error: {e}")
    
    logger.info("✅ All background tasks started")


async def stop_all_background_tasks():
    """Остановка всех фоновых задач."""
    logger.info("🛑 Stopping background tasks...")
    
    # 1. Rate limiter cleanup
    try:
        stop_cleanup_task()
        logger.info("✅ Rate limiter cleanup stopped")
    except Exception as e:
        logger.warning(f"⚠️ Rate limiter stop error: {e}")
    
    # 2. Tictactoe tasks
    try:
        from handlers.tictactoe import stop_background_tasks as stop_xo_tasks
        await stop_xo_tasks()
        logger.info("✅ Tictactoe tasks stopped")
    except Exception as e:
        logger.warning(f"⚠️ Tictactoe stop error: {e}")
    
    # 3. Остальные задачи
    for task in _cleanup_tasks:
        if task and not task.done():
            task.cancel()
    
    if _cleanup_tasks:
        try:
            await asyncio.gather(*_cleanup_tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"⚠️ Error gathering cleanup tasks: {e}")
    
    _cleanup_tasks.clear()
    logger.info("✅ All background tasks stopped")


# ==================== ГЛАВНОЕ МЕНЮ ====================

async def render_main_menu(user_id: int, chat_id: int, first_name: str) -> tuple[str, InlineKeyboardMarkup]:
    """Рендер текста и клавиатуры главного меню."""
    is_admin = await check_is_admin(user_id, chat_id)
    user = await get_user_cached(user_id)
    balance = await get_balance_safe(user_id)
    vip_level = safe_int(user.get('vip_level')) if user else 0
    daily_streak = safe_int(user.get('daily_streak')) if user else 0
    stats = await get_user_stats_safe(user_id)
    
    text = (
        f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
        f"👋 Привет, <b>{first_name}</b>!\n"
        f"💰 Баланс: <b>{balance}</b> NCoin\n"
        f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n"
        f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
        f"🎮 XO: <b>{stats['wins']}</b> побед ({stats['games_played']} игр)\n\n"
        f"👇 Выберите действие:"
    )
    return text, get_main_menu(is_admin)


# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    """Команда /start — главное меню."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    chat_id = message.chat.id if message.chat else user_id
    
    logger.info(f"🚀 /start from {user_id}")
    
    # Регистрация пользователя если нужно
    user = await get_user_cached(user_id)
    if not user and db:
        try:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            # Обновляем кэш
            _user_cache.pop(user_id, None)
            await get_user_cached(user_id)
        except Exception as e:
            logger.error(f"Create user error: {e}")
    
    text, keyboard = await render_main_menu(user_id, chat_id, first_name)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help — справка."""
    if not message:
        return
    
    text = (
        "🤖 <b>NEXUS CHAT MANAGER — ПОМОЩЬ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📌 ОСНОВНЫЕ КОМАНДЫ:</b>\n"
        "<code>/start</code> — главное меню\n"
        "<code>/daily</code> — ежедневный бонус\n"
        "<code>/balance</code> — баланс\n"
        "<code>/stats</code> — статистика\n"
        "<code>/top</code> — топы\n"
        "<code>/xo</code> — крестики-нолики\n"
        "<code>/vip</code> — VIP статус\n"
        "<code>/profile</code> — профиль\n"
        "<code>/donate</code> — поддержать\n"
        "<code>/health</code> — проверка бота (админ)\n\n"
        f"💡 В группах: /start@{BOT_USERNAME}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("health"))
async def cmd_health(message: Message):
    """Команда /health — проверка состояния бота (для админов)."""
    if not message or not message.from_user:
        return
    
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Доступ только для владельца", parse_mode=ParseMode.HTML)
        return
    
    status = {
        "🤖 Бот": "✅ Работает",
        "🗄️ База данных": "✅ Подключена" if db else "❌ Отключена",
        "💾 Кэш пользователей": f"{len(_user_cache)} записей",
        "🔄 Фоновые задачи": f"{len(_background_tasks) + len(_cleanup_tasks)} активных",
        "⏱️ Аптайм": f"{time.time() - START_TIME:.0f} сек" if 'START_TIME' in globals() else "N/A"
    }
    
    text = "🏥 <b>HEALTH CHECK</b>\n\n" + "\n".join(f"{k}: {v}" for k, v in status.items())
    await message.answer(text, parse_mode=ParseMode.HTML)


# ==================== ПРЯМЫЕ ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("daily"))
async def cmd_daily_direct(message: Message):
    """Прямой обработчик /daily."""
    if not message or not message.from_user:
        return
    logger.info(f"🎁 /daily from {message.from_user.id}")
    try:
        from handlers.economy import cmd_daily
        await cmd_daily(message)
    except Exception as e:
        logger.error(f"Daily error: {e}", exc_info=True)
        await message.answer("❌ Ошибка получения бонуса. Попробуйте позже.", parse_mode=ParseMode.HTML)


@dp.message(Command("balance"))
async def cmd_balance_direct(message: Message):
    """Прямой обработчик /balance."""
    if not message or not message.from_user:
        return
    logger.info(f"💰 /balance from {message.from_user.id}")
    try:
        from handlers.economy import cmd_balance
        await cmd_balance(message)
    except Exception as e:
        logger.error(f"Balance error: {e}", exc_info=True)
        await message.answer("❌ Ошибка получения баланса.", parse_mode=ParseMode.HTML)


@dp.message(Command("profile"))
async def cmd_profile_direct(message: Message):
    """Прямой обработчик /profile."""
    if not message or not message.from_user:
        return
    try:
        from handlers.profile import cmd_profile
        await cmd_profile(message)
    except Exception as e:
        logger.error(f"Profile error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки профиля.", parse_mode=ParseMode.HTML)


@dp.message(Command("stats"))
async def cmd_stats_direct(message: Message):
    """Прямой обработчик /stats."""
    if not message or not message.from_user:
        return
    try:
        from handlers.stats import cmd_stats
        await cmd_stats(message)
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки статистики.", parse_mode=ParseMode.HTML)


@dp.message(Command("top"))
async def cmd_top_direct(message: Message):
    """Прямой обработчик /top."""
    if not message or not message.from_user:
        return
    try:
        from handlers.stats import cmd_top
        await cmd_top(message)
    except Exception as e:
        logger.error(f"Top error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки топов.", parse_mode=ParseMode.HTML)


@dp.message(Command("vip"))
async def cmd_vip_direct(message: Message):
    """Прямой обработчик /vip."""
    if not message or not message.from_user:
        return
    try:
        from handlers.vip import cmd_vip
        await cmd_vip(message)
    except Exception as e:
        logger.error(f"VIP error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки VIP.", parse_mode=ParseMode.HTML)


# ==================== CALLBACK: НАЗАД ====================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Возврат в главное меню."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    first_name = callback.from_user.first_name or "Пользователь"
    
    text, keyboard = await render_main_menu(user_id, chat_id, first_name)
    
    if not await safe_callback_edit(callback, text, keyboard):
        await callback.answer("⚠️ Ошибка обновления", show_alert=False)
    else:
        await callback.answer()


# ==================== УСТАНОВКА БОТА ДЛЯ МОДУЛЕЙ ====================

def setup_bot_for_modules():
    """Передача экземпляра бота в модули."""
    modules = [
        ("handlers.tictactoe", "set_bot"),
        ("handlers.smart_commands", "set_bot"),
        ("handlers.referral", "set_bot"),
    ]
    for module_name, func_name in modules:
        try:
            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name, None)
            if func and callable(func):
                func(bot)
                logger.info(f"✅ Bot set for {module_name}")
        except Exception as e:
            logger.warning(f"⚠️ {module_name}.{func_name}: {e}")


# ==================== ЗАГРУЗКА ВСЕХ РОУТЕРОВ ====================

def load_all_routers():
    """Динамическая загрузка всех роутеров."""
    routers = [
        ("handlers.vip", "router"),
        ("handlers.profile", "router"),
        ("handlers.economy", "router"),
        ("handlers.tictactoe", "router"),
        ("handlers.stats", "router"),
        ("handlers.tag", "router"),
        ("handlers.admin", "router"),
        ("handlers.rating", "router"),
        ("handlers.smart_commands", "router"),
        ("handlers.referral", "router"),
        ("handlers.tag_user", "router"),
        ("handlers.ranks", "router"),
        ("handlers.tag_admin", "router"),
        ("handlers.tag_trigger", "router"),
    ]
    for module_name, attr_name in routers:
        try:
            module = __import__(module_name, fromlist=[attr_name])
            router = getattr(module, attr_name, None)
            if router:
                dp.include_router(router)
                logger.info(f"✅ Loaded: {module_name}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load {module_name}: {e}")


# ==================== ОБРАБОТЧИКИ КНОПОК МЕНЮ ====================

# Вспомогательная функция для безопасного вызова хендлеров меню
async def safe_menu_callback(callback: CallbackQuery, handler_func, error_msg: str = "❌ Ошибка"):
    """Безопасный вызов хендлера меню с обработкой ошибок."""
    if not callback or not callback.message:
        return
    try:
        await handler_func(callback.message)
    except Exception as e:
        logger.error(f"{error_msg}: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard(), parse_mode=ParseMode.HTML)
    finally:
        await callback.answer()


@dp.callback_query(F.data == "menu_vip")
async def menu_vip(callback: CallbackQuery):
    await safe_menu_callback(callback, lambda m: __import__("handlers.vip", fromlist=["cmd_vip"]).cmd_vip(m), "VIP error")


@dp.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    await safe_menu_callback(callback, lambda m: __import__("handlers.profile", fromlist=["cmd_profile"]).cmd_profile(m), "Profile error")


@dp.callback_query(F.data == "menu_balance")
async def menu_balance(callback: CallbackQuery):
    await safe_menu_callback(callback, lambda m: __import__("handlers.economy", fromlist=["cmd_balance"]).cmd_balance(m), "Balance error")


@dp.callback_query(F.data == "menu_rank")
async def menu_rank(callback: CallbackQuery):
    try:
        from handlers.ranks import cmd_rank
        await safe_menu_callback(callback, lambda m: cmd_rank(m), "Rank error")
    except Exception as e:
        logger.error(f"Rank error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_xo")
async def menu_xo(callback: CallbackQuery):
    try:
        from handlers.tictactoe import cmd_xo
        await safe_menu_callback(callback, lambda m: cmd_xo(m), "XO error")
    except Exception as e:
        logger.error(f"XO error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    try:
        from handlers.stats import cmd_stats
        await safe_menu_callback(callback, lambda m: cmd_stats(m), "Stats error")
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_all")
async def menu_all(callback: CallbackQuery):
    try:
        from handlers.tag import cmd_all
        await safe_menu_callback(callback, lambda m: cmd_all(m), "Tag all error")
    except Exception as e:
        logger.error(f"Tag all error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_ref")
async def menu_ref(callback: CallbackQuery):
    try:
        from handlers.referral import ref_menu_callback
        await ref_menu_callback(callback)
    except Exception as e:
        logger.error(f"Ref error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_relations")
async def menu_relations(callback: CallbackQuery):
    if not callback or not callback.message:
        return
    await safe_callback_edit(callback, "💕 <b>ОТНОШЕНИЯ</b>\n\nВ разработке.", get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_groups")
async def menu_groups(callback: CallbackQuery):
    if not callback or not callback.message:
        return
    await safe_callback_edit(callback, "👥 <b>ГРУППЫ</b>\n\nВ разработке.", get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_rp")
async def menu_rp(callback: CallbackQuery):
    try:
        from handlers.smart_commands import cmd_my_custom_rp
        await safe_menu_callback(callback, lambda m: cmd_my_custom_rp(m), "RP error")
    except Exception as e:
        logger.error(f"RP error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_tags")
async def menu_tags(callback: CallbackQuery):
    try:
        from handlers.tag_user import my_tags_menu_callback
        await my_tags_menu_callback(callback)
    except Exception as e:
        logger.error(f"Tags error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_topchats")
async def menu_topchats(callback: CallbackQuery):
    try:
        from handlers.rating import cmd_top_chats
        await safe_menu_callback(callback, lambda m: cmd_top_chats(m), "Top chats error")
    except Exception as e:
        logger.error(f"Top chats error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_privacy")
async def menu_privacy(callback: CallbackQuery):
    if not callback or not callback.message:
        return
    text = "🔒 <b>ПОЛИТИКА</b>\n\n• Telegram ID\n• Имя\n• Баланс\n• Статистика\n\nУдаление: /delete_my_data"
    await safe_callback_edit(callback, text, get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    if not callback or not callback.message:
        return
    await cmd_help(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "menu_donate")
async def menu_donate(callback: CallbackQuery):
    try:
        from handlers.economy import cmd_donate as economy_donate
        await safe_menu_callback(callback, lambda m: economy_donate(m), "Donate error")
    except Exception as e:
        logger.error(f"Donate error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_feedback")
async def menu_feedback(callback: CallbackQuery):
    if not callback or not callback.message:
        return
    text = "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\nНапишите: <code>/feedback ваш текст</code>"
    await safe_callback_edit(callback, text, get_back_keyboard())
    await callback.answer()


# 🔥 ИСПРАВЛЕННЫЙ ОБРАБОТЧИК АДМИН-ПАНЕЛИ
@dp.callback_query(F.data == "menu_admin")
async def menu_admin(callback: CallbackQuery):
    """
    Прокси-хендлер для админ-панели.
    🔥 Делегирует обработку в handlers.admin для единообразия.
    """
    if not callback or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    logger.info(f"🔥 ADMIN PANEL: user_id={user_id}, OWNER_ID={OWNER_ID}")
    
    if not is_super_admin(user_id):
        await callback.answer(f"❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        # 🔥 Делегируем обработку в handlers.admin
        from handlers.admin import admin_panel_callback
        await admin_panel_callback(callback)
    except Exception as e:
        logger.error(f"Admin panel error: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка открытия админ-панели", reply_markup=get_back_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer()


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

# Глобальная переменная для аптайма
START_TIME = time.time()


async def on_startup():
    """Инициализация при запуске бота."""
    global START_TIME
    START_TIME = time.time()
    
    logger.info("🚀 NEXUS Bot v6.0.6-hardened starting...")
    
    # Установка бота в модули
    setup_bot_for_modules()
    
    # Загрузка роутеров
    load_all_routers()
    
    # Запуск фоновых задач
    await start_all_background_tasks()
    
    # Инициализация БД
    if db:
        try:
            await db.initialize()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ DB init error: {e}")
    
    # Загрузка RP команд
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        logger.info("✅ Custom RP loaded")
    except Exception as e:
        logger.warning(f"⚠️ Custom RP: {e}")
    
    # Обновление стриков
    try:
        from handlers.stats import update_all_streaks
        await update_all_streaks()
        logger.info("✅ Streaks updated")
    except Exception as e:
        logger.warning(f"⚠️ Streaks update: {e}")
    
    logger.info("✅ ALL SYSTEMS GO! Бот готов к работе! 🎉")


async def on_shutdown():
    """Очистка при выключении бота."""
    logger.info("🛑 Shutting down NEXUS Bot...")
    
    # Остановка фоновых задач
    await stop_all_background_tasks()
    
    # Очистка кэша
    _user_cache.clear()
    _cache_time.clear()
    
    # Закрытие БД
    if db and hasattr(db, 'close'):
        try:
            await db.close()
            logger.info("✅ Database closed")
        except Exception as e:
            logger.warning(f"⚠️ DB close error: {e}")
    
    # Закрытие бота
    await bot.session.close()
    
    logger.info("👋 NEXUS Bot stopped gracefully")


@dp.message()
async def debug_unhandled(message: Message):
    """Логирование необработанных сообщений для отладки."""
    if not message:
        return
    text = message.text[:100] if message.text else "НЕ ТЕКСТ"
    chat_id = message.chat.id if message.chat else "N/A"
    user_id = message.from_user.id if message.from_user else "N/A"
    logger.debug(f"⚠️ UNHANDLED: chat={chat_id} user={user_id} text={text}")


async def main():
    """Точка входа."""
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("📡 Starting polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 Fatal error: {e}", exc_info=True)
        sys.exit(1)

