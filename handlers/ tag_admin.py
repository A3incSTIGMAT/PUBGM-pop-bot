"""
Модуль управления тегами для администраторов чата
Команда: /tagadmin
"""

import logging
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from utils.tag_categories import (
    get_chat_enabled_categories,
    DEFAULT_CATEGORIES,
    toggle_chat_category,
    add_custom_category,
    delete_custom_category
)

router = Router()
logger = logging.getLogger(__name__)

# Настройки
MAX_CATEGORY_NAME_LENGTH = 50


class TagAdminState(StatesGroup):
    adding_custom = State()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def _check_admin_access(callback_or_message: CallbackQuery | Message, chat_id: int) -> bool:
    """Универсальная проверка: пользователь — админ в указанном чате"""
    try:
        user_id = callback_or_message.from_user.id
        # Проверяем, что chat_id из данных совпадает с реальным чатом
        if hasattr(callback_or_message, 'message') and callback_or_message.message.chat.id != chat_id:
            return False
        member = await callback_or_message.bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except Exception as e:
        logger.warning(f"Admin check failed for user {callback_or_message.from_user.id} in chat {chat_id}: {e}")
        return False


def _escape_html(text: str) -> str:
    """Безопасное экранирование для ParseMode.HTML"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ==================== КОМАНДА /tagadmin ====================

@router.message(Command("tagadmin"))
async def cmd_tagadmin(message: Message):
    """Панель управления тегами для админов"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    # Проверка прав
    if not await _check_admin_access(message, chat_id):
        await message.answer("❌ Только администраторы могут управлять тегами!")
        return
    
    try:
        categories = await get_chat_enabled_categories(chat_id)
        enabled_slugs = {c["slug"] for c in categories}
    except Exception as e:
        logger.error(f"Failed to load categories for chat {chat_id}: {e}")
        await message.answer("❌ Ошибка загрузки категорий. Попробуйте позже.")
        return
    
    keyboard = []
    
    # Глобальные категории
    for cat in DEFAULT_CATEGORIES:
        is_enabled = cat["slug"] in enabled_slugs
        status = "✅" if is_enabled else "❌"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {cat['icon']} {cat['name']}",
                callback_data=f"tagadmin_toggle_{chat_id}_{cat['slug']}_{1 if not is_enabled else 0}"
            )
        ])
    
    # Кастомные категории
    custom_cats = [c for c in categories if c["slug"].startswith("custom_")]
    if custom_cats:
        keyboard.append([InlineKeyboardButton(text="─" * 25, callback_data="ignore")])
        for cat in custom_cats:
            safe_name = _escape_html(cat["name"])
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🗑️ Удалить: {cat['icon']} {safe_name}",
                    callback_data=f"tagadmin_delconf_{chat_id}_{cat['slug']}"  # Сначала подтверждение
                )
            ])
    
    keyboard.append([
        InlineKeyboardButton(text="➕ Добавить категорию", callback_data=f"tagadmin_add_custom_{chat_id}")
    ])
    keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")
    ])
    
    await message.answer(
        f"👑 <b>УПРАВЛЕНИЕ ТЕГАМИ</b>\n\n"
        f"Чат: <code>{_escape_html(message.chat.title)}</code>\n\n"
        f"✅ — категория активна\n"
        f"❌ — категория скрыта\n\n"
        f"💡 <i>Участники видят только включённые категории в /mytags</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


# ==================== ОБРАБОТКА КОЛБЭКОВ ====================

@router.callback_query(F.data.startswith("tagadmin_toggle_"))
async def toggle_category(callback: CallbackQuery):
    """Включение/отключение категории в чате"""
    try:
        parts = callback.data.split("_")
        if len(parts) != 5:
            await callback.answer("❌ Неверный формат запроса", show_alert=True)
            return
            
        chat_id = int(parts[2])
        slug = parts[3]
        value = bool(int(parts[4]))
        
        # 🔐 ПРОВЕРКА БЕЗОПАСНОСТИ
        if not await _check_admin_access(callback, chat_id):
            await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
            return
        
        await toggle_chat_category(chat_id, slug, value)
        
        cat_name = next((c["name"] for c in DEFAULT_CATEGORIES if c["slug"] == slug), slug)
        status = "включена" if value else "отключена"
        await callback.answer(f"✅ {cat_name}: {status}")
        
        # Обновляем панель (с обработкой возможного удаления сообщения)
        try:
            await cmd_tagadmin(callback.message)
        except:
            # Если сообщение удалено, отправляем новое
            await callback.message.answer("✅ Настройки обновлены")
            
    except Exception as e:
        logger.error(f"Toggle category error: {e}")
        await callback.answer("❌ Ошибка при обновлении настроек", show_alert=True)


@router.callback_query(F.data.startswith("tagadmin_add_custom_"))
async def start_add_custom(callback: CallbackQuery, state: FSMContext):
    """Начало добавления кастомной категории"""
    try:
        chat_id = int(callback.data.split("_")[-1])
        
        if not await _check_admin_access(callback, chat_id):
            await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
            return
        
        await state.set_state(TagAdminState.adding_custom)
        await state.update_data(chat_id=chat_id)
        
        await callback.message.answer(
            "➕ <b>НОВАЯ КАТЕГОРИЯ</b>\n\n"
            "Введите название категории (с эмодзи):\n"
            f"Пример: <code>🔍 Поиск напарника</code>\n"
            f"Макс. длина: {MAX_CATEGORY_NAME_LENGTH} символов\n\n"
            "❌ Отмена: /cancel",
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Start add custom error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(TagAdminState.adding_custom)
async def save_custom_category(message: Message, state: FSMContext):
    """Сохранение кастомной категории"""
    if message.text and message.text.startswith("/"):
        await state.clear()
        return
    
    try:
        data = await state.get_data()
        chat_id = data.get("chat_id")
        
        if not chat_id or not await _check_admin_access(message, chat_id):
            await state.clear()
            await message.answer("❌ Сессия истекла или нет прав")
            return
        
        name = message.text.strip()
        
        # Валидация
        if not name:
            await message.answer("❌ Название не может быть пустым")
            return
        if len(name) > MAX_CATEGORY_NAME_LENGTH:
            await message.answer(f"❌ Название слишком длинное (макс. {MAX_CATEGORY_NAME_LENGTH})")
            return
        
        slug = await add_custom_category(chat_id, name, message.from_user.id)
        await state.clear()
        
        safe_name = _escape_html(name)
        await message.answer(f"✅ Категория <b>{safe_name}</b> добавлена и активирована!", parse_mode=ParseMode.HTML)
        await cmd_tagadmin(message)
        
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {e}")
    except Exception as e:
        logger.error(f"Save custom category error: {e}")
        await message.answer("❌ Ошибка при сохранении категории")
        await state.clear()


@router.callback_query(F.data.startswith("tagadmin_delconf_"))
async def confirm_delete_category(callback: CallbackQuery):
    """Подтверждение удаления кастомной категории"""
    try:
        parts = callback.data.split("_")
        chat_id = int(parts[2])
        slug = parts[3]
        
        if not await _check_admin_access(callback, chat_id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return
        
        # Получаем название для отображения
        categories = await get_chat_enabled_categories(chat_id)
        cat = next((c for c in categories if c["slug"] == slug), None)
        cat_name = cat["name"] if cat else slug
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"tagadmin_delete_custom_{chat_id}_{slug}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"tagadmin_toggle_{chat_id}_{slug}_1")  # Просто вернёмся
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"tagadmin_back_{chat_id}")]
        ])
        
        safe_name = _escape_html(cat_name)
        await callback.message.edit_text(
            f"⚠️ <b>УДАЛЕНИЕ КАТЕГОРИИ</b>\n\n"
            f"Вы действительно хотите удалить:\n"
            f"<b>{safe_name}</b>?\n\n"
            f"❗ Все пользовательские подписки на эту категорию будут удалены.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Confirm delete error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("tagadmin_delete_custom_"))
async def delete_custom_category_callback(callback: CallbackQuery):
    """Фактическое удаление кастомной категории"""
    try:
        parts = callback.data.split("_")
        chat_id = int(parts[3])
        slug = parts[4]
        
        if not await _check_admin_access(callback, chat_id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return
        
        await delete_custom_category(chat_id, slug)
        await callback.answer("✅ Категория удалена")
        
        try:
            await cmd_tagadmin(callback.message)
        except:
            await callback.message.answer("✅ Категория удалена. Настройки обновлены.")
            
    except Exception as e:
        logger.error(f"Delete category error: {e}")
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


@router.callback_query(F.data.startswith("tagadmin_back_"))
async def back_to_admin_panel(callback: CallbackQuery):
    """Возврат в панель администратора"""
    try:
        chat_id = int(callback.data.split("_")[-1])
        if not await _check_admin_access(callback, chat_id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return
        await cmd_tagadmin(callback.message)
    except:
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(Command("cancel"), TagAdminState.adding_custom)
async def cancel_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Добавление категории отменено")

