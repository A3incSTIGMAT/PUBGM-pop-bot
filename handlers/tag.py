#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/tag.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Модуль тегов — /all, /tag, /tagrole
# ИСПРАВЛЕНИЯ: Защита от memory leak, обработка ошибок, конфигурируемые параметры
# ============================================

import asyncio
import html
import logging
import re
import time
from typing import Dict, List, Optional, Set

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from database import db, DatabaseError

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

# Можно вынести в config.py
TAG_COOLDOWN = 300  # 5 минут между общими сборами
BATCH_SIZE = 10  # Количество упоминаний в одном сообщении
BATCH_DELAY = 1.0  # Задержка между батчами
MAX_MEMBERS_TO_FETCH = 200  # Максимальное количество участников для сбора
COOLDOWN_CLEANUP_INTERVAL = 3600  # Очистка кулдаунов раз в час

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

_cooldown_storage: Dict[str, float] = {}
_cooldown_lock = asyncio.Lock()


async def _cleanup_expired_cooldowns() -> None:
    """Периодическая очистка истекших кулдаунов."""
    while True:
        await asyncio.sleep(COOLDOWN_CLEANUP_INTERVAL)
        current_time = time.time()
        async with _cooldown_lock:
            expired = [
                key for key, timestamp in _cooldown_storage.items()
                if current_time - timestamp > TAG_COOLDOWN * 2
            ]
            for key in expired:
                del _cooldown_storage[key]
            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired cooldowns")


