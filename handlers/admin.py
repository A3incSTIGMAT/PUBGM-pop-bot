#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/admin.py
# ВЕРСИЯ: 3.6.0-production (все критические и средние ошибки исправлены)
# ОПИСАНИЕ: Админ-панель — полный аудит и исправление всех проблем
# ============================================
# ИСПРАВЛЕНИЯ v3.6.0:
#   🔴 Импорты перенесены внутрь try-блоков (строки 507, 635, 665)
#   🟡 validate_chat_id теперь пропускает отрицательные ID супергрупп
#   🟡 asyncio.gather с return_exceptions=True для изоляции сбоев
#   🟡 Добавлен callback для мониторинга фоновых задач
#   🟡 Исправлена обработка пустых SUPER_ADMIN_IDS
#   🟢 Добавлены docstrings с примерами
#   🟢 Улучшено логирование фоновых задач
# ============================================

import asyncio
import functools
import html
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Any, List, Dict, Tuple, Callable, Awaitable

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramAPIError

from database import db, DatabaseError
from config import SUPER_ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)


# ==================== КОНФИГУРАЦИЯ С ВАЛИДАЦИЕЙ ====================

class AdminConfig:
    """
    Конфигурация админ-панели.
    
    Все таймауты и лимиты вынесены в этот класс для удобной настройки.
    При старте вызывается validate() для проверки корректности значений.
    Поддерживает загрузку из переменных окружения (приоритет над значениями по умолчанию).
    
    Пример использования:
        >>> AdminConfig.validate()
        []
        >>> AdminConfig.TIMEOUT_STATS
        10.0
    """
    
    # Загрузка из переменных окружения с fallback-значениями
    TIMEOUT_STATS = float(os.getenv("ADMIN_TIMEOUT_STATS", "10.0"))
    TIMEOUT_CLEANUP = float(os.getenv("ADMIN_TIMEOUT_CLEANUP", "30.0"))
    TIMEOUT_CHAT_INFO = float(os.getenv("ADMIN_TIMEOUT_CHAT_INFO", "5.0"))
    TIMEOUT_GLOBAL_CLEANUP = float(os.getenv("ADMIN_TIMEOUT_GLOBAL_CLEANUP", "60.0"))
    TIMEOUT_DEFAULT = float(os.getenv("ADMIN_TIMEOUT_DEFAULT", "15.0"))
    
    MAX_CHATS_DISPLAY = int(os.getenv("ADMIN_MAX_CHATS_DISPLAY", "20"))
    MAX_CONCURRENT_CHATS = int(os.getenv("ADMIN_MAX_CONCURRENT_CHATS", "5"))
    TOP_USERS_LIMIT = int(os.getenv("ADMIN_TOP_USERS_LIMIT", "10"))
    TOP_WORDS_LIMIT = int(os.getenv("ADMIN_TOP_WORDS_LIMIT", "15"))
    
    OWNER_ID = int(os.getenv("OWNER_ID", "895844198"))
    LOG_SENSITIVE_DATA = os.getenv("ADMIN_LOG_SENSITIVE_DATA", "false").lower() == "true"
    
    @classmethod
    def validate(cls) -> List[str]:
        """
        Валидация конфигурации при старте.
        
        Returns:
            Список ошибок (пустой если всё корректно)
            
        Пример:
            >>> errors = AdminConfig.validate()
            >>> if errors: print("; ".join(errors))
        """
        errors = []
        
        # Проверка таймаутов
        for name in ['TIMEOUT_STATS', 'TIMEOUT_CLEANUP', 'TIMEOUT_CHAT_INFO',
                      'TIMEOUT_GLOBAL_CLEANUP', 'TIMEOUT_DEFAULT']:
            value = getattr(cls, name)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"{name} must be > 0, got {value}")
        
        # Проверка лимитов
        for name in ['MAX_CHATS_DISPLAY', 'MAX_CONCURRENT_CHATS',
                      'TOP_USERS_LIMIT', 'TOP_WORDS_LIMIT']:
            value = getattr(cls, name)
            if not isinstance(value, int) or value <= 0:
                errors.append(f"{name} must be > 0, got {value}")
        
        # Проверка ID владельца
        if not isinstance(cls.OWNER_ID, int) or cls.OWNER_ID <= 0:
            errors.append(f"OWNER_ID must be a positive integer, got {cls.OWNER_ID}")
        
        # Проверка SUPER_ADMIN_IDS
        if SUPER_ADMIN_IDS is None:
            errors.append("SUPER_ADMIN_IDS is None — check config.py")
        elif not isinstance(SUPER_ADMIN_IDS, (list, tuple, set)):
            errors.append(f"SUPER_ADMIN_IDS must be a list, got {type(SUPER_ADMIN_IDS).__name__}")
        
        return errors


# Валидация при импорте
_config_errors = AdminConfig.validate()
if _config_errors:
    logger.error("❌ AdminConfig validation failed: %s", "; ".join(_config_errors))
else:
    logger.info("✅ AdminConfig validated successfully")


# ==================== CALLBACK-КОНСТАНТЫ ====================

class CB_:
    """Callback data константы для защиты от опечаток."""
    MENU_ADMIN = "menu_admin"
    STATS = "admin_stats"
    CLEANUP = "admin_cleanup"
    SUMMARY = "admin_summary"
    CHATS = "admin_chats"
    RELOAD = "admin_reload"
    BACK = "admin_back"
    CLOSE = "admin_close"
    CLEANUP_ALL = "admin_cleanup_all"


# ==================== МЕТРИКИ ====================

