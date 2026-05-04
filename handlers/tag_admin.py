#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/tag_admin.py
# ВЕРСИЯ: 2.1.0-production (исправленная после аудита)
# ОПИСАНИЕ: Управление категориями тегов (админ-панель)
# ============================================
# ИСПРАВЛЕНИЯ v2.1.0:
#   🟡 Добавлена проверка типа чата (группа/супергруппа)
#   🟡 Проверка callback.from_user во всех обработчиках
#   🟡 Безопасный ответ на callback
#   🟡 exc_info=True во всех logger.error
#   🟢 DEVELOPER_IDS с защитой от None
# ============================================

import html
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from config import SUPER_ADMIN_IDS, ADMIN_IDS
from handlers.tag_categories import (
    get_all_categories,
    get_chat_enabled_slugs,
    toggle_chat_category,
    init_categories
)
from database import DatabaseError

logger = logging.getLogger(__name__)
router = Router()

# ==================== КОНСТАНТЫ ====================

# ID разработчиков с защитой от None
DEVELOPER_IDS = (SUPER_ADMIN_IDS or []) or (ADMIN_IDS or [])


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def _safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = True) -> None:
    """Безопасный ответ на callback."""
    if callback is None:
        return
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramAPIError:
        pass


def _is_group_chat(callback: CallbackQuery) -> bool:
    """Проверка, что callback из группы или супергруппы."""
    if callback is None or callback.message is None:
        return False
    chat = callback.message.chat
    return chat is not None and getattr(chat, 'type', None) in ['group', 'supergroup']


async def can_manage_tags(bot, user_id: int, chat_id: int) -> bool:
    """
    Проверяет, может ли пользователь управлять тегами:
    - владелец чата
    - или разработчик (в любом чате, где он админ)
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        True если есть права на управление
    """
    if bot is None or user_id is None or chat_id is None:
        return False
    
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        
        # Владелец чата
        if member.status == 'creator':
            return True
        
        # Разработчик — если админ в этом чате
        if user_id in DEVELOPER_IDS and member.status == 'administrator':
            return True
        
        return False
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Manage tags check failed for {user_id} in {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error in can_manage_tags: {e}", exc_info=True)
        return False


def get_back_keyboard(callback_data: str = "tag_admin_menu") -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой НАЗАД.
    
    Args:
        callback_data: Callback для кнопки возврата
        
    Returns:
        InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])


# ==================== ОБРАБОТЧИКИ ====================

@router.callback_query(F.data == "tag_admin_menu")
async def tag_admin_menu(callback: CallbackQuery) -> None:
    """Меню управления тегами."""
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    if not _is_group_chat(callback):
        await _safe_callback_answer(callback, "❌ Управление тегами доступно только в группах!")
        return
    
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    if not await can_manage_tags(callback.bot, user_id, chat_id):
        await _safe_callback_answer(callback, "❌ Только владелец чата может управлять тегами!")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 ВКЛЮЧИТЬ КАТЕГОРИИ", callback_data="tag_enable_categories")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "👑 <b>УПРАВЛЕНИЕ ТЭГАМИ</b>\n\n"
        "Здесь вы можете включить или отключить категории тегов в вашем чате.\n\n"
        "Участники смогут подписываться только на включённые категории.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "tag_enable_categories")
async def tag_enable_categories(callback: CallbackQuery) -> None:
    """Список категорий для включения/отключения."""
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    if not _is_group_chat(callback):
        await _safe_callback_answer(callback, "❌ Управление тегами доступно только в группах!")
        return
    
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    if not await can_manage_tags(callback.bot, user_id, chat_id):
        await _safe_callback_answer(callback, "❌ Только владелец чата!")
        return
    
    try:
        await init_categories()
        all_categories = await get_all_categories()
        enabled_slugs = await get_chat_enabled_slugs(chat_id)
        
        if not all_categories:
            await callback.message.edit_text(
                "❌ Категории не найдены. Попробуйте позже.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard()
            )
            await _safe_callback_answer(callback)
            return
        
        keyboard = []
        for cat in all_categories:
            status = "✅" if cat["slug"] in enabled_slugs else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status} {cat['icon']} {cat['name']}",
                    callback_data=f"toggle_cat_{cat['slug']}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_admin_menu")])
        
        await callback.message.edit_text(
            "📋 <b>КАТЕГОРИИ ТЭГОВ</b>\n\n"
            "✅ — категория активна (участники могут подписываться)\n"
            "❌ — категория скрыта\n\n"
            "Нажмите на категорию, чтобы изменить статус:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await _safe_callback_answer(callback)
        
    except DatabaseError as e:
        logger.error(f"❌ Database error in tag_enable_categories: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка базы данных")
    except Exception as e:
        logger.error(f"❌ Unexpected error in tag_enable_categories: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Произошла ошибка")


@router.callback_query(F.data.startswith("toggle_cat_"))
async def toggle_category(callback: CallbackQuery) -> None:
    """Включение/отключение категории."""
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    if not _is_group_chat(callback):
        await _safe_callback_answer(callback, "❌ Управление тегами доступно только в группах!")
        return
    
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    # Извлекаем slug (поддерживает slug с подчёркиваниями, например "video_call")
    parts = callback.data.split("_")
    if len(parts) < 3:
        await _safe_callback_answer(callback, "❌ Неверный формат")
        return
    
    category_slug = "_".join(parts[2:])
    
    if not await can_manage_tags(callback.bot, user_id, chat_id):
        await _safe_callback_answer(callback, "❌ Только владелец чата!")
        return
    
    try:
        enabled_slugs = await get_chat_enabled_slugs(chat_id)
        is_enabled = category_slug in enabled_slugs
        
        await toggle_chat_category(chat_id, category_slug, not is_enabled)
        
        status = "включена ✅" if not is_enabled else "отключена ❌"
        await callback.answer(f"Категория {status}")
        
        # Обновляем список
        await tag_enable_categories(callback)
        
    except DatabaseError as e:
        logger.error(f"❌ Database error in toggle_category: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка базы данных")
    except Exception as e:
        logger.error(f"❌ Unexpected error in toggle_category: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Произошла ошибка")


# ==================== КОМАНДА ДЛЯ БЫСТРОГО ДОСТУПА ====================

@router.callback_query(F.data == "tag_settings")
async def tag_settings_callback(callback: CallbackQuery) -> None:
    """Алиас для tag_admin_menu."""
    await tag_admin_menu(callback)
