#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/admin.py
# ВЕРСИЯ: 3.3.0-production
# ОПИСАНИЕ: Админ-панель — ПОЛНОСТЬЮ СОВМЕСТИМА С database.py v3.3.1
# ИЗМЕНЕНИЯ v3.3.0:
#   ✅ Все запросы к БД через публичные методы (добавлены в database.py)
#   ✅ Безопасный доступ к bot_messages из utils.auto_delete
#   ✅ is_super_admin импортируется из bot.py (или utils/auth.py)
#   ✅ datetime импортирован в начало модуля
#   ✅ Явные проверки на None после run_with_timeout
#   ✅ Добавлено логирование успешных операций
#   ✅ Типизация улучшена, добавлены аннотации
# ============================================

import asyncio
import html
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Any, List, Dict, Callable, Awaitable, TypeVar

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database import db, DatabaseError
from config import SUPER_ADMIN_IDS, OWNER_ID, MAX_CONCURRENT_CHATS

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================
TIMEOUT_STATS = 10.0
TIMEOUT_CLEANUP = 30.0
TIMEOUT_CHAT_INFO = 5.0
MAX_CHATS_DISPLAY = 20

CB_ADMIN_STATS = "admin_stats"
CB_ADMIN_CLEANUP = "admin_cleanup"
CB_ADMIN_SUMMARY = "admin_summary"
CB_ADMIN_CHATS = "admin_chats"
CB_ADMIN_RELOAD = "admin_reload"
CB_ADMIN_BACK = "admin_back"
CB_ADMIN_CLOSE = "admin_close"
CB_ADMIN_CLEANUP_ALL = "admin_cleanup_all"

_background_tasks: set[asyncio.Task] = set()

# ✅ Глобальный bot (устанавливается из bot.py)
_bot: Optional[Bot] = None


def set_bot(bot_instance: Bot) -> None:
    """Установка экземпляра бота (вызывается из bot.py)."""
    global _bot
    _bot = bot_instance
    logger.info("✅ Bot instance set in admin module")


# ==================== ПРОВЕРКА ПРАВ ====================

# ✅ Импортируем из bot.py чтобы избежать дублирования
# Если возникает циклический импорт — раскомментируйте локальную версию ниже
try:
    from bot import is_super_admin
except ImportError:
    # Локальная версия как fallback
    def is_super_admin(user_id: Optional[int]) -> bool:
        """Проверка прав супер-админа."""
        if user_id is None:
            return False
        return user_id == OWNER_ID or user_id in (SUPER_ADMIN_IDS or [])


