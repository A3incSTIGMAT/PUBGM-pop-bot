#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 7.4.3-production
# ОПИСАНИЕ: NEXUS Chat Manager — Полная совместимость с database.py v3.3.1
# ИЗМЕНЕНИЯ v7.4.3:
#   ✅ Исправлена опечатка в get_back_keyboard (SyntaxError)
#   ✅ Убран неиспользуемый импорт timedelta
#   ✅ Улучшена производительность _message_save_cooldown (автоочистка)
#   ✅ Добавлен лимит на размер кэша сообщений
# ============================================

import asyncio
import logging
import sys
import time
import html
import os
from datetime import datetime
from typing import Dict, Set, Optional, Any, List, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, Message, Update
)

# ✅ Исправленные импорты для aiogram 3.x с fallback
try:
    from aiogram.exceptions import (
        TelegramBadRequest, 
        TelegramForbiddenError,
        AiogramError as TelegramAPIError
    )
except ImportError:
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    TelegramAPIError = Exception

from dotenv import load_dotenv

# ✅ Опциональная очистка окружения перед загрузкой .env
if os.getenv('CLEAR_ENV_ON_START', 'false').lower() == 'true':
    for key in list(os.environ.keys()):
        if key.startswith(('NEXUS_', 'BOT_', 'DB_')):
            del os.environ[key]

load_dotenv()

# ==================== ЛОГИРОВАНИЕ ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГ ====================

from config import (
    BOT_TOKEN, START_BALANCE, ADMIN_IDS, SUPER_ADMIN_IDS,
    BOT_USERNAME, GAME_COMMISSION, MORNING_CLEANUP_HOUR,
    DONATE_URL, DONATE_BANK, DONATE_RECEIVER, DATABASE_PATH
)

if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN not set!")
    sys.exit(1)

ADMIN_IDS = ADMIN_IDS if ADMIN_IDS is not None else []
SUPER_ADMIN_IDS = SUPER_ADMIN_IDS if SUPER_ADMIN_IDS is not None else []
START_BALANCE = START_BALANCE if START_BALANCE is not None else 1000

OWNER_ID = 895844198
BOT_ID: Optional[int] = None

logger.info(f"🔧 OWNER_ID: {OWNER_ID}")
logger.info(f"🔧 ADMIN_IDS: {ADMIN_IDS}")
logger.info(f"🔧 SUPER_ADMIN_IDS: {SUPER_ADMIN_IDS}")

# ==================== БОТ ====================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_background_tasks: Set[asyncio.Task] = set()
_cleanup_tasks: List[asyncio.Task] = []
_startup_time = datetime.now()

# ==================== FSM ДЛЯ ОБРАТНОЙ СВЯЗИ ====================

class FeedbackState(StatesGroup):
    waiting_for_message = State()


# ==================== RATE LIMITER ====================

try:
    from utils.rate_limiter import RateLimiter, start_cleanup_task, stop_cleanup_task
    daily_limiter = RateLimiter(limit=1, period=10)
except ImportError:
    logger.warning("⚠️ utils.rate_limiter not found, using fallback")
    
    class FallbackLimiter:
        def __init__(self, *args, **kwargs): pass
        def is_allowed(self, *args, **kwargs): return True
    daily_limiter = FallbackLimiter()
    
    def start_cleanup_task(): pass
    def stop_cleanup_task(): pass


# ==================== БАЗА ДАННЫХ ====================

from database import db, DatabaseError

# Кэш с синхронизацией инвалидации
_user_cache: Dict[int, Tuple[Optional[dict], float]] = {}
_CACHE_TTL = 30  # секунд
MAX_CACHE_SIZE = 1000  # Максимальный размер кэша


