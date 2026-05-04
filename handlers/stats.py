#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/stats.py
# ВЕРСИЯ: 2.4.0-production (исправленная после аудита)
# ОПИСАНИЕ: Модуль статистики — оптимизированный кэш, валидация, метрики
# ============================================
# ИСПРАВЛЕНИЯ v2.4.0:
#   🟡 Добавлен _shutdown_event для корректного завершения
#   🟡 hasattr проверки для методов БД
#   🟡 CancelledError обработка в show_top_list
#   🟡 Безопасный доступ к callback.from_user
#   🟢 Константы вынесены в os.getenv()
# ============================================

import asyncio
import functools
import html
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime
from typing import Optional, Dict, List, Any, Union, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db, DatabaseError

router = Router()
logger = logging.getLogger(__name__)


# ==================== КОНФИГУРАЦИЯ С ВАЛИДАЦИЕЙ ====================

class StatsConfig:
    """Конфигурация модуля статистики."""
    
    TOP_LIMIT = int(os.getenv("STATS_TOP_LIMIT", "15"))
    MAX_NAME_LENGTH = int(os.getenv("STATS_MAX_NAME_LENGTH", "20"))
    TIMEOUT_STATS = float(os.getenv("STATS_TIMEOUT_STATS", "10.0"))
    TIMEOUT_TOP = float(os.getenv("STATS_TIMEOUT_TOP", "10.0"))
    CACHE_TTL_STATS = int(os.getenv("STATS_CACHE_TTL_STATS", "60"))
    CACHE_TTL_TOP = int(os.getenv("STATS_CACHE_TTL_TOP", "300"))
    MAX_CACHE_SIZE = int(os.getenv("STATS_MAX_CACHE_SIZE", "100"))
    CACHE_CLEANUP_INTERVAL = int(os.getenv("STATS_CACHE_CLEANUP_INTERVAL", "60"))
    METRICS_LOG_INTERVAL = int(os.getenv("STATS_METRICS_LOG_INTERVAL", "3600"))
    BOT_USER_ID = "bot"
    
    @classmethod
    def validate(cls) -> List[str]:
        """Валидация конфигурации при старте."""
        errors = []
        
        for name in ['TIMEOUT_STATS', 'TIMEOUT_TOP', 'CACHE_TTL_STATS',
                      'CACHE_TTL_TOP', 'CACHE_CLEANUP_INTERVAL', 'METRICS_LOG_INTERVAL']:
            value = getattr(cls, name)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"{name} must be > 0, got {value}")
        
        for name in ['TOP_LIMIT', 'MAX_NAME_LENGTH', 'MAX_CACHE_SIZE']:
            value = getattr(cls, name)
            if not isinstance(value, int) or value <= 0:
                errors.append(f"{name} must be > 0, got {value}")
        
        if cls.MAX_NAME_LENGTH < 3:
            errors.append("MAX_NAME_LENGTH should be >= 3")
        
        return errors


_config_errors = StatsConfig.validate()
if _config_errors:
    logger.error("❌ StatsConfig validation failed: %s", "; ".join(_config_errors))


# ==================== МЕТРИКИ СО СБРОСОМ ====================

class StatsMetrics:
    """Метрики модуля статистики с поддержкой сброса."""
    
    stats_requests: int = 0
    stats_success: int = 0
    stats_errors: int = 0
    top_requests: int = 0
    top_success: int = 0
    top_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_cleanups: int = 0
    track_messages: int = 0
    track_errors: int = 0
    _last_reset: float = time.time()
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        total_cache = cls.cache_hits + cls.cache_misses
        return {
            "stats": {
                "requests": cls.stats_requests,
                "success": cls.stats_success,
                "errors": cls.stats_errors,
            },
            "top": {
                "requests": cls.top_requests,
                "success": cls.top_success,
                "errors": cls.top_errors,
            },
            "cache": {
                "hits": cls.cache_hits,
                "misses": cls.cache_misses,
                "hit_rate": round(cls.cache_hits / total_cache * 100, 1) if total_cache > 0 else 0,
                "cleanups": cls.cache_cleanups,
            },
            "track": {
                "messages": cls.track_messages,
                "errors": cls.track_errors,
            },
            "since_reset_seconds": round(time.time() - cls._last_reset, 1),
        }
    
    @classmethod
    def reset_counters(cls) -> None:
        """Сброс всех счётчиков метрик."""
        cls.stats_requests = 0
        cls.stats_success = 0
        cls.stats_errors = 0
        cls.top_requests = 0
        cls.top_success = 0
        cls.top_errors = 0
        cls.cache_hits = 0
        cls.cache_misses = 0
        cls.cache_cleanups = 0
        cls.track_messages = 0
        cls.track_errors = 0
        cls._last_reset = time.time()
        logger.info("✅ Stats metrics reset")


