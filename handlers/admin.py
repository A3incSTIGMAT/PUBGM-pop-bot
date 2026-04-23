#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/admin.py
# ВЕРСИЯ: 3.0.9-production
# ОПИСАНИЕ: Админ-панель — ПРОДАКШН ВЕРСИЯ
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

# 🔥 ВЛАДЕЛЕЦ — гарантированно преобразуем в int
OWNER_ID = 895844198
BOT_ID = 8766720586  # ID бота для проверки

# Хранилище фоновых задач
_background_tasks: set[asyncio.Task] = set()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_callback_user_id(callback: CallbackQuery) -> Optional[int]:
    """
    Безопасное получение user_id из callback.
    🔥 Возвращает None если не удалось определить пользователя.
    """
    if not callback or not callback.from_user:
        return None
    
    user_id = callback.from_user.id
    
    # Если это бот — пробуем получить из reply_to_message
    if user_id == BOT_ID:
        if callback.message and callback.message.reply_to_message:
            reply_user = callback.message.reply_to_message.from_user
            if reply_user:
                logger.debug(f"📩 Got user_id from reply_to_message: {reply_user.id}")
                return reply_user.id
        return None
    
    return user_id


def is_super_admin(user_id: Optional[int]) -> bool:
    """
    Проверка прав супер-админа.
    🔥 ИСПРАВЛЕНО: явное преобразование типов для надёжного сравнения
    """
    if user_id is None:
        logger.warning("⚠️ is_super_admin: user_id is None")
        return False
    
    try:
        user_id_int = int(user_id)
        owner_id_int = int(OWNER_ID)
        
        is_owner = (user_id_int == owner_id_int)
        is_super = user_id_int in SUPER_ADMIN_IDS if SUPER_ADMIN_IDS else False
        
        if is_owner:
            logger.info(f"✅ User {user_id_int} identified as OWNER")
        elif is_super:
            logger.info(f"✅ User {user_id_int} identified as SUPER_ADMIN")
        
        return is_owner or is_super
        
    except (ValueError, TypeError) as e:
        logger.error(f"❌ Error checking admin rights for user_id={user_id}: {e}")
        return False


def require_super_admin(func):
    """Декоратор для проверки прав (для команд/сообщений)."""
    async def wrapper(message: Message, *args, **kwargs):
        if not message or not message.from_user:
            logger.warning("⚠️ require_super_admin: message or from_user is None")
            return
        
        user_id = message.from_user.id
        logger.debug(f"🔍 Checking admin rights for user {user_id} (command: {message.text})")
        
        if not is_super_admin(user_id):
            logger.warning(f"🚫 Access denied for user {user_id} (OWNER_ID={OWNER_ID})")
            await message.answer(
                "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
                f"Ваш ID: <code>{user_id}</code>\n"
                f"ID владельца: <code>{OWNER_ID}</code>\n\n"
                "Эта команда только для владельца бота.",
                parse_mode=ParseMode.HTML
            )
            return
        return await func(message, *args, **kwargs)
    return wrapper


def require_super_admin_callback(func):
    """
    Декоратор проверки прав для callback-хендлеров.
    🔥 БЕЗОПАСНО: никогда не фоллбечит на OWNER_ID
    """
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if not callback:
            logger.warning("⚠️ require_super_admin_callback: callback is None")
            return
        
        # Получаем user_id безопасным способом
        user_id = get_callback_user_id(callback)
        
        # 🔥 КРИТИЧНО: если user_id не определён — ОТКАЗ в доступе
        if user_id is None:
            logger.error(f"🚫 Could not identify user in callback: data={callback.data}")
            await callback.answer("❌ Ошибка проверки прав", show_alert=True)
            return
        
        logger.debug(f"🔍 Callback user_id: {user_id} (OWNER_ID={OWNER_ID})")
        
        if not is_super_admin(user_id):
            logger.warning(f"🚫 Callback access denied for user {user_id}")
            await callback.answer(
                f"❌ Доступ запрещён\n\nВаш ID: {user_id}\nТребуется ID: {OWNER_ID}",
                show_alert=True
            )
            return
        
        # Логируем успешный доступ
        logger.info(f"🔐 Admin {user_id} accessed via callback: {callback.data}")
        
        return await func(callback, *args, **kwargs)
    return wrapper


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


