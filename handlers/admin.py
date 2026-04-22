#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Файл: handlers/admin.py
Назначение: Админ-панель для владельца/разработчика Nexus Bot
Доступ: Только для SUPER_ADMIN_IDS из config.py
Версия: 2.0.0-production
Последнее изменение: 2026-04-22
"""

# === SYSTEM IMPORTS ===
import asyncio
import html
import logging
from functools import wraps
from typing import Optional, List, Dict, Any, Callable, Awaitable, Union

# === THIRD-PARTY IMPORTS ===
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import (
    TelegramAPIError, 
    TelegramBadRequest, 
    TelegramForbiddenError,
    TelegramRetryAfter
)

# === PROJECT IMPORTS ===
from config import ADMIN_IDS, SUPER_ADMIN_IDS
from database import db
from utils.auto_delete import (
    cleanup_all_chats,
    delete_bot_messages,
    get_chat_daily_stats,
    get_chat_top_words,
    get_chat_active_users,
    send_daily_summary,
    bot_messages,
    add_bot_message
)

# === MODULE CONSTANTS ===
logger = logging.getLogger(__name__)
router = Router(name="admin_panel")

# Константы callback_data для типобезопасности и предотвращения опечаток
CB_ADMIN_MENU = "admin_menu"
CB_ADMIN_STATS = "admin_stats"
CB_ADMIN_CLEANUP = "admin_cleanup"
CB_ADMIN_SUMMARY = "admin_summary"
CB_ADMIN_CHATS = "admin_chats"
CB_ADMIN_SEARCH = "admin_search"
CB_ADMIN_BALANCE = "admin_balance"
CB_ADMIN_BROADCAST = "admin_broadcast"
CB_ADMIN_RELOAD = "admin_reload"
CB_ADMIN_BACK = "admin_back"
CB_ADMIN_CLOSE = "admin_close"
CB_ADMIN_CLEANUP_ALL = "admin_cleanup_all"

# Таймауты для операций (в секундах)
TIMEOUT_STATS = 10.0
TIMEOUT_CLEANUP = 30.0
TIMEOUT_CHAT_INFO = 5.0

# Максимальное количество элементов в списках
MAX_CHATS_DISPLAY = 20
MAX_TOP_WORDS = 15
MAX_ACTIVE_USERS = 10

# === PRIVATE HELPERS ===

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML с защитой от XSS."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def is_super_admin(user_id: Optional[int]) -> bool:
    """
    Проверка прав супер-админа с защитой от пустых списков.
    
    Args:
        user_id: ID пользователя для проверки
        
    Returns:
        True если пользователь супер-админ, иначе False
    """
    if user_id is None:
        return False
    if not SUPER_ADMIN_IDS:
        logger.critical("SUPER_ADMIN_IDS is empty! No admin access configured.")
        return False
    return user_id in SUPER_ADMIN_IDS


def is_admin(user_id: Optional[int]) -> bool:
    """
    Проверка прав администратора (включает супер-админов).
    
    Args:
        user_id: ID пользователя для проверки
        
    Returns:
        True если пользователь админ, иначе False
    """
    if user_id is None:
        return False
    return user_id in ADMIN_IDS or is_super_admin(user_id)


def require_super_admin(func: Callable) -> Callable:
    """
    Декоратор для проверки прав супер-админа с логированием.
    
    Args:
        func: Асинхронная функция-обработчик
        
    Returns:
        Обернутая функция с проверкой прав
    """
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs) -> Any:
        # Защита от None
        if message is None:
            logger.warning("require_super_admin called with None message")
            return
        
        if message.from_user is None:
            logger.warning("require_super_admin: message.from_user is None")
            return
        
        user_id = message.from_user.id
        
        if not is_super_admin(user_id):
            logger.warning(
                f"Unauthorized admin access attempt | "
                f"user_id={user_id} | "
                f"username=@{message.from_user.username} | "
                f"chat_id={message.chat.id if message.chat else 'N/A'}"
            )
            try:
                await message.answer(
                    "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
                    "Эта команда только для владельца бота.",
                    parse_mode=ParseMode.HTML
                )
            except TelegramAPIError as e:
                logger.error(f"Failed to send access denied message: {e}")
            return
        
        logger.info(f"Admin access granted for user {user_id}")
        return await func(message, *args, **kwargs)
    
    return wrapper


def _build_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает стандартную клавиатуру админ-меню."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data=CB_ADMIN_STATS)],
        [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ЧАТ", callback_data=CB_ADMIN_CLEANUP)],
        [InlineKeyboardButton(text="🌅 СВОДКА ДНЯ", callback_data=CB_ADMIN_SUMMARY)],
        [InlineKeyboardButton(text="📋 ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CHATS)],
        [InlineKeyboardButton(text="🔍 ПОИСК ПОЛЬЗОВАТЕЛЯ", callback_data=CB_ADMIN_SEARCH)],
        [InlineKeyboardButton(text="💰 УПРАВЛЕНИЕ БАЛАНСОМ", callback_data=CB_ADMIN_BALANCE)],
        [InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data=CB_ADMIN_BROADCAST)],
        [InlineKeyboardButton(text="🔄 ПЕРЕЗАГРУЗКА КОМАНД", callback_data=CB_ADMIN_RELOAD)],
        [InlineKeyboardButton(text="❌ ЗАКРЫТЬ", callback_data=CB_ADMIN_CLOSE)],
    ])


def _build_admin_panel_text(user_id: int, first_name: str, chat_id: int) -> str:
    """Генерирует текст для админ-панели."""
    return (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v5.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Владелец: <b>{safe_html_escape(first_name)}</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💬 Чат: <code>{chat_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )


async def _safe_edit_or_reply(
    callback: CallbackQuery,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
    chat_id: Optional[int] = None
) -> bool:
    """
    Безопасное редактирование сообщения с fallback на новое.
    
    Args:
        callback: Объект callback запроса
        text: Текст для отображения
        markup: Клавиатура (опционально)
        chat_id: ID чата для fallback сообщения
        
    Returns:
        True если сообщение отредактировано, False если создано новое
    """
    if callback.message is None:
        return False
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        logger.warning(f"Edit text failed with bad request: {e}")
    except TelegramRetryAfter as e:
        logger.warning(f"Rate limited, retry after {e.retry_after}s")
        await asyncio.sleep(e.retry_after)
        try:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            return True
        except Exception as retry_error:
            logger.error(f"Retry edit failed: {retry_error}")
    except TelegramAPIError as e:
        logger.error(f"Telegram API error in edit: {e}")
    
    # Fallback: отправляем новое сообщение
    try:
        target_chat = chat_id or (callback.message.chat.id if callback.message.chat else None)
        if target_chat and callback.bot:
            msg = await callback.bot.send_message(
                target_chat,
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )
            add_bot_message(target_chat, msg.message_id)
    except Exception as e:
        logger.error(f"Fallback send failed: {e}")
    
    return False


async def _run_with_timeout(coro: Awaitable, timeout: float, operation_name: str) -> Any:
    """
    Выполняет корутину с таймаутом.
    
    Args:
        coro: Корутина для выполнения
        timeout: Таймаут в секундах
        operation_name: Название операции для логирования
        
    Returns:
        Результат корутины или None при таймауте
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Timeout ({timeout}s) exceeded for operation: {operation_name}")
        return None
    except Exception as e:
        logger.error(f"Error in {operation_name}: {e}")
        return None