# ==================== ОПТИМИЗИРОВАННЫЙ LRU-КЭШ ====================

class OptimizedLRUCache:
    """LRU-кэш на OrderedDict с периодической очисткой."""
    
    def __init__(self, max_size: int = 100, ttl: int = 60, name: str = "cache") -> None:
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self._name = name
        self._last_cleanup = time.time()
        self._cleanup_interval = StatsConfig.CACHE_CLEANUP_INTERVAL
    
    def _cleanup_if_needed(self) -> None:
        """Периодическая очистка просроченных записей."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        expired = [
            k for k, (_, ts) in self._cache.items()
            if now - ts > self._ttl
        ]
        for k in expired:
            del self._cache[k]
        
        if expired:
            StatsMetrics.cache_cleanups += 1
            logger.debug(
                "🧹 Cache '%s' cleanup: removed %d expired, size: %d",
                self._name, len(expired), len(self._cache)
            )
        
        self._last_cleanup = now
    
    def get(self, key: str) -> Optional[Any]:
        """Получение из кэша с проверкой TTL."""
        self._cleanup_if_needed()
        
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                self._cache.move_to_end(key)
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Сохранение в кэш."""
        self._cleanup_if_needed()
        self._cache.pop(key, None)
        
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        
        self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Полная очистка кэша."""
        self._cache.clear()
    
    @property
    def size(self) -> int:
        return len(self._cache)


# Инициализация кэшей
_stats_cache = OptimizedLRUCache(
    max_size=StatsConfig.MAX_CACHE_SIZE,
    ttl=StatsConfig.CACHE_TTL_STATS,
    name="stats"
)
_top_cache = OptimizedLRUCache(
    max_size=20,
    ttl=StatsConfig.CACHE_TTL_TOP,
    name="top"
)


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

_metrics_log_task: Optional[asyncio.Task] = None
_shutdown_event: asyncio.Event = asyncio.Event()


async def _metrics_log_loop() -> None:
    """Периодическое логирование метрик."""
    while not _shutdown_event.is_set():
        try:
            # Ждём с проверкой shutdown каждую секунду
            for _ in range(StatsConfig.METRICS_LOG_INTERVAL):
                if _shutdown_event.is_set():
                    return
                await asyncio.sleep(1)
            
            metrics = StatsMetrics.to_dict()
            logger.info(
                "📊 Stats metrics: requests=%d, cache_hit_rate=%s%%, "
                "track_messages=%d, uptime=%ds",
                metrics["stats"]["requests"],
                metrics["cache"]["hit_rate"],
                metrics["track"]["messages"],
                metrics["since_reset_seconds"]
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("❌ Metrics log error: %s", e, exc_info=True)


async def start_metrics_logging() -> None:
    """Запуск логирования метрик."""
    global _metrics_log_task
    _shutdown_event.clear()
    if _metrics_log_task is None or _metrics_log_task.done():
        _metrics_log_task = asyncio.create_task(_metrics_log_loop())
        logger.info("✅ Stats metrics logging started")


async def stop_metrics_logging() -> None:
    """Остановка логирования метрик."""
    global _metrics_log_task
    _shutdown_event.set()
    if _metrics_log_task and not _metrics_log_task.done():
        _metrics_log_task.cancel()
        try:
            await _metrics_log_task
        except asyncio.CancelledError:
            pass
        _metrics_log_task = None
        logger.info("✅ Stats metrics logging stopped")


# ==================== ДЕКОРАТОРЫ ====================

def stats_callback(func):
    """Унифицированный декоратор для callback-обработчиков статистики."""
    @functools.wraps(func)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if not callback or not callback.message:
            if callback:
                await _safe_callback_answer(callback, "❌ Ошибка")
            return
        
        try:
            return await func(callback, *args, **kwargs)
        except asyncio.CancelledError:
            raise
        except DatabaseError as e:
            logger.error("❌ DB error in %s: %s", func.__name__, e, exc_info=True)
            await _safe_callback_answer(callback, "❌ Ошибка базы данных")
        except asyncio.TimeoutError:
            logger.error("⏱ Timeout in %s", func.__name__)
            await _safe_callback_answer(callback, "❌ Таймаут загрузки")
        except Exception as e:
            logger.error("❌ Error in %s: %s", func.__name__, e, exc_info=True)
            await _safe_callback_answer(callback, "❌ Ошибка")
    
    return wrapper


async def _safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = True) -> None:
    """Безопасный ответ на callback."""
    if callback is None:
        return
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except Exception:
        pass


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_number(num: Any) -> str:
    """Форматирование числа с разделителями."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return str(text) if text else ""


