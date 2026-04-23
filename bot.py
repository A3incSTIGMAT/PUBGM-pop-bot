#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 6.0.7-user-fix-final
# ОПИСАНИЕ: NEXUS Chat Manager — ИСПРАВЛЕНО ОПРЕДЕЛЕНИЕ ПОЛЬЗОВАТЕЛЯ В CALLBACK
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
BOT_ID: Optional[int] = None

logger.info(f"🔧 Bot starting with OWNER_ID: {OWNER_ID}")

# ==================== БОТ ====================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

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
CACHE_TTL = 30
CACHE_TTL_ERROR = 5


async def get_user_cached(user_id: int) -> Optional[dict]:
    """Получение пользователя с кэшированием."""
    if user_id is None or db is None:
        return None
    
    now = time.time()
    
    if user_id in _user_cache:
        if now - _cache_time.get(user_id, 0) < CACHE_TTL:
            return _user_cache[user_id]
    
    try:
        user = await db.get_user(user_id)
        ttl = CACHE_TTL if user else CACHE_TTL_ERROR
        _user_cache[user_id] = user
        _cache_time[user_id] = now
        return user
    except Exception as e:
        logger.warning(f"⚠️ DB error for user {user_id}: {e}")
        _user_cache[user_id] = None
        _cache_time[user_id] = now
        return None


async def get_balance_safe(user_id: int) -> int:
    """Безопасное получение баланса."""
    if user_id is None or db is None:
        return 0
    try:
        return await db.get_balance(user_id) or 0
    except Exception:
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
    except Exception:
        pass
    return default_stats