async def safe_edit_or_reply(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    """Безопасное редактирование или отправка нового сообщения."""
    if not callback or not callback.message:
        return False
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        await callback.answer()
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        logger.warning(f"⚠️ Edit error: {e}")
        try:
            await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await callback.answer()
            return True
        except Exception as e2:
            logger.error(f"❌ Fallback send failed: {e2}")
            await callback.answer("⚠️ Ошибка обновления", show_alert=False)
            return False
    except Exception as e:
        logger.error(f"❌ Edit failed: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=False)
        return False


def get_admin_panel_text(user_id: int, first_name: Optional[str], chat_id: int) -> str:
    """Генерация текста главной панели (устранение дубликатов)."""
    is_owner = is_super_admin(user_id)
    owner_status = "✅ ВЛАДЕЛЕЦ" if is_owner else "❌ НЕ владелец"
    
    return (
        "🔐 <b>АДМИН-ПАНЕЛЬ NEXUS BOT v5.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Владелец: <b>{safe_html_escape(first_name)}</b>\n"
        f"🆔 Ваш ID: <code>{user_id}</code>\n"
        f"🔑 Статус: <b>{owner_status}</b>\n"
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
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=CB_ADMIN_BACK),
         InlineKeyboardButton(text="❌ ЗАКРЫТЬ", callback_data=CB_ADMIN_CLOSE)],
    ])


# ==================== CALLBACK: ГЛАВНОЕ МЕНЮ ====================

@router.callback_query(F.data == "menu_admin")
@require_super_admin_callback
async def admin_panel_callback(callback: CallbackQuery) -> None:
    """Открытие админ-панели."""
    if not callback or not callback.message:
        return

    # Декоратор уже проверил права, user_id гарантированно валиден
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "Владелец"
    
    text = get_admin_panel_text(user_id, first_name, callback.message.chat.id)
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())