def format_date(date_str: Optional[str]) -> str:
    """Форматирование даты."""
    if not date_str:
        return "Неизвестно"
    try:
        s = str(date_str)
        if "T" in s:
            return s.split("T")[0]
        return s[:10] if len(s) >= 10 else s
    except Exception:
        return "Неизвестно"


def get_medal(position: Optional[int]) -> str:
    """Получение медали для позиции в топе."""
    if position is None:
        return "—"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(position, f"{position}.")


def safe_get(obj: Optional[Dict], key: str, default: Any = 0) -> Any:
    """Безопасное получение значения из словаря."""
    if obj is None:
        return default
    value = obj.get(key)
    if value is None:
        return default
    if isinstance(default, int) and isinstance(value, (int, float)):
        return max(0, int(value))
    return value


def escape_name(user: Optional[Dict]) -> str:
    """Форматирование имени пользователя с многоточием при обрезке."""
    if user is None:
        return "Пользователь"
    
    username = user.get("username")
    if username and str(username) != "None":
        return "@" + safe_html_escape(str(username))
    
    first_name = user.get("first_name")
    if first_name and str(first_name) != "None":
        name = str(first_name)
        if len(name) > StatsConfig.MAX_NAME_LENGTH:
            name = name[:StatsConfig.MAX_NAME_LENGTH - 1] + "…"
        return safe_html_escape(name)
    
    return "Пользователь"


async def get_full_user_stats(user_id: int) -> Optional[Dict[str, Any]]:
    """Получение полной статистики пользователя с кэшированием."""
    if user_id is None or db is None:
        return None
    
    cache_key = f"stats:{user_id}"
    cached = _stats_cache.get(cache_key)
    if cached is not None:
        StatsMetrics.cache_hits += 1
        return cached
    
    StatsMetrics.cache_misses += 1
    
    try:
        if hasattr(db, 'get_user_stats') and callable(db.get_user_stats):
            stats = await asyncio.wait_for(
                db.get_user_stats(user_id),
                timeout=StatsConfig.TIMEOUT_STATS
            )
            if stats:
                _stats_cache.set(cache_key, stats)
            return stats
    except asyncio.TimeoutError:
        logger.error(f"⏱ Timeout getting stats for user {user_id}")
    except DatabaseError as e:
        logger.error(f"❌ DB error getting user stats for {user_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting user stats: {e}", exc_info=True)
    
    return None


async def get_cached_top_users(order_by: str) -> List[Dict[str, Any]]:
    """Получение топа пользователей с кэшированием."""
    cache_key = f"top:{order_by}"
    cached = _top_cache.get(cache_key)
    if cached is not None:
        return cached
    
    try:
        if hasattr(db, 'get_top_users') and callable(db.get_top_users):
            top_users = await asyncio.wait_for(
                db.get_top_users(limit=StatsConfig.TOP_LIMIT, order_by=order_by),
                timeout=StatsConfig.TIMEOUT_TOP
            )
            if top_users:
                _top_cache.set(cache_key, top_users)
            return top_users or []
    except asyncio.TimeoutError:
        logger.error(f"⏱ Timeout getting top users for {order_by}")
    except DatabaseError as e:
        logger.error(f"❌ DB error getting top users: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting top users: {e}", exc_info=True)
    
    return []


async def _find_user_by_username(username: str) -> Optional[Dict]:
    """Безопасный поиск пользователя по username."""
    if db is None:
        return None
    try:
        if hasattr(db, 'get_user_by_username') and callable(db.get_user_by_username):
            return await db.get_user_by_username(username)
        else:
            user = await db._execute_with_retry(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
                (username,), fetch_one=True
            )
            return dict(user) if user else None
    except DatabaseError as e:
        logger.error(f"❌ Error finding user @{username}: {e}")
        return None


# ==================== ФОРМАТИРОВАНИЕ ====================