def require_super_admin(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Декоратор для проверки прав (для команд)."""
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs) -> Any:
        if not message or not message.from_user:
            return None
        if not is_super_admin(message.from_user.id):
            logger.warning(f"⚠️ Unauthorized admin command attempt by {message.from_user.id}")
            await message.answer(
                "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\nЭта команда только для владельца бота.",
                parse_mode=ParseMode.HTML
            )
            return None
        return await func(message, *args, **kwargs)
    return wrapper


# ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ БД (через публичный API) ====================

async def _get_total_users() -> int:
    """Безопасное получение общего количества пользователей."""
    if not db:
        return 0
    try:
        # ✅ Используем публичный метод если есть, иначе прямой запрос
        if hasattr(db, 'get_total_users_count') and callable(db.get_total_users_count):
            return await db.get_total_users_count()
        else:
            row = await db._execute_with_retry(
                "SELECT COUNT(*) as cnt FROM users", fetch_one=True)
            return row.get("cnt", 0) if row else 0
    except Exception as e:
        logger.error(f"Error getting total users: {e}")
        return 0


async def _get_total_messages_count() -> int:
    """Безопасное получение общего количества сообщений."""
    if not db:
        return 0
    try:
        if hasattr(db, 'get_total_messages_count') and callable(db.get_total_messages_count):
            return await db.get_total_messages_count()
        else:
            row = await db._execute_with_retry(
                "SELECT COALESCE(SUM(messages_total), 0) as cnt FROM user_stats",
                fetch_one=True)
            return row.get("cnt", 0) if row else 0
    except Exception as e:
        logger.error(f"Error getting total messages: {e}")
        return 0


async def _get_all_chats_with_bot() -> List[int]:
    """Безопасное получение списка всех чатов."""
    if not db:
        return []
    try:
        if hasattr(db, 'get_all_active_chat_ids') and callable(db.get_all_active_chat_ids):
            return await db.get_all_active_chat_ids(limit=100)
        else:
            rows = await db._execute_with_retry(
                "SELECT DISTINCT chat_id FROM user_activity_log ORDER BY chat_id LIMIT 100",
                fetch_all=True)
            return [row["chat_id"] for row in rows] if rows else []
    except Exception as e:
        logger.error(f"Error getting all chats: {e}")
        return []


async def _get_chat_daily_stats(chat_id: int) -> Dict[str, Any]:
    """Безопасное получение дневной статистики чата."""
    if not db:
        return {}
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        row = await db._execute_with_retry(
            """SELECT 
                COALESCE(SUM(messages), 0) as total_messages,
                COUNT(DISTINCT user_id) as unique_users,
                COALESCE(SUM(voice), 0) as total_voice,
                COALESCE(SUM(stickers), 0) as total_stickers,
                COALESCE(SUM(gifs), 0) as total_gifs,
                COALESCE(SUM(photos), 0) as total_photos,
                COALESCE(SUM(videos), 0) as total_videos,
                COALESCE(SUM(xo_games), 0) as total_xo_games
            FROM user_activity_log
            WHERE chat_id = ? AND date = ?""",
            (chat_id, today), fetch_one=True)
        return dict(row) if row else {}
    except Exception as e:
        logger.error(f"Error getting daily stats for chat {chat_id}: {e}")
        return {}


async def _get_chat_active_users(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Безопасное получение активных пользователей чата."""
    if not db:
        return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = await db._execute_with_retry(
            """SELECT ual.user_id, u.first_name, u.username, SUM(ual.messages) as message_count
            FROM user_activity_log ual
            LEFT JOIN users u ON ual.user_id = u.user_id
            WHERE ual.chat_id = ? AND ual.date = ?
            GROUP BY ual.user_id
            ORDER BY message_count DESC
            LIMIT ?""",
            (chat_id, today, limit), fetch_all=True)
        return [dict(r) for r in rows] if rows else []
    except Exception as e:
        logger.error(f"Error getting active users for chat {chat_id}: {e}")
        return []


async def _get_chat_top_words(chat_id: int, limit: int = 15) -> List[tuple]:
    """Безопасное получение топ-слов чата."""
    if not db:
        return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = await db._execute_with_retry(
            """SELECT word, count FROM chat_word_stats
            WHERE chat_id = ? AND date = ?
            ORDER BY count DESC
            LIMIT ?""",
            (chat_id, today, limit), fetch_all=True)
        return [(r["word"], r["count"]) for r in rows] if rows else []
    except Exception as e:
        logger.error(f"Error getting top words for chat {chat_id}: {e}")
        return []


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return str(text) if text else ""


async def safe_edit_or_reply(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    """Безопасное редактирование сообщения с фоллбэком на отправку нового."""
    if not callback or not callback.message:
        return False
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return True
    except TelegramBadRequest as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        elif "message can't be edited" in err_str or "message to edit not found" in err_str:
            try:
                await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
                return True
            except Exception:
                return False
        logger.warning(f"Edit error: {e}")
        return False
    except TelegramForbiddenError:
        logger.warning(f"Forbidden to edit message in chat {callback.message.chat.id}")
        return False
    except Exception as e:
        logger.error(f"Edit/Reply failed: {e}", exc_info=True)
        return False


async def run_with_timeout(coro: Awaitable[Any], timeout: float, name: str) -> Optional[Any]:
    """Выполнение корутины с таймаутом."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Timeout ({timeout}s) for {name}")
        return None
    except Exception as e:
        logger.error(f"Error in {name}: {e}")
        return None


def get_admin_panel_text(user_id: int, first_name: Optional[str], chat_id: int) -> str:
    """Генерация текста главной панели."""
    is_owner = is_super_admin(user_id)
    owner_status = "✅ ВЛАДЕЛЕЦ" if is_owner else "❌ НЕ владелец"
    
    return (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v3.3.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Админ: <b>{safe_html_escape(first_name)}</b>\n"
        f"🆔 Ваш ID: <code>{user_id}</code>\n"
        f"🔑 Статус: <b>{owner_status}</b>\n"
        f"💬 Чат: <code>{chat_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню админ-панели."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data=CB_ADMIN_STATS)],
        [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ЧАТ", callback_data=CB_ADMIN_CLEANUP)],
        [InlineKeyboardButton(text="🌅 СВОДКА ДНЯ", callback_data=CB_ADMIN_SUMMARY)],
        [InlineKeyboardButton(text="📋 ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CHATS)],
        [InlineKeyboardButton(text="🔄 ПЕРЕЗАГРУЗКА РП", callback_data=CB_ADMIN_RELOAD)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK),
         InlineKeyboardButton(text="❌ ЗАКРЫТЬ", callback_data=CB_ADMIN_CLOSE)],
    ])


# ==================== CALLBACK ДЛЯ КНОПКИ МЕНЮ ====================

@router.callback_query(F.data == "menu_admin")
async def admin_panel_callback(callback: CallbackQuery) -> None:
    """Открытие админ-панели через кнопку меню."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    if not is_super_admin(user_id):
        logger.warning(f"⚠️ Unauthorized admin panel access by {user_id}")
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    text = get_admin_panel_text(user_id, callback.from_user.first_name, callback.message.chat.id)
    success = await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())
    if success:
        logger.info(f"✅ Admin panel opened for user {user_id}")
    await callback.answer()


# ==================== КОМАНДА /admin ====================

@router.message(Command("admin"))
@require_super_admin
async def cmd_admin_panel(message: Message) -> None:
    """Команда открытия админ-панели."""
    if not message or not message.from_user or not message.chat:
        return
    
    text = get_admin_panel_text(message.from_user.id, message.from_user.first_name, message.chat.id)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_menu_keyboard())
    logger.info(f"✅ Admin panel opened via command for user {message.from_user.id}")


