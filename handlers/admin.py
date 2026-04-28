#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/admin.py
# ВЕРСИЯ: 3.5.5-production (финальная исправленная)
# ОПИСАНИЕ: Админ-панель — все критические ошибки исправлены
# ИСПРАВЛЕНИЯ v3.5.5:
#   ✅ ImportError → ImportError (критическая опечатка)
#   ✅ get_admin_menu_keyboard() → get_admin_menu_keyboard() (опечатка)
#   ✅ Уточнена проверка "member" в fetch_chat_info_async
#   ✅ Добавлена валидация AdminConfig при старте
#   ✅ Параметр date в fetch_* функциях для гибкости
#   ✅ Оптимизирован LIMIT в fetch_all_chat_ids
#   ✅ Метрики успешных/неудачных операций
# ============================================

import asyncio
import functools
import html
import logging
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
    """
    
    TIMEOUT_STATS = 10.0          # Таймаут сбора статистики (сек)
    TIMEOUT_CLEANUP = 30.0        # Таймаут очистки одного чата (сек)
    TIMEOUT_CHAT_INFO = 5.0       # Таймаут получения информации о чате (сек)
    TIMEOUT_GLOBAL_CLEANUP = 60.0 # Таймаут глобальной очистки (сек)
    TIMEOUT_DEFAULT = 15.0        # Таймаут по умолчанию (сек)
    
    MAX_CHATS_DISPLAY = 20        # Чатов на странице
    MAX_CONCURRENT_CHATS = 5      # Одновременных запросов к API
    TOP_USERS_LIMIT = 10          # Пользователей в топе
    TOP_WORDS_LIMIT = 15          # Слов в топе
    
    OWNER_ID = 895844198          # ID владельца бота
    LOG_SENSITIVE_DATA = False    # Логировать ли ID полностью
    
    @classmethod
    def validate(cls) -> List[str]:
        """
        Валидация конфигурации при старте.
        
        Returns:
            Список ошибок (пустой если всё корректно)
        """
        errors = []
        
        # Проверка таймаутов
        for name in ['TIMEOUT_STATS', 'TIMEOUT_CLEANUP', 'TIMEOUT_CHAT_INFO',
                      'TIMEOUT_GLOBAL_CLEANUP', 'TIMEOUT_DEFAULT']:
            value = getattr(cls, name)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(name + " must be > 0, got " + str(value))
        
        # Проверка лимитов
        for name in ['MAX_CHATS_DISPLAY', 'MAX_CONCURRENT_CHATS',
                      'TOP_USERS_LIMIT', 'TOP_WORDS_LIMIT']:
            value = getattr(cls, name)
            if not isinstance(value, int) or value <= 0:
                errors.append(name + " must be > 0, got " + str(value))
        
        # Проверка ID владельца
        if not isinstance(cls.OWNER_ID, int) or cls.OWNER_ID <= 0:
            errors.append("OWNER_ID must be a positive integer")
        
        return errors


# Валидация при импорте
_config_errors = AdminConfig.validate()
if _config_errors:
    logger.error("AdminConfig validation failed: %s", "; ".join(_config_errors))


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
    """Счётчики операций для мониторинга."""
    
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


# ==================== СОСТОЯНИЕ МОДУЛЯ ====================

class AdminState:
    """Инкапсуляция глобального состояния модуля."""
    
    _bot: Optional[Bot] = None
    _background_tasks: set[asyncio.Task] = set()
    _initialized: bool = False
    
    @classmethod
    def set_bot(cls, bot_instance: Bot) -> None:
        cls._bot = bot_instance
        cls._initialized = True
        logger.info("✅ Bot instance set in admin module")
    
    @classmethod
    def get_bot(cls) -> Optional[Bot]:
        return cls._bot
    
    @classmethod
    def is_ready(cls) -> bool:
        return cls._initialized and cls._bot is not None
    
    @classmethod
    def add_task(cls, task: asyncio.Task) -> None:
        cls._background_tasks.add(task)
        task.add_done_callback(lambda t: cls._background_tasks.discard(t))
    
    @classmethod
    async def cleanup_tasks(cls) -> None:
        for task in list(cls._background_tasks):
            if task and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        cls._background_tasks.clear()
        # Периодическая очистка выполненных задач
        cls._background_tasks = {t for t in cls._background_tasks if not t.done()}
        logger.info("✅ Admin background tasks cleaned up")


def set_bot(bot_instance: Bot) -> None:
    AdminState.set_bot(bot_instance)


async def cleanup_background_tasks() -> None:
    await AdminState.cleanup_tasks()


# ==================== ДЕКОРАТОРЫ ====================

def require_admin(func):
    """Декоратор проверки прав супер-админа в callback'ах."""
    @functools.wraps(func)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if not await _check_callback_access(callback):
            return
        return await func(callback, *args, **kwargs)
    return wrapper


