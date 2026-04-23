#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/admin.py
# ВЕРСИЯ: 3.0.4-optimized
# ОПИСАНИЕ: Админ-панель — ИСПРАВЛЕН CALLBACK, ОПТИМИЗИРОВАНО
# ============================================

import asyncio
import html
import logging
from typing import Optional, Any

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database import db
from config import SUPER_ADMIN_IDS

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

# 🔥 ВЛАДЕЛЕЦ (рекомендуется вынести в config.py через os.getenv)
OWNER_ID = 895844198

# ==================== ПРОВЕРКА ПРАВ ====================
def is_super_admin(user_id: Optional[int]) -> bool:
    """Проверка прав супер-админа."""
    if user_id is None:
        return False
    if user_id == OWNER_ID:
        return True
    return user_id in SUPER_ADMIN_IDS


def require_super_admin(func):
    """Декоратор для проверки прав (для команд/сообщений)."""
    async def wrapper(message: Message, *args, **kwargs):
        if not message or not message.from_user:
            return
        if not is_super_admin(message.from_user.id):
            await message.answer(
                "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\nЭта команда только для владельца бота.",
                parse_mode=ParseMode.HTML
            )
            return
        return await func(message, *args, **kwargs)
    return wrapper


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
def safe_html_escape(text: Optional[str]) -> str:
    """Безопасный экранировщик для HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def run_with_timeout(coro, timeout: float, name: str) -> Any:
    """Запуск корутины с таймаутом и логированием."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Timeout ({timeout}s) for {name}")
        return None
    except Exception as e:
        logger.error(f"⚠️ Error in {name}: {e}", exc_info=True)
        return None