class AdminMetrics:
    """
    Счётчики операций для мониторинга.
    
    Метрики живут в памяти и обнуляются при рестарте.
    Для продакшн-мониторинга рекомендуется сохранять в БД или Prometheus.
    
    Пример:
        >>> AdminMetrics.stats_requests += 1
        >>> AdminMetrics.to_dict()['stats']['requests']
        1
    """
    
    stats_requests: int = 0
    stats_success: int = 0
    stats_errors: int = 0
    cleanup_requests: int = 0
    cleanup_success: int = 0
    cleanup_errors: int = 0
    summary_requests: int = 0
    summary_success: int = 0
    summary_errors: int = 0
    chats_requests: int = 0
    chats_success: int = 0
    chats_errors: int = 0
    reload_requests: int = 0
    reload_success: int = 0
    reload_errors: int = 0
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Экспорт метрик в словарь для health-check."""
        return {
            "stats": {
                "requests": cls.stats_requests,
                "success": cls.stats_success,
                "errors": cls.stats_errors,
            },
            "cleanup": {
                "requests": cls.cleanup_requests,
                "success": cls.cleanup_success,
                "errors": cls.cleanup_errors,
            },
            "summary": {
                "requests": cls.summary_requests,
                "success": cls.summary_success,
                "errors": cls.summary_errors,
            },
            "chats": {
                "requests": cls.chats_requests,
                "success": cls.chats_success,
                "errors": cls.chats_errors,
            },
            "reload": {
                "requests": cls.reload_requests,
                "success": cls.reload_success,
                "errors": cls.reload_errors,
            },
        }
    
    @classmethod
    def reset(cls) -> None:
        """Сброс всех метрик."""
        for attr in dir(cls):
            if attr.endswith('_requests') or attr.endswith('_success') or attr.endswith('_errors'):
                setattr(cls, attr, 0)


# ==================== СОСТОЯНИЕ МОДУЛЯ ====================

class AdminState:
    """
    Инкапсуляция глобального состояния модуля.
    
    Хранит экземпляр бота и управляет фоновыми задачами.
    Потокобезопасность обеспечивается выполнением в одном event loop.
    
    Пример:
        >>> AdminState.set_bot(bot_instance)
        >>> AdminState.is_ready()
        True
    """
    
    _bot: Optional[Bot] = None
    _background_tasks: set[asyncio.Task] = set()
    _tasks_lock: asyncio.Lock = asyncio.Lock()
    _initialized: bool = False
    
    @classmethod
    async def set_bot(cls, bot_instance: Bot) -> None:
        """Установка экземпляра бота."""
        cls._bot = bot_instance
        cls._initialized = True
        logger.info("✅ Bot instance set in admin module")
    
    @classmethod
    def get_bot(cls) -> Optional[Bot]:
        """Получение экземпляра бота."""
        return cls._bot
    
    @classmethod
    def is_ready(cls) -> bool:
        """Проверка готовности модуля."""
        return cls._initialized and cls._bot is not None
    
    @classmethod
    async def add_task(cls, task: asyncio.Task) -> None:
        """
        Добавление фоновой задачи с автоматической очисткой.
        
        Задача автоматически удаляется из списка при завершении.
        
        Args:
            task: Асинхронная задача для выполнения в фоне
        """
        async with cls._tasks_lock:
            cls._background_tasks.add(task)
        
        def _on_done(t: asyncio.Task) -> None:
            cls._background_tasks.discard(t)
            if t.exception():
                logger.error("❌ Background task failed: %s", t.exception(), exc_info=True)
            else:
                logger.debug("✅ Background task completed")
        
        task.add_done_callback(_on_done)
    
    @classmethod
    async def cleanup_tasks(cls) -> None:
        """
        Корректное завершение всех фоновых задач.
        
        Вызывать при остановке бота.
        Отменяет все незавершённые задачи с таймаутом 5 секунд.
        """
        async with cls._tasks_lock:
            tasks = list(cls._background_tasks)
            cls._background_tasks.clear()
        
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        
        logger.info("✅ Admin background tasks cleaned up (%d tasks)", len(tasks))


# Публичные функции для внешнего использования
def set_bot(bot_instance: Bot) -> None:
    """Установка экземпляра бота (синхронная обёртка)."""
    asyncio.create_task(AdminState.set_bot(bot_instance))


async def cleanup_background_tasks() -> None:
    """Очистка фоновых задач при остановке."""
    await AdminState.cleanup_tasks()


# ==================== ДЕКОРАТОРЫ ====================

def require_admin(func):
    """
    Декоратор проверки прав супер-админа в callback'ах.
    
    Если пользователь не супер-админ — callback.answer с ошибкой
    и функция не вызывается.
    
    Пример:
        @router.callback_query(F.data == CB_.STATS)
        @require_admin
        async def admin_stats_callback(callback: CallbackQuery) -> None:
            ...
    """
    @functools.wraps(func)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if not await _check_callback_access(callback):
            return
        try:
            return await func(callback, *args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("❌ Error in %s: %s", func.__name__, e, exc_info=True)
            await callback.answer("❌ Внутренняя ошибка", show_alert=True)
    return wrapper


# ==================== ПРОВЕРКА ПРАВ ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    """
    Проверка, является ли пользователь супер-админом.
    
    Супер-админы: владелец (OWNER_ID) + все из SUPER_ADMIN_IDS.
    
    Args:
        user_id: ID пользователя для проверки
        
    Returns:
        True если пользователь супер-админ
        
    Пример:
        >>> is_super_admin(895844198)
        True
        >>> is_super_admin(None)
        False
    """
    if user_id is None:
        return False
    if user_id == AdminConfig.OWNER_ID:
        return True
    # Безопасная проверка SUPER_ADMIN_IDS (может быть None)
    admin_ids = SUPER_ADMIN_IDS or []
    return user_id in admin_ids


async def _check_callback_access(callback: CallbackQuery) -> bool:
    """Проверка прав для callback_query."""
    if not callback or not callback.from_user:
        if callback:
            try:
                await callback.answer("❌ Ошибка доступа", show_alert=True)
            except Exception:
                pass
        return False
    return _check_user_access(callback.from_user.id, callback)


async def _check_message_access(message: Message) -> bool:
    """Проверка прав для message."""
    if not message or not message.from_user:
        return False
    return _check_user_access(message.from_user.id, message)


def _check_user_access(user_id: int, event: Any) -> bool:
    """
    Проверка прав и отправка уведомления при отказе.
    
    Args:
        user_id: ID пользователя
        event: Объект события (Message или CallbackQuery)
        
    Returns:
        True если доступ разрешён
    """
    if not is_super_admin(user_id):
        logger.warning(
            "⚠️ Unauthorized admin access attempt by user_id=%s",
            user_id if AdminConfig.LOG_SENSITIVE_DATA else "***"
        )
        if hasattr(event, 'answer'):
            asyncio.create_task(
                event.answer("❌ Доступ запрещён", show_alert=True)
            )
        return False
    return True


# ==================== БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ ====================

def validate_chat_id(chat_id: Any) -> int:
    """
    Валидация chat_id.
    
    Принимает положительные и отрицательные значения (супергруппы: -100xxx).
    Отклоняет: None, 0, нечисловые строки.
    
    Args:
        chat_id: Значение для проверки
        
    Returns:
        Валидированный chat_id как int
        
    Raises:
        ValueError: при невалидном chat_id
        
    Пример:
        >>> validate_chat_id(-1001234567890)
        -1001234567890
        >>> validate_chat_id(123456)
        123456
        >>> validate_chat_id(0)
        ValueError: chat_id must not be zero
        >>> validate_chat_id(None)
        ValueError: chat_id is required
    """
    if chat_id is None:
        raise ValueError("chat_id is required")
    try:
        result = int(chat_id)
        if result == 0:
            raise ValueError("chat_id must not be zero (Telegram IDs are never 0)")
        return result
    except (ValueError, TypeError) as e:
        if isinstance(e, ValueError) and "chat_id" in str(e):
            raise
        raise ValueError(f"chat_id must be a valid integer, got {type(chat_id).__name__}: {chat_id}")


def safe_html(text: Optional[str]) -> str:
    """
    Безопасное HTML-экранирование.
    
    Args:
        text: Строка для экранирования
        
    Returns:
        Экранированная строка (пустая если text is None)
        
    Пример:
        >>> safe_html("<b>text</b>")
        '&lt;b&gt;text&lt;/b&gt;'
        >>> safe_html(None)
        ''
    """
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception as e:
        logger.warning("⚠️ HTML escape failed: %s", e)
        return str(text) if isinstance(text, str) else ""


def _safe_str(value: Any) -> str:
    """
    Безопасное преобразование в строку.
    
    Args:
        value: Любое значение
        
    Returns:
        Строковое представление или "?" при ошибке
        
    Пример:
        >>> _safe_str(123)
        '123'
        >>> _safe_str(None)
        '0'
    """
    if value is None:
        return "0"
    try:
        return str(value)
    except Exception:
        return "?"


def _mask_sensitive_id(value: Any) -> str:
    """
    Маскировка чувствительных ID в логах.
    
    Args:
        value: Значение для маскировки
        
    Returns:
        "***" если логирование чувствительных данных отключено, иначе str(value)
    """
    if not AdminConfig.LOG_SENSITIVE_DATA:
        return "***"
    return str(value)


# ==================== ПРОВЕРКИ ГОТОВНОСТИ ====================

def _is_db_ready() -> bool:
    """Проверка готовности базы данных."""
    return db is not None and getattr(db, '_initialized', False)


# ==================== СЛОЙ ДАННЫХ (БД) ====================

async def fetch_total_users() -> int:
    """
    Получение общего количества пользователей.
    
    Returns:
        Количество пользователей или 0 при ошибке
        
    Пример:
        >>> total = await fetch_total_users()
        >>> print(f"Users: {total}")
    """
    if not _is_db_ready():
        logger.warning("DB not available for fetch_total_users")
        return 0
    try:
        row = await db._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM users", fetch_one=True
        )
        return row.get("cnt", 0) if row else 0
    except DatabaseError as e:
        logger.error("DB error in fetch_total_users: %s", e)
        return 0
    except Exception as e:
        logger.error("Unexpected error in fetch_total_users: %s", e, exc_info=True)
        return 0


async def fetch_total_messages() -> int:
    """
    Получение общего количества сообщений.
    
    Returns:
        Количество сообщений или 0 при ошибке
    """
    if not _is_db_ready():
        logger.warning("DB not available for fetch_total_messages")
        return 0
    try:
        row = await db._execute_with_retry(
            "SELECT COALESCE(SUM(messages_total), 0) as cnt FROM user_stats",
            fetch_one=True
        )
        return row.get("cnt", 0) if row else 0
    except DatabaseError as e:
        logger.error("DB error in fetch_total_messages: %s", e)
        return 0
    except Exception as e:
        logger.error("Unexpected error in fetch_total_messages: %s", e, exc_info=True)
        return 0


async def fetch_all_chat_ids(limit: int = 100) -> List[int]:
    """
    Получение списка всех чатов с ботом.
    
    Args:
        limit: Максимальное количество чатов
        
    Returns:
        Список chat_id (может содержать отрицательные для супергрупп)
        
    Пример:
        >>> chats = await fetch_all_chat_ids(limit=20)
        >>> len(chats)
        15
    """
    if not _is_db_ready():
        logger.warning("DB not available for fetch_all_chat_ids")
        return []
    try:
        rows = await db._execute_with_retry(
            "SELECT DISTINCT chat_id FROM user_activity_log "
            "ORDER BY chat_id DESC LIMIT ?",
            (limit,), fetch_all=True
        )
        return [row["chat_id"] for row in rows] if rows else []
    except DatabaseError as e:
        logger.error("DB error in fetch_all_chat_ids: %s", e)
        return []
    except Exception as e:
        logger.error("Unexpected error in fetch_all_chat_ids: %s", e, exc_info=True)
        return []


async def fetch_chat_daily_stats(
    chat_id: int, date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получение дневной статистики чата.
    
    Args:
        chat_id: ID чата (может быть отрицательным для супергрупп)
        date: Дата в формате YYYY-MM-DD (по умолчанию — сегодня)
        
    Returns:
        Словарь со статистикой или пустой словарь при ошибке
        
    Пример:
        >>> stats = await fetch_chat_daily_stats(-1001234567890)
        >>> stats.get('total_messages', 0)
        42
    """
    if not _is_db_ready():
        logger.warning("DB not available for fetch_chat_daily_stats")
        return {}
    try:
        chat_id = validate_chat_id(chat_id)
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        row = await db._execute_with_retry(
            "SELECT "
            "COALESCE(SUM(messages), 0) AS total_messages, "
            "COUNT(DISTINCT user_id) AS unique_users, "
            "COALESCE(SUM(voice), 0) AS total_voice, "
            "COALESCE(SUM(stickers), 0) AS total_stickers, "
            "COALESCE(SUM(gifs), 0) AS total_gifs, "
            "COALESCE(SUM(photos), 0) AS total_photos, "
            "COALESCE(SUM(videos), 0) AS total_videos, "
            "COALESCE(SUM(xo_games), 0) AS total_xo_games "
            "FROM user_activity_log "
            "WHERE chat_id = ? AND date = ?",
            (chat_id, date), fetch_one=True
        )
        return dict(row) if row else {}
    except DatabaseError as e:
        logger.error("DB error in fetch_chat_daily_stats: %s", e)
        return {}
    except ValueError as e:
        logger.error("Validation error in fetch_chat_daily_stats: %s", e)
        return {}
    except Exception as e:
        logger.error("Unexpected error in fetch_chat_daily_stats: %s", e, exc_info=True)
        return {}