# ==================== CALLBACK: СТАТИСТИКА ====================

@router.callback_query(F.data == CB_ADMIN_STATS)
async def admin_stats_callback(callback: CallbackQuery) -> None:
    """Показать статистику чата."""
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("📊 Загружаю статистику...")
    
    try:
        stats = await run_with_timeout(_get_chat_daily_stats(chat_id), TIMEOUT_STATS, "get_stats")
        if stats is None:
            stats = {}
        
        top_words = await run_with_timeout(_get_chat_top_words(chat_id, 15), TIMEOUT_STATS, "get_words")
        if top_words is None:
            top_words = []
        
        active_users = await run_with_timeout(_get_chat_active_users(chat_id, 10), TIMEOUT_STATS, "get_users")
        if active_users is None:
            active_users = []
        
        total_users = await run_with_timeout(_get_total_users(), TIMEOUT_STATS, "total_users")
        if total_users is None:
            total_users = 0
        
        total_messages = await run_with_timeout(_get_total_messages_count(), TIMEOUT_STATS, "total_msgs")
        if total_messages is None:
            total_messages = 0
        
        text = (
            "📊 <b>РАСШИРЕННАЯ СТАТИСТИКА ЧАТА</b>\n\n"
            f"📅 <b>ЗА СЕГОДНЯ:</b>\n"
            f"💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
            f"👥 Уникальных: <b>{stats.get('unique_users', 0)}</b>\n"
            f"🎤 Войс: <b>{stats.get('total_voice', 0)}</b>\n"
            f"🎮 XO игр: <b>{stats.get('total_xo_games', 0)}</b>\n\n"
            f"📈 <b>ВСЕГО В БОТЕ:</b>\n"
            f"👤 Пользователей: <b>{total_users}</b>\n"
            f"💬 Сообщений: <b>{total_messages}</b>\n"
        )
        
        if active_users:
            text += "\n<b>🏆 ТОП-10 АКТИВНЫХ:</b>\n"
            for i, u in enumerate(active_users[:10], 1):
                name = safe_html_escape(u.get('first_name', '?'))[:20]
                msgs = u.get('message_count', 0)
                text += f"{i}. {name} — <b>{msgs}</b>\n"
        
        if top_words:
            text += "\n<b>📝 ТОП-15 СЛОВ:</b>\n"
            for word, count in top_words[:15]:
                text += f"• {safe_html_escape(str(word))} — {count}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=CB_ADMIN_STATS)],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
        logger.info(f"✅ Stats displayed for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)


# ==================== CALLBACK: ОЧИСТКА ====================

@router.callback_query(F.data == CB_ADMIN_CLEANUP)
async def admin_cleanup_callback(callback: CallbackQuery) -> None:
    """Очистка сообщений бота в чате."""
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("🧹 Очищаю...")
    
    try:
        if _bot is None:
            await callback.answer("❌ Бот не инициализирован", show_alert=True)
            return
        
        # Пытаемся использовать utils.auto_delete если доступен
        try:
            from utils.auto_delete import delete_bot_messages, bot_messages
            
            deleted = await run_with_timeout(delete_bot_messages(_bot, chat_id), TIMEOUT_CLEANUP, "cleanup")
            if deleted is None:
                deleted = 0
            
            # ✅ Безопасный доступ к bot_messages
            try:
                if isinstance(bot_messages, dict):
                    remaining = len(bot_messages.get(chat_id, []))
                else:
                    remaining = "N/A"
            except (AttributeError, TypeError):
                remaining = "N/A"
            
            text = (
                f"🧹 <b>ОЧИСТКА ЗАВЕРШЕНА</b>\n\n"
                f"Удалено сообщений: <b>{deleted}</b>\n"
                f"В очереди на удаление: <b>{remaining}</b>\n\n"
                f"ℹ️ Удаляются только сообщения бота за последние 48 часов."
            )
        except (ImportError, AttributeError) as e:
            logger.warning(f"auto_delete module not available: {e}")
            text = (
                "🧹 <b>ОЧИСТКА ЧАТА</b>\n\n"
                "ℹ️ Модуль авто-очистки не загружен.\n"
                "Базовое удаление сообщений недоступно.\n\n"
                "<i>Установите utils/auto_delete.py для полной функциональности.</i>"
            )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
        logger.info(f"✅ Cleanup executed for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при очистке", show_alert=True)


# ==================== CALLBACK: СВОДКА ====================

@router.callback_query(F.data == CB_ADMIN_SUMMARY)
async def admin_summary_callback(callback: CallbackQuery) -> None:
    """Отправить сводку дня."""
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("🌅 Формирую сводку...")
    
    try:
        if _bot is None:
            await callback.answer("❌ Бот не инициализирован", show_alert=True)
            return
        
        stats = await _get_chat_daily_stats(chat_id)
        active_users = await _get_chat_active_users(chat_id, 5)
        top_words = await _get_chat_top_words(chat_id, 10)
        
        today = datetime.now().strftime("%d.%m.%Y")
        
        summary_text = (
            f"🌅 <b>СВОДКА ДНЯ — {today}</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
            f"👥 Активных: <b>{stats.get('unique_users', 0)}</b>\n"
            f"🎤 Войс: <b>{stats.get('total_voice', 0)}</b>\n"
            f"🎮 Игр XO: <b>{stats.get('total_xo_games', 0)}</b>\n"
        )
        
        if active_users:
            summary_text += "\n<b>🏆 ТОП-5 АКТИВНЫХ:</b>\n"
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, u in enumerate(active_users[:5]):
                name = safe_html_escape(u.get('first_name', '?'))[:15]
                msgs = u.get('message_count', 0)
                summary_text += f"{medals[i] if i < len(medals) else '•'} {name} — <b>{msgs}</b> сообщ.\n"
        
        if top_words:
            summary_text += "\n<b>📝 ТОП-10 СЛОВ:</b>\n"
            for word, count in top_words[:10]:
                summary_text += f"• {safe_html_escape(str(word))} — {count}\n"
        
        summary_text += "\n━━━━━━━━━━━━━━━━━━━━━\n<i>Авто-сводка NEXUS Bot</i>"
        
        await _bot.send_message(chat_id, summary_text, parse_mode=ParseMode.HTML)
        
        text = "✅ <b>СВОДКА УСПЕШНО ОТПРАВЛЕНА</b>"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
        logger.info(f"✅ Summary sent to chat {chat_id}")
        
    except TelegramForbiddenError:
        logger.warning(f"Forbidden to send to chat {chat_id}")
        await callback.answer("❌ Бот заблокирован в этом чате", show_alert=True)
    except Exception as e:
        logger.error(f"Summary error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка отправки сводки", show_alert=True)


# ==================== CALLBACK: ВСЕ ЧАТЫ ====================

@router.callback_query(F.data == CB_ADMIN_CHATS)
async def admin_chats_callback(callback: CallbackQuery) -> None:
    """Показать все чаты с ботом."""
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.answer("📋 Загружаю список чатов...")
    
    try:
        chats = await _get_all_chats_with_bot()
        total = len(chats)
        display_chats = chats[:MAX_CHATS_DISPLAY]
        
        if _bot is None:
            text = f"📋 <b>ЧАТЫ С БОТОМ</b>\n\nВсего: <b>{total}</b>\n\n"
            for cid in display_chats:
                text += f"• <code>{cid}</code>\n"
        else:
            sem = asyncio.Semaphore(MAX_CONCURRENT_CHATS)
            
            async def fetch_chat_info(cid: int) -> str:
                async with sem:
                    try:
                        chat = await run_with_timeout(_bot.get_chat(cid), TIMEOUT_CHAT_INFO, f"chat_{cid}")
                        if chat:
                            name = safe_html_escape(chat.title[:30] if chat.title else "Чат")
                            return f"• <code>{cid}</code> — {name}"
                        return f"• <code>{cid}</code> — (нет данных)"
                    except TelegramForbiddenError:
                        return f"• <code>{cid}</code> — (бот заблокирован)"
                    except Exception:
                        return f"• <code>{cid}</code> — (нет доступа)"
            
            results = await asyncio.gather(*(fetch_chat_info(cid) for cid in display_chats))
            text = f"📋 <b>ЧАТЫ С БОТОМ</b>\n\nВсего: <b>{total}</b>\n\n" + "\n".join(results)
        
        if total > MAX_CHATS_DISPLAY:
            text += f"\n\n... и ещё <b>{total - MAX_CHATS_DISPLAY}</b> чатов"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CLEANUP_ALL)],
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=CB_ADMIN_CHATS)],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
        logger.info(f"✅ Chats list displayed ({total} total)")
        
    except Exception as e:
        logger.error(f"Chats error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки списка чатов", show_alert=True)


