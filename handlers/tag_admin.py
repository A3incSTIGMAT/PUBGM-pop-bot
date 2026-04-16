"""
Модуль управления категориями тегов
Доступ: владелец чата + разработчик (в чатах, где он админ)
"""

import logging
from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.tag_categories import (
    get_all_categories, get_chat_enabled_slugs, toggle_chat_category, init_categories
)

logger = logging.getLogger(__name__)
router = Router()

# ID разработчика (имеет доступ к управлению тегами в чатах, где он админ)
DEVELOPER_IDS = [895844198]  # ← твой Telegram ID


async def can_manage_tags(bot, user_id: int, chat_id: int) -> bool:
    """Проверяет, может ли пользователь управлять тегами:
    - владелец чата
    - или разработчик (в любом чате, где он админ)
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        
        # Владелец чата
        if member.status == 'creator':
            return True
        
        # Разработчик (ты) — если ты админ в этом чате
        if user_id in DEVELOPER_IDS and member.status == 'administrator':
            return True
        
        return False
    except Exception as e:
        logger.error(f"Manage tags check failed: {e}")
        return False


@router.callback_query(F.data == "tag_admin_menu")
async def tag_admin_menu(callback: types.CallbackQuery):
    """Меню управления тегами"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    if not await can_manage_tags(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только владелец чата может управлять тегами!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 ВКЛЮЧИТЬ КАТЕГОРИИ", callback_data="tag_enable_categories")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "👑 *УПРАВЛЕНИЕ ТЭГАМИ*\n\n"
        "Здесь вы можете включить или отключить категории тегов в вашем чате.\n\n"
        "Участники смогут подписываться только на включённые категории.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "tag_enable_categories")
async def tag_enable_categories(callback: types.CallbackQuery):
    """Список категорий для включения/отключения"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    if not await can_manage_tags(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только владелец чата!", show_alert=True)
        return
    
    await init_categories()
    
    all_categories = await get_all_categories()
    enabled_slugs = await get_chat_enabled_slugs(chat_id)
    
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
        "📋 *КАТЕГОРИИ ТЭГОВ*\n\n"
        "✅ — категория активна (участники могут подписываться)\n"
        "❌ — категория скрыта\n\n"
        "Нажмите на категорию, чтобы изменить статус:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_cat_"))
async def toggle_category(callback: types.CallbackQuery):
    """Включение/отключение категории"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    category_slug = callback.data.split("_")[2]
    
    if not await can_manage_tags(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только владелец чата!", show_alert=True)
        return
    
    enabled_slugs = await get_chat_enabled_slugs(chat_id)
    is_enabled = category_slug in enabled_slugs
    
    await toggle_chat_category(chat_id, category_slug, not is_enabled)
    
    status = "включена" if not is_enabled else "отключена"
    await callback.answer(f"✅ Категория {status}")
    
    # Обновляем список
    await tag_enable_categories(callback)
