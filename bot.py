#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 7.6.0-production (полный аудит и исправление)
# ОПИСАНИЕ: NEXUS Chat Manager — главный файл бота
# ============================================
# ИСПРАВЛЕНИЯ v7.6.0:
#   🔴 FeedbackState импортируется из handlers.start (единый источник)
#   🟡 _message_save_cooldown защищён asyncio.Lock
#   🟡 Добавлены недостающие роутеры (ai_assistant, start, tag_categories)
#   🟡 Константы кэша вынесены в os.getenv()
#   🟡 exc_info=True во всех logger.error/critical
#   🟡 datetime.now() → datetime.now(timezone.utc)
#   🟢 Упрощён safe_html_escape (без двойной очистки)
# ============================================

import asyncio
import html
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)

# Fallback для TelegramAPIError
try:
    from aiogram.exceptions import TelegramAPIError
except ImportError:
    TelegramAPIError = Exception

from dotenv import load_dotenv

load_dotenv()

# ==================== ЛОГИРОВАНИЕ ====================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    BOT_USERNAME,
    DATABASE_PATH,
    DONATE_BANK,
    DONATE_RECEIVER,
    DONATE_URL,
    GAME_COMMISSION,
    MORNING_CLEANUP_HOUR,
    START_BALANCE,
    SUPER_ADMIN_IDS,
)


def validate_config() -> bool:
    """Проверка обязательных параметров конфигурации."""
    errors = []

    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is not set")
    if not START_BALANCE or START_BALANCE < 0:
        errors.append("START_BALANCE must be >= 0")
    if not BOT_USERNAME:
        errors.append("BOT_USERNAME is not set")

    if errors:
        logger.critical("❌ Configuration validation failed:")
        for error in errors:
            logger.critical("   - %s", error)
        return False

    logger.info("✅ Configuration validated")
    return True


if not validate_config():
    sys.exit(1)

# Нормализация списков
ADMIN_IDS = ADMIN_IDS or []
SUPER_ADMIN_IDS = SUPER_ADMIN_IDS or []
START_BALANCE = START_BALANCE or 1000

OWNER_ID = int(os.getenv("OWNER_ID", "895844198"))
BOT_ID: Optional[int] = None

# ==================== БОТ И ДИСПЕТЧЕР ====================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_background_tasks: Set[asyncio.Task] = set()
_startup_time = datetime.now(timezone.utc)

# ==================== FSM (импорт из handlers.start) ====================

try:
    from handlers.start import FeedbackState
except ImportError:
    from aiogram.fsm.state import State, StatesGroup

    class FeedbackState(StatesGroup):
        waiting_for_message = State()

# ==================== RATE LIMITER ====================

try:
    from utils.rate_limiter import (
        RateLimiter,
        start_cleanup_task,
        stop_cleanup_task,
    )

    daily_limiter = RateLimiter(limit=1, period=10)
except ImportError:
    logger.warning("⚠️ utils.rate_limiter not found, using fallback")

    class FallbackLimiter:
        def __init__(self, *args, **kwargs):
            pass

        def is_allowed(self, *args, **kwargs) -> bool:
            return True

    daily_limiter = FallbackLimiter()

    def start_cleanup_task():
        pass

    def stop_cleanup_task():
        pass

# ==================== БАЗА ДАННЫХ ====================

from database import DatabaseError, db

# Кэш пользователей
_user_cache: Dict[int, Tuple[Optional[Dict[str, Any]], float]] = {}
_CACHE_TTL = int(os.getenv("CACHE_TTL", "30"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "1000"))
CACHE_CLEANUP_INTERVAL = int(os.getenv("CACHE_CLEANUP_INTERVAL", "300"))

_cache_hits = 0
_cache_misses = 0
_last_cache_cleanup = time.time()
_cache_lock = asyncio.Lock()