@router.message(Command("admin"))
@require_super_admin
async def cmd_admin_panel(message: Message) -> None:
    """Команда открытия админ-панели."""
    if not message or not message.from_user or not message.chat:
        return
    text = get_admin_panel_text(message.from_user.id, message.from_user.first_name, message.chat.id)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_menu_keyboard())


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    """Показать свой ID для отладки прав доступа."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    is_owner = is_super_admin(user_id)
    
    await message.answer(
        f"🔍 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>\n\n"
        f"👤 Имя: <b>{safe_html_escape(message.from_user.first_name)}</b>\n"
        f"🆔 Ваш ID: <code>{user_id}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n\n"
        f"🔑 <b>ПРОВЕРКА ПРАВ:</b>\n"
        f"ID владельца в боте: <code>{OWNER_ID}</code>\n"
        f"Вы владелец: <b>{'✅ ДА' if is_owner else '❌ НЕТ'}</b>\n\n"
        f"💡 <i>Если вы владелец, но доступ запрещён — проверьте, что OWNER_ID={OWNER_ID} совпадает с вашим ID {user_id}</i>",
        parse_mode=ParseMode.HTML
    )


# ==================== CALLBACK: СТАТИСТИКА ====================

@router.callback_query(F.data == CB_ADMIN_STATS)
@require_super_admin_callback
async def admin_stats_callback(callback: CallbackQuery) -> None:
    """Показать статистику чата."""
    if not callback or not callback.message:
        return

    chat_id = callback.message.chat.id
    await callback.answer("📊 Загружаю статистику...")

    try:
        from utils.auto_delete import get_chat_daily_stats, get_chat_top_words, get_chat_active_users

        stats = await run_with_timeout(get_chat_daily_stats(chat_id), TIMEOUT_STATS, "get_stats")
        top_words = await run_with_timeout(get_chat_top_words(chat_id, 15), TIMEOUT_STATS, "get_words")
        active_users = await run_with_timeout(get_chat_active_users(chat_id, 10), TIMEOUT_STATS, "get_users")

        total_users = await run_with_timeout(db.get_total_users(), TIMEOUT_STATS, "total_users") if db is not None else 0
        total_messages = await run_with_timeout(db.get_total_messages_count(), TIMEOUT_STATS, "total_msgs") if db is not None else 0

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
@require_super_admin_callback
async def admin_cleanup_callback(callback: CallbackQuery) -> None:
    """Очистка сообщений бота в чате."""
    if not callback or not callback.message:
        return

    chat_id = callback.message.chat.id
    await callback.answer("🧹 Очищаю...")

    try:
        from utils.auto_delete import delete_bot_messages, bot_messages

        deleted = await run_with_timeout(delete_bot_messages(callback.bot, chat_id), TIMEOUT_CLEANUP, "cleanup")
        
        remaining = "N/A"
        try:
            if isinstance(bot_messages, dict):
                remaining = len(bot_messages.get(chat_id, []))
            elif isinstance(bot_messages, (list, set, tuple)):
                remaining = len(bot_messages)
        except Exception as e:
            logger.warning(f"⚠️ Could not get remaining messages: {e}")

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
@require_super_admin_callback
async def admin_summary_callback(callback: CallbackQuery) -> None:
    """Отправить сводку дня."""
    if not callback or not callback.message:
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
@require_super_admin_callback
async def admin_chats_callback(callback: CallbackQuery) -> None:
    """Показать список чатов с ботом."""
    if not callback or not callback.message:
        return

    await callback.answer("📋 Загружаю...")
    try:
        chats = await db.get_all_chats_with_bot() if db is not None else []
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
@require_super_admin_callback
async def admin_cleanup_all_callback(callback: CallbackQuery) -> None:
    """Запустить глобальную очистку всех чатов."""
    if not callback:
        return

    await callback.answer("🧹 Глобальная очистка запущена...", show_alert=True)
    try:
        from utils.auto_delete import cleanup_all_chats

        async def _safe_cleanup(bot: Bot):
            try:
                await cleanup_all_chats(bot)
                logger.info("✅ Global cleanup completed")
            except Exception as e:
                logger.error(f"🌍 Background cleanup failed: {e}", exc_info=True)

        task = asyncio.create_task(_safe_cleanup(callback.bot))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        
        await safe_edit_or_reply(callback, "🧹 <b>ГЛОБАЛЬНАЯ ОЧИСТКА ЗАПУЩЕНА</b>\n\nПроцесс выполняется в фоне.")
    except Exception as e:
        logger.error(f"🌍 Cleanup all error: {e}", exc_info=True)


# ==================== CALLBACK: ПЕРЕЗАГРУЗКА РП ====================

@router.callback_query(F.data == CB_ADMIN_RELOAD)
@require_super_admin_callback
async def admin_reload_callback(callback: CallbackQuery) -> None:
    """Перезагрузить RP команды."""
    if not callback:
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
@require_super_admin_callback
async def admin_back_callback(callback: CallbackQuery) -> None:
    """Вернуться в главное меню админ-панели."""
    if not callback or not callback.message:
        return

    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "Владелец"
    
    text = get_admin_panel_text(user_id, first_name, callback.message.chat.id)
    await safe_edit_or_reply(callback, text, get_admin_menu_keyboard())


# ==================== CALLBACK: ЗАКРЫТЬ ====================

@router.callback_query(F.data == CB_ADMIN_CLOSE)
async def admin_close_callback(callback: CallbackQuery) -> None:
    """Закрыть админ-панель (доступно без проверки прав для удобства)."""
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
    """Быстрая статистика за сегодня."""
    if not message or not message.chat: 
        return
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
    """Быстрая очистка чата."""
    if not message or not message.chat: 
        return
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
    """Быстрая отправка сводки."""
    if not message or not message.chat: 
        return
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
    """Быстрый список чатов."""
    if not message: 
        return
    try:
        chats = await db.get_all_chats_with_bot() if db is not None else []
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
    """Быстрая перезагрузка RP команд."""
    if not message: 
        return
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        await message.answer("✅ РП команды перезагружены!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"🔄 Quick reload error: {e}")
        await message.answer("❌ Ошибка", parse_mode=ParseMode.HTML)