def safe_int(value: Any) -> int:
    """Безопасное преобразование в int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        import html
        return html.escape(str(text))
    except Exception:
        return ""


# ==================== ПОЛУЧЕНИЕ РЕАЛЬНОГО ID ПОЛЬЗОВАТЕЛЯ ====================

def get_real_user_id_from_callback(callback: CallbackQuery) -> Optional[int]:
    """
    Получить НАСТОЯЩИЙ ID пользователя из callback.
    🔥 В группах callback.from_user.id может быть ID бота!
    """
    if not callback or not callback.from_user:
        return None
    
    user_id = callback.from_user.id
    
    # Если это бот — пробуем получить настоящего пользователя из reply_to_message
    if BOT_ID and user_id == BOT_ID:
        if callback.message and callback.message.reply_to_message:
            reply_user = callback.message.reply_to_message.from_user
            if reply_user:
                logger.info(f"📩 Got real user_id from reply: {reply_user.id}")
                return reply_user.id
        
        # Fallback на владельца (для экстренного доступа)
        logger.warning(f"⚠️ Could not get real user, using OWNER_ID as fallback")
        return OWNER_ID
    
    return user_id


def get_user_name_from_callback(callback: CallbackQuery, user_id: int) -> str:
    """Получить имя пользователя из callback."""
    if not callback:
        return "Пользователь"
    
    # Если это бот — пробуем получить имя из reply
    if BOT_ID and callback.from_user.id == BOT_ID:
        if callback.message and callback.message.reply_to_message:
            reply_user = callback.message.reply_to_message.from_user
            if reply_user:
                return reply_user.first_name or "Пользователь"
    
    return callback.from_user.first_name or "Пользователь"


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


# ==================== ГЛАВНОЕ МЕНЮ ====================

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
    """Безопасное редактирование сообщения через callback."""
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
        f"👋 Привет, <b>{safe_html_escape(first_name)}</b>!\n"
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
    
    user = await get_user_cached(user_id)
    if not user and db:
        try:
            await db.create_user(user_id, username, first_name, START_BALANCE)
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
        "<code>/donate</code> — поддержать\n\n"
        f"💡 В группах: /start@{BOT_USERNAME}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("health"))
async def cmd_health(message: Message):
    """Команда /health — проверка состояния бота."""
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
    if not callback or not callback.message:
        return
    
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка определения пользователя", show_alert=True)
        return
    
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    first_name = get_user_name_from_callback(callback, user_id)
    
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

async def safe_menu_callback(callback: CallbackQuery, user_id: int, handler_func, error_msg: str = "❌ Ошибка"):
    """Безопасный вызов хендлера меню с подменой from_user."""
    if not callback or not callback.message:
        return
    
    try:
        # Создаём фейковое сообщение с правильным from_user
        fake_message = callback.message
        original_user = fake_message.from_user
        
        # Получаем имя пользователя
        first_name = get_user_name_from_callback(callback, user_id)
        
        fake_message.from_user = types.User(
            id=user_id, 
            is_bot=False, 
            first_name=first_name,
            username=None
        )
        
        await handler_func(fake_message)
        fake_message.from_user = original_user
        
    except Exception as e:
        logger.error(f"{error_msg}: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard(), parse_mode=ParseMode.HTML)
    finally:
        await callback.answer()


@dp.callback_query(F.data == "menu_vip")
async def menu_vip(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    from handlers.vip import cmd_vip
    await safe_menu_callback(callback, user_id, cmd_vip, "VIP error")


@dp.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    from handlers.profile import cmd_profile
    await safe_menu_callback(callback, user_id, cmd_profile, "Profile error")


@dp.callback_query(F.data == "menu_balance")
async def menu_balance(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    from handlers.economy import cmd_balance
    await safe_menu_callback(callback, user_id, cmd_balance, "Balance error")


@dp.callback_query(F.data == "menu_rank")
async def menu_rank(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    try:
        from handlers.ranks import cmd_rank
        await safe_menu_callback(callback, user_id, cmd_rank, "Rank error")
    except Exception as e:
        logger.error(f"Rank error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_xo")
async def menu_xo(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    try:
        from handlers.tictactoe import cmd_xo
        await safe_menu_callback(callback, user_id, cmd_xo, "XO error")
    except Exception as e:
        logger.error(f"XO error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    try:
        from handlers.stats import cmd_stats
        await safe_menu_callback(callback, user_id, cmd_stats, "Stats error")
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_all")
async def menu_all(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    try:
        from handlers.tag import cmd_all
        await safe_menu_callback(callback, user_id, cmd_all, "Tag all error")
    except Exception as e:
        logger.error(f"Tag all error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
        await callback.answer()


@dp.callback_query(F.data == "menu_ref")
async def menu_ref(callback: CallbackQuery):
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
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
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    try:
        from handlers.smart_commands import cmd_my_custom_rp
        await safe_menu_callback(callback, user_id, cmd_my_custom_rp, "RP error")
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
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    try:
        from handlers.rating import cmd_top_chats
        await safe_menu_callback(callback, user_id, cmd_top_chats, "Top chats error")
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
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    try:
        from handlers.economy import cmd_donate as economy_donate
        await safe_menu_callback(callback, user_id, economy_donate, "Donate error")
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
    """Админ-панель — исправлено определение пользователя."""
    if not callback or not callback.message:
        return
    
    user_id = get_real_user_id_from_callback(callback)
    if user_id is None:
        await callback.answer("❌ Ошибка определения пользователя", show_alert=True)
        return
    
    logger.info(f"🔥 ADMIN PANEL: user_id={user_id}, OWNER_ID={OWNER_ID}")
    
    if not is_super_admin(user_id):
        await callback.answer(f"❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        from handlers.admin import get_admin_menu_keyboard, get_admin_panel_text
        
        user = await get_user_cached(user_id)
        first_name = user.get('first_name') if user else get_user_name_from_callback(callback, user_id)
        
        text = get_admin_panel_text(user_id, first_name, callback.message.chat.id)
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Admin panel error: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка открытия админ-панели", reply_markup=get_back_keyboard())
    
    await callback.answer()


# ==================== УПРАВЛЕНИЕ ФОНОВЫМИ ЗАДАЧАМИ ====================

async def start_all_background_tasks():
    """Запуск всех фоновых задач с отслеживанием."""
    logger.info("🔄 Starting background tasks...")
    
    try:
        start_cleanup_task()
        logger.info("✅ Rate limiter cleanup started")
    except Exception as e:
        logger.warning(f"⚠️ Rate limiter cleanup error: {e}")
    
    try:
        from handlers.tictactoe import start_background_tasks as start_xo_tasks
        await start_xo_tasks()
        logger.info("✅ Tictactoe tasks started")
    except Exception as e:
        logger.warning(f"⚠️ Tictactoe tasks error: {e}")
    
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
    
    try:
        stop_cleanup_task()
        logger.info("✅ Rate limiter cleanup stopped")
    except Exception as e:
        logger.warning(f"⚠️ Rate limiter stop error: {e}")
    
    try:
        from handlers.tictactoe import stop_background_tasks as stop_xo_tasks
        await stop_xo_tasks()
        logger.info("✅ Tictactoe tasks stopped")
    except Exception as e:
        logger.warning(f"⚠️ Tictactoe stop error: {e}")
    
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


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

START_TIME = time.time()


async def on_startup():
    """Инициализация при запуске бота."""
    global START_TIME, BOT_ID
    START_TIME = time.time()
    
    # 🔥 Получаем ID бота
    me = await bot.get_me()
    BOT_ID = me.id
    logger.info(f"🤖 Bot ID: {BOT_ID}")
    
    logger.info("🚀 NEXUS Bot v6.0.7-user-fix-final starting...")
    
    setup_bot_for_modules()
    load_all_routers()
    await start_all_background_tasks()
    
    if db:
        try:
            await db.initialize()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ DB init error: {e}")
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        logger.info("✅ Custom RP loaded")
    except Exception as e:
        logger.warning(f"⚠️ Custom RP: {e}")
    
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
    
    await stop_all_background_tasks()
    
    _user_cache.clear()
    _cache_time.clear()
    
    if db and hasattr(db, 'close'):
        try:
            await db.close()
            logger.info("✅ Database closed")
        except Exception as e:
            logger.warning(f"⚠️ DB close error: {e}")
    
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