async def get_user_cached(user_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Получение пользователя с кэшированием и авто-созданием."""
    global _cache_hits, _cache_misses, _last_cache_cleanup

    if user_id is None or db is None:
        return None

    now = time.time()

    async with _cache_lock:
        if now - _last_cache_cleanup > CACHE_CLEANUP_INTERVAL:
            _cleanup_expired_cache(now)
            _last_cache_cleanup = now

        if user_id in _user_cache:
            data, timestamp = _user_cache[user_id]
            if now - timestamp < _CACHE_TTL:
                _cache_hits += 1
                return data

    _cache_misses += 1

    try:
        user = await db.get_user(user_id)

        if not user:
            await db.create_user(
                user_id=user_id, username=None, first_name=None, balance=START_BALANCE
            )
            user = await db.get_user(user_id)

        if user:
            async with _cache_lock:
                if len(_user_cache) >= MAX_CACHE_SIZE:
                    sorted_items = sorted(_user_cache.items(), key=lambda x: x[1][1])
                    for old_id, _ in sorted_items[: MAX_CACHE_SIZE // 10]:
                        del _user_cache[old_id]
                _user_cache[user_id] = (user, now)
        return user

    except DatabaseError as e:
        logger.error("❌ DB error getting user %s: %s", user_id, e, exc_info=True)
        return None
    except Exception as e:
        logger.error("❌ Unexpected error getting user %s: %s", user_id, e, exc_info=True)
        return None


def _cleanup_expired_cache(now: float) -> None:
    """Очистка устаревших записей кэша."""
    expired_keys = [
        uid for uid, (_, timestamp) in _user_cache.items() if now - timestamp > _CACHE_TTL
    ]
    for uid in expired_keys:
        del _user_cache[uid]
    if expired_keys:
        logger.debug("🧹 Cache cleanup: removed %d expired entries", len(expired_keys))


def get_cache_stats() -> Dict[str, int]:
    """Статистика кэша."""
    total = _cache_hits + _cache_misses
    return {
        "hits": _cache_hits,
        "misses": _cache_misses,
        "size": len(_user_cache),
        "hit_rate": round(_cache_hits / total * 100, 1) if total > 0 else 0,
    }


def invalidate_user_cache(user_id: Optional[int]) -> None:
    """Инвалидация кэша пользователя."""
    if user_id and user_id in _user_cache:
        del _user_cache[user_id]


async def get_balance_safe(user_id: Optional[int]) -> int:
    """Безопасное получение баланса."""
    if user_id is None or db is None:
        return 0
    try:
        return await db.get_balance(user_id) or 0
    except Exception as e:
        logger.error("❌ Error getting balance for %s: %s", user_id, e, exc_info=True)
        return 0


async def get_user_stats_safe(user_id: Optional[int]) -> Dict[str, int]:
    """Быстрый доступ к статистике."""
    if user_id is None or db is None:
        return {"wins": 0, "games_played": 0, "messages_total": 0, "rank": 1, "xp": 0, "balance": 0}
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return {
                "wins": stats.get("wins", 0) or 0,
                "games_played": stats.get("games_played", 0) or 0,
                "messages_total": stats.get("messages_total", 0) or 0,
                "rank": stats.get("rank", 1) or 1,
                "xp": stats.get("xp", 0) or 0,
                "balance": stats.get("balance", 0) or 0,
            }
    except Exception as e:
        logger.error("❌ Error getting stats for %s: %s", user_id, e, exc_info=True)
    return {"wins": 0, "games_played": 0, "messages_total": 0, "rank": 1, "xp": 0, "balance": 0}


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
        return html.escape(str(text))
    except Exception:
        return str(text) if isinstance(text, str) else ""


# ==================== ПРОВЕРКА АДМИНА ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    """Проверка прав супер-админа."""
    if user_id is None:
        return False
    return user_id == OWNER_ID or user_id in (SUPER_ADMIN_IDS or [])


async def is_admin_db(user_id: Optional[int]) -> bool:
    """Проверка прав администратора."""
    if user_id is None or db is None:
        return False
    try:
        if hasattr(db, "is_admin") and callable(db.is_admin):
            return await db.is_admin(user_id) or is_super_admin(user_id)
    except Exception as e:
        logger.debug("db.is_admin() not available: %s", e)
    return is_super_admin(user_id) or user_id in (ADMIN_IDS or [])


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Генерация клавиатуры главного меню."""
    keyboard = [
        [
            InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="menu_vip"),
            InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="menu_profile"),
        ],
        [
            InlineKeyboardButton(text="💰 БАЛАНС", callback_data="menu_balance"),
            InlineKeyboardButton(text="🏆 РАНГ", callback_data="menu_rank"),
        ],
        [
            InlineKeyboardButton(text="🎮 КРЕСТИКИ-НОЛИКИ", callback_data="menu_xo"),
            InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="menu_stats"),
        ],
        [
            InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="menu_all"),
            InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="menu_ref"),
        ],
        [
            InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="menu_relations"),
            InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="menu_groups"),
        ],
        [
            InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="menu_rp"),
            InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="menu_tags"),
        ],
        [
            InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="menu_topchats"),
            InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="menu_privacy"),
        ],
        [
            InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="menu_help"),
            InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="menu_donate"),
        ],
        [InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="menu_feedback")],
    ]
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard(callback_data: str = "back_to_menu") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой НАЗАД."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
        ]
    )