def _create_background_task(coro: Awaitable, task_name: str) -> None:
    """
    Создает фоновую задачу с обработкой исключений.
    
    Args:
        coro: Корутина для выполнения
        task_name: Имя задачи для логирования
    """
    async def _wrapper():
        try:
            await coro
        except Exception as e:
            logger.error(f"Background task '{task_name}' failed: {e}", exc_info=True)
    
    asyncio.create_task(_wrapper())
    logger.info(f"Background task '{task_name}' started")


# === PUBLIC HANDLERS ===

@router.message(Command("admin"))
@require_super_admin
async def cmd_admin_panel(message: Message) -> None:
    """Главная панель администратора."""
    if message is None:
        return
    
    # Проверка наличия чата (может быть вызвано из ЛС)
    if message.chat is None:
        logger.warning("Admin command called without chat context")
        await message.answer("❌ Эта команда должна выполняться в чате.")
        return
    
    if message.from_user is None:
        return
    
    try:
        text = _build_admin_panel_text(
            message.from_user.id,
            message.from_user.first_name or "Владелец",
            message.chat.id
        )
        keyboard = _build_admin_menu_keyboard()
        
        msg = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        add_bot_message(message.chat.id, msg.message_id)
        logger.info(f"Admin panel opened for user {message.from_user.id} in chat {message.chat.id}")
        
    except TelegramForbiddenError:
        logger.warning(f"Bot blocked or kicked from chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send admin panel: {e}")
        await message.answer("❌ Не удалось открыть админ-панель. Попробуйте позже.")


