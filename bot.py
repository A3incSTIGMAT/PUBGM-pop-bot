#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 6.0.13-final
# ОПИСАНИЕ: NEXUS Chat Manager — ДОБАВЛЕН HANDLERS.RELATIONSHIPS
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
    if user_id is None or db is None:
        return None
    now = time.time()
    if user_id in _user_cache and now - _cache_time.get(user_id, 0) < CACHE_TTL:
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
    if user_id is None or db is None:
        return 0
    try:
        return await db.get_balance(user_id) or 0
    except Exception:
        return 0


async def get_user_stats_safe(user_id: int) -> dict:
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
    if value is None: return 0
    try: return int(value)
    except: return 0


def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try:
        import html
        return html.escape(str(text))
    except Exception:
        return ""


# ==================== ПРОВЕРКА АДМИНА ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    if user_id is None: return False
    try: return int(user_id) == OWNER_ID or int(user_id) in SUPER_ADMIN_IDS
    except: return False


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])


async def safe_callback_edit(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    if not callback or not callback.message: return False
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower(): return True
        try:
            await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            return True
        except: return False
    except: return False


async def render_main_menu(user_id: int, chat_id: int, first_name: str) -> tuple[str, InlineKeyboardMarkup]:
    is_admin = await check_is_admin(user_id, chat_id) if 'check_is_admin' in dir() else (is_super_admin(user_id))
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


async def check_is_admin(user_id: int, chat_id: int) -> bool:
    if user_id is None: return False
    if is_super_admin(user_id): return True
    if user_id in ADMIN_IDS: return True
    if chat_id and bot:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return member.status in ['creator', 'administrator']
        except: pass
    return False


# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    if not message or not message.from_user: return
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
    if not message: return
    text = (
        "🤖 <b>NEXUS CHAT MANAGER — ПОМОЩЬ</b>\n\n"
        "<b>📌 ОСНОВНЫЕ КОМАНДЫ:</b>\n"
        "<code>/start</code> — главное меню\n"
        "<code>/daily</code> — ежедневный бонус\n"
        "<code>/balance</code> — баланс\n"
        "<code>/stats</code> — статистика\n"
        "<code>/xo</code> — крестики-нолики\n"
        "<code>/vip</code> — VIP статус\n"
        "<code>/marry</code> — предложить брак 💍\n"
        "<code>/flirt</code> — флирт 💋\n"
        "<code>/hug</code> — объятия 🤗\n\n"
        f"💡 В группах: /start@{BOT_USERNAME}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


# ==================== ПРЯМЫЕ ОБРАБОТЧИКИ ====================

@dp.message(Command("daily"))
async def cmd_daily_direct(message: Message):
    if not message or not message.from_user: return
    try:
        from handlers.economy import cmd_daily
        await cmd_daily(message)
    except Exception as e:
        logger.error(f"Daily error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@dp.message(Command("balance"))
async def cmd_balance_direct(message: Message):
    if not message or not message.from_user: return
    try:
        from handlers.economy import cmd_balance
        await cmd_balance(message)
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@dp.message(Command("profile"))
async def cmd_profile_direct(message: Message):
    if not message or not message.from_user: return
    try:
        from handlers.profile import cmd_profile
        await cmd_profile(message)
    except Exception as e:
        logger.error(f"Profile error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@dp.message(Command("stats"))
async def cmd_stats_direct(message: Message):
    if not message or not message.from_user: return
    try:
        from handlers.stats import cmd_stats
        await cmd_stats(message)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@dp.message(Command("top"))
async def cmd_top_direct(message: Message):
    if not message or not message.from_user: return
    try:
        from handlers.stats import cmd_top
        await cmd_top(message)
    except Exception as e:
        logger.error(f"Top error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@dp.message(Command("vip"))
async def cmd_vip_direct(message: Message):
    if not message or not message.from_user: return
    try:
        from handlers.vip import cmd_vip
        await cmd_vip(message)
    except Exception as e:
        logger.error(f"VIP error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


# ==================== CALLBACK: НАЗАД ====================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    if not callback or not callback.message: return
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    first_name = callback.from_user.first_name or "Пользователь"
    
    text, keyboard = await render_main_menu(user_id, chat_id, first_name)
    
    if not await safe_callback_edit(callback, text, keyboard):
        await callback.answer("⚠️ Ошибка обновления", show_alert=False)
    else:
        await callback.answer()


# ==================== УСТАНОВКА БОТА ====================

def setup_bot_for_modules():
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


# ==================== ЗАГРУЗКА РОУТЕРОВ ====================

def load_all_routers():
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
        ("handlers.relationships", "router"),  # 🔥 ДОБАВЛЕНО!
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

@dp.callback_query(F.data == "menu_vip")
async def menu_vip(callback: CallbackQuery):
    try:
        from handlers.vip import cmd_vip
        await cmd_vip(callback.message)
    except Exception as e:
        logger.error(f"VIP error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    try:
        from handlers.profile import cmd_profile
        await cmd_profile(callback.message)
    except Exception as e:
        logger.error(f"Profile error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_balance")
async def menu_balance(callback: CallbackQuery):
    try:
        from handlers.economy import cmd_balance
        await cmd_balance(callback.message)
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_rank")
async def menu_rank(callback: CallbackQuery):
    try:
        from handlers.ranks import cmd_rank
        await cmd_rank(callback.message)
    except Exception as e:
        logger.error(f"Rank error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_xo")
async def menu_xo(callback: CallbackQuery):
    try:
        from handlers.tictactoe import cmd_xo
        await cmd_xo(callback.message)
    except Exception as e:
        logger.error(f"XO error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    try:
        from handlers.stats import cmd_stats
        await cmd_stats(callback.message)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_all")
async def menu_all(callback: CallbackQuery):
    try:
        from handlers.tag import cmd_all
        await cmd_all(callback.message)
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
    """Кнопка ОТНОШЕНИЯ — теперь работает!"""
    try:
        from handlers.relationships import relationships_menu
        await relationships_menu(callback)
    except Exception as e:
        logger.error(f"Relations error: {e}")
        await callback.message.answer("❌ Ошибка загрузки отношений", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_groups")
async def menu_groups(callback: CallbackQuery):
    await callback.message.edit_text("👥 <b>ГРУППЫ</b>\n\nВ разработке.", parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_rp")
async def menu_rp(callback: CallbackQuery):
    try:
        from handlers.smart_commands import cmd_my_custom_rp
        await cmd_my_custom_rp(callback.message)
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
        await cmd_top_chats(callback.message)
    except Exception as e:
        logger.error(f"Top chats error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_privacy")
async def menu_privacy(callback: CallbackQuery):
    text = "🔒 <b>ПОЛИТИКА</b>\n\n• Telegram ID\n• Имя\n• Баланс\n• Статистика\n\nУдаление: /delete_my_data"
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "menu_donate")
async def menu_donate(callback: CallbackQuery):
    try:
        from handlers.economy import cmd_donate as economy_donate
        await economy_donate(callback.message)
    except Exception as e:
        logger.error(f"Donate error: {e}")
        await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_feedback")
async def menu_feedback(callback: CallbackQuery):
    text = "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\nНапишите: <code>/feedback ваш текст</code>"
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_admin")
async def menu_admin(callback: CallbackQuery):
    if not callback or not callback.message or not callback.from_user: return
    user_id = callback.from_user.id
    
    if not is_super_admin(user_id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        from handlers.admin import admin_panel_callback
        await admin_panel_callback(callback)
    except ImportError as e:
        await callback.message.answer(f"❌ Ошибка импорта админ-панели!\n<code>{e}</code>", parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка открытия админ-панели\n<code>{e}</code>", parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    finally:
        await callback.answer()


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

async def start_all_background_tasks():
    try: start_cleanup_task(); logger.info("✅ Rate limiter started")
    except Exception as e: logger.warning(f"Rate limiter: {e}")
    
    try:
        from handlers.tictactoe import start_background_tasks as start_xo_tasks
        await start_xo_tasks(); logger.info("✅ Tictactoe tasks started")
    except Exception as e: logger.warning(f"Tictactoe: {e}")
    
    try:
        from utils.auto_delete import schedule_morning_cleanup
        task = asyncio.create_task(schedule_morning_cleanup(bot))
        _cleanup_tasks.append(task)
        logger.info("✅ Morning cleanup scheduled")
    except Exception as e: logger.warning(f"Cleanup: {e}")


async def stop_all_background_tasks():
    try: stop_cleanup_task()
    except: pass
    try:
        from handlers.tictactoe import stop_background_tasks as stop_xo_tasks
        await stop_xo_tasks()
    except: pass
    for task in _cleanup_tasks:
        if task and not task.done(): task.cancel()
    _cleanup_tasks.clear()


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

START_TIME = time.time()


async def on_startup():
    global START_TIME, BOT_ID
    START_TIME = time.time()
    me = await bot.get_me()
    BOT_ID = me.id
    logger.info(f"🤖 Bot ID: {BOT_ID}")
    logger.info("🚀 NEXUS Bot v6.0.13-final starting...")
    
    setup_bot_for_modules()
    load_all_routers()
    await start_all_background_tasks()
    
    if db:
        try: await db.initialize(); logger.info("✅ Database initialized")
        except Exception as e: logger.error(f"DB: {e}")
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands(); logger.info("✅ Custom RP loaded")
    except Exception as e: logger.warning(f"Custom RP: {e}")
    
    try:
        from handlers.stats import update_all_streaks
        await update_all_streaks(); logger.info("✅ Streaks updated")
    except Exception as e: logger.warning(f"Streaks: {e}")
    
    logger.info("✅ ALL SYSTEMS GO! Бот готов к работе! 🎉")


async def on_shutdown():
    logger.info("🛑 Shutting down...")
    await stop_all_background_tasks()
    _user_cache.clear(); _cache_time.clear()
    if db and hasattr(db, 'close'):
        try: await db.close()
        except: pass
    await bot.session.close()
    logger.info("👋 Stopped")


@dp.message()
async def debug_unhandled(message: Message):
    if not message: return
    text = message.text[:100] if message.text else "НЕ ТЕКСТ"
    logger.debug(f"⚠️ UNHANDLED: {message.chat.id if message.chat else 'N/A'} - {text}")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    logger.info("📡 Starting polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("👋 Interrupted")
    except Exception as e: logger.critical(f"💥 Fatal: {e}", exc_info=True); sys.exit(1)