async def safe_callback_edit(
    callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """Безопасное редактирование сообщения."""
    if not callback or not callback.message:
        return False
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return True
    except TelegramBadRequest as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            return True
        if "message can't be edited" in err_str:
            try:
                await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
                return True
            except Exception:
                return False
        logger.warning("⚠️ BadRequest in edit: %s", e)
        return False
    except TelegramForbiddenError:
        logger.warning("⚠️ Forbidden to edit message")
        return False
    except TelegramAPIError as e:
        logger.error("❌ Telegram API error in edit: %s", e, exc_info=True)
        return False
    except Exception as e:
        logger.error("❌ Unexpected error in edit: %s", e, exc_info=True)
        return False


async def render_main_menu(
    user_id: int, chat_id: int, first_name: str
) -> Tuple[str, InlineKeyboardMarkup]:
    """Формирование текста главного меню."""
    is_admin = await is_admin_db(user_id)
    balance = await get_balance_safe(user_id)
    stats = await get_user_stats_safe(user_id)

    user = await get_user_cached(user_id)
    vip_level = safe_int(user.get("vip_level")) if user else 0
    daily_streak = safe_int(user.get("daily_streak")) if user else 0

    text = (
        "🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
        f"👋 Привет, <b>{safe_html_escape(first_name)}</b>!\n"
        f"💰 Баланс: <b>{balance:,}</b> NCoin\n"
        f"⭐ VIP: {'✅ Ур. ' + str(vip_level) if vip_level > 0 else '❌ Нет'}\n"
        f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
        f"🏆 Ранг: <b>#{stats['rank']}</b> ({stats['xp']} XP)\n"
        f"🎮 XO: <b>{stats['wins']}</b> побед ({stats['games_played']} игр)\n"
        f"💬 Сообщений: <b>{stats['messages_total']:,}</b>\n\n"
        "👇 Выберите действие:"
    )
    return text, get_main_menu(is_admin)


# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject) -> None:
    """Обработка /start с авто-регистрацией и deep links."""
    if not message or not message.from_user:
        return

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    chat_id = message.chat.id if message.chat else user_id

    logger.info("🚀 /start from %s (chat: %s)", user_id, chat_id)

    if db:
        try:
            await db.create_user(
                user_id=user_id, username=username, first_name=first_name, balance=START_BALANCE
            )
            invalidate_user_cache(user_id)
        except DatabaseError as e:
            logger.error("❌ DB error creating user %s: %s", user_id, e, exc_info=True)
        except Exception as e:
            logger.error("❌ Unexpected error creating user %s: %s", user_id, e, exc_info=True)

    args = command.args
    if args == "gifts":
        await _handle_deep_link(message, "handlers.economy", "show_gifts_catalog", "каталог")
        return
    elif args == "help":
        await cmd_help(message)
        return
    elif args and args.startswith("ref"):
        await _handle_deep_link(message, "handlers.referral", "process_ref_link", "реферальная ссылка")
        return

    text, keyboard = await render_main_menu(user_id, chat_id, first_name)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def _handle_deep_link(message: Message, module: str, func: str, name: str) -> None:
    """Универсальный обработчик deep link."""
    try:
        mod = __import__(module, fromlist=[func])
        handler = getattr(mod, func, None)
        if handler and callable(handler):
            await handler(message)
        else:
            await message.answer(f"⚠️ Раздел {name} временно недоступен.")
    except ImportError:
        await message.answer(f"⚠️ Раздел {name} временно недоступен.")
    except Exception as e:
        logger.error("❌ Error in %s: %s", name, e, exc_info=True)
        await message.answer(f"⚠️ Ошибка загрузки {name}.")


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Справка с актуальными командами."""
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
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Отмена любого FSM-состояния."""
    if not message:
        return
    await state.clear()
    await message.answer("❌ <b>Действие отменено</b>", parse_mode=ParseMode.HTML)
    if message.from_user:
        text, keyboard = await render_main_menu(
            message.from_user.id,
            message.chat.id if message.chat else message.from_user.id,
            message.from_user.first_name or "Пользователь",
        )
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("health"))
async def cmd_health(message: Message) -> None:
    """Health-check эндпоинт."""
    uptime = datetime.now(timezone.utc) - _startup_time
    uptime_str = str(uptime).split(".")[0]
    cache_stats = get_cache_stats()

    text = (
        "🟢 <b>HEALTH CHECK</b>\n\n"
        "🤖 Бот: ok\n"
        f"🗄️ БД: {'ok' if db and db._initialized else 'fail'}\n"
        f"💾 Кэш пользователей: {len(_user_cache)}\n"
        f"📊 Попаданий кэша: {cache_stats['hits']}\n"
        f"📊 Промахов кэша: {cache_stats['misses']}\n"
        f"📊 Hit rate: {cache_stats['hit_rate']}%\n"
        f"⏱️ Аптайм: {uptime_str}\n"
        "🔖 Версия: 7.6.0"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


# ==================== БЕЗОПАСНЫЙ ВЫЗОВ ОБРАБОТЧИКОВ ====================

async def _safe_handler(message: Message, module_name: str, func_name: str, error_msg: str) -> None:
    """Безопасный вызов обработчика команды."""
    if not message:
        return

    try:
        module = __import__(module_name, fromlist=[func_name])
        func = getattr(module, func_name, None)
        if func and callable(func):
            await func(message)
        else:
            logger.warning("⚠️ Function %s not found in %s", func_name, module_name)
            await message.answer(error_msg)
    except ImportError as e:
        logger.error("❌ Import error %s.%s: %s", module_name, func_name, e, exc_info=True)
        await message.answer("⚠️ Функция временно недоступна.")
    except Exception as e:
        logger.error("❌ Error in %s.%s: %s", module_name, func_name, e, exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# ==================== ПРЯМЫЕ ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("daily"))
async def cmd_daily_direct(message: Message) -> None:
    await _safe_handler(message, "handlers.economy", "cmd_daily", "❌ Ошибка ежедневного бонуса")


@dp.message(Command("balance"))
async def cmd_balance_direct(message: Message) -> None:
    await _safe_handler(message, "handlers.economy", "cmd_balance", "❌ Ошибка проверки баланса")


@dp.message(Command("profile"))
async def cmd_profile_direct(message: Message) -> None:
    await _safe_handler(message, "handlers.profile", "cmd_profile", "❌ Ошибка профиля")


@dp.message(Command("stats"))
async def cmd_stats_direct(message: Message) -> None:
    await _safe_handler(message, "handlers.stats", "cmd_stats", "❌ Ошибка статистики")


@dp.message(Command("top"))
async def cmd_top_direct(message: Message) -> None:
    await _safe_handler(message, "handlers.stats", "cmd_top", "❌ Ошибка топа")


@dp.message(Command("vip"))
async def cmd_vip_direct(message: Message) -> None:
    await _safe_handler(message, "handlers.vip", "cmd_vip", "❌ Ошибка VIP")


@dp.message(Command("policy"))
async def cmd_policy_direct(message: Message) -> None:
    """Показ политики."""
    if not message:
        return
    if db:
        try:
            sections = db.get_all_policy_sections()
            text = "🔒 <b>ПОЛИТИКА И ПРАВИЛА NEXUS</b>\n\n"
            for sec in sections:
                content = db.get_policy_section(sec["key"])
                text += f"{sec['emoji']} <b>{sec['title']}</b>\n{content}\n\n"
            text += f"<i>Последнее обновление: {datetime.now(timezone.utc).strftime('%d.%m.%Y')}</i>"
            await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
            return
        except Exception as e:
            logger.error("❌ Error loading policy: %s", e, exc_info=True)

    await cmd_help(message)


# ==================== ОБРАТНАЯ СВЯЗЬ ====================

_feedback_cooldown: Dict[int, float] = {}
FEEDBACK_COOLDOWN = int(os.getenv("FEEDBACK_COOLDOWN", "60"))


@dp.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext) -> None:
    """Начало обратной связи с rate limiting."""
    if not message or not message.from_user:
        return

    user_id = message.from_user.id
    now = time.time()

    last_feedback = _feedback_cooldown.get(user_id, 0)
    if now - last_feedback < FEEDBACK_COOLDOWN:
        remaining = int(FEEDBACK_COOLDOWN - (now - last_feedback))
        await message.answer(f"⏰ Подождите {remaining} секунд перед следующим обращением.")
        return

    _feedback_cooldown[user_id] = now

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
        reply_markup=get_back_keyboard(),
    )


