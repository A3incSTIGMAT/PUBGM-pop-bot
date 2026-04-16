"""
Модуль управления подписками пользователя на теги
"""

import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.tag_categories import (
    get_chat_enabled_categories, get_user_subscriptions, toggle_user_subscription
)

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("mytags"))
async def cmd_mytags(message: types.Message):
    """Управление подписками на теги"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    # Отправляем сообщение "Загрузка..."
    loading_msg = await message.answer("🔄 Загрузка категорий...")
    
    try:
        categories = await get_chat_enabled_categories(chat_id)
        
        if not categories:
            await loading_msg.edit_text(
                "📭 В этом чате нет активных категорий тегов.\n\n"
                "Попросите администратора настроить их через /tagadmin"
            )
            return
        
        subs = await get_user_subscriptions(user_id, chat_id)
        
        keyboard = []
        for cat in categories:
            is_on = subs.get(cat["slug"], True)
            status_text = "✅ ВКЛ" if is_on else "❌ ВЫКЛ"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{cat['icon']} {cat['name']} [{status_text}]",
                    callback_data=f"tagsub_{chat_id}_{cat['slug']}_{1 if not is_on else 0}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")])
        
        await loading_msg.edit_text(
            f"🏷️ *МОИ ТЕГИ*\n\nЧат: {message.chat.title}\n\n"
            "✅ ВКЛ — вы получаете уведомления\n"
            "❌ ВЫКЛ — уведомления отключены\n\n"
            "👇 Нажмите на категорию, чтобы изменить статус:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in mytags: {e}")
        await loading_msg.edit_text(
            "❌ Ошибка загрузки категорий.\n\n"
            "Пожалуйста, попробуйте позже или сообщите администратору."
        )


@router.callback_query(F.data.startswith("tagsub_"))
async def toggle_user_subscription_callback(callback: types.CallbackQuery):
    """Переключение подписки пользователя с визуальным обновлением"""
    try:
        parts = callback.data.split("_")
        chat_id = int(parts[1])
        category_slug = parts[2]
        new_state = bool(int(parts[3]))
        
        # Меняем подписку
        await toggle_user_subscription(callback.from_user.id, chat_id, category_slug, new_state)
        
        # Получаем обновлённые данные
        categories = await get_chat_enabled_categories(chat_id)
        subs = await get_user_subscriptions(callback.from_user.id, chat_id)
        
        # Перестраиваем клавиатуру
        keyboard = []
        for cat in categories:
            is_on = subs.get(cat["slug"], True)
            status_text = "✅ ВКЛ" if is_on else "❌ ВЫКЛ"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{cat['icon']} {cat['name']} [{status_text}]",
                    callback_data=f"tagsub_{chat_id}_{cat['slug']}_{1 if not is_on else 0}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")])
        
        cat_name = next((c["name"] for c in categories if c["slug"] == category_slug), category_slug)
        status_text = "включены" if new_state else "отключены"
        
        await callback.message.edit_text(
            f"🏷️ *МОИ ТЕГИ*\n\nЧат: {callback.message.chat.title}\n\n"
            "✅ ВКЛ — вы получаете уведомления\n"
            "❌ ВЫКЛ — уведомления отключены\n\n"
            "👇 Нажмите на категорию, чтобы изменить статус:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
        await callback.answer(f"✅ {cat_name}: уведомления {status_text}!")
        
    except Exception as e:
        logger.error(f"Error in tagsub callback: {e}")
        await callback.answer("❌ Ошибка при изменении подписки", show_alert=True)


@router.callback_query(F.data == "my_tags_menu")
async def my_tags_menu_callback(callback: types.CallbackQuery):
    """Кнопка 'Мои теги' из главного меню"""
    await cmd_mytags(callback.message)
    await callback.answer()