def format_user_stats(stats: Dict[str, Any]) -> str:
    """Форматирование персональной статистики пользователя."""
    first_name = safe_html_escape(str(stats.get("first_name") or "Пользователь"))
    register_date = format_date(stats.get("user_register_date"))
    days_active = safe_get(stats, "days_active", 0)
    
    games = safe_get(stats, "games_played", 0)
    wins = safe_get(stats, "wins", 0)
    losses = safe_get(stats, "losses", 0)
    draws = safe_get(stats, "draws", 0)
    wins_vs_bot = safe_get(stats, "wins_vs_bot", 0)
    max_win_streak = safe_get(stats, "max_win_streak", 0)
    winrate = (wins / games * 100) if games > 0 else 0
    
    media_count = (
        safe_get(stats, "total_photos", 0) +
        safe_get(stats, "total_videos", 0) +
        safe_get(stats, "total_gifs", 0)
    )
    
    lines = [
        "📊 <b>СТАТИСТИКА</b>",
        "",
        f"👤 <b>{first_name}</b>",
        f"📅 В боте с: {register_date} ({days_active} дней)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "💬 <b>АКТИВНОСТЬ:</b>",
        f"├ Всего сообщений: <b>{format_number(safe_get(stats, 'messages_total'))}</b>",
        f"├ Сегодня: <b>{format_number(safe_get(stats, 'messages_today'))}</b>",
        f"├ Голосовых: <b>{format_number(safe_get(stats, 'total_voice'))}</b>",
        f"├ Стикеров: <b>{format_number(safe_get(stats, 'total_stickers'))}</b>",
        f"└ Медиа: <b>{format_number(media_count)}</b>",
        "",
        "🔥 <b>СТРИК АКТИВНОСТИ:</b>",
        f"├ Дней активности: <b>{format_number(days_active)}</b>",
        f"├ Текущий стрик: <b>{format_number(safe_get(stats, 'current_streak'))} дней</b>",
        f"└ Макс. стрик: <b>{format_number(safe_get(stats, 'max_streak'))} дней</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>",
        f"├ Игр всего: <b>{format_number(games)}</b>",
        f"├ Побед: <b>{format_number(wins)}</b>",
        f"├ Поражений: <b>{format_number(losses)}</b>",
        f"├ Ничьих: <b>{format_number(draws)}</b>",
        f"├ Винрейт: <b>{round(winrate, 1)}%</b>",
        f"├ Побед над ботом: <b>{format_number(wins_vs_bot)}</b>",
        f"└ Макс. винстрик: <b>{format_number(max_win_streak)}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "💰 <b>ЭКОНОМИКА:</b>",
        f"├ Баланс: <b>{format_number(safe_get(stats, 'balance'))} NCoin</b>",
        f"├ Всего заработано: <b>{format_number(safe_get(stats, 'total_earned'))} NCoin</b>",
        f"├ Всего потрачено: <b>{format_number(safe_get(stats, 'total_spent'))} NCoin</b>",
        f"├ Daily бонусов: <b>{format_number(safe_get(stats, 'daily_claims'))} раз</b>",
        f"└ Daily стрик: <b>{format_number(safe_get(stats, 'daily_streak'))} дней</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "💎 <b>ДОНАТ:</b>",
        f"├ Задоначено: <b>{format_number(safe_get(stats, 'total_donated_rub'))} ₽</b>",
        f"└ Получено NCoin: <b>{format_number(safe_get(stats, 'total_donated_coins'))}</b>",
    ]
    
    return "\n".join(lines)


def format_top_list(
    title: str,
    users: List[Dict[str, Any]],
    value_key: str,
    suffix: str = "",
    extra_key: Optional[str] = None
) -> str:
    """
    Форматирование списка топа.
    
    Args:
        title: Заголовок
        users: Список пользователей
        value_key: Ключ для основного значения
        suffix: Суффикс (ед. измерения)
        extra_key: Дополнительный ключ (в скобках)
        
    Returns:
        Отформатированный HTML-текст
    """
    if not users:
        return f"📊 {title}\n\nПока нет данных!"
    
    lines = [title, "", "━━━━━━━━━━━━━━━━━━━━━", ""]
    
    for i, u in enumerate(users, 1):
        if u is None:
            continue
        
        medal = get_medal(i)
        name = escape_name(u)
        value = format_number(safe_get(u, value_key, 0))
        
        extra = ""
        if extra_key:
            extra_val = safe_get(u, extra_key, 0)
            if extra_val > 0:
                extra = f" ({format_number(extra_val)})"
        
        lines.append(f"{medal} <b>{name}</b> — {value}{suffix}{extra}")
    
    return "\n".join(lines)