@dp.message(FeedbackState.waiting_for_message)
async def process_feedback(message: Message, state: FSMContext) -> None:
    """Обработка сообщения обратной связи."""
    if not message or not message.from_user:
        return

    text = (message.text or "").strip()
    user_id = message.from_user.id

    if text.lower() in ("/cancel", "отмена", "отменить"):
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
            logger.info("✅ Feedback ticket #%s created by user %s", ticket_id, user_id)
        except DatabaseError as e:
            logger.error("❌ DB error creating feedback ticket: %s", e, exc_info=True)
        except Exception as e:
            logger.error("❌ Unexpected error creating feedback ticket: %s", e, exc_info=True)

    if ADMIN_IDS:
        notify_text = (
            f"📝 <b>НОВЫЙ ОТЗЫВ #{ticket_id or 'N/A'}</b>\n\n"
            f"👤 От: {safe_html_escape(message.from_user.full_name)}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
        )
        if message.from_user.username:
            notify_text += f"🔖 Username: @{safe_html_escape(message.from_user.username)}\n"
        notify_text += f"💬 Сообщение:\n{safe_html_escape(text)}"
        await _notify_admins(notify_text)

    await state.clear()

    confirmation = "✅ <b>Спасибо за обратную связь!</b>\n\n"
    if ticket_id:
        confirmation += f"🎫 Ваш тикет: #{ticket_id}\n"
    confirmation += (
        "Ваше сообщение сохранено и отправлено разработчику.\n"
        "Мы ответим в личные сообщения в ближайшее время.\n\n"
        "<i>Статус тикета можно проверить командой /tickets</i>"
    )
    await message.answer(confirmation, parse_mode=ParseMode.HTML)


async def _notify_admins(text: str) -> None:
    """Отправка уведомления администраторам."""
    for admin_id in ADMIN_IDS:
        if admin_id is None:
            continue
        try:
            await bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except TelegramForbiddenError:
            logger.warning("⚠️ Cannot notify admin %s: Forbidden", admin_id)
        except TelegramAPIError as e:
            logger.error("❌ Error notifying admin %s: %s", admin_id, e, exc_info=True)
        except Exception as e:
            logger.error("❌ Unexpected error notifying admin %s: %s", admin_id, e, exc_info=True)


