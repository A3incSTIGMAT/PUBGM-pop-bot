#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 7.1.0-production
# ОПИСАНИЕ: NEXUS Chat Manager — АВТОУДАЛЕНИЕ МЕНЮ + DAILY_BONUS CALLBACK
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

# 🔥 ВЛАДЕЛЕЦ
OWNER_ID = 895844198
BOT_ID: Optional[int] = None

logger.info(f"🔧 OWNER_ID: {OWNER_ID}")

# ==================== БОТ ====================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_background_tasks: Set[asyncio.Task] = set()
_cleanup_tasks: list[asyncio.Task] = []

# ==================== АВТОУДАЛЕНИЕ СООБЩЕНИЙ ====================

# Хранит ID последних сообщений бота: {chat_id: {user_id: [message_ids]}}
_bot_messages: Dict[int, Dict[int, list]] = {}
MAX_STORED_MESSAGES = 20  # Максимум хранимых ID сообщений на пользователя


async def delete_previous_bot_messages(chat_id: int, user_id: int, keep_last: int = 0) -> None:
    """
    Удаляет предыдущие сообщения бота для конкретного пользователя в чате.
    Оставляет keep_last последних сообщений (0 = удалить все).
    🔥 ДОБАВЛЕНО В V7.1.0
    """
    if chat_id is None or user_id is None:
        return
    
    if chat_id not in _bot_messages:
        _bot_messages[chat_id] = {}
    
    if user_id not in _bot_messages[chat_id]:
        _bot_messages[chat_id][user_id] = []
        return
    
    messages = _bot_messages[chat_id][user_id]
    
    if len(messages) <= keep_last:
        return
    
    # Удаляем все кроме keep_last последних
    to_delete = messages[:len(messages) - keep_last]
    _bot_messages[chat_id][user_id] = messages[len(messages) - keep_last:]
    
    for msg_id in to_delete:
        if msg_id is None:
            continue
        try:
            await bot.delete_message(chat_id, msg_id)
            await asyncio.sleep(0.05)
        except TelegramAPIError:
            pass


async def track_bot_message(chat_id: int, user_id: int, message_id: int) -> None:
    """
    Сохраняет ID сообщения бота для последующего автоудаления.
    🔥 ДОБАВЛЕНО В V7.1.0
    """
    if chat_id is None or user_id is None or message_id is None:
        return
    
    if chat_id not in _bot_messages:
        _bot_messages[chat_id] = {}
    
    if user_id not in _bot_messages[chat_id]:
        _bot_messages[chat_id][user_id] = []
    
    _bot_messages[chat_id][user_id].append(message_id)
    
    # Ограничиваем историю
    if len(_bot_messages[chat_id][user_id]) > MAX_STORED_MESSAGES:
        _bot_messages[chat_id][user_id] = _bot_messages[chat_id][user_id][-MAX_STORED_MESSAGES:]