async def get_user_cached(user_id: Optional[int]) -> Optional[dict]:
    """✅ Получение пользователя с кэшем и авто-созданием если нет"""
    if user_id is None or db is None:
        return None
    
    now = time.time()
    if user_id in _user_cache:
        data, timestamp = _user_cache[user_id]
        if now - timestamp < _CACHE_TTL:
            return data
    
    try:
        user = await db.get_user(user_id)
        
        if not user:
            await db.create_user(
                user_id=user_id,
                username=None,
                first_name=None,
                balance=START_BALANCE
            )
            user = await db.get_user(user_id)
        
        if user:
            # ✅ Автоочистка кэша при превышении лимита
            if len(_user_cache) >= MAX_CACHE_SIZE:
                # Удаляем 10% самых старых записей
                sorted_items = sorted(_user_cache.items(), key=lambda x: x[1][1])
                for old_id, _ in sorted_items[:MAX_CACHE_SIZE // 10]:
                    del _user_cache[old_id]
                logger.debug(f"Cache cleanup: removed {MAX_CACHE_SIZE // 10} old entries")
            
            _user_cache[user_id] = (user, now)
        return user
        
    except DatabaseError as e:
        logger.error(f"❌ DB error getting user {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error getting user {user_id}: {e}")
        return None


def invalidate_user_cache(user_id: Optional[int]):
    """✅ Инвалидация кэша при изменении данных пользователя"""
    if user_id and user_id in _user_cache:
        del _user_cache[user_id]


async def get_balance_safe(user_id: Optional[int]) -> int:
    """✅ Безопасное получение баланса с кэшем"""
    if user_id is None or db is None:
        return 0
    try:
        return await db.get_balance(user_id) or 0
    except Exception as e:
        logger.error(f"❌ Error getting balance for {user_id}: {e}")
        return 0


async def get_user_stats_safe(user_id: Optional[int]) -> dict:
    """✅ Быстрый доступ к статистике с дефолтами"""
    if user_id is None or db is None:
        return {'wins': 0, 'games_played': 0, 'messages_total': 0, 'rank': 1}
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return {
                'wins': stats.get('wins', 0) or 0,
                'games_played': stats.get('games_played', 0) or 0,
                'messages_total': stats.get('messages_total', 0) or 0,
                'rank': stats.get('rank', 1) or 1,
                'xp': stats.get('xp', 0) or 0,
                'balance': stats.get('balance', 0) or 0
            }
    except Exception as e:
        logger.error(f"❌ Error getting stats for {user_id}: {e}")
    return {'wins': 0, 'games_played': 0, 'messages_total': 0, 'rank': 1, 'xp': 0, 'balance': 0}


def safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def safe_html_escape(text: Optional[str]) -> str:
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except:
        return str(text)


# ==================== ПРОВЕРКА АДМИНА ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    """✅ Проверка супер-админа: локальный список + владелец"""
    if user_id is None:
        return False
    return user_id == OWNER_ID or user_id in (SUPER_ADMIN_IDS or [])


async def is_admin_db(user_id: Optional[int]) -> bool:
    """✅ Проверка админа (локальный список, БД-метода пока нет)"""
    if user_id is None or db is None:
        return False
    
    # Пробуем через БД если метод есть
    try:
        if hasattr(db, 'is_admin') and callable(db.is_admin):
            return await db.is_admin(user_id) or is_super_admin(user_id)
    except Exception as e:
        logger.debug(f"db.is_admin() not available: {e}")
    
    # Fallback: локальная проверка
    return is_super_admin(user_id) or user_id in (ADMIN_IDS or [])


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
    """✅ Исправленная сигнатура (была опечатка)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])


async def safe_callback_edit(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    """✅ Безопасное редактирование сообщения с обработкой всех ошибок"""
    if not callback or not callback.message:
        return False
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        if "message can't be edited" in str(e).lower():
            try:
                await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
                return True
            except:
                return False
        return False
    except TelegramForbiddenError:
        logger.warning(f"⚠️ Forbidden to edit message for user {callback.from_user.id}")
        return False
    except TelegramAPIError as e:
        logger.error(f"❌ Telegram API error in edit: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error in edit: {e}")
        return False


async def render_main_menu(user_id: int, chat_id: int, first_name: str) -> Tuple[str, InlineKeyboardMarkup]:
    """✅ Формирование текста главного меню с актуальными данными"""
    is_admin = await is_admin_db(user_id)
    balance = await get_balance_safe(user_id)
    stats = await get_user_stats_safe(user_id)
    
    user = await get_user_cached(user_id)
    vip_level = safe_int(user.get('vip_level')) if user else 0
    daily_streak = safe_int(user.get('daily_streak')) if user else 0

    text = (
        f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
        f"👋 Привет, <b>{safe_html_escape(first_name)}</b>!\n"
        f"💰 Баланс: <b>{balance:,}</b> NCoin\n"
        f"⭐ VIP: {'✅ Ур. ' + str(vip_level) if vip_level > 0 else '❌ Нет'}\n"
        f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
        f"🏆 Ранг: <b>#{stats['rank']}</b> ({stats['xp']} XP)\n"
        f"🎮 XO: <b>{stats['wins']}</b> побед ({stats['games_played']} игр)\n"
        f"💬 Сообщений: <b>{stats['messages_total']:,}</b>\n\n"
        f"👇 Выберите действие:"
    )
    return text, get_main_menu(is_admin)


# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    """✅ Обработка /start с авто-регистрацией и deep links"""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    chat_id = message.chat.id if message.chat else user_id

    logger.info(f"🚀 /start from {user_id} (chat: {chat_id})")

    if db:
        try:
            await db.create_user(
                user_id=user_id,
                username=username,
                first_name=first_name,
                balance=START_BALANCE
            )
            invalidate_user_cache(user_id)
        except DatabaseError as e:
            logger.error(f"❌ DB error creating user {user_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error creating user {user_id}: {e}")

    args = command.args
    if args == "gifts":
        try:
            from handlers.economy import show_gifts_catalog
            await show_gifts_catalog(message)
        except ImportError:
            await message.answer("⚠️ Каталог временно недоступен.")
        except Exception as e:
            logger.error(f"❌ Error showing gifts: {e}")
            await message.answer("⚠️ Ошибка загрузки каталога.")
        return
    elif args == "help":
        await cmd_help(message)
        return

    text, keyboard = await render_main_menu(user_id, chat_id, first_name)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """✅ Справка с актуальными командами"""
    if not message:
        return
    text = (
        "🤖 <b>NEXUS CHAT MANAGER</b>\n\n"
        "<b>📌 ОСНОВНЫЕ КОМАНДЫ:</b>\n"
        "<code>/start</code> — главное меню\n"
        "<code>/daily</code> — ежедневный бонус (+100 NCoin)\n"
        "<code>/balance</code> — проверить баланс\n"
        "<code>/xo</code> — игра «Крестики-нолики»\n"
        "<code>/vip</code> — VIP статус и привилегии\n"
        "<code>/profile</code> — моя анкета и настройки\n"
        "<code>/stats</code> — моя статистика в чате\n"
        "<code>/top</code> — топ игроков по балансу/активности\n"
        "<code>/marry @user</code> — предложить брак 💍\n"
        "<code>/divorce</code> — расторгнуть брак 💔\n"
        "<code>/flirt @user</code> — флирт 💋\n"
        "<code>/hug @user</code> — объятия 🤗\n"
        "<code>/tag add #метка</code> — добавить тег себе 🏷️\n"
        "<code>/feedback</code> — написать разработчику 💬\n"
        "<code>/policy</code> — правила и конфиденциальность 🔒\n"
        "<code>/cancel</code> — отменить текущее действие ❌\n"
        "<code>/health</code> — проверка состояния бота 🟢\n\n"
        f"💡 В группах: <code>/start@{BOT_USERNAME}</code>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """✅ Отмена любого FSM-состояния"""
    if not message:
        return
    await state.clear()
    await message.answer("❌ <b>Действие отменено</b>", parse_mode=ParseMode.HTML)
    if message.from_user:
        text, keyboard = await render_main_menu(
            message.from_user.id,
            message.chat.id if message.chat else message.from_user.id,
            message.from_user.first_name or "Пользователь"
        )
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("health"))
async def cmd_health(message: Message):
    """✅ Health-check эндпоинт для мониторинга"""
    uptime = datetime.now() - _startup_time
    uptime_str = str(uptime).split('.')[0]
    
    status = {
        "bot": "ok",
        "db": "ok" if db and db._initialized else "fail",
        "cache_users": len(_user_cache),
        "uptime": uptime_str,
        "version": "7.4.3"
    }
    text = (
        "🟢 <b>HEALTH CHECK</b>\n\n"
        f"🤖 Бот: {status['bot']}\n"
        f"🗄️ БД: {status['db']}\n"
        f"💾 Кэш пользователей: {status['cache_users']}\n"
        f"⏱️ Аптайм: {status['uptime']}\n"
        f"🔖 Версия: {status['version']}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


# ==================== ПРЯМЫЕ ОБРАБОТЧИКИ КОМАНД ====================

async def _safe_handler_import(module_path: str, func_name: str, message: Message, fallback_text: str = "❌ Ошибка"):
    """✅ Универсальный безопасный импорт и вызов хендлера"""
    try:
        module = __import__(module_path, fromlist=[func_name])
        func = getattr(module, func_name, None)
        if func and callable(func):
            await func(message)
        else:
            logger.warning(f"⚠️ Function {func_name} not found in {module_path}")
            await message.answer(fallback_text)
    except ImportError as e:
        logger.error(f"❌ Import error {module_path}.{func_name}: {e}")
        await message.answer("⚠️ Функция временно недоступна.")
    except Exception as e:
        logger.error(f"❌ Error in {module_path}.{func_name}: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@dp.message(Command("daily"))
async def cmd_daily_direct(message: Message):
    if message: await _safe_handler_import("handlers.economy", "cmd_daily", message, "❌ Ошибка ежедневного бонуса")

@dp.message(Command("balance"))
async def cmd_balance_direct(message: Message):
    if message: await _safe_handler_import("handlers.economy", "cmd_balance", message, "❌ Ошибка проверки баланса")

@dp.message(Command("profile"))
async def cmd_profile_direct(message: Message):
    if message: await _safe_handler_import("handlers.profile", "cmd_profile", message, "❌ Ошибка профиля")

@dp.message(Command("stats"))
async def cmd_stats_direct(message: Message):
    if message: await _safe_handler_import("handlers.stats", "cmd_stats", message, "❌ Ошибка статистики")

@dp.message(Command("top"))
async def cmd_top_direct(message: Message):
    if message: await _safe_handler_import("handlers.stats", "cmd_top", message, "❌ Ошибка топа")

@dp.message(Command("vip"))
async def cmd_vip_direct(message: Message):
    if message: await _safe_handler_import("handlers.vip", "cmd_vip", message, "❌ Ошибка VIP")

@dp.message(Command("policy"))
async def cmd_policy_direct(message: Message):
    """✅ Показ политики из единого источника (БД/константы)"""
    if not message:
        return
    if db:
        try:
            sections = db.get_all_policy_sections()
            text = "🔒 <b>ПОЛИТИКА И ПРАВИЛА NEXUS</b>\n\n"
            for sec in sections:
                content = db.get_policy_section(sec['key'])
                text += f"{sec['emoji']} <b>{sec['title']}</b>\n{content}\n\n"
            text += "<i>Последнее обновление: " + datetime.now().strftime("%d.%m.%Y") + "</i>"
            await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
            return
        except Exception as e:
            logger.error(f"❌ Error loading policy: {e}")
    
    await cmd_help(message)


# ==================== ОБРАТНАЯ СВЯЗЬ (через БД) ====================

@dp.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext):
    """✅ Начало обратной связи с сохранением в БД"""
    if not message or not message.from_user:
        return
    
    await state.set_state(FeedbackState.waiting_for_message)
    await message.answer(
        "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\n"
        "Напишите ваше сообщение в ответном письме.\n\n"
        "📌 <i>Что можно написать:</i>\n"
        "• Предложение по улучшению бота 🚀\n"
        "• Сообщение об ошибке или баге 🐛\n"
        "• Вопрос по работе функций ❓\n"
        "• Жалоба на пользователя/модератора ⚖️\n\n"
        "❌ Для отмены: <code>/cancel</code>\n"
        "⏱️ У вас есть 5 минут на ответ",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )


@dp.message(FeedbackState.waiting_for_message)
async def process_feedback(message: Message, state: FSMContext):
    """✅ Обработка сообщения обратной связи с сохранением в БД"""
    if not message or not message.from_user:
        return
    
    text = (message.text or "").strip()
    user_id = message.from_user.id
    
    if text.lower() in ('/cancel', 'отмена', 'отменить'):
        await state.clear()
        await message.answer("❌ Отправка обратной связи отменена.")
        return
    
    if len(text) < 10:
        await message.answer("❌ Слишком короткое сообщение! Минимум 10 символов.")
        return
    if len(text) > 2000:
        await message.answer("❌ Слишком длинное сообщение! Максимум 2000 символов.")
        return
    
    ticket_id = None
    if db:
        try:
            ticket_id = await db.create_feedback_ticket(user_id=user_id, message=text)
            logger.info(f"✅ Feedback ticket #{ticket_id} created by user {user_id}")
        except DatabaseError as e:
            logger.error(f"❌ DB error creating feedback ticket: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error creating feedback ticket: {e}")
    
    if ADMIN_IDS:
        notify_text = (
            f"📝 <b>НОВЫЙ ОТЗЫВ #{ticket_id or 'N/A'}</b>\n\n"
            f"👤 От: {safe_html_escape(message.from_user.full_name)}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"{'🔖 Username: @' + safe_html_escape(message.from_user.username) + '\n' if message.from_user.username else ''}"
            f"💬 Сообщение:\n{safe_html_escape(text)}"
        )
        for admin_id in ADMIN_IDS:
            if admin_id is None:
                continue
            try:
                await bot.send_message(admin_id, notify_text, parse_mode=ParseMode.HTML)
            except TelegramForbiddenError:
                logger.warning(f"⚠️ Cannot notify admin {admin_id}: Forbidden")
            except TelegramAPIError as e:
                logger.error(f"❌ Error notifying admin {admin_id}: {e}")
            except Exception as e:
                logger.error(f"❌ Unexpected error notifying admin {admin_id}: {e}")
    
    await state.clear()
    
    confirmation = (
        "✅ <b>Спасибо за обратную связь!</b>\n\n"
        f"{'🎫 Ваш тикет: #' + str(ticket_id) + '\n' if ticket_id else ''}"
        "Ваше сообщение сохранено и отправлено разработчику.\n"
        "Мы ответим в личные сообщения в ближайшее время.\n\n"
        "<i>Статус тикета можно проверить командой /tickets</i>"
    )
    await message.answer(confirmation, parse_mode=ParseMode.HTML)


# ==================== CALLBACK: НАЗАД ====================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """✅ Возврат в главное меню из любого раздела"""
    if not callback or not callback.message or not callback.from_user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    first_name = callback.from_user.first_name or "Пользователь"

    try:
        text, keyboard = await render_main_menu(user_id, chat_id, first_name)
        if not await safe_callback_edit(callback, text, keyboard):
            await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"❌ Error in back_to_menu: {e}")
        await callback.message.answer("❌ Ошибка загрузки меню", reply_markup=get_back_keyboard())
    
    await callback.answer()


# ==================== УСТАНОВКА БОТА ДЛЯ МОДУЛЕЙ ====================

def setup_bot_for_modules():
    """✅ Регистрация бота в модулях, которые хранят глобальную ссылку"""
    modules_to_setup = [
        ("handlers.tictactoe", "set_bot"),
        ("handlers.smart_commands", "set_bot"),
        ("handlers.referral", "set_bot"),
        ("handlers.admin", "set_bot"),
    ]
    
    for module_name, func_name in modules_to_setup:
        try:
            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name, None)
            if func and callable(func):
                func(bot)
                logger.info(f"✅ Bot set for {module_name}")
        except ImportError:
            logger.warning(f"⚠️ Module {module_name} not found, skipping")
        except AttributeError:
            logger.warning(f"⚠️ Function {func_name} not found in {module_name}")
        except Exception as e:
            logger.warning(f"⚠️ Error setting bot for {module_name}: {e}")


# ==================== ЗАГРУЗКА РОУТЕРОВ ====================

def load_all_routers():
    """✅ Динамическая загрузка всех роутеров с обработкой ошибок"""
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
    
    loaded = 0
    for module_name, attr_name in routers:
        try:
            module = __import__(module_name, fromlist=[attr_name])
            router = getattr(module, attr_name, None)
            if router:
                dp.include_router(router)
                logger.info(f"✅ Loaded router: {module_name}")
                loaded += 1
            else:
                logger.warning(f"⚠️ Router '{attr_name}' not found in {module_name}")
        except ImportError as e:
            logger.warning(f"⚠️ Cannot import {module_name}: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Error loading {module_name}: {e}")
    
    logger.info(f"📦 Loaded {loaded}/{len(routers)} routers")


# ==================== ОБРАБОТЧИКИ КНОПОК МЕНЮ ====================

async def _handle_menu_callback(callback: CallbackQuery, module: str, func: str, error_msg: str):
    """✅ Универсальный обработчик кнопок меню"""
    if not callback or not callback.message:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    try:
        module_obj = __import__(module, fromlist=[func])
        handler = getattr(module_obj, func, None)
        if handler and callable(handler):
            await handler(callback.message)
        else:
            logger.warning(f"⚠️ Handler {func} not found in {module}")
            await callback.message.answer("⚠️ Функция в разработке", reply_markup=get_back_keyboard())
    except ImportError:
        logger.error(f"❌ Cannot import {module}.{func}")
        await callback.message.answer("⚠️ Раздел временно недоступен", reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error(f"❌ Error in {module}.{func}: {e}")
        await callback.message.answer(error_msg, reply_markup=get_back_keyboard())
    finally:
        await callback.answer()


@dp.callback_query(F.data == "menu_vip")
async def menu_vip(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.vip", "cmd_vip", "❌ Ошибка загрузки VIP")

@dp.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.profile", "cmd_profile", "❌ Ошибка профиля")

@dp.callback_query(F.data == "menu_balance")
async def menu_balance(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.economy", "cmd_balance", "❌ Ошибка баланса")

@dp.callback_query(F.data == "menu_rank")
async def menu_rank(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.ranks", "cmd_rank", "❌ Ошибка рангов")

@dp.callback_query(F.data == "menu_xo")
async def menu_xo(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.tictactoe", "cmd_xo", "❌ Ошибка игры")

@dp.callback_query(F.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.stats", "cmd_stats", "❌ Ошибка статистики")

@dp.callback_query(F.data == "menu_all")
async def menu_all(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.tag", "cmd_all", "❌ Ошибка тегов")

@dp.callback_query(F.data == "menu_ref")
async def menu_ref(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.referral", "ref_menu_callback", "❌ Ошибка рефералки")

@dp.callback_query(F.data == "menu_relations")
async def menu_relations(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.relationships", "relationships_menu", "❌ Ошибка отношений")

@dp.callback_query(F.data == "menu_groups")
async def menu_groups(callback: CallbackQuery):
    if not callback or not callback.message:
        return
    await safe_callback_edit(
        callback,
        "👥 <b>ГРУППЫ</b>\n\nФункция в разработке.\nСкоро: создание кланов, войны, общий чат.",
        get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_rp")
async def menu_rp(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.smart_commands", "cmd_my_custom_rp", "❌ Ошибка РП")

@dp.callback_query(F.data == "menu_tags")
async def menu_tags(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.tag_user", "my_tags_menu_callback", "❌ Ошибка тегов")

@dp.callback_query(F.data == "menu_topchats")
async def menu_topchats(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.rating", "cmd_top_chats", "❌ Ошибка рейтинга")

@dp.callback_query(F.data == "menu_privacy")
async def menu_privacy(callback: CallbackQuery):
    """✅ Политика из единого источника (БД)"""
    if not callback or not callback.message:
        return
    
    try:
        if db:
            sections = db.get_all_policy_sections()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=sec['emoji'] + " " + sec['title'], callback_data=f"policy:{sec['key']}")]
                for sec in sections
            ] + [[InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]])
            
            intro = (
                "🔒 <b>ПОЛИТИКА И ПРАВИЛА NEXUS</b>\n\n"
                "Выберите раздел для просмотра:\n"
                "• Правила чата и модерация 📜\n"
                "• Конфиденциальность данных 🔐\n"
                "• Система наказаний ⚖️\n"
                "• Обратная связь и поддержка 📬\n"
                "• Контакты разработчиков 👥"
            )
            await safe_callback_edit(callback, intro, keyboard)
        else:
            text = (
                "🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<b>📌 ДАННЫЕ:</b> ID, имя, баланс, статистика игр, анкета.\n"
                "<b>📌 ИСПОЛЬЗОВАНИЕ:</b> Работа бота, игры, экономика, топы.\n"
                "<b>📌 ХРАНЕНИЕ:</b> Защищённая БД, не передаётся третьим лицам.\n"
                "<b>📌 УДАЛЕНИЕ:</b> Команда <code>/delete_my_data</code>.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "✅ Все данные используются только для работы бота"
            )
            await safe_callback_edit(callback, text, get_back_keyboard())
    except Exception as e:
        logger.error(f"❌ Error loading policy: {e}")
        await callback.message.answer("❌ Ошибка загрузки политики", reply_markup=get_back_keyboard())
    
    await callback.answer()


@dp.callback_query(F.data.startswith("policy:"))
async def policy_section_callback(callback: CallbackQuery):
    """✅ Показ конкретного раздела политики"""
    if not callback or not callback.message:
        return
    
    section_key = callback.data.split(":")[1] if ":" in callback.data else None
    if not section_key or not db:
        await callback.answer("❌ Раздел не найден", show_alert=True)
        return
    
    try:
        content = db.get_policy_section(section_key)
        sections = db.get_all_policy_sections()
        current = next((s for s in sections if s['key'] == section_key), None)
        
        if current and content:
            text = f"{current['emoji']} <b>{current['title']}</b>\n\n{content}"
            section_idx = next((i for i, s in enumerate(sections) if s['key'] == section_key), 0)
            
            prev_key = sections[section_idx - 1]['key'] if section_idx > 0 else None
            next_key = sections[section_idx + 1]['key'] if section_idx < len(sections) - 1 else None
            
            nav_buttons = []
            if prev_key:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Пред.", callback_data=f"policy:{prev_key}"))
            nav_buttons.append(InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu"))
            if next_key:
                nav_buttons.append(InlineKeyboardButton(text="След. ▶️", callback_data=f"policy:{next_key}"))
            
            nav_keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons])
            await safe_callback_edit(callback, text, nav_keyboard)
        else:
            await callback.answer("❌ Содержимое не найдено", show_alert=True)
    except Exception as e:
        logger.error(f"❌ Error showing policy section {section_key}: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    
    await callback.answer()


@dp.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "menu_donate")
async def menu_donate(callback: CallbackQuery):
    await _handle_menu_callback(callback, "handlers.economy", "cmd_donate", "❌ Ошибка доната")

@dp.callback_query(F.data == "menu_feedback")
async def menu_feedback(callback: CallbackQuery, state: FSMContext):
    """✅ Обратная связь через кнопку меню"""
    if not callback or not callback.message:
        return
    
    await state.set_state(FeedbackState.waiting_for_message)
    await safe_callback_edit(
        callback,
        "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\n"
        "Напишите ваше сообщение в ответном письме.\n\n"
        "📌 <i>Что можно написать:</i>\n"
        "• Предложение по улучшению 🚀\n"
        "• Сообщение об ошибке 🐛\n"
        "• Вопрос по работе бота ❓\n"
        "• Жалоба на пользователя ⚖️\n\n"
        "❌ Для отмены: <code>/cancel</code>",
        get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_admin")
async def menu_admin(callback: CallbackQuery):
    """✅ Админ-панель с проверкой прав"""
    if not callback or not callback.message or not callback.from_user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    if not await is_admin_db(user_id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        logger.warning(f"⚠️ Unauthorized admin panel access attempt by {user_id}")
        return
    
    try:
        from handlers.admin import admin_panel_callback
        await admin_panel_callback(callback)
    except ImportError:
        await callback.message.answer("⚠️ Админ-панель в разработке", reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error(f"❌ Error in admin panel: {e}")
        await callback.message.answer("❌ Ошибка загрузки админ-панели", reply_markup=get_back_keyboard())
    
    await callback.answer()


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

async def start_all_background_tasks():
    """✅ Запуск всех фоновых задач с обработкой ошибок"""
    try:
        start_cleanup_task()
        logger.info("✅ Rate limiter cleanup started")
    except Exception as e:
        logger.warning(f"⚠️ Rate limiter cleanup error: {e}")
    
    try:
        from utils.auto_delete import schedule_morning_cleanup
        task = asyncio.create_task(schedule_morning_cleanup(bot))
        _cleanup_tasks.append(task)
        logger.info("✅ Morning cleanup scheduled")
    except ImportError:
        logger.warning("⚠️ utils.auto_delete not found, skipping morning cleanup")
    except Exception as e:
        logger.warning(f"⚠️ Morning cleanup error: {e}")

    async def periodic_rank_update():
        """✅ Обновление рангов активных пользователей раз в 10 минут."""
        while True:
            try:
                await asyncio.sleep(600)
                
                if db:
                    # Получаем топ-100 активных пользователей и проверяем их ранги
                    try:
                        active_users = await db._execute_with_retry(
                            """SELECT DISTINCT user_id FROM user_activity_log 
                               WHERE date >= date('now', '-1 days') 
                               LIMIT 100""",
                            fetch_all=True
                        )
                        if active_users:
                            updated = 0
                            for row in active_users:
                                uid = row['user_id']
                                # Проверяем, нужно ли пересчитывать ранг
                                rank_info = await db.get_user_rank(uid)
                                if rank_info and rank_info.get('needs_recalc'):
                                    await db.recalculate_user_rank(uid)
                                    updated += 1
                            if updated > 0:
                                logger.info(f"🔄 Updated ranks for {updated} users")
                    except Exception as e:
                        logger.debug(f"Rank update query error: {e}")
                    
            except asyncio.CancelledError:
                logger.info("🔄 Periodic rank update task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in periodic_rank_update: {e}")
                await asyncio.sleep(60)
    
    stats_task = asyncio.create_task(periodic_rank_update())
    _background_tasks.add(stats_task)
    stats_task.add_done_callback(_background_tasks.discard)
    logger.info("✅ Periodic rank update task started")


async def stop_all_background_tasks():
    """✅ Корректная остановка всех фоновых задач"""
    try:
        stop_cleanup_task()
    except:
        pass
    
    for task in list(_background_tasks) + _cleanup_tasks:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    _background_tasks.clear()
    _cleanup_tasks.clear()
    logger.info("✅ Background tasks stopped")


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

async def on_startup():
    """✅ Инициализация при запуске бота"""
    global BOT_ID
    
    try:
        me = await bot.get_me()
        BOT_ID = me.id
        logger.info(f"🤖 Bot: @{me.username} (ID: {BOT_ID})")
    except Exception as e:
        logger.critical(f"❌ Cannot get bot info: {e}")
        sys.exit(1)
    
    logger.info("🚀 NEXUS Bot v7.4.3 starting...")

    setup_bot_for_modules()
    load_all_routers()
    
    if db:
        try:
            await db.initialize()
            logger.info("✅ Database initialized")
        except DatabaseError as e:
            logger.critical(f"❌ Database initialization failed: {e}")
            sys.exit(1)
        except Exception as e:
            logger.critical(f"❌ Unexpected DB error: {e}")
            sys.exit(1)
    
    try:
        from handlers.ranks import init_ranks_table
        await init_ranks_table()
        logger.info("✅ Ranks table initialized")
    except ImportError:
        logger.warning("⚠️ handlers.ranks not found, skipping ranks init")
    except Exception as e:
        logger.warning(f"⚠️ Ranks init error: {e}")

    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        logger.info("✅ Custom RP commands loaded")
    except ImportError:
        logger.warning("⚠️ handlers.smart_commands not found")
    except Exception as e:
        logger.warning(f"⚠️ Custom RP load error: {e}")

    try:
        from handlers.smart_commands import set_bot as set_smart_bot
        set_smart_bot(bot)
        logger.info("✅ Bot ID updated in smart_commands")
    except:
        pass

    await start_all_background_tasks()
    
    if SUPER_ADMIN_IDS:
        for admin_id in SUPER_ADMIN_IDS:
            if admin_id is None:
                continue
            try:
                await bot.send_message(
                    admin_id,
                    f"🚀 <b>NEXUS Bot v7.4.3 запущен!</b>\n\n"
                    f"✅ БД: подключена\n"
                    f"✅ Роутеры: загружены ({len(dp.sub_routers)})\n"
                    f"✅ Фоновые задачи: активны\n"
                    f"🕒 Время: {datetime.now().strftime('%H:%M:%S')}",
                    parse_mode=ParseMode.HTML
                )
            except TelegramForbiddenError:
                logger.warning(f"⚠️ Cannot notify super-admin {admin_id}: Forbidden")
            except Exception as e:
                logger.warning(f"⚠️ Error notifying admin {admin_id}: {e}")

    logger.info("✅ ALL SYSTEMS GO! Bot is ready.")


async def on_shutdown():
    """✅ Корректное завершение работы"""
    logger.info("🛑 Shutting down NEXUS Bot...")
    
    await stop_all_background_tasks()
    
    _user_cache.clear()
    logger.info("✅ User cache cleared")
    
    if db and hasattr(db, 'close'):
        try:
            await db.close()
            logger.info("✅ Database connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing DB: {e}")
    
    try:
        await bot.session.close()
        logger.info("✅ Bot session closed")
    except Exception as e:
        logger.warning(f"⚠️ Error closing bot session: {e}")
    
    logger.info("👋 NEXUS Bot stopped gracefully")


# ==================== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ====================

_message_save_cooldown: Dict[int, float] = {}
_SAVE_COOLDOWN = 2
_MAX_COOLDOWN_ENTRIES = 5000

@dp.message()
async def save_all_messages(message: Message):
    """
    ✅ Сохраняет сообщения для статистики с rate limiting.
    Использует db.track_word() вместо удалённого db.log_chat_message().
    """
    if not message or not db or not message.chat or not message.from_user:
        return

    if message.text and message.text.startswith('/'):
        return
    if message.from_user.is_bot:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""
    now = time.time()

    last_save = _message_save_cooldown.get(user_id, 0)
    if now - last_save < _SAVE_COOLDOWN:
        return
    _message_save_cooldown[user_id] = now
    
    # ✅ Автоочистка старых записей из cooldown-словаря
    if len(_message_save_cooldown) > _MAX_COOLDOWN_ENTRIES:
        cutoff = now - 300  # удаляем записи старше 5 минут
        old_keys = [uid for uid, t in _message_save_cooldown.items() if t < cutoff]
        for uid in old_keys:
            del _message_save_cooldown[uid]

    start_time = time.time()
    
    try:
        # ✅ Сохранение слов через track_word
        if text and len(text.strip()) >= 3:
            words = text.lower().split()
            saved_words = 0
            for word in words:
                clean_word = word.strip('.,!?;:()[]{}"\'-')
                if len(clean_word) >= 3 and saved_words < 10:
                    await db.track_word(chat_id, clean_word)
                    saved_words += 1

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

    except DatabaseError as e:
        if "database is locked" not in str(e).lower():
            logger.debug(f"⚠️ DB error saving message from {user_id}: {e}")
    except Exception as e:
        logger.debug(f"⚠️ Unexpected error saving message from {user_id}: {e}")
    finally:
        # ✅ Логирование медленных запросов
        duration = time.time() - start_time
        if duration > 1.0:
            logger.warning(f"⚠️ Slow message save ({duration:.2f}s) for user {user_id}")


# ==================== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК ====================

@dp.errors()
async def errors_handler(update: Update, exception: Exception):
    """✅ Глобальный обработчик необработанных исключений с безопасным доступом"""
    user_id: Any = 'unknown'
    try:
        if hasattr(update, 'event') and update.event:
            event = update.event
            if hasattr(event, 'from_user') and event.from_user:
                user_id = event.from_user.id
            elif hasattr(event, 'chat') and hasattr(event.chat, 'id'):
                user_id = f"chat:{event.chat.id}"
    except Exception:
        pass
    
    if isinstance(exception, TelegramForbiddenError):
        logger.warning(f"⚠️ Forbidden: bot blocked by user {user_id}")
        return True
    elif isinstance(exception, TelegramBadRequest):
        logger.warning(f"⚠️ BadRequest: {exception}")
        return True
    elif isinstance(exception, TelegramAPIError):
        logger.error(f"❌ Telegram API error: {exception}")
        return True
    else:
        logger.critical(f"💥 Unhandled exception: {type(exception).__name__}: {exception}", exc_info=True)
        return True


# ==================== ТОЧКА ВХОДА ====================

async def main():
    """✅ Главная функция запуска"""
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    dp.errors.register(errors_handler)
    
    logger.info("📡 Starting polling...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("👋 Received keyboard interrupt")
    except Exception as e:
        logger.critical(f"💥 Polling error: {type(e).__name__}: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 Fatal error: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)