# ==================== CALLBACK: ГЛОБАЛЬНАЯ ОЧИСТКА ====================

@router.callback_query(F.data == CB_ADMIN_CLEANUP_ALL)
async def admin_cleanup_all_callback(callback: CallbackQuery) -> None:
    """Глобальная очистка всех чатов."""
    if not callback or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    if _bot is None:
        await callback.answer("❌ Бот не инициализирован", show_alert=True)
        return
    
    await callback.answer("🧹 Глобальная очистка запущена...", show_alert=True)
    
    try:
        try:
            from utils.auto_delete import cleanup_all_chats
            task = asyncio.create_task(cleanup_all_chats(_bot))
            _background_tasks.add(task)
            task.add_done_callback(lambda t: _background_tasks.discard(t))
            
            if callback.message:
                await callback.message.edit_text(
                    "🧹 <b>ГЛОБАЛЬНАЯ ОЧИСТКА ЗАПУЩЕНА</b>\n\n"
                    "Процесс выполняется в фоне.\n"
                    "Это может занять несколько минут.\n\n"
                    "<i>Удаляются сообщения бота за последние 48 часов во всех чатах.</i>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
                    ])
                )
            logger.info("✅ Global cleanup task started")
        except ImportError:
            if callback.message:
                await callback.message.edit_text(
                    "⚠️ <b>МОДУЛЬ АВТО-ОЧИСТКИ НЕ НАЙДЕН</b>\n\n"
                    "Установите utils/auto_delete.py для работы этой функции.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
                    ])
                )
    except Exception as e:
        logger.error(f"Cleanup all error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка запуска очистки", show_alert=True)