async def safe_edit_or_reply(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Безопасное редактирование или отправка нового сообщения."""
    if not callback or not callback.message:
        return
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
        else:
            logger.warning(f"⚠️ Edit error: {e}")
            try:
                await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"❌ Edit failed: {e}")


def get_admin_panel_text(user_id: int, first_name: Optional[str], chat_id: int) -> str:
    """Генерация текста главной панели (устранение дубликатов)."""
    return (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v5.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Владелец: <b>{safe_html_escape(first_name)}</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💬 Чат: <code>{chat_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data=CB_ADMIN_STATS)],
        [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ЧАТ", callback_data=CB_ADMIN_CLEANUP)],
        [InlineKeyboardButton(text="🌅 СВОДКА ДНЯ", callback_data=CB_ADMIN_SUMMARY)],
        [InlineKeyboardButton(text="📋 ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CHATS)],
        [InlineKeyboardButton(text="🔄 ПЕРЕЗАГРУЗКА РП", callback_data=CB_ADMIN_RELOAD)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK),  # ✅ ИСПРАВЛЕНО
         InlineKeyboardButton(text="❌ ЗАКРЫТЬ", callback_data=CB_ADMIN_CLOSE)],
    ])


# ==================== CALLBACK: ГЛАВНОЕ МЕНЮ ====================
@router.callback_query(F.data == "menu_admin")
async def admin_panel_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    text = get_admin_panel_text(
        callback.from_user.id,
        callback.from_user.first_name,
        callback.message.chat.id
    )
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())
    await callback.answer()


@router.message(Command("admin"))
@require_super_admin
async def cmd_admin_panel(message: Message) -> None:
    if not message or not message.from_user or not message.chat:
        return
    text = get_admin_panel_text(message.from_user.id, message.from_user.first_name, message.chat.id)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_menu_keyboard())


# ==================== CALLBACK: СТАТИСТИКА ====================
@router.callback_query(F.data == CB_ADMIN_STATS)
async def admin_stats_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    chat_id = callback.message.chat.id
    await callback.answer("📊 Загружаю статистику...")

    try:
        from utils.auto_delete import get_chat_daily_stats, get_chat_top_words, get_chat_active_users

        stats = await run_with_timeout(get_chat_daily_stats(chat_id), TIMEOUT_STATS, "get_stats")
        top_words = await run_with_timeout(get_chat_top_words(chat_id, 15), TIMEOUT_STATS, "get_words")
        active_users = await run_with_timeout(get_chat_active_users(chat_id, 10), TIMEOUT_STATS, "get_users")

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
        logger.error(f"📊 Stats error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки", show_alert=True)


# ==================== CALLBACK: ОЧИСТКА ====================
@router.callback_query(F.data == CB_ADMIN_CLEANUP)
async def admin_cleanup_callback(callback: CallbackQuery) -> None:
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
        
        # ✅ Безопасная проверка типа коллекции сообщений
        remaining = "N/A"
        if isinstance(bot_messages, dict):
            remaining = len(bot_messages.get(chat_id, []))
        elif hasattr(bot_messages, '__len__'):
            remaining = len(bot_messages)

        text = f"🧹 <b>ОЧИСТКА ЗАВЕРШЕНА</b>\n\nУдалено: <b>{deleted or 0}</b>\nВ очереди: <b>{remaining}</b>"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
    except Exception as e:
        logger.error(f"🧹 Cleanup error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка очистки", show_alert=True)


# ==================== CALLBACK: СВОДКА ====================
@router.callback_query(F.data == CB_ADMIN_SUMMARY)
async def admin_summary_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer("🌅 Отправляю...")
    try:
        from utils.auto_delete import send_daily_summary
        await send_daily_summary(callback.bot, callback.message.chat.id)
        
        text = "✅ <b>СВОДКА ОТПРАВЛЕНА</b>"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
    except Exception as e:
        logger.error(f"🌅 Summary error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка отправки", show_alert=True)


# ==================== CALLBACK: ВСЕ ЧАТЫ ====================
@router.callback_query(F.data == CB_ADMIN_CHATS)
async def admin_chats_callback(callback: CallbackQuery) -> None:
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
            except Exception as e:
                logger.debug(f"Chat info error for {cid}: {e}")
                text += f"{i}. <code>{cid}</code> — (нет доступа)\n"

        if len(chats) > MAX_CHATS_DISPLAY:
            text += f"\n... и ещё {len(chats) - MAX_CHATS_DISPLAY}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ВСЕ ЧАТЫ", callback_data=CB_ADMIN_CLEANUP_ALL)],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK)],
        ])
        await safe_edit_or_reply(callback, text, keyboard)
    except Exception as e:
        logger.error(f"📋 Chats error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки", show_alert=True)


# ==================== CALLBACK: ГЛОБАЛЬНАЯ ОЧИСТКА ====================
@router.callback_query(F.data == CB_ADMIN_CLEANUP_ALL)
async def admin_cleanup_all_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer("🧹 Глобальная очистка запущена...", show_alert=True)
    try:
        from utils.auto_delete import cleanup_all_chats

        # ✅ Безопасный запуск фоновой задачи с логированием ошибок
        async def _safe_cleanup(bot: Bot):
            try:
                await cleanup_all_chats(bot)
            except Exception as e:
                logger.error(f"🌍 Background cleanup failed: {e}", exc_info=True)

        asyncio.create_task(_safe_cleanup(callback.bot))
        await safe_edit_or_reply(callback, "🧹 <b>ГЛОБАЛЬНАЯ ОЧИСТКА ЗАПУЩЕНА</b>\n\nПроцесс выполняется в фоне.")
    except Exception as e:
        logger.error(f"🌍 Cleanup all error: {e}", exc_info=True)


# ==================== CALLBACK: ПЕРЕЗАГРУЗКА РП ====================
@router.callback_query(F.data == CB_ADMIN_RELOAD)
async def admin_reload_callback(callback: CallbackQuery) -> None:
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
        logger.error(f"🔄 Reload error: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ==================== CALLBACK: НАЗАД ====================
@router.callback_query(F.data == CB_ADMIN_BACK)
async def admin_back_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message or not callback.from_user:
        return
    if not is_super_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    text = get_admin_panel_text(
        callback.from_user.id,
        callback.from_user.first_name,
        callback.message.chat.id
    )
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())
    await callback.answer()


# ==================== CALLBACK: ЗАКРЫТЬ ====================
@router.callback_query(F.data == CB_ADMIN_CLOSE)
async def admin_close_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message:
        return
    try:
        await callback.message.delete()
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
    if not message or not message.chat: return
    try:
        from utils.auto_delete import get_chat_daily_stats, get_chat_active_users
        stats = await get_chat_daily_stats(message.chat.id) or {}
        active = await get_chat_active_users(message.chat.id, 5) or []

        text = f"📊 <b>СТАТИСТИКА ЗА СЕГОДНЯ</b>\n\n💬 Сообщений: <b>{stats.get('total_messages', 0)}</b>\n👥 Активных: <b>{stats.get('unique_users', 0)}</b>"
        if active:
            text += "\n\n<b>ТОП-5:</b>\n"
            for i, u in enumerate(active[:5], 1):
                name = safe_html_escape(u.get('first_name', '?'))[:15]
                text += f"{i}. {name} — {u.get('message_count', 0)}\n"
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"📊 Quick stats error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@router.message(Command("cleanup"))
@require_super_admin
async def cmd_cleanup_chat(message: Message) -> None:
    if not message or not message.chat: return
    try:
        from utils.auto_delete import delete_bot_messages
        msg = await message.answer("🧹 Очищаю...")
        deleted = await delete_bot_messages(message.bot, message.chat.id)
        await msg.edit_text(f"✅ Очищено: <b>{deleted or 0}</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"🧹 Quick cleanup error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@router.message(Command("summary"))
@require_super_admin
async def cmd_summary_now(message: Message) -> None:
    if not message or not message.chat: return
    try:
        from utils.auto_delete import send_daily_summary
        await send_daily_summary(message.bot, message.chat.id)
        await message.answer("✅ Сводка отправлена", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"🌅 Quick summary error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


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
        logger.error(f"📋 Quick chats error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)


@router.message(Command("reload_rp"))
@require_super_admin
async def cmd_reload_rp(message: Message) -> None:
    if not message: return
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        await message.answer("✅ РП команды перезагружены!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"🔄 Quick reload error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)

