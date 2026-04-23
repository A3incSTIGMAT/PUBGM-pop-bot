#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/tag_user.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Управление подписками пользователя на теги
# ============================================

import html
import logging
from typing import Optional, Dict, List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> Optional[Dict]:
    """Получить пользователя или создать если не существует."""
    if user_id is None or db is None:
        return None
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            logger.info(f"Auto-registered user {user_id} in tag_user")
        return user
    except DatabaseError as e:
        logger.error(f"Database error in get_or_create_user: {e}")
        return None


async def check_tag_tables_exist() -> bool:
    """Проверить существование таблиц тегов."""
    if db is None:
        return False
    
    try:
        row = await db._execute_with_retry(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_tag_settings'",
            fetch_one=True
        )
        return row is not None
    except DatabaseError as e:
        logger.error(f"Error checking tag tables: {e}")
        return False


# ==================== ИМПОРТ ФУНКЦИЙ ====================

from handlers.tag_categories import (
    get_chat_enabled_categories, 
    get_user_subscriptions, 
    toggle_user_subscription
)


# ==================== ОБНОВЛЕНИЕ СООБЩЕНИЯ ====================

async def update_tags_message(message: Message, user_id: int, chat_id: int) -> None:
    """Обновить сообщение с тегами."""
    if not message:
        return
    
    try:
        categories = await get_chat_enabled_categories(chat_id)
        subs = await get_user_subscriptions(user_id, chat_id)
        
        if not categories:
            await message.edit_text(
                "📭 <b>В этом чате нет активных категорий тегов</b>\n\n"
                "Администратор может добавить их через /tagadmin",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
                ])
            )
            return
        
        # Сортируем категории
        categories.sort(key=lambda x: x.get('name', ''))
        
        keyboard = []
        for cat in categories:
            slug = cat.get("slug", "")
            is_on = subs.get(slug, True)
            status_text = "✅ ВКЛ" if is_on else "❌ ВЫКЛ"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{cat.get('icon', '🔔')} {cat.get('name', 'Unknown')} [{status_text}]",
                    callback_data=f"tagsub_{chat_id}_{slug}_{1 if not is_on else 0}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(text="✅ ВКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_1"),
            InlineKeyboardButton(text="❌ ВЫКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_0")
        ])
        keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД В МЕНЮ", callback_data="back_to_menu")])
        
        total_cats = len(categories)
        enabled_count = sum(1 for cat in categories if subs.get(cat.get("slug", ""), True))
        
        chat_title = safe_html_escape(message.chat.title) if message.chat else "Чат"
        
        await message.edit_text(
            f"🏷️ <b>МОИ ТЕГИ</b>\n\n"
            f"📌 Чат: <b>{chat_title}</b>\n"
            f"📊 Активно: <b>{enabled_count}/{total_cats}</b> категорий\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ <b>ВКЛ</b> — вы получаете уведомления\n"
            f"❌ <b>ВЫКЛ</b> — уведомления отключены\n\n"
            f"👇 Нажмите на категорию, чтобы изменить статус:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except DatabaseError as e:
        logger.error(f"Database error updating tags message: {e}")
        await message.edit_text(
            "❌ Ошибка базы данных. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    except TelegramAPIError as e:
        logger.error(f"Telegram error updating tags message: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating tags message: {e}")


# ==================== КОМАНДА /mytags ====================

@router.message(Command("mytags"))
async def cmd_mytags(message: Message) -> None:
    """Управление подписками на теги."""
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    # Авторегистрация
    await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    
    loading_msg = await message.answer("🔄 Загрузка категорий...")
    
    try:
        tables_exist = await check_tag_tables_exist()
        
        if not tables_exist:
            await loading_msg.edit_text(
                "📭 <b>Система тегов ещё не настроена</b>\n\n"
                "Администратор должен сначала включить категории через /tagadmin",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
                ])
            )
            return
        
        await update_tags_message(loading_msg, user_id, chat_id)
        
    except Exception as e:
        logger.error(f"Error in mytags: {e}", exc_info=True)
        await loading_msg.edit_text(
            f"❌ <b>Ошибка загрузки категорий</b>\n\n"
            f"Попробуйте позже или сообщите администратору.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )


# ==================== КОЛЛБЭКИ ====================

@router.callback_query(F.data.startswith("tagsub_"))
async def toggle_subscription_callback(callback: CallbackQuery) -> None:
    """Переключение подписки пользователя."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    try:
        parts = callback.data.split("_")
        
        # Обработка "включить/выключить все"
        if parts[1] == "all":
            if len(parts) != 4:
                await callback.answer("❌ Неверный формат", show_alert=True)
                return
            
            chat_id = int(parts[2])
            new_state = bool(int(parts[3]))
            
            categories = await get_chat_enabled_categories(chat_id)
            
            for cat in categories:
                await toggle_user_subscription(
                    callback.from_user.id, 
                    chat_id, 
                    cat["slug"], 
                    new_state
                )
            
            status_text = "включены" if new_state else "отключены"
            await callback.answer(f"✅ Все уведомления {status_text}!", show_alert=True)
            
            await update_tags_message(callback.message, callback.from_user.id, chat_id)
            return
        
        # Обработка отдельной категории
        if len(parts) != 4:
            await callback.answer("❌ Неверный формат", show_alert=True)
            return
            
        chat_id = int(parts[1])
        category_slug = parts[2]
        new_state = bool(int(parts[3]))
        
        # Авторегистрация
        await get_or_create_user(
            callback.from_user.id,
            callback.from_user.username,
            callback.from_user.first_name
        )
        
        # Меняем подписку
        await toggle_user_subscription(
            callback.from_user.id, 
            chat_id, 
            category_slug, 
            new_state
        )
        
        # Обновляем сообщение
        await update_tags_message(callback.message, callback.from_user.id, chat_id)
        
        # Получаем название категории
        categories = await get_chat_enabled_categories(chat_id)
        cat_name = next(
            (c.get("name", category_slug) for c in categories if c.get("slug") == category_slug), 
            category_slug
        )
        status_text = "включены" if new_state else "отключены"
        
        await callback.answer(f"✅ {cat_name}: уведомления {status_text}!")
        
    except DatabaseError as e:
        logger.error(f"Database error in tagsub: {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.error(f"Error in tagsub: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при изменении подписки", show_alert=True)


@router.callback_query(F.data == "my_tags_menu")
async def my_tags_menu_callback(callback: CallbackQuery) -> None:
    """Кнопка 'Мои теги' из главного меню."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    
    if callback.message.chat.type not in ['group', 'supergroup']:
        await callback.message.edit_text(
            "❌ <b>Управление тегами доступно только в группах!</b>\n\n"
            "Добавьте бота в группу и используйте команду <code>/mytags</code> там.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return
    
    loading_msg = await callback.message.edit_text("🔄 Загрузка категорий...")
    
    try:
        tables_exist = await check_tag_tables_exist()
        
        if not tables_exist:
            await loading_msg.edit_text(
                "📭 <b>Система тегов ещё не настроена</b>\n\n"
                "Администратор должен сначала включить категории через /tagadmin",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
                ])
            )
            await callback.answer()
            return
        
        await update_tags_message(loading_msg, user_id, chat_id)
        
    except Exception as e:
        logger.error(f"Error in my_tags_menu: {e}", exc_info=True)
        await loading_msg.edit_text(
            "❌ <b>Ошибка загрузки категорий</b>\n\n"
            "Попробуйте позже или используйте команду /mytags",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    
    await callback.answer()