async def fetch_chat_active_users(
    chat_id: int, limit: int = 10, date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Получение активных пользователей чата.
    
    Args:
        chat_id: ID чата
        limit: Максимальное количество пользователей
        date: Дата в формате YYYY-MM-DD (по умолчанию — сегодня)
        
    Returns:
        Список словарей с данными пользователей
        
    Пример:
        >>> users = await fetch_chat_active_users(-1001234567890, limit=5)
        >>> users[0]['first_name']
        'Alice'
    """
    if not _is_db_ready():
        logger.warning("DB not available for fetch_chat_active_users")
        return []
    try:
        chat_id = validate_chat_id(chat_id)
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        rows = await db._execute_with_retry(
            "SELECT ual.user_id, u.first_name, u.username, "
            "SUM(ual.messages) AS message_count "
            "FROM user_activity_log ual "
            "LEFT JOIN users u ON ual.user_id = u.user_id "
            "WHERE ual.chat_id = ? AND ual.date = ? "
            "GROUP BY ual.user_id "
            "ORDER BY message_count DESC LIMIT ?",
            (chat_id, date, limit), fetch_all=True
        )
        return [dict(r) for r in rows] if rows else []
    except DatabaseError as e:
        logger.error("DB error in fetch_chat_active_users: %s", e)
        return []
    except ValueError as e:
        logger.error("Validation error in fetch_chat_active_users: %s", e)
        return []
    except Exception as e:
        logger.error("Unexpected error in fetch_chat_active_users: %s", e, exc_info=True)
        return []


async def fetch_chat_top_words(
    chat_id: int, limit: int = 15, date: Optional[str] = None
) -> List[Tuple[str, int]]:
    """
    Получение топ-слов чата.
    
    Args:
        chat_id: ID чата
        limit: Максимальное количество слов
        date: Дата в формате YYYY-MM-DD (по умолчанию — сегодня)
        
    Returns:
        Список кортежей (слово, количество)
        
    Пример:
        >>> words = await fetch_chat_top_words(-1001234567890, limit=5)
        >>> words[0]
        ('привет', 42)
    """
    if not _is_db_ready():
        logger.warning("DB not available for fetch_chat_top_words")
        return []
    try:
        chat_id = validate_chat_id(chat_id)
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        rows = await db._execute_with_retry(
            "SELECT word, count FROM chat_word_stats "
            "WHERE chat_id = ? AND date = ? "
            "ORDER BY count DESC LIMIT ?",
            (chat_id, date, limit), fetch_all=True
        )
        return [(r["word"], r["count"]) for r in rows] if rows else []
    except DatabaseError as e:
        logger.error("DB error in fetch_chat_top_words: %s", e)
        return []
    except ValueError as e:
        logger.error("Validation error in fetch_chat_top_words: %s", e)
        return []
    except Exception as e:
        logger.error("Unexpected error in fetch_chat_top_words: %s", e, exc_info=True)
        return []


# ==================== СЛОЙ ФОРМАТИРОВАНИЯ ====================

def format_stats_text(
    stats: Dict[str, Any],
    active_users: List[Dict[str, Any]],
    top_words: List[Tuple[str, int]],
    total_users: int,
    total_messages: int
) -> str:
    """
    Форматирование расширенной статистики чата.
    
    Args:
        stats: Статистика за день
        active_users: Список активных пользователей
        top_words: Список топ-слов
        total_users: Всего пользователей
        total_messages: Всего сообщений
        
    Returns:
        HTML-строка со статистикой
    """
    text = (
        "📊 <b>РАСШИРЕННАЯ СТАТИСТИКА ЧАТА</b>\n\n"
        "📅 <b>ЗА СЕГОДНЯ:</b>\n"
        f"💬 Сообщений: <b>{_safe_str(stats.get('total_messages'))}</b>\n"
        f"👥 Уникальных: <b>{_safe_str(stats.get('unique_users'))}</b>\n"
        f"🎤 Войс: <b>{_safe_str(stats.get('total_voice'))}</b>\n"
        f"🎮 XO игр: <b>{_safe_str(stats.get('total_xo_games'))}</b>\n\n"
        "📈 <b>ВСЕГО В БОТЕ:</b>\n"
        f"👤 Пользователей: <b>{_safe_str(total_users)}</b>\n"
        f"💬 Сообщений: <b>{_safe_str(total_messages)}</b>\n"
    )
    
    if active_users:
        text += f"\n<b>🏆 ТОП-{len(active_users)} АКТИВНЫХ:</b>\n"
        for i, u in enumerate(active_users, 1):
            name = safe_html(str(u.get('first_name', '?')))[:20]
            msgs = _safe_str(u.get('message_count'))
            text += f"{i}. {name} — <b>{msgs}</b>\n"
    
    if top_words:
        text += f"\n<b>📝 ТОП-{len(top_words)} СЛОВ:</b>\n"
        for word, count in top_words:
            text += f"• {safe_html(str(word))} — {_safe_str(count)}\n"
    
    return text


def format_summary_text(
    stats: Dict[str, Any],
    active_users: List[Dict[str, Any]],
    top_words: List[Tuple[str, int]]
) -> str:
    """
    Форматирование сводки дня.
    
    Args:
        stats: Статистика за день
        active_users: Топ-5 активных пользователей
        top_words: Топ-10 слов
        
    Returns:
        HTML-строка со сводкой
    """
    today = datetime.now().strftime("%d.%m.%Y")
    
    text = (
        f"🌅 <b>СВОДКА ДНЯ — {today}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 Сообщений: <b>{_safe_str(stats.get('total_messages'))}</b>\n"
        f"👥 Активных: <b>{_safe_str(stats.get('unique_users'))}</b>\n"
        f"🎤 Войс: <b>{_safe_str(stats.get('total_voice'))}</b>\n"
        f"🎮 Игр XO: <b>{_safe_str(stats.get('total_xo_games'))}</b>\n"
    )
    
    if active_users:
        text += "\n<b>🏆 ТОП-5 АКТИВНЫХ:</b>\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, u in enumerate(active_users[:5]):
            name = safe_html(str(u.get('first_name', '?')))[:15]
            msgs = _safe_str(u.get('message_count'))
            medal = medals[i] if i < len(medals) else '•'
            text += f"{medal} {name} — <b>{msgs}</b> сообщ.\n"
    
    if top_words:
        text += "\n<b>📝 ТОП-10 СЛОВ:</b>\n"
        for word, count in top_words[:10]:
            text += f"• {safe_html(str(word))} — {_safe_str(count)}\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━━\n<i>Авто-сводка NEXUS Bot</i>"
    return text


def format_admin_panel_text(
    user_id: int, first_name: Optional[str], chat_id: int
) -> str:
    """
    Форматирование текста админ-панели.
    
    Args:
        user_id: ID пользователя
        first_name: Имя пользователя
        chat_id: ID чата
        
    Returns:
        HTML-строка админ-панели
    """
    is_owner = is_super_admin(user_id)
    owner_status = "👑 Владелец" if is_owner else "🔐 Админ"
    
    return (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v3.6.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Админ: <b>{safe_html(first_name)}</b>\n"
        f"🆔 Ваш ID: <code>{_safe_str(user_id)}</code>\n"
        f"🔑 Статус: <b>{owner_status}</b>\n"
        f"💬 Чат: <code>{_safe_str(chat_id)}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )


def format_chats_list_text(display_chats: List[str], total: int) -> str:
    """
    Форматирование списка чатов.
    
    Args:
        display_chats: Список строк с информацией о чатах
        total: Общее количество чатов
        
    Returns:
        HTML-строка со списком чатов
    """
    text = (
        f"📋 <b>ЧАТЫ С БОТОМ</b>\n\nВсего: <b>{_safe_str(total)}</b>\n\n"
    )
    text += "\n".join(display_chats)
    
    if total > AdminConfig.MAX_CHATS_DISPLAY:
        remaining = total - AdminConfig.MAX_CHATS_DISPLAY
        text += f"\n\n... и ещё <b>{_safe_str(remaining)}</b> чатов"
    
    return text


# ==================== СЛОЙ ОТОБРАЖЕНИЯ (КЛАВИАТУРЫ) ====================

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data=CB_.STATS)],
        [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ЧАТ", callback_data=CB_.CLEANUP)],
        [InlineKeyboardButton(text="🌅 СВОДКА ДНЯ", callback_data=CB_.SUMMARY)],
        [InlineKeyboardButton(text="📋 ВСЕ ЧАТЫ", callback_data=CB_.CHATS)],
        [InlineKeyboardButton(text="🔄 ПЕРЕЗАГРУЗКА РП", callback_data=CB_.RELOAD)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_.BACK),
         InlineKeyboardButton(text="❌ ЗАКРЫТЬ", callback_data=CB_.CLOSE)],
    ])


def get_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для страницы статистики."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=CB_.STATS)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_.BACK)],
    ])


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой НАЗАД."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_.BACK)]
    ])


def get_chats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для страницы списка чатов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ВСЕ ЧАТЫ", callback_data=CB_.CLEANUP_ALL)],
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=CB_.CHATS)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_.BACK)],
    ])


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def safe_edit_or_reply(
    callback: CallbackQuery,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """
    Безопасное редактирование сообщения с fallback на новое.
    
    Args:
        callback: CallbackQuery от пользователя
        text: Текст для отправки
        markup: Клавиатура
        
    Returns:
        True при успехе, False при ошибке
    """
    if not callback or not callback.message:
        return False
    
    try:
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML, reply_markup=markup
        )
        return True
    except TelegramBadRequest as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            return True
        if "message can't be edited" in err_str:
            try:
                await callback.message.answer(
                    text, parse_mode=ParseMode.HTML, reply_markup=markup
                )
                return True
            except TelegramAPIError:
                return False
        logger.warning("Edit error: %s", e)
        return False
    except TelegramForbiddenError:
        logger.warning(
            "Forbidden to edit message in chat %s",
            _mask_sensitive_id(callback.message.chat.id)
        )
        return False
    except TelegramAPIError as e:
        logger.error("Telegram API error in edit: %s", e)
        return False
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("Unexpected error in safe_edit_or_reply: %s", e, exc_info=True)
        return False


async def fetch_chat_info_async(cid: int, sem: asyncio.Semaphore) -> str:
    """
    Безопасное получение информации о чате.
    
    Args:
        cid: ID чата
        sem: Семафор для ограничения конкурентности
        
    Returns:
        Строка с информацией о чате для отображения в списке
        
    Пример:
        >>> sem = asyncio.Semaphore(5)
        >>> info = await fetch_chat_info_async(-1001234567890, sem)
        >>> print(info)
        '• <code>-1001234567890</code> — Название Чата'
    """
    async with sem:
        try:
            bot = AdminState.get_bot()
            if bot is None:
                return f"• <code>{_safe_str(cid)}</code> — (бот не инициализирован)"
            
            chat = await asyncio.wait_for(
                bot.get_chat(cid),
                timeout=AdminConfig.TIMEOUT_CHAT_INFO
            )
            
            if chat is None:
                return f"• <code>{_safe_str(cid)}</code> — (нет данных)"
            
            name = safe_html(str(chat.title)[:30] if chat.title else "Чат")
            return f"• <code>{_safe_str(cid)}</code> — {name}"
            
        except asyncio.TimeoutError:
            return f"• <code>{_safe_str(cid)}</code> — (таймаут)"
        except asyncio.CancelledError:
            raise
        except TelegramForbiddenError as e:
            err_str = str(e).lower()
            if "bot was kicked" in err_str or "bot is not a member" in err_str:
                return f"• <code>{_safe_str(cid)}</code> — (бот исключён из чата)"
            elif "not enough rights" in err_str:
                return f"• <code>{_safe_str(cid)}</code> — (недостаточно прав)"
            else:
                return f"• <code>{_safe_str(cid)}</code> — (доступ запрещён)"
        except TelegramBadRequest as e:
            err_str = str(e).lower()
            if "chat not found" in err_str:
                return f"• <code>{_safe_str(cid)}</code> — (чат не найден)"
            else:
                logger.warning("Bad request for chat %s: %s", _mask_sensitive_id(cid), e)
                return f"• <code>{_safe_str(cid)}</code> — (некорректный запрос)"
        except TelegramAPIError as e:
            logger.warning("API error for chat %s: %s", _mask_sensitive_id(cid), e)
            return f"• <code>{_safe_str(cid)}</code> — (ошибка API)"
        except Exception as e:
            logger.error("Unexpected error for chat %s: %s", _mask_sensitive_id(cid), e, exc_info=True)
            return f"• <code>{_safe_str(cid)}</code> — (неизвестная ошибка)"


# ==================== HEALTH CHECK ====================

async def admin_health_check() -> Dict[str, Any]:
    """
    Проверка здоровья модуля.
    
    Returns:
        Словарь с состоянием модуля, метриками и готовностью
        
    Пример:
        >>> health = await admin_health_check()
        >>> health['bot_ready']
        True
    """
    return {
        "module": "admin",
        "version": "3.6.0-production",
        "bot_ready": AdminState.is_ready(),
        "db_ready": _is_db_ready(),
        "background_tasks": len(AdminState._background_tasks),
        "super_admins_count": len(SUPER_ADMIN_IDS or []) + 1,
        "config_errors": _config_errors,
        "metrics": AdminMetrics.to_dict(),
    }


# ==================== CALLBACK: ГЛАВНОЕ МЕНЮ ====================

@router.callback_query(F.data == CB_.MENU_ADMIN)
@require_admin
async def admin_panel_callback(callback: CallbackQuery) -> None:
    """Отображение главного меню админ-панели."""
    text = format_admin_panel_text(
        callback.from_user.id,
        callback.from_user.first_name,
        callback.message.chat.id
    )
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())
    await callback.answer()


# ==================== КОМАНДА /admin ====================

@router.message(Command("admin"))
async def cmd_admin_panel(message: Message) -> None:
    """Обработчик команды /admin."""
    if not await _check_message_access(message):
        return
    
    text = format_admin_panel_text(
        message.from_user.id,
        message.from_user.first_name,
        message.chat.id
    )
    await message.answer(
        text, parse_mode=ParseMode.HTML, reply_markup=get_admin_menu_keyboard()
    )


# ==================== CALLBACK: СТАТИСТИКА ====================

@router.callback_query(F.data == CB_.STATS)
@require_admin
async def admin_stats_callback(callback: CallbackQuery) -> None:
    """Сбор и отображение расширенной статистики."""
    chat_id = callback.message.chat.id
    await callback.answer("📊 Загружаю статистику...")
    
    AdminMetrics.stats_requests += 1
    logger.info("📊 Stats requested for chat %s", _mask_sensitive_id(chat_id))
    
    try:
        # Используем return_exceptions=True для изоляции сбоев
        results = await asyncio.wait_for(
            asyncio.gather(
                fetch_chat_daily_stats(chat_id),
                fetch_chat_top_words(chat_id, AdminConfig.TOP_WORDS_LIMIT),
                fetch_chat_active_users(chat_id, AdminConfig.TOP_USERS_LIMIT),
                fetch_total_users(),
                fetch_total_messages(),
                return_exceptions=True
            ),
            timeout=AdminConfig.TIMEOUT_STATS
        )
        
        # Извлекаем результаты, заменяя ошибки на пустые значения
        stats = results[0] if not isinstance(results[0], Exception) else {}
        top_words = results[1] if not isinstance(results[1], Exception) else []
        active_users = results[2] if not isinstance(results[2], Exception) else []
        total_users = results[3] if not isinstance(results[3], Exception) else 0
        total_messages = results[4] if not isinstance(results[4], Exception) else 0
        
        # Логируем ошибки если были
        for i, (name, result) in enumerate([
            ("stats", results[0]), ("top_words", results[1]),
            ("active_users", results[2]), ("total_users", results[3]),
            ("total_messages", results[4])
        ]):
            if isinstance(result, Exception):
                logger.error("Stats subquery '%s' failed: %s", name, result)
        
        text = format_stats_text(
            stats, active_users, top_words, total_users, total_messages
        )
        await safe_edit_or_reply(callback, text, get_stats_keyboard())
        AdminMetrics.stats_success += 1
        logger.info("✅ Stats displayed for chat %s", _mask_sensitive_id(chat_id))
        
    except asyncio.TimeoutError:
        AdminMetrics.stats_errors += 1
        logger.error("Stats timeout for chat %s", _mask_sensitive_id(chat_id))
        await callback.answer("❌ Таймаут загрузки статистики", show_alert=True)
    except asyncio.CancelledError:
        AdminMetrics.stats_errors += 1
        raise
    except DatabaseError as e:
        AdminMetrics.stats_errors += 1
        logger.error("Stats DB error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        AdminMetrics.stats_errors += 1
        logger.error("Stats error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)


# ==================== CALLBACK: ОЧИСТКА ====================

@router.callback_query(F.data == CB_.CLEANUP)
@require_admin
async def admin_cleanup_callback(callback: CallbackQuery) -> None:
    """
    Очистка сообщений бота в текущем чате.
    
    Удаляет сообщения бота за последние 48 часов.
    """
    chat_id = callback.message.chat.id
    await callback.answer("🧹 Очищаю...")
    
    bot = AdminState.get_bot()
    if bot is None:
        await callback.answer("❌ Бот не инициализирован", show_alert=True)
        return
    
    AdminMetrics.cleanup_requests += 1
    logger.info("🧹 Cleanup requested for chat %s", _mask_sensitive_id(chat_id))
    
    try:
        # ✅ Импорт внутри try-блока
        from utils.auto_delete import delete_bot_messages, bot_messages
        
        deleted = await asyncio.wait_for(
            delete_bot_messages(bot, chat_id),
            timeout=AdminConfig.TIMEOUT_CLEANUP
        )
        
        remaining = (
            len(bot_messages.get(chat_id, []))
            if isinstance(bot_messages, dict) else "N/A"
        )
        
        text = (
            "🧹 <b>ОЧИСТКА ЗАВЕРШЕНА</b>\n\n"
            f"Удалено сообщений: <b>{_safe_str(deleted)}</b>\n"
            f"В очереди на удаление: <b>{_safe_str(remaining)}</b>\n\n"
            "ℹ️ Удаляются только сообщения бота за последние 48 часов."
        )
        await safe_edit_or_reply(callback, text, get_back_keyboard())
        AdminMetrics.cleanup_success += 1
        logger.info("✅ Cleanup completed for chat %s: %s messages", 
                   _mask_sensitive_id(chat_id), deleted)
        
    except asyncio.TimeoutError:
        AdminMetrics.cleanup_errors += 1
        logger.error("Cleanup timeout for chat %s", _mask_sensitive_id(chat_id))
        await callback.answer("❌ Таймаут очистки", show_alert=True)
    except asyncio.CancelledError:
        AdminMetrics.cleanup_errors += 1
        raise
    except ImportError as e:
        AdminMetrics.cleanup_errors += 1
        logger.warning("Auto-delete module not available: %s", e)
        text = (
            "🧹 <b>ОЧИСТКА ЧАТА</b>\n\n"
            "ℹ️ Модуль авто-очистки не загружен.\n"
            "<i>Установите utils/auto_delete.py для полной функциональности.</i>"
        )
        await safe_edit_or_reply(callback, text, get_back_keyboard())
    except Exception as e:
        AdminMetrics.cleanup_errors += 1
        logger.error("Cleanup error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка при очистке", show_alert=True)


# ==================== CALLBACK: СВОДКА ====================

@router.callback_query(F.data == CB_.SUMMARY)
@require_admin
async def admin_summary_callback(callback: CallbackQuery) -> None:
    """Формирование и отправка сводки дня."""
    chat_id = callback.message.chat.id
    await callback.answer("🌅 Формирую сводку...")
    
    bot = AdminState.get_bot()
    if bot is None:
        await callback.answer("❌ Бот не инициализирован", show_alert=True)
        return
    
    AdminMetrics.summary_requests += 1
    logger.info("🌅 Summary requested for chat %s", _mask_sensitive_id(chat_id))
    
    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                fetch_chat_daily_stats(chat_id),
                fetch_chat_active_users(chat_id, 5),
                fetch_chat_top_words(chat_id, 10),
                return_exceptions=True
            ),
            timeout=AdminConfig.TIMEOUT_STATS
        )
        
        stats = results[0] if not isinstance(results[0], Exception) else {}
        active_users = results[1] if not isinstance(results[1], Exception) else []
        top_words = results[2] if not isinstance(results[2], Exception) else []
        
        summary_text = format_summary_text(stats, active_users, top_words)
        await bot.send_message(chat_id, summary_text, parse_mode=ParseMode.HTML)
        await safe_edit_or_reply(callback, "✅ <b>СВОДКА УСПЕШНО ОТПРАВЛЕНА</b>", get_back_keyboard())
        AdminMetrics.summary_success += 1
        logger.info("✅ Summary sent for chat %s", _mask_sensitive_id(chat_id))
        
    except asyncio.TimeoutError:
        AdminMetrics.summary_errors += 1
        await callback.answer("❌ Таймаут формирования сводки", show_alert=True)
    except asyncio.CancelledError:
        AdminMetrics.summary_errors += 1
        raise
    except TelegramForbiddenError:
        AdminMetrics.summary_errors += 1
        await callback.answer("❌ Бот заблокирован в этом чате", show_alert=True)
    except Exception as e:
        AdminMetrics.summary_errors += 1
        logger.error("Summary error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка отправки сводки", show_alert=True)


# ==================== CALLBACK: ВСЕ ЧАТЫ ====================

@router.callback_query(F.data == CB_.CHATS)
@require_admin
async def admin_chats_callback(callback: CallbackQuery) -> None:
    """Отображение списка всех чатов с ботом."""
    await callback.answer("📋 Загружаю список чатов...")
    
    AdminMetrics.chats_requests += 1
    
    try:
        chats = await fetch_all_chat_ids(limit=AdminConfig.MAX_CHATS_DISPLAY * 2)
        total = len(chats)
        display_chats_ids = chats[:AdminConfig.MAX_CHATS_DISPLAY]
        
        bot = AdminState.get_bot()
        if bot is None:
            display_strings = [
                f"• <code>{_safe_str(cid)}</code>" for cid in display_chats_ids
            ]
        else:
            sem = asyncio.Semaphore(AdminConfig.MAX_CONCURRENT_CHATS)
            display_strings = await asyncio.wait_for(
                asyncio.gather(
                    *(fetch_chat_info_async(cid, sem) for cid in display_chats_ids),
                    return_exceptions=True
                ),
                timeout=AdminConfig.TIMEOUT_CHAT_INFO * len(display_chats_ids) + 5.0
            )
            # Заменяем исключения на сообщения об ошибке
            display_strings = [
                f"• <code>{_safe_str(cid)}</code> — (ошибка)"
                if isinstance(s, Exception) else s
                for cid, s in zip(display_chats_ids, display_strings)
            ]
        
        text = format_chats_list_text(list(display_strings), total)
        await safe_edit_or_reply(callback, text, get_chats_keyboard())
        AdminMetrics.chats_success += 1
        
    except asyncio.TimeoutError:
        AdminMetrics.chats_errors += 1
        await callback.answer("❌ Таймаут загрузки списка чатов", show_alert=True)
    except asyncio.CancelledError:
        AdminMetrics.chats_errors += 1
        raise
    except Exception as e:
        AdminMetrics.chats_errors += 1
        logger.error("Chats error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка загрузки списка чатов", show_alert=True)


# ==================== CALLBACK: ГЛОБАЛЬНАЯ ОЧИСТКА ====================

@router.callback_query(F.data == CB_.CLEANUP_ALL)
@require_admin
async def admin_cleanup_all_callback(callback: CallbackQuery) -> None:
    """
    Запуск глобальной очистки всех чатов.
    
    Выполняется в фоновом режиме.
    """
    bot = AdminState.get_bot()
    if bot is None:
        await callback.answer("❌ Бот не инициализирован", show_alert=True)
        return
    
    await callback.answer("🧹 Глобальная очистка запущена...", show_alert=True)
    
    try:
        # ✅ Импорт внутри try-блока
        from utils.auto_delete import cleanup_all_chats
        
        task = asyncio.create_task(
            asyncio.wait_for(
                cleanup_all_chats(bot),
                timeout=AdminConfig.TIMEOUT_GLOBAL_CLEANUP
            )
        )
        await AdminState.add_task(task)
        
        if callback.message:
            await callback.message.edit_text(
                "🧹 <b>ГЛОБАЛЬНАЯ ОЧИСТКА ЗАПУЩЕНА</b>\n\n"
                "Процесс выполняется в фоне.\n"
                "Это может занять несколько минут.\n\n"
                "<i>Удаляются сообщения бота за последние 48 часов.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard()
            )
    except ImportError as e:
        logger.warning("Auto-delete module not available for global cleanup: %s", e)
        if callback.message:
            await callback.message.edit_text(
                "⚠️ <b>МОДУЛЬ АВТО-ОЧИСТКИ НЕ НАЙДЕН</b>\n\n"
                "Установите utils/auto_delete.py для работы этой функции.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard()
            )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("Cleanup all error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка запуска очистки", show_alert=True)


# ==================== CALLBACK: ПЕРЕЗАГРУЗКА РП ====================

@router.callback_query(F.data == CB_.RELOAD)
@require_admin
async def admin_reload_callback(callback: CallbackQuery) -> None:
    """Перезагрузка РП-команд из базы данных."""
    AdminMetrics.reload_requests += 1
    
    try:
        # ✅ Импорт внутри try-блока
        from handlers.smart_commands import load_custom_rp_commands
        
        await load_custom_rp_commands()
        await callback.answer("✅ РП команды перезагружены!", show_alert=True)
        
        if callback.message:
            await callback.message.edit_text(
                "🔄 <b>РП КОМАНДЫ ПЕРЕЗАГРУЖЕНЫ</b>\n\n"
                "Все кастомные РП-команды обновлены из базы данных.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard()
            )
        AdminMetrics.reload_success += 1
    except ImportError as e:
        AdminMetrics.reload_errors += 1
        logger.warning("RP module not available: %s", e)
        await callback.answer("⚠️ Модуль РП не найден", show_alert=True)
    except asyncio.CancelledError:
        AdminMetrics.reload_errors += 1
        raise
    except Exception as e:
        AdminMetrics.reload_errors += 1
        logger.error("Reload error: %s", e, exc_info=True)
        await callback.answer(f"❌ Ошибка перезагрузки: {str(e)}", show_alert=True)


# ==================== CALLBACK: НАЗАД И ЗАКРЫТЬ ====================

@router.callback_query(F.data == CB_.BACK)
@require_admin
async def admin_back_callback(callback: CallbackQuery) -> None:
    """Возврат в главное меню админ-панели."""
    text = format_admin_panel_text(
        callback.from_user.id,
        callback.from_user.first_name,
        callback.message.chat.id
    )
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == CB_.CLOSE)
@require_admin
async def admin_close_callback(callback: CallbackQuery) -> None:
    """Закрытие админ-панели."""
    if not callback or not callback.message:
        return
    
    try:
        await callback.message.delete()
    except TelegramAPIError:
        try:
            await callback.message.edit_text("🔒 Админ-панель закрыта")
        except TelegramAPIError:
            pass
    await callback.answer()


# ==================== ШУТДАУН ХУК ====================

async def on_shutdown() -> None:
    """
    Обработчик остановки бота.
    
    Корректно завершает все фоновые задачи и логирует состояние.
    """
    metrics = AdminMetrics.to_dict()
    logger.info("📊 Final admin metrics: %s", metrics)
    await cleanup_background_tasks()
    logger.info("✅ Admin module shutdown complete")