async def safe_send_message(
    chat_id: int,
    text: str,
    user_id: Optional[int] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    delete_previous: bool = True,
    keep_last: int = 0
) -> Optional[Message]:
    """
    Безопасная отправка сообщения с автоудалением предыдущих.
    🔥 ДОБАВЛЕНО В V7.1.0
    """
    if chat_id is None or not text:
        return None
    
    if delete_previous and user_id is not None:
        await delete_previous_bot_messages(chat_id, user_id, keep_last)
    
    try:
        msg = await bot.send_message(
            chat_id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        
        if msg and user_id is not None:
            await track_bot_message(chat_id, user_id, msg.message_id)
        
        return msg
        
    except TelegramAPIError as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return None


# ==================== RATE LIMITER ====================

from utils.rate_limiter import RateLimiter, start_cleanup_task, stop_cleanup_task

daily_limiter = RateLimiter(limit=1, period=10)

# ==================== БАЗА ДАННЫХ ====================

from database import db, DatabaseError

_user_cache: Dict[int, Optional[dict]] = {}
_cache_time: Dict[int, float] = {}
CACHE_TTL = 30


async def get_user_cached(user_id: int) -> Optional[dict]:
    if user_id is None or db is None: return None
    now = time.time()
    if user_id in _user_cache and now - _cache_time.get(user_id, 0) < CACHE_TTL:
        return _user_cache[user_id]
    try:
        user = await db.get_user(user_id)
        _user_cache[user_id] = user
        _cache_time[user_id] = now
        return user
    except: return None


async def get_balance_safe(user_id: int) -> int:
    if user_id is None or db is None: return 0
    try: return await db.get_balance(user_id) or 0
    except: return 0


async def get_user_stats_safe(user_id: int) -> dict:
    if user_id is None or db is None: return {'wins': 0, 'games_played': 0}
    try:
        stats = await db.get_user_stats(user_id)
        if stats: return {'wins': stats.get('wins',0) or 0, 'games_played': stats.get('games_played',0) or 0}
    except: pass
    return {'wins': 0, 'games_played': 0}


def safe_int(value: Any) -> int:
    if value is None: return 0
    try: return int(value)
    except: return 0


def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try:
        import html
        return html.escape(str(text))
    except: return ""


# ==================== ПРОВЕРКА АДМИНА ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    if user_id is None: return False
    return user_id == OWNER_ID or user_id in SUPER_ADMIN_IDS


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
    is_admin = is_super_admin(user_id)
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
        except Exception as e: logger.error(f"Create user: {e}")
    
    text, keyboard = await render_main_menu(user_id, chat_id, first_name)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not message: return
    text = (
        "🤖 <b>NEXUS CHAT MANAGER</b>\n\n"
        "<b>📌 КОМАНДЫ:</b>\n"
        "<code>/start</code> — меню\n"
        "<code>/daily</code> — бонус\n"
        "<code>/balance</code> — баланс\n"
        "<code>/xo</code> — крестики-нолики\n"
        "<code>/vip</code> — VIP\n"
        "<code>/marry</code> — брак 💍\n"
        "<code>/flirt</code> — флирт 💋\n"
        f"💡 В группах: /start@{BOT_USERNAME}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


# ==================== ПРЯМЫЕ ОБРАБОТЧИКИ ====================

@dp.message(Command("daily"))
async def cmd_daily_direct(message: Message):
    if not message: return
    try:
        from handlers.economy import cmd_daily
        await cmd_daily(message)
    except Exception as e: logger.error(f"Daily: {e}")

@dp.message(Command("balance"))
async def cmd_balance_direct(message: Message):
    if not message: return
    try:
        from handlers.economy import cmd_balance
        await cmd_balance(message)
    except Exception as e: logger.error(f"Balance: {e}")

@dp.message(Command("profile"))
async def cmd_profile_direct(message: Message):
    if not message: return
    try:
        from handlers.profile import cmd_profile
        await cmd_profile(message)
    except Exception as e: logger.error(f"Profile: {e}")

@dp.message(Command("stats"))
async def cmd_stats_direct(message: Message):
    if not message: return
    try:
        from handlers.stats import cmd_stats
        await cmd_stats(message)
    except Exception as e: logger.error(f"Stats: {e}")

@dp.message(Command("top"))
async def cmd_top_direct(message: Message):
    if not message: return
    try:
        from handlers.stats import cmd_top
        await cmd_top(message)
    except Exception as e: logger.error(f"Top: {e}")

@dp.message(Command("vip"))
async def cmd_vip_direct(message: Message):
    if not message: return
    try:
        from handlers.vip import cmd_vip
        await cmd_vip(message)
    except Exception as e: logger.error(f"VIP: {e}")


# ==================== CALLBACK: НАЗАД (С АВТОУДАЛЕНИЕМ) ====================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """
    Обработчик кнопки НАЗАД.
    🔥 V7.1.0: Удаляет предыдущее меню и показывает новое.
    """
    if not callback or not callback.message: return
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    first_name = callback.from_user.first_name or "Пользователь"
    
    is_admin = is_super_admin(user_id)
    balance = await get_balance_safe(user_id)
    stats = await get_user_stats_safe(user_id)
    
    text = (
        f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
        f"💰 Баланс: <b>{balance}</b> NCoin\n"
        f"🎮 XO: <b>{stats['wins']}</b> побед ({stats['games_played']} игр)\n\n"
        f"👇 Выберите категорию:"
    )
    
    # Пробуем отредактировать текущее сообщение
    if not await safe_callback_edit(callback, text, get_main_menu(is_admin)):
        # Если не получилось — удаляем старое и отправляем новое
        await delete_previous_bot_messages(chat_id, user_id, keep_last=0)
        await safe_send_message(chat_id, text, user_id, reply_markup=get_main_menu(is_admin), delete_previous=False)
    
    await callback.answer()


# ==================== CALLBACK: DAILY_BONUS (ИЗ СВОДКИ) ====================

@dp.callback_query(F.data == "daily_bonus")
async def callback_daily_bonus(callback: CallbackQuery):
    """
    Обработчик инлайн-кнопки «Ежедневная награда» из сводки.
    🔥 ДОБАВЛЕНО В V7.1.0
    """
    if not callback or not callback.message: return
    
    try:
        await callback.answer()
    except Exception:
        pass
    
    try:
        from handlers.economy import cmd_daily
        # Создаём фейковое сообщение для передачи в обработчик
        # cmd_daily ожидает Message, но мы можем передать callback.message
        await cmd_daily(callback.message)
    except Exception as e:
        logger.error(f"Daily bonus callback error: {e}")
        try:
            await callback.message.answer(
                "❌ Ошибка получения бонуса. Попробуйте /daily",
                reply_markup=get_back_keyboard()
            )
        except Exception:
            pass


# ==================== УСТАНОВКА БОТА ====================

def setup_bot_for_modules():
    for module_name, func_name in [
        ("handlers.tictactoe", "set_bot"),
        ("handlers.smart_commands", "set_bot"),
        ("handlers.referral", "set_bot"),
    ]:
        try:
            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name, None)
            if func and callable(func):
                func(bot)
                logger.info(f"✅ Bot set for {module_name}")
        except Exception as e: logger.warning(f"⚠️ {module_name}: {e}")


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
        ("handlers.relationships", "router"),
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
        except Exception as e: logger.warning(f"⚠️ {module_name}: {e}")


# ==================== ОБРАБОТЧИКИ КНОПОК МЕНЮ (С АВТОУДАЛЕНИЕМ) ====================

@dp.callback_query(F.data == "menu_vip")
async def menu_vip(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.vip import cmd_vip; await cmd_vip(callback.message)
    except Exception as e: logger.error(f"VIP: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.profile import cmd_profile; await cmd_profile(callback.message)
    except Exception as e: logger.error(f"Profile: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_balance")
async def menu_balance(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.economy import cmd_balance; await cmd_balance(callback.message)
    except Exception as e: logger.error(f"Balance: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_rank")
async def menu_rank(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.ranks import cmd_rank; await cmd_rank(callback.message)
    except Exception as e: logger.error(f"Rank: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_xo")
async def menu_xo(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.tictactoe import cmd_xo; await cmd_xo(callback.message)
    except Exception as e: logger.error(f"XO: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.stats import cmd_stats; await cmd_stats(callback.message)
    except Exception as e: logger.error(f"Stats: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_all")
async def menu_all(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.tag import cmd_all; await cmd_all(callback.message)
    except Exception as e: logger.error(f"Tag: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_ref")
async def menu_ref(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.referral import ref_menu_callback; await ref_menu_callback(callback)
    except Exception as e: logger.error(f"Ref: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_relations")
async def menu_relations(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.relationships import relationships_menu; await relationships_menu(callback)
    except Exception as e: logger.error(f"Relations: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_groups")
async def menu_groups(callback: CallbackQuery):
    text = "👥 <b>ГРУППЫ</b>\n\nВ разработке."
    if not await safe_callback_edit(callback, text, get_back_keyboard()):
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_rp")
async def menu_rp(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.smart_commands import cmd_my_custom_rp; await cmd_my_custom_rp(callback.message)
    except Exception as e: logger.error(f"RP: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_tags")
async def menu_tags(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.tag_user import my_tags_menu_callback; await my_tags_menu_callback(callback)
    except Exception as e: logger.error(f"Tags: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_topchats")
async def menu_topchats(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.rating import cmd_top_chats; await cmd_top_chats(callback.message)
    except Exception as e: logger.error(f"TopChats: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_privacy")
async def menu_privacy(callback: CallbackQuery):
    text = "🔒 <b>ПОЛИТИКА</b>\n\n• Telegram ID\n• Имя\n• Баланс\n• Статистика\n\nУдаление: /delete_my_data"
    if not await safe_callback_edit(callback, text, get_back_keyboard()):
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    await cmd_help(callback.message); await callback.answer()

@dp.callback_query(F.data == "menu_donate")
async def menu_donate(callback: CallbackQuery):
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else callback.from_user.id,
        callback.from_user.id,
        keep_last=0
    )
    try: from handlers.economy import cmd_donate as economy_donate; await economy_donate(callback.message)
    except Exception as e: logger.error(f"Donate: {e}"); await callback.message.answer("❌ Ошибка", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_feedback")
async def menu_feedback(callback: CallbackQuery):
    text = "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\nНапишите: <code>/feedback ваш текст</code>"
    if not await safe_callback_edit(callback, text, get_back_keyboard()):
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_admin")
async def menu_admin(callback: CallbackQuery):
    if not callback or not callback.message or not callback.from_user: return
    user_id = callback.from_user.id
    if not is_super_admin(user_id):
        await callback.answer("❌ Доступ запрещён", show_alert=True); return
    await delete_previous_bot_messages(
        callback.message.chat.id if callback.message.chat else user_id,
        user_id,
        keep_last=0
    )
    try:
        from handlers.admin import admin_panel_callback
        await admin_panel_callback(callback)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

async def start_all_background_tasks():
    try: start_cleanup_task()
    except: pass
    try:
        from utils.auto_delete import schedule_morning_cleanup
        task = asyncio.create_task(schedule_morning_cleanup(bot))
        _cleanup_tasks.append(task)
        logger.info("✅ Morning cleanup scheduled")
    except Exception as e: logger.warning(f"Cleanup: {e}")


async def stop_all_background_tasks():
    try: stop_cleanup_task()
    except: pass
    for task in _cleanup_tasks:
        if task and not task.done(): task.cancel()
    _cleanup_tasks.clear()


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

async def on_startup():
    global BOT_ID
    me = await bot.get_me()
    BOT_ID = me.id
    logger.info(f"🤖 Bot ID: {BOT_ID}")
    logger.info("🚀 NEXUS Bot v7.1.0 starting...")
    
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
    
    logger.info("✅ ALL SYSTEMS GO!")


async def on_shutdown():
    logger.info("🛑 Shutting down...")
    await stop_all_background_tasks()
    _user_cache.clear()
    _bot_messages.clear()
    if db and hasattr(db, 'close'):
        try: await db.close()
        except: pass
    await bot.session.close()
    logger.info("👋 Stopped")


# 🔥 СОХРАНЕНИЕ ВСЕХ СООБЩЕНИЙ ДЛЯ СТАТИСТИКИ
@dp.message()
async def save_all_messages(message: Message):
    """
    Сохраняет ВСЕ сообщения в БД для статистики.
    🔥 Это критически важно для работы сводки дня!
    Без этой функции статистика всегда будет показывать 0.
    """
    if not message or not db or not message.chat or not message.from_user:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""
    
    try:
        # Сохраняем слова для анализа тем
        if text and len(text) >= 3:
            await db.log_chat_message(chat_id, user_id, text)
        
        # Трекинг активности с chat_id
        activity_type = "message"
        if message.sticker:
            activity_type = "sticker"
        elif message.voice:
            activity_type = "voice"
        elif message.video:
            activity_type = "video"
        elif message.photo:
            activity_type = "photo"
        elif message.animation:
            activity_type = "gif"
        
        await db.track_user_activity(user_id, chat_id, activity_type, 1)
        
    except Exception as e:
        logger.error(f"❌ Save message error: {e}")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    logger.info("📡 Starting polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("👋 Interrupted")
    except Exception as e: logger.critical(f"💥 Fatal: {e}", exc_info=True); sys.exit(1)