# ==================== КЛАВИАТУРЫ ====================

def stats_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="stats_my")],
        [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def tops_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ТОП ПО СООБЩЕНИЯМ", callback_data="top_messages")],
        [InlineKeyboardButton(text="💰 ТОП ПО БАЛАНСУ", callback_data="top_balance")],
        [InlineKeyboardButton(text="🎮 ТОП ПО XO", callback_data="top_xo")],
        [InlineKeyboardButton(text="🔥 ТОП ПО АКТИВНОСТИ", callback_data="top_activity")],
        [InlineKeyboardButton(text="⭐ ТОП ПО XP", callback_data="top_xp")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
    ])


def back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])


# ==================== ОТОБРАЖЕНИЕ ====================

async def show_user_stats(
    target_id: int,
    target: Union[Message, CallbackQuery],
    is_callback: bool = False
) -> None:
    """Показать статистику пользователя."""
    StatsMetrics.stats_requests += 1
    
    try:
        stats = await get_full_user_stats(target_id)
        
        if not stats:
            text = "❌ <b>Пользователь не найден!</b>\n\nИспользуйте /start для регистрации."
            if is_callback:
                await target.message.edit_text(
                    text, parse_mode=ParseMode.HTML,
                    reply_markup=back_keyboard("stats_menu")
                )
            else:
                await target.answer(text, parse_mode=ParseMode.HTML)
            return
        
        StatsMetrics.stats_success += 1
        text = format_user_stats(stats)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
        ])
        
        if is_callback:
            await target.message.edit_text(
                text, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
            await target.answer()
        else:
            await target.answer(
                text, parse_mode=ParseMode.HTML,
                reply_markup=stats_menu_keyboard()
            )
    except asyncio.TimeoutError:
        StatsMetrics.stats_errors += 1
        error_text = "❌ Таймаут загрузки статистики."
        if is_callback:
            await target.message.edit_text(error_text, parse_mode=ParseMode.HTML)
            await target.answer("❌ Таймаут", show_alert=True)
        else:
            await target.answer(error_text, parse_mode=ParseMode.HTML)
    except DatabaseError as e:
        StatsMetrics.stats_errors += 1
        logger.error(f"❌ Database error in show_user_stats: {e}", exc_info=True)
        error_text = "❌ Ошибка базы данных."
        if is_callback:
            await target.message.edit_text(error_text, parse_mode=ParseMode.HTML)
            await target.answer("❌ Ошибка", show_alert=True)
        else:
            await target.answer(error_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        StatsMetrics.stats_errors += 1
        logger.error(f"❌ Unexpected error in show_user_stats: {e}", exc_info=True)
        if is_callback:
            await target.answer("❌ Ошибка", show_alert=True)
        else:
            await target.answer("❌ Произошла ошибка.", parse_mode=ParseMode.HTML)


async def show_top_list(
    callback: CallbackQuery,
    title: str,
    order_by: str,
    value_key: str,
    suffix: str = "",
    extra_key: Optional[str] = None
) -> None:
    """Показать топ-список."""
    StatsMetrics.top_requests += 1
    
    try:
        top_users = await get_cached_top_users(order_by)
        
        if not top_users:
            await callback.message.edit_text(
                f"📊 {title}\n\nПока нет данных!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        StatsMetrics.top_success += 1
        text = format_top_list(title, top_users, value_key, suffix, extra_key)
        
        # Добавляем результат пользователя если он авторизован
        if callback.from_user:
            user_stats = await get_full_user_stats(callback.from_user.id)
            if user_stats:
                user_value = safe_get(user_stats, value_key, 0)
                text += (
                    "\n\n━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 Ваш результат: <b>{format_number(user_value)}{suffix}</b>"
                )
        
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except asyncio.TimeoutError:
        StatsMetrics.top_errors += 1
        await _safe_callback_answer(callback, "❌ Таймаут загрузки")
    except asyncio.CancelledError:
        StatsMetrics.top_errors += 1
        raise
    except Exception as e:
        StatsMetrics.top_errors += 1
        logger.error(f"❌ Error in show_top_list: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка")


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Показать статистику пользователя (свою или чужую по @username)."""
    if not message or not message.from_user:
        return
    
    target_id = message.from_user.id
    
    if message.text:
        args = message.text.strip().split()
        if len(args) > 1 and args[1].startswith('@'):
            username = args[1].lstrip('@')
            if username:
                target = await _find_user_by_username(username)
                if target:
                    target_id = target.get("user_id", target_id)
    
    await show_user_stats(target_id, message)


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    """Показать меню топов."""
    if not message:
        return
    await message.answer(
        "🏆 <b>ТОПЫ NEXUS</b>\n\nВыберите категорию:",
        parse_mode=ParseMode.HTML,
        reply_markup=tops_menu_keyboard()
    )


# ==================== CALLBACK: МЕНЮ ====================

@router.callback_query(F.data == "stats_menu")
@router.callback_query(F.data == "menu_stats")
@stats_callback
async def stats_menu_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📊 <b>СТАТИСТИКА</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=stats_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "stats_my")
@stats_callback
async def stats_my_callback(callback: CallbackQuery) -> None:
    await show_user_stats(callback.from_user.id, callback, is_callback=True)


@router.callback_query(F.data == "stats_tops")
@stats_callback
async def stats_tops_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🏆 <b>ТОПЫ NEXUS</b>\n\nВыберите категорию:",
        parse_mode=ParseMode.HTML,
        reply_markup=tops_menu_keyboard()
    )
    await callback.answer()


# ==================== CALLBACK: ТОПЫ ====================

@router.callback_query(F.data == "top_messages")
@stats_callback
async def top_messages_callback(callback: CallbackQuery) -> None:
    await show_top_list(
        callback,
        f"💬 <b>ТОП-{StatsConfig.TOP_LIMIT} ПО СООБЩЕНИЯМ</b>",
        order_by="messages",
        value_key="messages_total",
        suffix=" сообщ."
    )


@router.callback_query(F.data == "top_balance")
@stats_callback
async def top_balance_callback(callback: CallbackQuery) -> None:
    await show_top_list(
        callback,
        f"💰 <b>ТОП-{StatsConfig.TOP_LIMIT} ПО БАЛАНСУ</b>",
        order_by="balance",
        value_key="balance",
        suffix=" NCoin"
    )


@router.callback_query(F.data == "top_xo")
@stats_callback
async def top_xo_callback(callback: CallbackQuery) -> None:
    await show_top_list(
        callback,
        f"🎮 <b>ТОП-{StatsConfig.TOP_LIMIT} ПО XO</b>",
        order_by="wins",
        value_key="wins",
        suffix=" побед",
        extra_key="games_played"
    )


@router.callback_query(F.data == "top_activity")
@stats_callback
async def top_activity_callback(callback: CallbackQuery) -> None:
    await show_top_list(
        callback,
        f"🔥 <b>ТОП-{StatsConfig.TOP_LIMIT} ПО АКТИВНОСТИ</b>",
        order_by="activity",
        value_key="days_active",
        suffix=" дней"
    )


@router.callback_query(F.data == "top_xp")
@stats_callback
async def top_xp_callback(callback: CallbackQuery) -> None:
    await show_top_list(
        callback,
        f"⭐ <b>ТОП-{StatsConfig.TOP_LIMIT} ПО XP</b>",
        order_by="xp",
        value_key="xp",
        suffix=" XP"
    )


# ==================== ИНТЕГРАЦИОННЫЕ ФУНКЦИИ ====================

async def track_message(user_id: int, message: Message) -> None:
    """
    Отслеживание сообщения для статистики.
    Вызывается из bot.py через save_all_messages.
    """
    if user_id is None or message is None or message.chat is None:
        return
    
    chat_id = message.chat.id
    
    try:
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
        StatsMetrics.track_messages += 1
    except DatabaseError as e:
        StatsMetrics.track_errors += 1
        logger.error(f"❌ Database error tracking activity: {e}", exc_info=True)
    except Exception as e:
        StatsMetrics.track_errors += 1
        logger.error(f"❌ Unexpected error tracking activity: {e}", exc_info=True)


async def track_xo_game(
    user_id: int, result_type: str, bet: int = 0, won: int = 0
) -> None:
    """
    Отслеживание игры в крестики-нолики.
    Вызывается из handlers/tictactoe.py.
    """
    if user_id is None:
        return
    if isinstance(user_id, str) and user_id == StatsConfig.BOT_USER_ID:
        return
    
    try:
        if hasattr(db, 'update_xo_stats') and callable(db.update_xo_stats):
            await db.update_xo_stats(user_id, result_type, bet or 0, won or 0)
    except DatabaseError as e:
        logger.error(f"❌ Database error tracking XO game: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"❌ Unexpected error tracking XO game: {e}", exc_info=True)