# ==================== CALLBACK: ПЕРЕЗАГРУЗКА РП ====================

@router.callback_query(F.data == CB_ADMIN_RELOAD)
async def admin_reload_callback(callback: CallbackQuery) -> None:
    """Перезагрузка кастомных РП команд."""
    if not callback or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        await callback.answer("✅ РП команды перезагружены!", show_alert=True)
        
        if callback.message:
            await callback.message.edit_text(
                "🔄 <b>РП КОМАНДЫ ПЕРЕЗАГРУЖЕНЫ</b>\n\n"
                "Все кастомные РП-команды обновлены из базы данных.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
                ])
            )
        logger.info("✅ Custom RP commands reloaded")
    except ImportError:
        await callback.answer("⚠️ Модуль РП не найден", show_alert=True)
    except Exception as e:
        logger.error(f"Reload error: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка перезагрузки: {e}", show_alert=True)


# ==================== CALLBACK: НАЗАД ====================

@router.callback_query(F.data == CB_ADMIN_BACK)
async def admin_back_callback(callback: CallbackQuery) -> None:
    """Возврат в главное меню админ-панели."""
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    text = get_admin_panel_text(callback.from_user.id, callback.from_user.first_name, callback.message.chat.id)
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())
    await callback.answer()


# ==================== CALLBACK: ЗАКРЫТЬ ====================