# ==================== ПРОВЕРКА ПРАВ ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    if user_id == AdminConfig.OWNER_ID:
        return True
    return user_id in (SUPER_ADMIN_IDS or [])


async def _check_callback_access(callback: CallbackQuery) -> bool:
    if not callback or not callback.from_user:
        if callback:
            await callback.answer("❌ Ошибка", show_alert=True)
        return False
    return _check_user_access(callback.from_user.id, callback)


async def _check_message_access(message: Message) -> bool:
    if not message or not message.from_user:
        return False
    return _check_user_access(message.from_user.id, message)


def _check_user_access(user_id: int, event: Any) -> bool:
    if not is_super_admin(user_id):
        logger.warning(
            "⚠️ Unauthorized admin access attempt by user_id=%s",
            user_id if AdminConfig.LOG_SENSITIVE_DATA else "***"
        )
        if hasattr(event, 'answer'):
            asyncio.create_task(event.answer("❌ Доступ запрещён", show_alert=True))
        return False
    return True


# ==================== БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ ====================

def validate_chat_id(chat_id: Any) -> int:
    if chat_id is None:
        raise ValueError("chat_id is required")
    try:
        result = int(chat_id)
        if result <= 0:
            raise ValueError("chat_id must be positive")
        return result
    except (ValueError, TypeError):
        raise ValueError("chat_id must be a valid positive integer")


def safe_html(text: Optional[str]) -> str:
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def _safe_str(value: Any) -> str:
    if value is None:
        return "0"
    try:
        return str(value)
    except Exception:
        return "?"


def _mask_sensitive_id(value: Any) -> str:
    if not AdminConfig.LOG_SENSITIVE_DATA:
        return "***"
    return str(value)


# ==================== ПРОВЕРКИ ГОТОВНОСТИ ====================

def _is_db_ready() -> bool:
    return db is not None and getattr(db, '_initialized', False)


# ==================== СЛОЙ ДАННЫХ (БД) ====================

async def fetch_total_users() -> int:
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


async def fetch_total_messages() -> int:
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


async def fetch_all_chat_ids(limit: int = 100) -> List[int]:
    """
    Получение списка всех чатов с ботом.
    
    Args:
        limit: Максимальное количество чатов (по умолчанию = MAX_CHATS_DISPLAY)
    """
    if not _is_db_ready():
        logger.warning("DB not available for fetch_all_chat_ids")
        return []
    try:
        rows = await db._execute_with_retry(
            "SELECT DISTINCT chat_id FROM user_activity_log "
            "ORDER BY chat_id LIMIT ?",
            (limit,), fetch_all=True
        )
        return [row["chat_id"] for row in rows] if rows else []
    except DatabaseError as e:
        logger.error("DB error in fetch_all_chat_ids: %s", e)
        return []


