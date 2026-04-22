#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/admin.py
# ВЕРСИЯ: 3.0.0-full-fixed
# ОПИСАНИЕ: Админ-панель — ПОЛНОСТЬЮ РАБОЧАЯ
# ============================================

import asyncio
import html
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramBadRequest

from database import db, DatabaseError
from config import ADMIN_IDS, SUPER_ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

TIMEOUT_STATS = 10.0
TIMEOUT_CLEANUP = 30.0
TIMEOUT_CHAT_INFO = 5.0
MAX_CHATS_DISPLAY = 20
MAX_TOP_WORDS = 15
MAX_ACTIVE_USERS = 10

# Callback данные
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

# ==================== ПРОВЕРКА ПРАВ ====================

def is_super_admin(user_id: Optional[int]) -> bool:
    """Проверка прав супер-админа."""
    if user_id is None:
        return False
    if not SUPER_ADMIN_IDS:
        return False
    return user_id in SUPER_ADMIN_IDS


def require_super_admin(func):
    """Декоратор для проверки прав."""
    async def wrapper(message: Message, *args, **kwargs):
        if not message or not message.from_user:
            return
        if not is_super_admin(message.from_user.id):
            await message.answer("❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\nЭта команда только для владельца бота.", parse_mode=ParseMode.HTML)
            return
        return await func(message, *args, **kwargs)
    return wrapper


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try: return html.escape(str(text))
    except: return ""

def format_number(num: Any) -> str:
    if num is None: return "0"
    try: return f"{int(num):,}".replace(",", " ")
    except: return "0"

async def safe_edit_or_reply(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Безопасное редактирование сообщения."""
    if not callback or not callback.message:
        return
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
        else:
            logger.warning(f"Edit error: {e}")
            try:
                await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            except:
                pass
    except Exception as e:
        logger.error(f"Edit failed: {e}")

async def run_with_timeout(coro, timeout: float, name: str) -> Any:
    """Выполнение с таймаутом."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Timeout ({timeout}s) for {name}")
        return None
    except Exception as e:
        logger.error(f"Error in {name}: {e}")
        return None