# Запускаем фоновую очистку
asyncio.create_task(_cleanup_expired_cooldowns())


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def is_admin_in_chat(bot: Bot, user_id: int, chat_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором чата.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        True если администратор, иначе False
    """
    if bot is None:
        logger.warning("Bot is None in is_admin_in_chat")
        return False
    
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except TelegramAPIError as e:
        logger.warning(f"Admin check failed for {user_id} in {chat_id}: {e}")
        return False


async def is_bot_admin(bot: Bot, chat_id: int) -> bool:
    """
    Проверяет, является ли бот администратором чата.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        
    Returns:
        True если бот администратор, иначе False
    """
    if bot is None:
        logger.warning("Bot is None in is_bot_admin")
        return False
    
    try:
        bot_me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, bot_me.id)
        return member.status in ['creator', 'administrator']
    except TelegramAPIError as e:
        logger.warning(f"Bot admin check failed for chat {chat_id}: {e}")
        return False


async def check_cooldown(chat_id: int) -> tuple[bool, int]:
    """
    Проверяет кулдаун для общего сбора.
    
    Args:
        chat_id: ID чата
        
    Returns:
        (можно_ли_использовать, оставшееся_время_в_секундах)
    """
    cooldown_key = f"all:{chat_id}"
    current_time = time.time()
    
    async with _cooldown_lock:
        if cooldown_key in _cooldown_storage:
            last_used = _cooldown_storage[cooldown_key]
            elapsed = current_time - last_used
            if elapsed < TAG_COOLDOWN:
                return False, int(TAG_COOLDOWN - elapsed)
    
    return True, 0


async def set_cooldown(chat_id: int) -> None:
    """Устанавливает кулдаун для чата."""
    cooldown_key = f"all:{chat_id}"
    async with _cooldown_lock:
        _cooldown_storage[cooldown_key] = time.time()


async def get_chat_members_safe(bot: Bot, chat_id: int) -> List:
    """
    Безопасное получение списка участников чата.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        
    Returns:
        Список участников (не ботов)
    """
    members = []
    seen_ids: Set[int] = set()
    
    try:
        # Сначала получаем администраторов
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot and admin.user.id not in seen_ids:
                members.append(admin.user)
                seen_ids.add(admin.user.id)
    except TelegramAPIError as e:
        logger.warning(f"Could not fetch admins: {e}")
    
    # Затем пытаемся получить остальных участников
    try:
        member_count = 0
        async for member in bot.get_chat_members(chat_id):
            if member_count >= MAX_MEMBERS_TO_FETCH:
                break
            if not member.user.is_bot and member.user.id not in seen_ids:
                members.append(member.user)
                seen_ids.add(member.user.id)
            member_count += 1
    except TelegramAPIError as e:
        logger.warning(f"Could not fetch all members: {e}")
    
    return members


def format_mentions(members: List) -> List[str]:
    """
    Форматирует список участников в упоминания.
    
    Args:
        members: Список объектов User
        
    Returns:
        Список строк с HTML-упоминаниями
    """
    mentions = []
    for member in members:
        if member.username:
            mentions.append(f"@{safe_html_escape(member.username)}")
        else:
            name = safe_html_escape(member.full_name or "Пользователь")
            mentions.append(f'<a href="tg://user?id={member.id}">{name}</a>')
    return mentions


def format_time_remaining(seconds: int) -> str:
    """Форматирует оставшееся время в читаемый вид."""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes} мин {secs} сек"


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("all"))
async def cmd_all(message: Message) -> None:
    """Команда общего сбора (только для админов)."""
    if message is None or message.from_user is None:
        return
    
    if message.chat is None:
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверка типа чата
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда /all работает только в группах!")
        return
    
    # Проверка регистрации
    try:
        user = await db.get_user(user_id)
        if not user:
            await message.answer("❌ Используйте /start для регистрации")
            return
    except DatabaseError as e:
        logger.error(f"Database error in cmd_all: {e}")
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
        return
    
    # Проверка прав
    if not await is_admin_in_chat(message.bot, user_id, chat_id):
        await message.answer(
            "❌ <b>Нет прав!</b>\n\n"
            "Только администраторы чата могут использовать /all.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not await is_bot_admin(message.bot, chat_id):
        await message.answer(
            "❌ <b>Ошибка:</b> Бот не является администратором чата!",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверка кулдауна
    can_use, remaining = await check_cooldown(chat_id)
    if not can_use:
        await message.answer(
            f"⏰ <b>Подождите!</b>\n\n"
            f"Следующий сбор через <b>{format_time_remaining(remaining)}</b>.",
            parse_mode=ParseMode.HTML
        )
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"confirm_all_{chat_id}"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
    ])
    
    safe_name = safe_html_escape(message.from_user.full_name)
    await message.answer(
        "📢 <b>ОБЩИЙ СБОР</b> 📢\n\n"
        "⚠️ <b>Внимание!</b>\n"
        "После подтверждения будет отправлено сообщение с упоминанием всех участников.\n\n"
        f"👤 Инициатор: {safe_name}\n"
        f"🛡️ Права: Администратор\n\n"
        "✅ <b>Подтвердите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.message(Command("tag"))
async def cmd_tag(message: Message) -> None:
    """Команда для упоминания пользователя."""
    if message is None or message.from_user is None:
        return
    
    if message.chat is None:
        return
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if message.text is None:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 <b>Как тэгать:</b>\n\n"
            "<code>/tag @username текст</code> — упомянуть пользователя\n"
            "Пример: <code>/tag @user Привет!</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = args[1]
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    if not match:
        await message.answer("❌ Укажите @username пользователя")
        return
    
    username = match.group(1)
    clean_text = re.sub(r'@\w+', '', text).strip()
    
    safe_author = safe_html_escape(message.from_user.full_name)
    if clean_text:
        safe_text = safe_html_escape(clean_text)
        result = f"🔔 {safe_text}\n\n👉 @{safe_html_escape(username)}"
    else:
        result = f"🔔 Вас упомянул {safe_author}\n\n👉 @{safe_html_escape(username)}"
    
    await message.answer(result, parse_mode=ParseMode.HTML)


@router.message(Command("tagrole"))
async def cmd_tag_role(message: Message) -> None:
    """Команда для упоминания всех администраторов."""
    if message is None or message.from_user is None:
        return
    
    if message.chat is None:
        return
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if message.text is None:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 <b>Как тэгать по роли:</b>\n\n"
            "<code>/tagrole админы текст</code> — упомянуть всех админов",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = args[1]
    role_match = re.match(r'(админы?)\s*(.*)', text, re.IGNORECASE)
    
    if not role_match:
        await message.answer(
            "❌ Используйте: <code>/tagrole админы текст</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    clean_text = role_match.group(2).strip()
    
    try:
        administrators = await message.bot.get_chat_administrators(message.chat.id)
        admins = [admin.user for admin in administrators if not admin.user.is_bot]
    except TelegramAPIError as e:
        logger.error(f"Failed to get admins: {e}")
        await message.answer(f"❌ Ошибка: {safe_html_escape(str(e))}", parse_mode=ParseMode.HTML)
        return
    
    if not admins:
        await message.answer("❌ Нет администраторов в этом чате", parse_mode=ParseMode.HTML)
        return
    
    mentions = format_mentions(admins)
    
    if clean_text:
        result = f"🔔 {safe_html_escape(clean_text)}\n\n{' '.join(mentions)}"
    else:
        result = f"🛡️ <b>Обращение к администраторам:</b>\n\n{' '.join(mentions)}"
    
    await message.answer(result, parse_mode=ParseMode.HTML)


# ==================== ОБРАБОТЧИКИ CALLBACK ====================

@router.callback_query(F.data.startswith("confirm_all_"))
async def confirm_all(callback: CallbackQuery) -> None:
    """Подтверждение общего сбора."""
    if callback is None or callback.message is None or callback.from_user is None:
        return
    
    try:
        parts = callback.data.split("_")
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат запроса", show_alert=True)
            return
        
        chat_id = int(parts[2])
        user_id = callback.from_user.id
        
        if callback.message.chat.id != chat_id:
            await callback.answer("❌ Несоответствие чата", show_alert=True)
            return
        
        # Проверка прав
        if not await is_admin_in_chat(callback.bot, user_id, chat_id):
            await callback.answer("❌ Только администраторы могут подтвердить!", show_alert=True)
            return
        
        await callback.answer("🔄 Собираю участников...")
        
        # Устанавливаем кулдаун
        await set_cooldown(chat_id)
        
        # Получаем участников
        members = await get_chat_members_safe(callback.bot, chat_id)
        
        if not members:
            await callback.message.edit_text("❌ Не удалось получить список участников.", parse_mode=ParseMode.HTML)
            return
        
        # Удаляем сообщение с подтверждением
        try:
            await callback.message.delete()
        except TelegramAPIError:
            pass
        
        mentions = format_mentions(members)
        safe_initiator = safe_html_escape(callback.from_user.full_name)
        
        total_batches = (len(mentions) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_idx in range(total_batches):
            start = batch_idx * BATCH_SIZE
            end = min(start + BATCH_SIZE, len(mentions))
            batch_mentions = mentions[start:end]
            batch_text = " ".join(batch_mentions)
            
            if batch_idx == 0:
                response = (
                    f"📢 <b>ОБЩИЙ СБОР!</b> 📢\n\n"
                    f"👤 <b>{safe_initiator}</b> (администратор)\n\n"
                    f"🔔 <b>ВНИМАНИЕ ВСЕМ УЧАСТНИКАМ!</b>\n\n"
                    f"{batch_text}"
                )
            else:
                response = (
                    f"📢 <b>Продолжение ({batch_idx + 1}/{total_batches})</b>\n\n"
                    f"{batch_text}"
                )
            
            try:
                await callback.bot.send_message(chat_id, response, parse_mode=ParseMode.HTML)
            except TelegramForbiddenError:
                logger.warning(f"Bot blocked in chat {chat_id}")
                break
            except TelegramAPIError as e:
                logger.error(f"Failed to send batch {batch_idx}: {e}")
            
            if batch_idx < total_batches - 1:
                await asyncio.sleep(BATCH_DELAY)
        
        # Финальное сообщение
        try:
            await callback.bot.send_message(
                chat_id,
                f"✅ <b>Общий сбор завершён!</b>\n\n"
                f"👥 Упомянуто участников: {len(mentions)}",
                parse_mode=ParseMode.HTML
            )
        except TelegramAPIError:
            pass
        
        await callback.answer("✅ Общий сбор завершён!")
        
    except Exception as e:
        logger.error(f"confirm_all error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при выполнении", show_alert=True)


@router.callback_query(F.data == "cancel_all")
async def cancel_all(callback: CallbackQuery) -> None:
    """Отмена общего сбора."""
    if callback is None or callback.message is None:
        return
    
    try:
        await callback.message.edit_text("❌ Общий сбор отменён.", parse_mode=ParseMode.HTML)
    except TelegramAPIError:
        pass
    await callback.answer()


@router.callback_query(F.data == "tag_menu")
async def tag_menu(callback: CallbackQuery) -> None:
    """Меню управления тегами."""
    if callback is None or callback.message is None:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    is_admin = await is_admin_in_chat(callback.bot, user_id, chat_id)
    
    if is_admin:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР (/all)", callback_data="start_all")],
            [InlineKeyboardButton(text="🛡️ НАПИСАТЬ АДМИНАМ", callback_data="tag_admins")],
            [InlineKeyboardButton(text="🔔 КАК ПОЛЬЗОВАТЬСЯ", callback_data="tag_help")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        text = (
            "📢 <b>УПРАВЛЕНИЕ ТЭГАМИ</b> (АДМИНИСТРАТОР)\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "• <code>/all</code> — общий сбор (1 раз в 5 минут)\n"
            "• <code>/tag @user</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы</code> — написать админам"
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛡️ НАПИСАТЬ АДМИНАМ", callback_data="tag_admins")],
            [InlineKeyboardButton(text="🔔 КАК ПОЛЬЗОВАТЬСЯ", callback_data="tag_help")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        text = (
            "📢 <b>УПРАВЛЕНИЕ ТЭГАМИ</b>\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "• <code>/tag @user</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы</code> — написать админам\n\n"
            "⚠️ <b>Общий сбор (/all)</b>\n"
            "Доступен только для администраторов."
        )
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramAPIError as e:
        logger.warning(f"Failed to edit tag_menu: {e}")
    
    await callback.answer()


@router.callback_query(F.data == "start_all")
async def start_all_callback(callback: CallbackQuery) -> None:
    """Запуск общего сбора через меню."""
    if callback is None or callback.message is None:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    if not await is_admin_in_chat(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только администраторы!", show_alert=True)
        return
    
    if not await is_bot_admin(callback.bot, chat_id):
        await callback.answer("❌ Бот не администратор!", show_alert=True)
        return
    
    can_use, remaining = await check_cooldown(chat_id)
    if not can_use:
        await callback.answer(f"⏰ Подождите {remaining} сек", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"confirm_all_{chat_id}"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
    ])
    
    safe_name = safe_html_escape(callback.from_user.full_name)
    try:
        await callback.message.edit_text(
            "📢 <b>ОБЩИЙ СБОР</b> 📢\n\n"
            "⚠️ <b>Внимание!</b>\n"
            "После подтверждения будет отправлено сообщение с упоминанием всех участников.\n\n"
            f"👤 Инициатор: {safe_name}\n"
            f"🛡️ Права: Администратор\n\n"
            "✅ <b>Подтвердите действие:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except TelegramAPIError as e:
        logger.warning(f"Failed to edit start_all: {e}")
    
    await callback.answer()


@router.callback_query(F.data == "tag_admins")
async def tag_admins_callback(callback: CallbackQuery) -> None:
    """Показать список администраторов."""
    if callback is None or callback.message is None:
        return
    
    chat_id = callback.message.chat.id
    
    try:
        administrators = await callback.bot.get_chat_administrators(chat_id)
        admins = [admin.user for admin in administrators if not admin.user.is_bot]
    except TelegramAPIError as e:
        logger.error(f"Failed to get admins: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if not admins:
        await callback.answer("❌ Нет администраторов", show_alert=True)
        return
    
    mentions = format_mentions(admins)
    
    try:
        await callback.message.edit_text(
            f"🛡️ <b>АДМИНИСТРАТОРЫ ЧАТА:</b>\n\n{' '.join(mentions)}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_menu")]
            ])
        )
    except TelegramAPIError as e:
        logger.warning(f"Failed to edit tag_admins: {e}")
    
    await callback.answer()


@router.callback_query(F.data == "tag_help")
async def tag_help_callback(callback: CallbackQuery) -> None:
    """Помощь по тегам."""
    if callback is None or callback.message is None:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_menu")]
    ])
    
    try:
        await callback.message.edit_text(
            "📢 <b>ПОМОЩЬ ПО ТЭГАМ</b>\n\n"
            "<b>📝 КОМАНДЫ ДЛЯ ВСЕХ:</b>\n"
            "• <code>/tag @user текст</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы текст</code> — написать администраторам\n\n"
            "<b>👑 КОМАНДЫ ДЛЯ АДМИНОВ:</b>\n"
            "• <code>/all</code> — общий сбор (1 раз в 5 минут)",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except TelegramAPIError as e:
        logger.warning(f"Failed to edit tag_help: {e}")
    
    await callback.answer()