# ==================== CALLBACK: НАЗАД ====================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery) -> None:
    """Возврат в главное меню."""
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
        logger.error("❌ Error in back_to_menu: %s", e, exc_info=True)
        await callback.message.answer("❌ Ошибка загрузки меню", reply_markup=get_back_keyboard())

    await callback.answer()


# ==================== УСТАНОВКА БОТА ДЛЯ МОДУЛЕЙ ====================

def setup_bot_for_modules() -> None:
    """Регистрация бота в модулях."""
    modules_with_set_bot = [
        "handlers.tictactoe",
        "handlers.smart_commands",
        "handlers.referral",
        "handlers.admin",
        "handlers.economy",
    ]

    for module_name in modules_with_set_bot:
        try:
            module = __import__(module_name, fromlist=["set_bot"])
            if hasattr(module, "set_bot") and callable(module.set_bot):
                module.set_bot(bot)
                logger.info("✅ Bot set for %s", module_name)
        except ImportError:
            logger.warning("⚠️ Module %s not found, skipping", module_name)
        except Exception as e:
            logger.warning("⚠️ Error setting bot for %s: %s", module_name, e)


# ==================== ЗАГРУЗКА РОУТЕРОВ ====================

_ROUTER_MODULES = {
    "handlers.vip": "router",
    "handlers.profile": "router",
    "handlers.economy": "router",
    "handlers.tictactoe": "router",
    "handlers.stats": "router",
    "handlers.tag": "router",
    "handlers.admin": "router",
    "handlers.rating": "router",
    "handlers.smart_commands": "router",
    "handlers.referral": "router",
    "handlers.relationships": "router",
    "handlers.tag_user": "router",
    "handlers.ranks": "router",
    "handlers.tag_admin": "router",
    "handlers.tag_trigger": "router",
    "handlers.start": "router",
    "handlers.ai_assistant": "router",
    "handlers.tag_categories": "router",
}

_loaded_routers_count = 0


def load_all_routers() -> None:
    """Динамическая загрузка всех роутеров."""
    global _loaded_routers_count
    total = len(_ROUTER_MODULES)

    for module_name, attr_name in _ROUTER_MODULES.items():
        try:
            module = __import__(module_name, fromlist=[attr_name])
            router = getattr(module, attr_name, None)
            if router:
                dp.include_router(router)
                logger.info("✅ Loaded router: %s", module_name)
                _loaded_routers_count += 1
            else:
                logger.warning("⚠️ Router '%s' not found in %s", attr_name, module_name)
        except ImportError as e:
            logger.warning("⚠️ Cannot import %s: %s", module_name, e)
        except Exception as e:
            logger.warning("⚠️ Error loading %s: %s", module_name, e)

    logger.info("📦 Loaded %s/%s routers", _loaded_routers_count, total)


# ==================== ОБРАБОТЧИКИ КНОПОК МЕНЮ ====================

