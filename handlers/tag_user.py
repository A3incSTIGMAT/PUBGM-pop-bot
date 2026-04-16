"""
Модуль управления подписками пользователя на теги
"""

import logging
import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Получить пользователя или создать если не существует"""
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Auto-registered user {user_id} in tag_user module")
    return user


async def check_tag_tables_exist() -> bool:
    """Проверить существование таблиц тегов (асинхронно)"""
    def _sync_check():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_tag_settings'")
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    return await asyncio.to_thread(_sync_check)


# ==================== ИМПОРТ ФУНКЦИЙ ИЗ TAG_CATEGORIES ====================

# Пытаемся импортировать, если не получится - создаём заглушки
try:
    from handlers.tag_categories import (
        get_chat_enabled_categories, 
        get_user_subscriptions, 
        toggle_user_subscription
    )
except ImportError:
    logger.warning("tag_categories module not found, using stubs")
    
    async def get_chat_enabled_categories(chat_id: int):
        """Заглушка для получения категорий"""
        return []
    
    async def get_user_subscriptions(user_id: int, chat_id: int):
        """Заглушка для получения подписок"""
        return {}
    
    async def toggle_user_subscription(user_id: int, chat_id: int, category_slug: str, state: bool):
        """Заглушка для переключения подписки"""
        pass


# ==================== КОМАНДА /mytags ====================

@router.message(Command("mytags"))
async def cmd_mytags(message: types.Message):
    """Управление подписками на теги"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Проверяем, что команда в группе
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    # Авторегистрация пользователя
    await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    loading_msg = await message.answer("🔄 Загрузка категорий...")
    
    try:
        # Проверяем, есть ли таблицы
        tables_exist = await check_tag_tables_exist()
        
        if not tables_exist:
            await loading_msg.edit_text(
                "📭 *Система тегов ещё не настроена*\n\n"
                "Администратор должен сначала включить категории через /tagadmin\n\n"
                "💡 *Для администраторов:*\n"
                "Используйте `/tagadmin` для настройки тегов в этом чате.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        categories = await get_chat_enabled_categories(chat_id)
        
        if not categories:
            await loading_msg.edit_text(
                "📭 *В этом чате нет активных категорий тегов*\n\n"
                "Администратор может добавить их через /tagadmin\n\n"
                "💡 *Совет:* Включите хотя бы одну категорию, чтобы участники могли подписываться.\n\n"
                "🔔 *Что такое теги?*\n"
                "Теги позволяют получать уведомления только по интересным вам темам: "
                "поиск игроков, важные объявления, розыгрыши и многое другое!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
                ])
            )
            return
        
        subs = await get_user_subscriptions(user_id, chat_id)
        
        # Сортируем категории по алфавиту
        categories.sort(key=lambda x: x.get('name', ''))
        
        keyboard = []
        for cat in categories:
            is_on = subs.get(cat.get("slug", ""), True)  # По умолчанию подписка включена
            status_text = "✅ ВКЛ" if is_on else "❌ ВЫКЛ"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{cat.get('icon', '🔔')} {cat.get('name', 'Unknown')} [{status_text}]",
                    callback_data=f"tagsub_{chat_id}_{cat['slug']}_{1 if not is_on else 0}"
                )
            ])
        
        # Добавляем кнопки управления
        keyboard.append([
            InlineKeyboardButton(text="✅ ВКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_1"),
            InlineKeyboardButton(text="❌ ВЫКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_0")
        ])
        keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД В МЕНЮ", callback_data="back_to_menu")])
        
        # Статистика подписок
        total_cats = len(categories)
        enabled_count = sum(1 for cat in categories if subs.get(cat.get("slug", ""), True))
        
        await loading_msg.edit_text(
            f"🏷️ *МОИ ТЕГИ*\n\n"
            f"📌 Чат: *{message.chat.title}*\n"
            f"📊 Активно: *{enabled_count}/{total_cats}* категорий\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ *ВКЛ* — вы получаете уведомления\n"
            f"❌ *ВЫКЛ* — уведомления отключены\n\n"
            f"👇 Нажмите на категорию, чтобы изменить статус:\n\n"
            f"💡 *Совет:* Отключите ненужные категории, чтобы не получать лишних уведомлений!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in mytags: {e}", exc_info=True)
        await loading_msg.edit_text(
            f"❌ *Ошибка загрузки категорий*\n\n"
            f"Причина: `{str(e)[:100]}`\n\n"
            f"Пожалуйста, сообщите администратору или попробуйте позже.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )


# ==================== КОЛЛБЭКИ ДЛЯ УПРАВЛЕНИЯ ПОДПИСКАМИ ====================

@router.callback_query(F.data.startswith("tagsub_"))
async def toggle_subscription_callback(callback: types.CallbackQuery):
    """Переключение подписки пользователя с визуальным обновлением"""
    try:
        parts = callback.data.split("_")
        
        # Обработка "включить/выключить все"
        if parts[1] == "all":
            if len(parts) != 4:
                await callback.answer("❌ Неверный формат запроса", show_alert=True)
                return
            
            chat_id = int(parts[2])
            new_state = bool(int(parts[3]))
            
            categories = await get_chat_enabled_categories(chat_id)
            
            # Переключаем все категории
            for cat in categories:
                await toggle_user_subscription(
                    callback.from_user.id, 
                    chat_id, 
                    cat["slug"], 
                    new_state
                )
            
            status_text = "включены" if new_state else "отключены"
            await callback.answer(f"✅ Все уведомления {status_text}!", show_alert=True)
            
            # Обновляем сообщение
            await update_tags_message(callback.message, callback.from_user.id, chat_id)
            return
        
        # Обработка отдельной категории
        if len(parts) != 4:
            await callback.answer("❌ Неверный формат запроса", show_alert=True)
            return
            
        chat_id = int(parts[1])
        category_slug = parts[2]
        new_state = bool(int(parts[3]))
        
        logger.info(f"Toggling subscription for user {callback.from_user.id} on {category_slug} to {new_state}")
        
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
        
        # Получаем обновлённые данные и обновляем сообщение
        await update_tags_message(callback.message, callback.from_user.id, chat_id)
        
        # Получаем название категории для уведомления
        categories = await get_chat_enabled_categories(chat_id)
        cat_name = next((c.get("name", category_slug) for c in categories if c.get("slug") == category_slug), category_slug)
        status_text = "включены" if new_state else "отключены"
        
        await callback.answer(f"✅ {cat_name}: уведомления {status_text}!")
        
    except Exception as e:
        logger.error(f"Error in tagsub callback: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при изменении подписки", show_alert=True)


async def update_tags_message(message: types.Message, user_id: int, chat_id: int):
    """Обновить сообщение с тегами"""
    try:
        categories = await get_chat_enabled_categories(chat_id)
        subs = await get_user_subscriptions(user_id, chat_id)
        
        # Сортируем категории
        categories.sort(key=lambda x: x.get('name', ''))
        
        keyboard = []
        for cat in categories:
            is_on = subs.get(cat.get("slug", ""), True)
            status_text = "✅ ВКЛ" if is_on else "❌ ВЫКЛ"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{cat.get('icon', '🔔')} {cat.get('name', 'Unknown')} [{status_text}]",
                    callback_data=f"tagsub_{chat_id}_{cat['slug']}_{1 if not is_on else 0}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(text="✅ ВКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_1"),
            InlineKeyboardButton(text="❌ ВЫКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_0")
        ])
        keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД В МЕНЮ", callback_data="back_to_menu")])
        
        total_cats = len(categories)
        enabled_count = sum(1 for cat in categories if subs.get(cat.get("slug", ""), True))
        
        await message.edit_text(
            f"🏷️ *МОИ ТЕГИ*\n\n"
            f"📌 Чат: *{message.chat.title}*\n"
            f"📊 Активно: *{enabled_count}/{total_cats}* категорий\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ *ВКЛ* — вы получаете уведомления\n"
            f"❌ *ВЫКЛ* — уведомления отключены\n\n"
            f"👇 Нажмите на категорию, чтобы изменить статус:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        logger.error(f"Error updating tags message: {e}")
        raise


# ==================== КНОПКА "МОИ ТЕГИ" ИЗ МЕНЮ ====================

@router.callback_query(F.data == "my_tags_menu")
async def my_tags_menu_callback(callback: types.CallbackQuery):
    """Кнопка 'Мои теги' из главного меню"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # Авторегистрация
    await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    # Проверяем тип чата
    if callback.message.chat.type not in ['group', 'supergroup']:
        await callback.message.edit_text(
            "❌ *Управление тегами доступно только в группах!*\n\n"
            "Добавьте бота в группу и используйте команду `/mytags` там.",
            parse_mode=ParseMode.MARKDOWN,
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
                "📭 *Система тегов ещё не настроена*\n\n"
                "Администратор должен сначала включить категории через /tagadmin",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
                ])
            )
            await callback.answer()
            return
        
        categories = await get_chat_enabled_categories(chat_id)
        
        if not categories:
            await loading_msg.edit_text(
                "📭 *В этом чате нет активных категорий тегов*\n\n"
                "Администратор может добавить их через /tagadmin",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
                ])
            )
            await callback.answer()
            return
        
        subs = await get_user_subscriptions(user_id, chat_id)
        categories.sort(key=lambda x: x.get('name', ''))
        
        keyboard = []
        for cat in categories:
            is_on = subs.get(cat.get("slug", ""), True)
            status_text = "✅ ВКЛ" if is_on else "❌ ВЫКЛ"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{cat.get('icon', '🔔')} {cat.get('name', 'Unknown')} [{status_text}]",
                    callback_data=f"tagsub_{chat_id}_{cat['slug']}_{1 if not is_on else 0}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(text="✅ ВКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_1"),
            InlineKeyboardButton(text="❌ ВЫКЛЮЧИТЬ ВСЕ", callback_data=f"tagsub_all_{chat_id}_0")
        ])
        keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД В МЕНЮ", callback_data="back_to_menu")])
        
        total_cats = len(categories)
        enabled_count = sum(1 for cat in categories if subs.get(cat.get("slug", ""), True))
        
        await loading_msg.edit_text(
            f"🏷️ *МОИ ТЕГИ*\n\n"
            f"📌 Чат: *{callback.message.chat.title}*\n"
            f"📊 Активно: *{enabled_count}/{total_cats}* категорий\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ *ВКЛ* — вы получаете уведомления\n"
            f"❌ *ВЫКЛ* — уведомления отключены\n\n"
            f"👇 Нажмите на категорию, чтобы изменить статус:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in my_tags_menu: {e}", exc_info=True)
        await loading_msg.edit_text(
            f"❌ *Ошибка загрузки категорий*\n\n"
            f"Попробуйте позже или используйте команду `/mytags`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    
    await callback.answer()


# ==================== ФУНКЦИЯ ДЛЯ СОВМЕСТИМОСТИ ====================

async def format_user_tags(user_id: int) -> str:
    """Форматирование тегов пользователя для отображения (для start.py)"""
    user = await db.get_user(user_id)
    if not user:
        return "❌ Пользователь не найден"
    
    # Здесь можно добавить логику получения тегов
    return "🏷️ *МОИ ТЕГИ*\n\nИспользуйте команду /mytags в группе для управления подписками."