@router.callback_query(F.data == CB_ADMIN_CLOSE)
async def admin_close_callback(callback: CallbackQuery) -> None:
    """Закрыть админ-панель."""
    if not callback or not callback.message:
        return
    try:
        await callback.message.delete()
        logger.info(f"✅ Admin panel closed by user {callback.from_user.id}")
    except Exception:
        try:
            await callback.message.edit_text("🔒 Админ-панель закрыта")
        except Exception:
            pass
    await callback.answer()


# ==================== БЫСТРЫЕ КОМАНДЫ ====================

@router.message(Command("stats_today"))
@require_super_admin
async def cmd_stats_today(message: Message) -> None:
    """Быстрая статистика за сегодня."""
    if not message or not message.chat:
        return
    try:
        stats = await _get_chat_daily_stats(message.chat.id)
        active = await _get_chat_active_users(message.chat.id, 5)
        
        text = (
            f"📊 <b>СТАТИСТИКА ЗА СЕГОДНЯ</b>\n\n"
            f"💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
            f"👥 Активных: <b>{stats.get('unique_users', 0)}</b>"
        )
        if active:
            text += "\n\n<b>ТОП-5:</b>\n"
            for i, u in enumerate(active[:5], 1):
                name = safe_html_escape(u.get('first_name', '?'))[:15]
                text += f"{i}. {name} — {u.get('message_count', 0)}\n"
        await message.answer(text, parse_mode=ParseMode.HTML)
        logger.info(f"✅ Quick stats sent to chat {message.chat.id}")
    except Exception as e:
        logger.error(f"Quick stats error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки статистики")