# ==================== ГЛАВНОЕ МЕНЮ АДМИНА ====================

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data=CB_ADMIN_STATS)],
        [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ЧАТ", callback_data=CB_ADMIN_CLEANUP)],
        [InlineKeyboardButton(text="🌅 СВОДКА ДНЯ", callback_data=CB_ADMIN_SUMMARY)],
        [InlineKeyboardButton(text="📋 ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CHATS)],
        [InlineKeyboardButton(text="🔄 ПЕРЕЗАГРУЗКА РП", callback_data=CB_ADMIN_RELOAD)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu"),
         InlineKeyboardButton(text="❌ ЗАКРЫТЬ", callback_data=CB_ADMIN_CLOSE)],
    ])


@router.message(Command("admin"))
@require_super_admin
async def cmd_admin_panel(message: Message) -> None:
    """Главная панель администратора."""
    if not message or not message.from_user or not message.chat:
        return
    
    text = (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v5.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Владелец: <b>{safe_html_escape(message.from_user.first_name)}</b>\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"💬 Чат: <code>{message.chat.id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_menu_keyboard())


# ==================== CALLBACK HANDLERS ====================

@router.callback_query(F.data == CB_ADMIN_STATS)
async def admin_stats_callback(callback: CallbackQuery) -> None:
    """Статистика чата."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("📊 Загружаю статистику...")
    
    try:
        # Получаем данные из БД
        from utils.auto_delete import get_chat_daily_stats, get_chat_top_words, get_chat_active_users
        
        stats = await run_with_timeout(get_chat_daily_stats(chat_id), TIMEOUT_STATS, "get_stats")
        top_words = await run_with_timeout(get_chat_top_words(chat_id, MAX_TOP_WORDS), TIMEOUT_STATS, "get_words")
        active_users = await run_with_timeout(get_chat_active_users(chat_id, MAX_ACTIVE_USERS), TIMEOUT_STATS, "get_users")
        
        total_users = await run_with_timeout(db.get_total_users(), TIMEOUT_STATS, "total_users") if db else 0
        total_messages = await run_with_timeout(db.get_total_messages_count(), TIMEOUT_STATS, "total_msgs") if db else 0
        
        stats = stats or {}
        text = (
            "📊 <b>РАСШИРЕННАЯ СТАТИСТИКА ЧАТА</b>\n\n"
            f"📅 <b>ЗА СЕГОДНЯ:</b>\n"
            f"💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
            f"👥 Уникальных: <b>{stats.get('unique_users', 0)}</b>\n\n"
            f"📈 <b>ВСЕГО:</b>\n"
            f"👤 В боте: <b>{total_users or 0}</b>\n"
            f"💬 Сообщений: <b>{total_messages or 0}</b>\n"
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
                text += f"• {safe_html_escape(word)} — {count}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=CB_ADMIN_STATS)],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        
        await safe_edit_or_reply(callback, text, keyboard)
        
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_CLEANUP)
async def admin_cleanup_callback(callback: CallbackQuery) -> None:
    """Очистка сообщений бота."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("🧹 Очищаю...")
    
    try:
        from utils.auto_delete import delete_bot_messages, bot_messages
        
        deleted = await run_with_timeout(delete_bot_messages(callback.bot, chat_id), TIMEOUT_CLEANUP, "cleanup")
        remaining = len(bot_messages.get(chat_id, []))
        
        text = f"🧹 <b>ОЧИСТКА ЗАВЕРШЕНА</b>\n\nУдалено: <b>{deleted or 0}</b>\nВ очереди: <b>{remaining}</b>"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_SUMMARY)
async def admin_summary_callback(callback: CallbackQuery) -> None:
    """Отправить сводку дня."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    chat_id = callback.message.chat.id
    await callback.answer("🌅 Отправляю...")
    
    try:
        from utils.auto_delete import send_daily_summary
        await send_daily_summary(callback.bot, chat_id)
        
        text = "✅ <b>СВОДКА ОТПРАВЛЕНА</b>"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
        
    except Exception as e:
        logger.error(f"Summary error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_CHATS)
async def admin_chats_callback(callback: CallbackQuery) -> None:
    """Список всех чатов."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.answer("📋 Загружаю...")
    
    try:
        chats = await db.get_all_chats_with_bot() if db else []
        
        text = f"📋 <b>ЧАТЫ С БОТОМ</b>\n\nВсего: <b>{len(chats)}</b>\n\n"
        
        for i, cid in enumerate(chats[:MAX_CHATS_DISPLAY], 1):
            try:
                info = await run_with_timeout(callback.bot.get_chat(cid), TIMEOUT_CHAT_INFO, f"chat_{cid}")
                name = info.title if info and info.title else f"Чат {cid}"
                text += f"{i}. <code>{cid}</code> — {safe_html_escape(name[:30])}\n"
            except TelegramForbiddenError:
                text += f"{i}. <code>{cid}</code> — (бот заблокирован)\n"
            except Exception:
                text += f"{i}. <code>{cid}</code> — (нет доступа)\n"
        
        if len(chats) > MAX_CHATS_DISPLAY:
            text += f"\n... и ещё {len(chats) - MAX_CHATS_DISPLAY}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CLEANUP_ALL)],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
        
    except Exception as e:
        logger.error(f"Chats error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_CLEANUP_ALL)
async def admin_cleanup_all_callback(callback: CallbackQuery) -> None:
    """Глобальная очистка."""
    if not callback or not callback.from_user:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.answer("🧹 Глобальная очистка запущена...", show_alert=True)
    
    try:
        from utils.auto_delete import cleanup_all_chats
        asyncio.create_task(cleanup_all_chats(callback.bot))
        
        if callback.message:
            await callback.message.edit_text(
                "🧹 <b>ГЛОБАЛЬНАЯ ОЧИСТКА ЗАПУЩЕНА</b>\n\nПроцесс выполняется в фоне.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Cleanup all error: {e}")


@router.callback_query(F.data == CB_ADMIN_RELOAD)
async def admin_reload_callback(callback: CallbackQuery) -> None:
    """Перезагрузка кастомных РП."""
    if not callback or not callback.from_user:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        await callback.answer("✅ РП команды перезагружены!", show_alert=True)
    except Exception as e:
        logger.error(f"Reload error: {e}")
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data == CB_ADMIN_BACK)
async def admin_back_callback(callback: CallbackQuery) -> None:
    """Возврат в меню админа."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    text = (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v5.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Владелец: <b>{safe_html_escape(callback.from_user.first_name)}</b>\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n"
        f"💬 Чат: <code>{callback.message.chat.id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == CB_ADMIN_CLOSE)
async def admin_close_callback(callback: CallbackQuery) -> None:
    """Закрыть админ-панель."""
    if not callback or not callback.message:
        return
    try:
        await callback.message.delete()
    except:
        try:
            await callback.message.edit_text("🔒 Админ-панель закрыта")
        except:
            pass
    await callback.answer()


# ==================== ЗАГЛУШКИ ====================

@router.callback_query(F.data == CB_ADMIN_SEARCH)
async def admin_search_stub(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    await callback.answer("🔍 В разработке", show_alert=True)

@router.callback_query(F.data == CB_ADMIN_BALANCE)
async def admin_balance_stub(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    await callback.answer("💰 В разработке", show_alert=True)

@router.callback_query(F.data == CB_ADMIN_BROADCAST)
async def admin_broadcast_stub(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    await callback.answer("📢 В разработке", show_alert=True)


# ==================== БЫСТРЫЕ КОМАНДЫ ====================

@router.message(Command("stats_today"))
@require_super_admin
async def cmd_stats_today(message: Message) -> None:
    if not message or not message.chat: return
    try:
        from utils.auto_delete import get_chat_daily_stats, get_chat_active_users
        stats = await get_chat_daily_stats(message.chat.id)
        active = await get_chat_active_users(message.chat.id, 5)
        
        text = f"📊 <b>СТАТИСТИКА ЗА СЕГОДНЯ</b>\n\n💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n👥 Активных: <b>{stats.get('unique_users', 0)}</b>"
        if active:
            text += "\n\n<b>ТОП-5:</b>\n"
            for i, u in enumerate(active[:5], 1):
                name = safe_html_escape(u.get('first_name', '?'))[:15]
                text += f"{i}. {name} — {u.get('message_count', 0)}\n"
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Quick stats error: {e}")
        await message.answer("❌ Ошибка")

@router.message(Command("cleanup"))
@require_super_admin
async def cmd_cleanup_chat(message: Message) -> None:
    if not message or not message.chat: return
    try:
        from utils.auto_delete import delete_bot_messages
        msg = await message.answer("🧹 Очищаю...")
        deleted = await delete_bot_messages(message.bot, message.chat.id)
        await msg.edit_text(f"✅ Очищено: <b>{deleted}</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Quick cleanup error: {e}")
        await message.answer("❌ Ошибка")

@router.message(Command("summary"))
@require_super_admin
async def cmd_summary_now(message: Message) -> None:
    if not message or not message.chat: return
    try:
        from utils.auto_delete import send_daily_summary
        await send_daily_summary(message.bot, message.chat.id)
        await message.answer("✅ Сводка отправлена")
    except Exception as e:
        logger.error(f"Quick summary error: {e}")
        await message.answer("❌ Ошибка")

@router.message(Command("chats"))
@require_super_admin
async def cmd_list_chats(message: Message) -> None:
    if not message: return
    try:
        chats = await db.get_all_chats_with_bot() if db else []
        text = f"📋 <b>ЧАТЫ ({len(chats)})</b>\n\n"
        for cid in chats[:15]:
            text += f"• <code>{cid}</code>\n"
        if len(chats) > 15:
            text += f"\n... и ещё {len(chats)-15}"
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Quick chats error: {e}")
        await message.answer("❌ Ошибка")

@router.message(Command("reload_rp"))
@require_super_admin
async def cmd_reload_rp(message: Message) -> None:
    if not message: return
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        await message.answer("✅ РП команды перезагружены!")
    except Exception as e:
        logger.error(f"Quick reload error: {e}")
        await message.answer("❌ Ошибка")