async def fetch_chat_daily_stats(
    chat_id: int, date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получение дневной статистики чата.
    
    Args:
        chat_id: ID чата
        date: Дата в формате YYYY-MM-DD (по умолчанию — сегодня)
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


async def fetch_chat_active_users(
    chat_id: int, limit: int = 10, date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Получение активных пользователей чата.
    
    Args:
        chat_id: ID чата
        limit: Максимальное количество пользователей
        date: Дата в формате YYYY-MM-DD (по умолчанию — сегодня)
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


async def fetch_chat_top_words(
    chat_id: int, limit: int = 15, date: Optional[str] = None
) -> List[Tuple[str, int]]:
    """
    Получение топ-слов чата.
    
    Args:
        chat_id: ID чата
        limit: Максимальное количество слов
        date: Дата в формате YYYY-MM-DD (по умолчанию — сегодня)
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


# ==================== СЛОЙ ФОРМАТИРОВАНИЯ ====================

def format_stats_text(
    stats: Dict[str, Any],
    active_users: List[Dict[str, Any]],
    top_words: List[Tuple[str, int]],
    total_users: int,
    total_messages: int
) -> str:
    text = (
        "📊 <b>РАСШИРЕННАЯ СТАТИСТИКА ЧАТА</b>\n\n"
        "📅 <b>ЗА СЕГОДНЯ:</b>\n"
        "💬 Сообщений: <b>" + _safe_str(stats.get('total_messages')) + "</b>\n"
        "👥 Уникальных: <b>" + _safe_str(stats.get('unique_users')) + "</b>\n"
        "🎤 Войс: <b>" + _safe_str(stats.get('total_voice')) + "</b>\n"
        "🎮 XO игр: <b>" + _safe_str(stats.get('total_xo_games')) + "</b>\n\n"
        "📈 <b>ВСЕГО В БОТЕ:</b>\n"
        "👤 Пользователей: <b>" + _safe_str(total_users) + "</b>\n"
        "💬 Сообщений: <b>" + _safe_str(total_messages) + "</b>\n"
    )
    
    if active_users:
        text += "\n<b>🏆 ТОП-" + _safe_str(len(active_users)) + " АКТИВНЫХ:</b>\n"
        for i, u in enumerate(active_users, 1):
            name = safe_html(u.get('first_name', '?'))[:20]
            msgs = _safe_str(u.get('message_count'))
            text += _safe_str(i) + ". " + name + " — <b>" + msgs + "</b>\n"
    
    if top_words:
        text += "\n<b>📝 ТОП-" + _safe_str(len(top_words)) + " СЛОВ:</b>\n"
        for word, count in top_words:
            text += "• " + safe_html(str(word)) + " — " + _safe_str(count) + "\n"
    
    return text


def format_summary_text(
    stats: Dict[str, Any],
    active_users: List[Dict[str, Any]],
    top_words: List[Tuple[str, int]]
) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    
    text = (
        "🌅 <b>СВОДКА ДНЯ — " + today + "</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 Сообщений: <b>" + _safe_str(stats.get('total_messages')) + "</b>\n"
        "👥 Активных: <b>" + _safe_str(stats.get('unique_users')) + "</b>\n"
        "🎤 Войс: <b>" + _safe_str(stats.get('total_voice')) + "</b>\n"
        "🎮 Игр XO: <b>" + _safe_str(stats.get('total_xo_games')) + "</b>\n"
    )
    
    if active_users:
        text += "\n<b>🏆 ТОП-5 АКТИВНЫХ:</b>\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, u in enumerate(active_users[:5]):
            name = safe_html(u.get('first_name', '?'))[:15]
            msgs = _safe_str(u.get('message_count'))
            medal = medals[i] if i < len(medals) else '•'
            text += medal + " " + name + " — <b>" + msgs + "</b> сообщ.\n"
    
    if top_words:
        text += "\n<b>📝 ТОП-10 СЛОВ:</b>\n"
        for word, count in top_words[:10]:
            text += "• " + safe_html(str(word)) + " — " + _safe_str(count) + "\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━━\n<i>Авто-сводка NEXUS Bot</i>"
    return text


def format_admin_panel_text(
    user_id: int, first_name: Optional[str], chat_id: int
) -> str:
    is_owner = is_super_admin(user_id)
    owner_status = "👑 Владелец" if is_owner else "🔐 Админ"
    
    return (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v3.5.5</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 Админ: <b>" + safe_html(first_name) + "</b>\n"
        "🆔 Ваш ID: <code>" + _safe_str(user_id) + "</code>\n"
        "🔑 Статус: <b>" + owner_status + "</b>\n"
        "💬 Чат: <code>" + _safe_str(chat_id) + "</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )


def format_chats_list_text(display_chats: List[str], total: int) -> str:
    text = (
        "📋 <b>ЧАТЫ С БОТОМ</b>\n\nВсего: <b>"
        + _safe_str(total) + "</b>\n\n"
    )
    text += "\n".join(display_chats)
    
    if total > AdminConfig.MAX_CHATS_DISPLAY:
        text += (
            "\n\n... и ещё <b>"
            + _safe_str(total - AdminConfig.MAX_CHATS_DISPLAY) + "</b> чатов"
        )
    
    return text


# ==================== СЛОЙ ОТОБРАЖЕНИЯ (КЛАВИАТУРЫ) ====================

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=CB_.STATS)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_.BACK)],
    ])


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_.BACK)]
    ])


def get_chats_keyboard() -> InlineKeyboardMarkup:
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


async def fetch_chat_info_async(cid: int, sem: asyncio.Semaphore) -> str:
    """
    Безопасное получение информации о чате.
    
    ✅ Уточнённые проверки ошибок API:
    - "chat not found" — чат не существует
    - "bot is not a member" / "bot was kicked" — бот не в чате
    - "not enough rights" — недостаточно прав
    """
    async with sem:
        try:
            bot = AdminState.get_bot()
            if bot is None:
                return "• <code>" + _safe_str(cid) + "</code> — (бот не инициализирован)"
            
            chat = await asyncio.wait_for(
                bot.get_chat(cid),
                timeout=AdminConfig.TIMEOUT_CHAT_INFO
            )
            
            if chat is None:
                return "• <code>" + _safe_str(cid) + "</code> — (нет данных)"
            
            name = safe_html(chat.title[:30] if chat.title else "Чат")
            return "• <code>" + _safe_str(cid) + "</code> — " + name
            
        except asyncio.TimeoutError:
            return "• <code>" + _safe_str(cid) + "</code> — (таймаут)"
        except TelegramForbiddenError as e:
            err_str = str(e).lower()
            if "bot was kicked" in err_str or "bot is not a member" in err_str:
                return "• <code>" + _safe_str(cid) + "</code> — (бот исключён из чата)"
            elif "not enough rights" in err_str:
                return "• <code>" + _safe_str(cid) + "</code> — (недостаточно прав)"
            else:
                return "• <code>" + _safe_str(cid) + "</code> — (доступ запрещён)"
        except TelegramBadRequest as e:
            err_str = str(e).lower()
            if "chat not found" in err_str:
                return "• <code>" + _safe_str(cid) + "</code> — (чат не найден)"
            else:
                logger.warning("Bad request for chat %s: %s", _mask_sensitive_id(cid), e)
                return "• <code>" + _safe_str(cid) + "</code> — (некорректный запрос)"
        except TelegramAPIError as e:
            logger.warning("API error for chat %s: %s", _mask_sensitive_id(cid), e)
            return "• <code>" + _safe_str(cid) + "</code> — (ошибка API)"
        except Exception as e:
            logger.error("Unexpected error for chat %s: %s", _mask_sensitive_id(cid), e, exc_info=True)
            return "• <code>" + _safe_str(cid) + "</code> — (неизвестная ошибка)"


# ==================== HEALTH CHECK ====================

async def admin_health_check() -> Dict[str, Any]:
    return {
        "module": "admin",
        "version": "3.5.5-production",
        "bot_ready": AdminState.is_ready(),
        "db_ready": _is_db_ready(),
        "background_tasks": len(AdminState._background_tasks),
        "super_admins_count": len(SUPER_ADMIN_IDS or []) + 1,
        "metrics": AdminMetrics.to_dict(),
    }


# ==================== CALLBACK: ГЛАВНОЕ МЕНЮ ====================

@router.callback_query(F.data == CB_.MENU_ADMIN)
@require_admin
async def admin_panel_callback(callback: CallbackQuery) -> None:
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
    chat_id = callback.message.chat.id
    await callback.answer("📊 Загружаю статистику...")
    
    AdminMetrics.stats_requests += 1
    
    try:
        stats, top_words, active_users, total_users, total_messages = (
            await asyncio.wait_for(
                asyncio.gather(
                    fetch_chat_daily_stats(chat_id),
                    fetch_chat_top_words(chat_id, AdminConfig.TOP_WORDS_LIMIT),
                    fetch_chat_active_users(chat_id, AdminConfig.TOP_USERS_LIMIT),
                    fetch_total_users(),
                    fetch_total_messages(),
                ),
                timeout=AdminConfig.TIMEOUT_STATS
            )
        )
        
        text = format_stats_text(
            stats or {}, active_users or [], top_words or [],
            total_users or 0, total_messages or 0
        )
        await safe_edit_or_reply(callback, text, get_stats_keyboard())
        AdminMetrics.stats_success += 1
        
    except asyncio.TimeoutError:
        AdminMetrics.stats_errors += 1
        await callback.answer("❌ Таймаут загрузки статистики", show_alert=True)
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
    chat_id = callback.message.chat.id
    await callback.answer("🧹 Очищаю...")
    
    bot = AdminState.get_bot()
    if bot is None:
        await callback.answer("❌ Бот не инициализирован", show_alert=True)
        return
    
    AdminMetrics.cleanup_requests += 1
    
    try:
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
            "Удалено сообщений: <b>" + _safe_str(deleted) + "</b>\n"
            "В очереди на удаление: <b>" + _safe_str(remaining) + "</b>\n\n"
            "ℹ️ Удаляются только сообщения бота за последние 48 часов."
        )
        await safe_edit_or_reply(callback, text, get_back_keyboard())
        AdminMetrics.cleanup_success += 1
        
    except asyncio.TimeoutError:
        AdminMetrics.cleanup_errors += 1
        await callback.answer("❌ Таймаут очистки", show_alert=True)
    except ImportError:
        AdminMetrics.cleanup_errors += 1
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
    chat_id = callback.message.chat.id
    await callback.answer("🌅 Формирую сводку...")
    
    bot = AdminState.get_bot()
    if bot is None:
        await callback.answer("❌ Бот не инициализирован", show_alert=True)
        return
    
    AdminMetrics.summary_requests += 1
    
    try:
        stats, active_users, top_words = await asyncio.wait_for(
            asyncio.gather(
                fetch_chat_daily_stats(chat_id),
                fetch_chat_active_users(chat_id, 5),
                fetch_chat_top_words(chat_id, 10),
            ),
            timeout=AdminConfig.TIMEOUT_STATS
        )
        
        summary_text = format_summary_text(stats or {}, active_users or [], top_words or [])
        await bot.send_message(chat_id, summary_text, parse_mode=ParseMode.HTML)
        await safe_edit_or_reply(callback, "✅ <b>СВОДКА УСПЕШНО ОТПРАВЛЕНА</b>", get_back_keyboard())
        AdminMetrics.summary_success += 1
        
    except asyncio.TimeoutError:
        AdminMetrics.summary_errors += 1
        await callback.answer("❌ Таймаут формирования сводки", show_alert=True)
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
    await callback.answer("📋 Загружаю список чатов...")
    
    AdminMetrics.chats_requests += 1
    
    try:
        chats = await fetch_all_chat_ids(limit=AdminConfig.MAX_CHATS_DISPLAY * 2)
        total = len(chats)
        display_chats_ids = chats[:AdminConfig.MAX_CHATS_DISPLAY]
        
        bot = AdminState.get_bot()
        if bot is None:
            display_strings = [
                "• <code>" + _safe_str(cid) + "</code>" for cid in display_chats_ids
            ]
        else:
            sem = asyncio.Semaphore(AdminConfig.MAX_CONCURRENT_CHATS)
            display_strings = await asyncio.wait_for(
                asyncio.gather(
                    *(fetch_chat_info_async(cid, sem) for cid in display_chats_ids)
                ),
                timeout=AdminConfig.TIMEOUT_CHAT_INFO * len(display_chats_ids) + 5.0
            )
        
        text = format_chats_list_text(list(display_strings), total)
        await safe_edit_or_reply(callback, text, get_chats_keyboard())
        AdminMetrics.chats_success += 1
        
    except asyncio.TimeoutError:
        AdminMetrics.chats_errors += 1
        await callback.answer("❌ Таймаут загрузки списка чатов", show_alert=True)
    except Exception as e:
        AdminMetrics.chats_errors += 1
        logger.error("Chats error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка загрузки списка чатов", show_alert=True)


# ==================== CALLBACK: ГЛОБАЛЬНАЯ ОЧИСТКА ====================

@router.callback_query(F.data == CB_.CLEANUP_ALL)
@require_admin
async def admin_cleanup_all_callback(callback: CallbackQuery) -> None:
    bot = AdminState.get_bot()
    if bot is None:
        await callback.answer("❌ Бот не инициализирован", show_alert=True)
        return
    
    await callback.answer("🧹 Глобальная очистка запущена...", show_alert=True)
    
    try:
        from utils.auto_delete import cleanup_all_chats
        task = asyncio.create_task(
            asyncio.wait_for(
                cleanup_all_chats(bot),
                timeout=AdminConfig.TIMEOUT_GLOBAL_CLEANUP
            )
        )
        AdminState.add_task(task)
        
        if callback.message:
            await callback.message.edit_text(
                "🧹 <b>ГЛОБАЛЬНАЯ ОЧИСТКА ЗАПУЩЕНА</b>\n\n"
                "Процесс выполняется в фоне.\n"
                "Это может занять несколько минут.\n\n"
                "<i>Удаляются сообщения бота за последние 48 часов.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard()
            )
    except ImportError:
        if callback.message:
            await callback.message.edit_text(
                "⚠️ <b>МОДУЛЬ АВТО-ОЧИСТКИ НЕ НАЙДЕН</b>\n\n"
                "Установите utils/auto_delete.py для работы этой функции.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard()
            )
    except Exception as e:
        logger.error("Cleanup all error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка запуска очистки", show_alert=True)


# ==================== CALLBACK: ПЕРЕЗАГРУЗКА РП ====================

@router.callback_query(F.data == CB_.RELOAD)
@require_admin
async def admin_reload_callback(callback: CallbackQuery) -> None:
    AdminMetrics.reload_requests += 1
    
    try:
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
    except ImportError:
        AdminMetrics.reload_errors += 1
        await callback.answer("⚠️ Модуль РП не найден", show_alert=True)
    except Exception as e:
        AdminMetrics.reload_errors += 1
        logger.error("Reload error: %s", e, exc_info=True)
        await callback.answer("❌ Ошибка перезагрузки: " + str(e), show_alert=True)


# ==================== CALLBACK: НАЗАД И ЗАКРЫТЬ ====================

@router.callback_query(F.data == CB_.BACK)
@require_admin
async def admin_back_callback(callback: CallbackQuery) -> None:
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
    await cleanup_background_tasks()
    logger.info("✅ Admin module shutdown complete")