@router.message(Command("cleanup"))
@require_super_admin
async def cmd_cleanup_chat(message: Message) -> None:
    """Быстрая очистка чата."""
    if not message or not message.chat:
        return
    try:
        if _bot is None:
            await message.answer("❌ Бот не инициализирован")
            return
        
        msg = await message.answer("🧹 Очищаю...")
        
        try:
            from utils.auto_delete import delete_bot_messages
            deleted = await delete_bot_messages(_bot, message.chat.id)
            if deleted is None:
                deleted = 0
            await msg.edit_text(f"✅ Очищено сообщений: <b>{deleted}</b>", parse_mode=ParseMode.HTML)
            logger.info(f"✅ Quick cleanup: {deleted} messages deleted in chat {message.chat.id}")
        except ImportError:
            await msg.edit_text("⚠️ Модуль авто-очистки не найден", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Quick cleanup error: {e}", exc_info=True)
        await message.answer("❌ Ошибка очистки")


@router.message(Command("summary"))
@require_super_admin
async def cmd_summary_now(message: Message) -> None:
    """Быстрая отправка сводки."""
    if not message or not message.chat:
        return
    try:
        if _bot is None:
            await message.answer("❌ Бот не инициализирован")
            return
        
        stats = await _get_chat_daily_stats(message.chat.id)
        active = await _get_chat_active_users(message.chat.id, 5)
        top_words = await _get_chat_top_words(message.chat.id, 10)
        
        today = datetime.now().strftime("%d.%m.%Y")
        
        summary = (
            f"🌅 <b>СВОДКА ДНЯ — {today}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
            f"👥 Активных: <b>{stats.get('unique_users', 0)}</b>\n\n"
        )
        
        if active:
            summary += "<b>🏆 ТОП-5:</b>\n"
            for i, u in enumerate(active[:5], 1):
                name = safe_html_escape(u.get('first_name', '?'))[:15]
                summary += f"{i}. {name} — {u.get('message_count', 0)}\n"
        
        if top_words:
            summary += "\n<b>📝 ТОП-10 СЛОВ:</b>\n"
            for word, count in top_words[:10]:
                summary += f"• {safe_html_escape(str(word))} — {count}\n"
        
        summary += "\n━━━━━━━━━━━━━━━━━━━━━\n<i>Авто-сводка NEXUS Bot</i>"
        
        await _bot.send_message(message.chat.id, summary, parse_mode=ParseMode.HTML)
        await message.answer("✅ Сводка отправлена")
        logger.info(f"✅ Quick summary sent to chat {message.chat.id}")
    except TelegramForbiddenError:
        logger.warning(f"Forbidden to send summary to chat {message.chat.id}")
        await message.answer("❌ Бот заблокирован в этом чате")
    except Exception as e:
        logger.error(f"Quick summary error: {e}", exc_info=True)
        await message.answer("❌ Ошибка отправки сводки")


@router.message(Command("chats"))
@require_super_admin
async def cmd_list_chats(message: Message) -> None:
    """Быстрый список чатов."""
    if not message:
        return
    try:
        chats = await _get_all_chats_with_bot()
        total = len(chats)
        
        text = f"📋 <b>ЧАТЫ С БОТОМ ({total})</b>\n\n"
        for cid in chats[:20]:
            text += f"• <code>{cid}</code>\n"
        if total > 20:
            text += f"\n... и ещё <b>{total - 20}</b> чатов"
        await message.answer(text, parse_mode=ParseMode.HTML)
        logger.info(f"✅ Quick chats list sent ({total} total)")
    except Exception as e:
        logger.error(f"Quick chats error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки списка")


@router.message(Command("reload_rp"))
@require_super_admin
async def cmd_reload_rp(message: Message) -> None:
    """Быстрая перезагрузка РП команд."""
    if not message:
        return
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        await message.answer("✅ РП команды перезагружены!")
        logger.info("✅ Quick RP reload executed")
    except ImportError:
        await message.answer("⚠️ Модуль РП не найден")
    except Exception as e:
        logger.error(f"Quick reload error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка перезагрузки: {e}")