async def _handle_menu_callback(callback: CallbackQuery, module: str, func: str, error_msg: str) -> None:
    """Универсальный обработчик кнопок меню."""
    if not callback or not callback.message:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    try:
        module_obj = __import__(module, fromlist=[func])
        handler = getattr(module_obj, func, None)
        if handler and callable(handler):
            await handler(callback.message)
        else:
            logger.warning("⚠️ Handler %s not found in %s", func, module)
            await callback.message.answer("⚠️ Функция в разработке", reply_markup=get_back_keyboard())
    except ImportError:
        logger.error("❌ Cannot import %s.%s", module, func, exc_info=True)
        await callback.message.answer("⚠️ Раздел временно недоступен", reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error("❌ Error in %s.%s: %s", module, func, e, exc_info=True)
        await callback.message.answer(error_msg, reply_markup=get_back_keyboard())
    finally:
        await callback.answer()


# Явная регистрация каждого обработчика (без замыкания в цикле)
@dp.callback_query(F.data == "menu_vip")
async def _h_menu_vip(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.vip", "cmd_vip", "❌ Ошибка загрузки VIP")


@dp.callback_query(F.data == "menu_profile")
async def _h_menu_profile(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.profile", "cmd_profile", "❌ Ошибка профиля")


@dp.callback_query(F.data == "menu_balance")
async def _h_menu_balance(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.economy", "cmd_balance", "❌ Ошибка баланса")


@dp.callback_query(F.data == "menu_rank")
async def _h_menu_rank(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.ranks", "cmd_rank", "❌ Ошибка рангов")


@dp.callback_query(F.data == "menu_xo")
async def _h_menu_xo(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.tictactoe", "cmd_xo", "❌ Ошибка игры")


@dp.callback_query(F.data == "menu_stats")
async def _h_menu_stats(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.stats", "cmd_stats", "❌ Ошибка статистики")


@dp.callback_query(F.data == "menu_all")
async def _h_menu_all(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.tag", "cmd_all", "❌ Ошибка тегов")


@dp.callback_query(F.data == "menu_ref")
async def _h_menu_ref(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.referral", "ref_menu_callback", "❌ Ошибка рефералки")


@dp.callback_query(F.data == "menu_relations")
async def _h_menu_relations(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.relationships", "relationships_menu", "❌ Ошибка отношений")


@dp.callback_query(F.data == "menu_rp")
async def _h_menu_rp(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.smart_commands", "cmd_my_custom_rp", "❌ Ошибка РП")


@dp.callback_query(F.data == "menu_tags")
async def _h_menu_tags(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.tag_user", "my_tags_menu_callback", "❌ Ошибка тегов")


@dp.callback_query(F.data == "menu_topchats")
async def _h_menu_topchats(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.rating", "cmd_top_chats", "❌ Ошибка рейтинга")


@dp.callback_query(F.data == "menu_donate")
async def _h_menu_donate(c: CallbackQuery):
    await _handle_menu_callback(c, "handlers.economy", "cmd_donate", "❌ Ошибка доната")


@dp.callback_query(F.data == "menu_groups")
async def menu_groups(callback: CallbackQuery) -> None:
    """Обработчик кнопки ГРУППЫ."""
    if not callback or not callback.message:
        return
    await safe_callback_edit(
        callback,
        "👥 <b>ГРУППЫ</b>\n\nФункция в разработке.\nСкоро: создание кланов, войны, общий чат.",
        get_back_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_privacy")
async def menu_privacy(callback: CallbackQuery) -> None:
    """Обработчик кнопки ПОЛИТИКА."""
    if not callback or not callback.message:
        return

    try:
        if db and hasattr(db, "get_all_policy_sections"):
            sections = db.get_all_policy_sections()
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"{sec['emoji']} {sec['title']}",
                            callback_data=f"policy:{sec['key']}",
                        )
                    ]
                    for sec in sections
                ]
                + [[InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]]
            )

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
        logger.error("❌ Error loading policy: %s", e, exc_info=True)
        await callback.message.answer("❌ Ошибка загрузки политики", reply_markup=get_back_keyboard())

    await callback.answer()


@dp.callback_query(F.data.startswith("policy:"))
async def policy_section_callback(callback: CallbackQuery) -> None:
    """Обработчик подразделов политики."""
    if not callback or not callback.message:
        return

    section_key = callback.data.split(":")[1] if ":" in callback.data else None
    if not section_key or not db:
        await callback.answer("❌ Раздел не найден", show_alert=True)
        return

    try:
        content = db.get_policy_section(section_key)
        sections = db.get_all_policy_sections()

        section_idx = next((i for i, s in enumerate(sections) if s["key"] == section_key), 0)
        current = sections[section_idx] if section_idx < len(sections) else None

        if current and content:
            text = f"{current['emoji']} <b>{current['title']}</b>\n\n{content}"

            prev_key = sections[section_idx - 1]["key"] if section_idx > 0 else None
            next_key = sections[section_idx + 1]["key"] if section_idx < len(sections) - 1 else None

            nav_buttons = []
            if prev_key:
                nav_buttons.append(
                    InlineKeyboardButton(text="◀️ Пред.", callback_data=f"policy:{prev_key}")
                )
            nav_buttons.append(InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu"))
            if next_key:
                nav_buttons.append(
                    InlineKeyboardButton(text="След. ▶️", callback_data=f"policy:{next_key}")
                )

            nav_keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons])
            await safe_callback_edit(callback, text, nav_keyboard)
        else:
            await callback.answer("❌ Содержимое не найдено", show_alert=True)
    except Exception as e:
        logger.error("❌ Error showing policy section %s: %s", section_key, e, exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

    await callback.answer()


@dp.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery) -> None:
    """Обработчик кнопки ПОМОЩЬ."""
    await cmd_help(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "menu_feedback")
async def menu_feedback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки ОБРАТНАЯ СВЯЗЬ."""
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
        get_back_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_admin")
async def menu_admin(callback: CallbackQuery) -> None:
    """Обработчик кнопки АДМИН-ПАНЕЛЬ."""
    if not callback or not callback.message or not callback.from_user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id

    if not await is_admin_db(user_id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        logger.warning("⚠️ Unauthorized admin panel access attempt by %s", user_id)
        return

    try:
        from handlers.admin import admin_panel_callback

        await admin_panel_callback(callback)
    except ImportError:
        await callback.message.answer("⚠️ Админ-панель в разработке", reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error("❌ Error in admin panel: %s", e, exc_info=True)
        await callback.message.answer("❌ Ошибка загрузки админ-панели", reply_markup=get_back_keyboard())

    await callback.answer()


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

async def start_all_background_tasks() -> None:
    """Запуск всех фоновых задач."""
    try:
        start_cleanup_task()
        logger.info("✅ Rate limiter cleanup started")
    except Exception as e:
        logger.warning("⚠️ Rate limiter cleanup error: %s", e)

    try:
        from utils.auto_delete import schedule_morning_cleanup

        task = asyncio.create_task(schedule_morning_cleanup(bot))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info("✅ Morning cleanup scheduled")
    except ImportError:
        logger.warning("⚠️ utils.auto_delete not found, skipping morning cleanup")
    except Exception as e:
        logger.warning("⚠️ Morning cleanup error: %s", e)

    async def periodic_rank_update() -> None:
        """Обновление рангов раз в 10 минут."""
        while True:
            try:
                await asyncio.sleep(600)
                if db:
                    try:
                        active_users = await db._execute_with_retry(
                            """SELECT DISTINCT user_id FROM user_activity_log 
                               WHERE date >= date('now', '-1 days') LIMIT 100""",
                            fetch_all=True,
                        )
                        if active_users:
                            updated = 0
                            for row in active_users:
                                uid = row["user_id"]
                                rank_info = await db.get_user_rank(uid)
                                if rank_info and rank_info.get("needs_recalc"):
                                    await db.recalculate_user_rank(uid)
                                    updated += 1
                            if updated > 0:
                                logger.info("🔄 Updated ranks for %s users", updated)
                    except Exception as e:
                        logger.debug("Rank update query error: %s", e)
            except asyncio.CancelledError:
                logger.info("🔄 Periodic rank update task cancelled")
                break
            except Exception as e:
                logger.error("❌ Error in periodic_rank_update: %s", e, exc_info=True)
                await asyncio.sleep(60)

    stats_task = asyncio.create_task(periodic_rank_update())
    _background_tasks.add(stats_task)
    stats_task.add_done_callback(_background_tasks.discard)
    logger.info("✅ Periodic rank update task started")


async def stop_all_background_tasks() -> None:
    """Остановка фоновых задач."""
    try:
        stop_cleanup_task()
    except Exception:
        pass

    for task in list(_background_tasks):
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    _background_tasks.clear()
    logger.info("✅ Background tasks stopped")


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

async def on_startup() -> None:
    """Инициализация при запуске бота."""
    global BOT_ID

    try:
        me = await bot.get_me()
        BOT_ID = me.id
        logger.info("🤖 Bot: @%s (ID: %s)", me.username, BOT_ID)
    except Exception as e:
        logger.critical("❌ Cannot get bot info: %s", e, exc_info=True)
        sys.exit(1)

    logger.info("🚀 NEXUS Bot v7.6.0 starting...")

    setup_bot_for_modules()
    load_all_routers()

    if db:
        try:
            await db.initialize()
            logger.info("✅ Database initialized")
        except DatabaseError as e:
            logger.critical("❌ Database initialization failed: %s", e, exc_info=True)
            sys.exit(1)
        except Exception as e:
            logger.critical("❌ Unexpected DB error: %s", e, exc_info=True)
            sys.exit(1)

    try:
        from handlers.ranks import init_ranks_table

        await init_ranks_table()
        logger.info("✅ Ranks table initialized")
    except ImportError:
        logger.warning("⚠️ handlers.ranks not found")
    except Exception as e:
        logger.warning("⚠️ Ranks init error: %s", e)

    try:
        from handlers.smart_commands import load_custom_rp_commands

        await load_custom_rp_commands()
        logger.info("✅ Custom RP commands loaded")
    except ImportError:
        logger.warning("⚠️ handlers.smart_commands not found")
    except Exception as e:
        logger.warning("⚠️ Custom RP load error: %s", e)

    try:
        from handlers.smart_commands import set_bot as set_smart_bot

        set_smart_bot(bot)
        logger.info("✅ Bot ID updated in smart_commands")
    except Exception:
        pass

    # Инициализация категорий тегов
    try:
        from handlers.tag_categories import init_categories

        await init_categories()
        logger.info("✅ Tag categories initialized")
    except ImportError:
        logger.warning("⚠️ handlers.tag_categories not found")
    except Exception as e:
        logger.warning("⚠️ Tag categories init error: %s", e)

    await start_all_background_tasks()

    if SUPER_ADMIN_IDS:
        startup_text = (
            "🚀 <b>NEXUS Bot v7.6.0 запущен!</b>\n\n"
            f"✅ БД: подключена\n"
            f"✅ Роутеры: загружены ({_loaded_routers_count})\n"
            f"✅ Фоновые задачи: активны\n"
            f"🕒 Время: {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
        )
        await _notify_super_admins(startup_text)

    logger.info("✅ ALL SYSTEMS GO! Bot is ready.")


async def _notify_super_admins(text: str) -> None:
    """Отправка уведомления супер-админам."""
    for admin_id in SUPER_ADMIN_IDS:
        if admin_id is None:
            continue
        try:
            await bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except TelegramForbiddenError:
            logger.warning("⚠️ Cannot notify super-admin %s: Forbidden", admin_id)
        except Exception as e:
            logger.warning("⚠️ Error notifying admin %s: %s", admin_id, e)


async def on_shutdown() -> None:
    """Корректное завершение работы."""
    logger.info("🛑 Shutting down NEXUS Bot...")

    await stop_all_background_tasks()
    _user_cache.clear()

    if db and hasattr(db, "close"):
        try:
            await db.close()
            logger.info("✅ Database connection closed")
        except Exception as e:
            logger.error("❌ Error closing DB: %s", e, exc_info=True)

    try:
        await bot.session.close()
        logger.info("✅ Bot session closed")
    except Exception as e:
        logger.warning("⚠️ Error closing bot session: %s", e)

    logger.info("👋 NEXUS Bot stopped gracefully")


# ==================== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ====================

_message_save_cooldown: Dict[int, float] = {}
_message_save_lock = asyncio.Lock()
_SAVE_COOLDOWN = int(os.getenv("SAVE_COOLDOWN", "2"))
_MAX_COOLDOWN_ENTRIES = int(os.getenv("MAX_COOLDOWN_ENTRIES", "5000"))


@dp.message()
async def save_all_messages(message: Message) -> None:
    """Сохранение сообщений для статистики с rate limiting."""
    if not message or not db or not message.chat or not message.from_user:
        return

    if message.text and message.text.startswith("/"):
        return
    if message.from_user.is_bot:
        return

    user_id = message.from_user.id
    text = message.text or ""
    now = time.time()

    # ✅ Потокобезопасная проверка кулдауна
    async with _message_save_lock:
        last_save = _message_save_cooldown.get(user_id, 0)
        if now - last_save < _SAVE_COOLDOWN:
            return
        _message_save_cooldown[user_id] = now

        # Автоочистка старых записей
        if len(_message_save_cooldown) > _MAX_COOLDOWN_ENTRIES:
            cutoff = now - 300
            old_keys = [uid for uid, t in _message_save_cooldown.items() if t < cutoff]
            for uid in old_keys:
                del _message_save_cooldown[uid]

    start_time = time.time()

    try:
        if text and len(text.strip()) >= 3:
            words = text.lower().split()
            clean_words = [
                w.strip('.,!?;:()[]{}"\'-') for w in words if len(w.strip('.,!?;:()[]{}"\'-')) >= 3
            ]
            for word in clean_words[:10]:
                await db.track_word(message.chat.id, word)

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

        await db.track_user_activity(user_id, message.chat.id, activity_type, 1)

        try:
            from handlers.ranks import track_message_activity

            await track_message_activity(user_id, message)
        except ImportError:
            pass
        except Exception as e:
            logger.debug("Rank tracking error: %s", e)

    except DatabaseError as e:
        if "database is locked" not in str(e).lower():
            logger.debug("⚠️ DB error from %s: %s", user_id, e)
    except Exception as e:
        logger.debug("⚠️ Unexpected error from %s: %s", user_id, e)
    finally:
        duration = time.time() - start_time
        if duration > 1.0:
            logger.warning("⚠️ Slow message save (%.2fs) for user %s", duration, user_id)


# ==================== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК ====================

@dp.errors()
async def errors_handler(update: Update, exception: Exception) -> bool:
    """Глобальный обработчик ошибок с категоризацией."""
    user_id: Any = "unknown"
    try:
        if hasattr(update, "event") and update.event:
            event = update.event
            if hasattr(event, "from_user") and event.from_user:
                user_id = event.from_user.id
            elif hasattr(event, "chat") and hasattr(event.chat, "id"):
                user_id = f"chat:{event.chat.id}"
    except Exception:
        pass

    if isinstance(exception, TelegramForbiddenError):
        logger.warning("⚠️ Forbidden: bot blocked by user %s", user_id)
        return True
    elif isinstance(exception, TelegramBadRequest):
        logger.warning("⚠️ BadRequest: %s", exception)
        return True
    elif isinstance(exception, TelegramAPIError):
        logger.error("❌ Telegram API error: %s", exception, exc_info=True)
        return True
    elif isinstance(exception, DatabaseError):
        logger.error("🗄️ Database error: %s", exception, exc_info=True)
        return True
    else:
        error_text = (
            "💥 <b>КРИТИЧЕСКАЯ ОШИБКА</b>\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"❗ Тип: {type(exception).__name__}\n"
            f"📝 Текст: {str(exception)[:200]}"
        )
        logger.critical(error_text, exc_info=True)

        if SUPER_ADMIN_IDS:
            asyncio.create_task(_notify_super_admins(error_text))

        return True


# ==================== ТОЧКА ВХОДА ====================

async def main() -> None:
    """Главная функция запуска бота."""
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    dp.errors.register(errors_handler)

    logger.info("📡 Starting polling...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("👋 Received keyboard interrupt")
    except Exception as e:
        logger.critical("💥 Polling error: %s: %s", type(e).__name__, e, exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.critical("💥 Fatal error: %s: %s", type(e).__name__, e, exc_info=True)
        sys.exit(1)