# === CALLBACK HANDLERS ===

@router.callback_query(F.data == CB_ADMIN_STATS)
async def admin_stats_callback(callback: CallbackQuery) -> None:
    """Показать расширенную статистику чата."""
    # Защита от None
    if callback is None or callback.message is None or callback.from_user is None:
        logger.warning("admin_stats_callback: invalid callback state")
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        logger.warning(f"Unauthorized stats access: user={callback.from_user.id}")
        return
    
    if callback.message.chat is None:
        await callback.answer("❌ Не удалось определить чат", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("📊 Загружаю статистику...")
    
    try:
        # Получаем статистику с таймаутами
        stats = await _run_with_timeout(
            get_chat_daily_stats(chat_id),
            TIMEOUT_STATS,
            "get_chat_daily_stats"
        ) or {}
        
        top_words = await _run_with_timeout(
            get_chat_top_words(chat_id, MAX_TOP_WORDS),
            TIMEOUT_STATS,
            "get_chat_top_words"
        ) or []
        
        active_users = await _run_with_timeout(
            get_chat_active_users(chat_id, MAX_ACTIVE_USERS),
            TIMEOUT_STATS,
            "get_chat_active_users"
        ) or []
        
        # Дополнительная статистика из БД
        total_users = await _run_with_timeout(
            db.get_total_users(),
            TIMEOUT_STATS,
            "db.get_total_users"
        ) or 0
        
        total_messages_all_time = await _run_with_timeout(
            db.get_total_messages_count(),
            TIMEOUT_STATS,
            "db.get_total_messages_count"
        ) or 0
        
        chat_members_count = await _run_with_timeout(
            db.get_chat_members_count(chat_id),
            TIMEOUT_STATS,
            "db.get_chat_members_count"
        ) or 0
        
        # Формируем текст
        text = (
            "📊 <b>РАСШИРЕННАЯ СТАТИСТИКА ЧАТА</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 <b>ЗА СЕГОДНЯ:</b>\n"
            f"💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
            f"👥 Уникальных пользователей: <b>{stats.get('unique_users', 0)}</b>\n\n"
            f"📈 <b>ВСЕГО:</b>\n"
            f"👤 Пользователей в боте: <b>{total_users}</b>\n"
            f"💬 Сообщений всего: <b>{total_messages_all_time}</b>\n"
            f"👥 Участников в чате: <b>{chat_members_count}</b>\n\n"
        )
        
        if active_users:
            text += "<b>🏆 ТОП-10 АКТИВНЫХ СЕГОДНЯ:</b>\n"
            for i, user in enumerate(active_users[:10], 1):
                name = safe_html_escape(user.get('first_name', 'Пользователь'))[:20]
                msgs = user.get('message_count', 0)
                text += f"{i}. {name} — <b>{msgs}</b>\n"
            text += "\n"
        
        if top_words:
            text += "<b>📝 ТОП-15 СЛОВ:</b>\n"
            for word, count in top_words[:15]:
                text += f"• {safe_html_escape(word)} — {count}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=CB_ADMIN_STATS)],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        
        await _safe_edit_or_reply(callback, text, keyboard)
        
    except Exception as e:
        logger.error(f"Stats generation failed: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)
    
    finally:
        try:
            await callback.answer()
        except Exception:
            pass


@router.callback_query(F.data == CB_ADMIN_CLEANUP)
async def admin_cleanup_callback(callback: CallbackQuery) -> None:
    """Очистка сообщений бота в текущем чате."""
    if callback is None or callback.message is None or callback.from_user is None:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    if callback.message.chat is None:
        await callback.answer("❌ Не удалось определить чат", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("🧹 Начинаю очистку...")
    
    try:
        deleted = await _run_with_timeout(
            delete_bot_messages(callback.bot, chat_id),
            TIMEOUT_CLEANUP,
            "delete_bot_messages"
        ) or 0
        
        remaining = len(bot_messages.get(chat_id, []))
        
        text = (
            "🧹 <b>ОЧИСТКА ЗАВЕРШЕНА</b>\n\n"
            f"Удалено сообщений бота: <b>{deleted}</b>\n"
            f"Оставшиеся в очереди: <b>{remaining}</b>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        
        await _safe_edit_or_reply(callback, text, keyboard, chat_id)
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при очистке", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_SUMMARY)
async def admin_summary_callback(callback: CallbackQuery) -> None:
    """Принудительно отправить сводку дня."""
    if callback is None or callback.message is None or callback.from_user is None:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    if callback.message.chat is None:
        await callback.answer("❌ Не удалось определить чат", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("🌅 Отправляю сводку...")
    
    try:
        await _run_with_timeout(
            send_daily_summary(callback.bot, chat_id),
            TIMEOUT_STATS,
            "send_daily_summary"
        )
        
        text = "✅ <b>СВОДКА ОТПРАВЛЕНА</b>\n\nСводка дня отправлена в чат."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        
        await _safe_edit_or_reply(callback, text, keyboard, chat_id)
        
    except Exception as e:
        logger.error(f"Summary send failed: {e}", exc_info=True)
        await callback.answer("❌ Не удалось отправить сводку", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_CHATS)
async def admin_chats_callback(callback: CallbackQuery) -> None:
    """Показать все чаты с ботом."""
    if callback is None or callback.message is None or callback.from_user is None:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.answer("📋 Загружаю список чатов...")
    
    try:
        chats = await _run_with_timeout(
            db.get_all_chats_with_bot(),
            TIMEOUT_STATS,
            "db.get_all_chats_with_bot"
        )
        
        if chats is None:
            await callback.answer("❌ Не удалось загрузить список чатов", show_alert=True)
            return
        
        text = "📋 <b>ЧАТЫ С БОТОМ</b>\n\n"
        text += f"Всего чатов: <b>{len(chats)}</b>\n\n"
        
        for i, chat_id in enumerate(chats[:MAX_CHATS_DISPLAY], 1):
            try:
                chat_info = await _run_with_timeout(
                    callback.bot.get_chat(chat_id),
                    TIMEOUT_CHAT_INFO,
                    f"get_chat({chat_id})"
                )
                
                if chat_info:
                    chat_name = chat_info.title or chat_info.full_name or f"Чат {chat_id}"
                    text += f"{i}. <code>{chat_id}</code> — {safe_html_escape(chat_name[:30])}\n"
                else:
                    text += f"{i}. <code>{chat_id}</code> — (нет доступа)\n"
            except TelegramForbiddenError:
                text += f"{i}. <code>{chat_id}</code> — (бот заблокирован)\n"
            except Exception as e:
                logger.warning(f"Failed to get chat info for {chat_id}: {e}")
                text += f"{i}. <code>{chat_id}</code> — (ошибка доступа)\n"
        
        if len(chats) > MAX_CHATS_DISPLAY:
            text += f"\n... и ещё {len(chats) - MAX_CHATS_DISPLAY} чатов"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CLEANUP_ALL)],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        
        await _safe_edit_or_reply(callback, text, keyboard)
        
    except Exception as e:
        logger.error(f"Chat list generation failed: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки списка чатов", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_CLEANUP_ALL)
async def admin_cleanup_all_callback(callback: CallbackQuery) -> None:
    """Очистить ВСЕ чаты."""
    if callback is None or callback.from_user is None:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.answer("🧹 Глобальная очистка запущена...", show_alert=True)
    
    # Запускаем в фоне с обработкой ошибок
    _create_background_task(cleanup_all_chats(callback.bot), "global_cleanup")
    
    if callback.message:
        try:
            await callback.message.edit_text(
                "🧹 <b>ГЛОБАЛЬНАЯ ОЧИСТКА ЗАПУЩЕНА</b>\n\n"
                "Очистка всех чатов запущена в фоновом режиме.\n"
                "Результаты будут в логах.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning(f"Failed to edit cleanup all message: {e}")


@router.callback_query(F.data == CB_ADMIN_BACK)
async def admin_back_callback(callback: CallbackQuery) -> None:
    """Вернуться в главное меню админа."""
    if callback is None or callback.message is None or callback.from_user is None:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    if callback.message.chat is None:
        return
    
    text = _build_admin_panel_text(
        callback.from_user.id,
        callback.from_user.first_name or "Владелец",
        callback.message.chat.id
    )
    keyboard = _build_admin_menu_keyboard()
    
    await _safe_edit_or_reply(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == CB_ADMIN_CLOSE)
async def admin_close_callback(callback: CallbackQuery) -> None:
    """Закрыть админ-панель."""
    if callback is None or callback.message is None:
        return
    
    try:
        await callback.message.delete()
        logger.info("Admin panel closed")
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e).lower():
            logger.debug("Admin panel already deleted")
        else:
            logger.warning(f"Failed to delete admin panel: {e}")
            try:
                await callback.message.edit_text("🔒 Админ-панель закрыта")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Unexpected error closing admin panel: {e}")
    
    await callback.answer()


# === STUB HANDLERS (GENERATED) ===

_STUB_CONFIGS = {
    CB_ADMIN_SEARCH: ("🔍", "Функция поиска пользователя в разработке"),
    CB_ADMIN_BALANCE: ("💰", "Управление балансом в разработке"),
    CB_ADMIN_BROADCAST: ("📢", "Рассылка в разработке"),
}

def _create_stub_handler(callback_data: str, emoji: str, message: str):
    """Фабрика для создания заглушек."""
    @router.callback_query(F.data == callback_data)
    async def stub_handler(callback: CallbackQuery) -> None:
        if callback is None or callback.from_user is None:
            return
        
        if not is_super_admin(callback.from_user.id):
            await callback.answer("❌ Доступ запрещён", show_alert=True)
            return
        
        await callback.answer(f"{emoji} {message}", show_alert=True)
    
    return stub_handler

# Регистрируем заглушки
for cb_data, (emoji, msg) in _STUB_CONFIGS.items():
    _create_stub_handler(cb_data, emoji, msg)


@router.callback_query(F.data == CB_ADMIN_RELOAD)
async def admin_reload_callback(callback: CallbackQuery) -> None:
    """Перезагрузка кастомных РП команд."""
    if callback is None or callback.from_user is None:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        
        await _run_with_timeout(
            load_custom_rp_commands(),
            TIMEOUT_STATS,
            "load_custom_rp_commands"
        )
        
        await callback.answer("✅ Кастомные РП команды перезагружены!", show_alert=True)
        logger.info(f"Custom RP commands reloaded by user {callback.from_user.id}")
        
    except ImportError as e:
        logger.error(f"Failed to import smart_commands: {e}")
        await callback.answer("❌ Модуль команд недоступен", show_alert=True)
    except Exception as e:
        logger.error(f"Reload custom RP failed: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка перезагрузки", show_alert=True)


# === QUICK COMMANDS ===

@router.message(Command("stats_today"))
@require_super_admin
async def cmd_stats_today(message: Message) -> None:
    """Быстрая команда: статистика за сегодня."""
    if message is None or message.chat is None:
        return
    
    try:
        chat_id = message.chat.id
        
        stats = await _run_with_timeout(
            get_chat_daily_stats(chat_id),
            TIMEOUT_STATS,
            "get_chat_daily_stats"
        ) or {}
        
        active_users = await _run_with_timeout(
            get_chat_active_users(chat_id, 5),
            TIMEOUT_STATS,
            "get_chat_active_users"
        ) or []
        
        text = (
            "📊 <b>СТАТИСТИКА ЗА СЕГОДНЯ</b>\n\n"
            f"💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
            f"👥 Активных: <b>{stats.get('unique_users', 0)}</b>\n\n"
        )
        
        if active_users:
            text += "<b>ТОП-5:</b>\n"
            for i, user in enumerate(active_users[:5], 1):
                name = safe_html_escape(user.get('first_name', '?'))[:15]
                msgs = user.get('message_count', 0)
                text += f"{i}. {name} — {msgs}\n"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Quick stats failed: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки статистики")


@router.message(Command("cleanup"))
@require_super_admin
async def cmd_cleanup_chat(message: Message) -> None:
    """Быстрая команда: очистить чат."""
    if message is None or message.chat is None:
        return
    
    chat_id = message.chat.id
    
    try:
        msg = await message.answer("🧹 Очищаю сообщения бота...")
        add_bot_message(chat_id, msg.message_id)
        
        deleted = await _run_with_timeout(
            delete_bot_messages(message.bot, chat_id),
            TIMEOUT_CLEANUP,
            "delete_bot_messages"
        ) or 0
        
        await msg.edit_text(f"✅ Очищено сообщений: <b>{deleted}</b>", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Quick cleanup failed: {e}", exc_info=True)
        await message.answer("❌ Ошибка при очистке")


@router.message(Command("summary"))
@require_super_admin
async def cmd_summary_now(message: Message) -> None:
    """Быстрая команда: отправить сводку."""
    if message is None or message.chat is None:
        return
    
    try:
        await _run_with_timeout(
            send_daily_summary(message.bot, message.chat.id),
            TIMEOUT_STATS,
            "send_daily_summary"
        )
        await message.answer("✅ Сводка отправлена")
        
    except Exception as e:
        logger.error(f"Quick summary failed: {e}", exc_info=True)
        await message.answer("❌ Ошибка отправки сводки")


@router.message(Command("chats"))
@require_super_admin
async def cmd_list_chats(message: Message) -> None:
    """Быстрая команда: список чатов."""
    if message is None:
        return
    
    try:
        chats = await _run_with_timeout(
            db.get_all_chats_with_bot(),
            TIMEOUT_STATS,
            "db.get_all_chats_with_bot"
        )
        
        if chats is None:
            await message.answer("❌ Не удалось загрузить список чатов")
            return
        
        text = f"📋 <b>ЧАТЫ С БОТОМ ({len(chats)})</b>\n\n"
        
        for chat_id in chats[:15]:
            text += f"• <code>{chat_id}</code>\n"
        
        if len(chats) > 15:
            text += f"\n... и ещё {len(chats) - 15}"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Quick chats list failed: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки чатов")


@router.message(Command("reload_rp"))
@require_super_admin
async def cmd_reload_rp(message: Message) -> None:
    """Быстрая команда: перезагрузить РП команды."""
    if message is None:
        return
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        
        await _run_with_timeout(
            load_custom_rp_commands(),
            TIMEOUT_STATS,
            "load_custom_rp_commands"
        )
        
        await message.answer("✅ Кастомные РП команды перезагружены!")
        logger.info(f"Custom RP commands reloaded via quick command by {message.from_user.id}")
        
    except ImportError as e:
        logger.error(f"Failed to import smart_commands: {e}")
        await message.answer("❌ Модуль команд недоступен")
    except Exception as e:
        logger.error(f"Quick reload failed: {e}", exc_info=True)
        await message.answer("❌ Ошибка перезагрузки")


# === MODULE EXPORT ===

def get_handlers() -> List[Router]:
    """
    Экспорт роутера для регистрации в bot.py.
    
    Returns:
        Список с роутером админ-панели
    """
    return [router]


# === TESTS ===

if __name__ == "__main__":
    import unittest
    from unittest.mock import AsyncMock, MagicMock, patch
    
    class TestAdminModule(unittest.IsolatedAsyncioTestCase):
        """Unit тесты для модуля admin."""
        
        def test_is_super_admin_with_valid_user(self):
            """Тест: валидный супер-админ."""
            if SUPER_ADMIN_IDS:
                self.assertTrue(is_super_admin(SUPER_ADMIN_IDS[0]))
        
        def test_is_super_admin_with_invalid_user(self):
            """Тест: невалидный пользователь."""
            self.assertFalse(is_super_admin(999999999))
        
        def test_is_super_admin_with_none(self):
            """Тест: None вместо user_id."""
            self.assertFalse(is_super_admin(None))
        
        def test_safe_html_escape_with_none(self):
            """Тест: экранирование None."""
            self.assertEqual(safe_html_escape(None), "")
        
        def test_safe_html_escape_with_html(self):
            """Тест: экранирование HTML."""
            self.assertEqual(safe_html_escape("<script>"), "&lt;script&gt;")
        
        def test_build_admin_menu_keyboard(self):
            """Тест: создание клавиатуры."""
            keyboard = _build_admin_menu_keyboard()
            self.assertIsInstance(keyboard, InlineKeyboardMarkup)
            self.assertEqual(len(keyboard.inline_keyboard), 9)
        
        def test_build_admin_panel_text(self):
            """Тест: генерация текста панели."""
            text = _build_admin_panel_text(123, "TestUser", 456)
            self.assertIn("123", text)
            self.assertIn("TestUser", text)
            self.assertIn("456", text)
        
        @patch('handlers.admin.is_super_admin', return_value=True)
        async def test_require_super_admin_decorator(self, mock_is_admin):
            """Тест: декоратор проверки прав."""
            @require_super_admin
            async def test_handler(msg):
                return "success"
            
            mock_msg = MagicMock()
            mock_msg.from_user.id = 123
            mock_msg.chat.id = 456
            
            result = await test_handler(mock_msg)
            self.assertEqual(result, "success")
    
    # Запуск тестов
    unittest.main(verbosity=2)
