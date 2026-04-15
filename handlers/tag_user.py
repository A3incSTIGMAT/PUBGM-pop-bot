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
    
    categories = await get_chat_enabled_categories(chat_id)
    if not categories:
        await message.answer("📭 В этом чате нет активных категорий тегов")
        return
    
    subs = await get_user_subscriptions(user_id, chat_id)
    
    keyboard = []
    for cat in categories:
        is_on = subs.get(cat["slug"], True)
        status = "🔔 ВКЛ" if is_on else "🔕 ВЫКЛ"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{cat['icon']} {cat['name']} [{status}]",
                callback_data=f"user_sub_{cat['slug']}_{1 if not is_on else 0}"
            )
        ])
    keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")])
    
    await message.answer(
        f"🏷️ *МОИ ТЕГИ*\n\nЧат: {message.chat.title}\n\n"
        "Выберите, на какие темы вы хотите получать уведомления:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@router.callback_query(F.data == "my_tags_menu")
async def my_tags_menu_callback(callback: types.CallbackQuery):
    """Кнопка 'Мои теги' из главного меню"""
    await cmd_mytags(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("user_sub_"))
async def toggle_user_subscription_callback(callback: types.CallbackQuery):
    """Переключение подписки пользователя"""
    parts = callback.data.split("_")
    category_slug = parts[2]
    value = bool(int(parts[3]))
    
    await toggle_user_subscription(
        callback.from_user.id, 
        callback.message.chat.id, 
        category_slug, 
        value
    )
    
    status = "включена" if value else "отключена"
    await callback.answer(f"✅ Подписка {status}")


    # Обновляем меню
    await cmd_mytags(callback.message)
