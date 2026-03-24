"""
Обработчик меню и callback-запросов
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from handlers.roles import get_user_role
from keyboards.main_menu import (
    get_main_menu, get_profile_menu, get_economy_menu,
    get_games_menu, get_moderation_menu, get_stats_menu,
    get_social_menu, get_settings_menu, get_management_menu,
    get_help_menu, get_back_menu
)
from database.db import get_balance, get_user_stats
from utils.helpers import delete_after_response

router = Router()

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Открыть главное меню"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    role = await get_user_role(chat_id, user_id)
    
    response = await message.answer(
        "🏠 **Главное меню NEXUS**\n\n"
        "Выберите категорию:",
        reply_markup=get_main_menu(role)
    )
    await delete_after_response(response, message, delay=60)

# ========== ОБРАБОТЧИКИ MENU ==========

@router.callback_query(lambda c: c.data == "menu_back_main")
async def menu_back_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    role = await get_user_role(chat_id, user_id)
    
    await callback.message.edit_text(
        "🏠 **Главное меню NEXUS**\n\n"
        "Выберите категорию:",
        reply_markup=get_main_menu(role)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    """Меню профиля"""
    await callback.message.edit_text(
        "👤 **Профиль**\n\n"
        "Выберите действие:",
        reply_markup=get_profile_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_economy")
async def menu_economy(callback: CallbackQuery):
    """Меню экономики"""
    await callback.message.edit_text(
        "💰 **Экономика NEXUS**\n\n"
        "Валюта: NCoin\n\n"
        "Выберите действие:",
        reply_markup=get_economy_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_games")
async def menu_games(callback: CallbackQuery):
    """Меню игр"""
    await callback.message.edit_text(
        "🎮 **Игры NEXUS**\n\n"
        "Выберите игру:",
        reply_markup=get_games_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_moderation")
async def menu_moderation(callback: CallbackQuery):
    """Меню модерации"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    role = await get_user_role(chat_id, user_id)
    is_admin = role in ['admin', 'creator', 'global_admin']
    
    await callback.message.edit_text(
        "🛡 **Модерация**\n\n"
        "Выберите действие:",
        reply_markup=get_moderation_menu(is_admin)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    """Меню статистики"""
    await callback.message.edit_text(
        "📊 **Статистика**\n\n"
        "Выберите тип статистики:",
        reply_markup=get_stats_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_social")
async def menu_social(callback: CallbackQuery):
    """Меню социальных функций"""
    await callback.message.edit_text(
        "🎁 **Социальные функции**\n\n"
        "Выберите действие:",
        reply_markup=get_social_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_settings")
async def menu_settings(callback: CallbackQuery):
    """Меню настроек (админ)"""
    await callback.message.edit_text(
        "⚙️ **Настройки чата**\n\n"
        "Выберите настройку:",
        reply_markup=get_settings_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_management")
async def menu_management(callback: CallbackQuery):
    """Меню управления (админ)"""
    await callback.message.edit_text(
        "👥 **Управление**\n\n"
        "Выберите действие:",
        reply_markup=get_management_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    """Меню помощи"""
    await callback.message.edit_text(
        "❓ **Помощь**\n\n"
        "Выберите раздел:",
        reply_markup=get_help_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_about")
async def menu_about(callback: CallbackQuery):
    """Информация о боте"""
    await callback.message.edit_text(
        "ℹ️ **О NEXUS**\n\n"
        "🤖 NEXUS — развивающаяся экосистема для вашего чата.\n\n"
        "✅ **Возможности:**\n"
        "• 🛡 Модерация\n"
        "• 💰 Экономика (NCoin)\n"
        "• 🎮 Игры\n"
        "• 📊 Статистика\n"
        "• 🔐 Защита от спама и ботов\n\n"
        "🚀 **Скоро:**\n"
        "• Магазин подарков\n"
        "• Кланы\n"
        "• VIP-статусы\n"
        "• Реальные покупки\n\n"
        "📖 Справка: /help\n"
        "🔧 Настройка: /setup\n\n"
        "Разработчик: @A3incSTIGMAT",
        reply_markup=get_back_menu()
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ПРОФИЛЯ ==========

@router.callback_query(lambda c: c.data == "profile_balance")
async def profile_balance(callback: CallbackQuery):
    """Показать баланс"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    await callback.message.edit_text(
        f"💰 **Ваш баланс:** {balance} NCoin\n\n"
        f"💡 Получить бонус: /daily",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_stats")
async def profile_stats(callback: CallbackQuery):
    """Показать статистику"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    stats = get_user_stats(user_id, chat_id)
    
    if stats:
        text = (
            f"📊 **Ваша статистика**\n\n"
            f"💰 Баланс: {stats['balance']} NCoin\n"
            f"💬 Сообщений: {stats['total_messages']}\n"
            f"👑 VIP: {'Да' if stats['is_vip'] else 'Нет'}\n"
            f"⭐ Репутация: {stats['reputation']}\n"
            f"🎂 ДР: {stats['birthday'] or 'не указан'}"
        )
    else:
        text = "📊 Статистика пока пуста. Напишите несколько сообщений!"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_birthday")
async def profile_birthday(callback: CallbackQuery):
    """Установка дня рождения"""
    await callback.message.edit_text(
        "🎂 **Установка дня рождения**\n\n"
        "Используйте команду /setbirthday для открытия календаря",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_role")
async def profile_role(callback: CallbackQuery):
    """Показать роль"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    role = await get_user_role(chat_id, user_id)
    
    role_names = {
        'global_admin': '🌍 Глобальный супер-админ',
        'creator': '👑 Владелец чата',
        'admin': '🛡 Администратор Telegram',
        'moderator': '🔨 Модератор бота',
        'user': '👤 Обычный участник'
    }
    
    await callback.message.edit_text(
        f"👑 **Ваша роль:** {role_names.get(role, 'Обычный участник')}",
        reply_markup=get_back_menu()
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ЭКОНОМИКИ ==========

@router.callback_query(lambda c: c.data == "eco_balance")
async def eco_balance(callback: CallbackQuery):
    """Показать баланс"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    await callback.message.edit_text(
        f"💰 **Ваш баланс:** {balance} NCoin\n\n"
        f"💡 Получить бонус: /daily",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_daily")
async def eco_daily(callback: CallbackQuery):
    """Ежедневный бонус"""
    await callback.message.edit_text(
        "🎁 **Ежедневный бонус**\n\n"
        "Используйте команду /daily для получения бонуса",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_gift")
async def eco_gift(callback: CallbackQuery):
    """Подарить NCoin"""
    await callback.message.edit_text(
        "🎁 **Подарить NCoin**\n\n"
        "Используйте команду /gift @username [сумма]\n"
        "Пример: /gift @ivan 50",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_top")
async def eco_top(callback: CallbackQuery):
    """Топ богачей"""
    await callback.message.edit_text(
        "🏆 **Топ богачей**\n\n"
        "Используйте команду /top для просмотра топа",
        reply_markup=get_back_menu()
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ИГР ==========

@router.callback_query(lambda c: c.data == "game_rps")
async def game_rps(callback: CallbackQuery):
    """Запуск игры камень-ножницы-бумага"""
    await callback.message.edit_text(
        "🎮 **Камень-ножницы-бумага**\n\n"
        "Используйте команду /rps для начала игры",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "game_roulette")
async def game_roulette(callback: CallbackQuery):
    """Запуск рулетки"""
    await callback.message.edit_text(
        "🎲 **Рулетка**\n\n"
        "Используйте команду /roulette для начала игры",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "game_duel")
async def game_duel(callback: CallbackQuery):
    """Дуэль (в разработке)"""
    await callback.message.edit_text(
        "⚔️ **Дуэль**\n\n"
        "Функция в разработке. Скоро будет доступна!",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "game_slot")
async def game_slot(callback: CallbackQuery):
    """Слот-машина (в разработке)"""
    await callback.message.edit_text(
        "🎰 **Слот-машина**\n\n"
        "Функция в разработке. Скоро будет доступна!",
        reply_markup=get_back_menu()
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ СТАТИСТИКИ ==========

@router.callback_query(lambda c: c.data == "stats_my")
async def stats_my(callback: CallbackQuery):
    """Моя статистика"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    stats = get_user_stats(user_id, chat_id)
    
    if stats:
        text = (
            f"📊 **Ваша статистика**\n\n"
            f"💰 Баланс: {stats['balance']} NCoin\n"
            f"💬 Сообщений: {stats['total_messages']}\n"
            f"👑 VIP: {'Да' if stats['is_vip'] else 'Нет'}\n"
            f"⭐ Репутация: {stats['reputation']}\n"
            f"🎂 ДР: {stats['birthday'] or 'не указан'}"
        )
    else:
        text = "📊 Статистика пока пуста. Напишите несколько сообщений!"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "stats_chat")
async def stats_chat(callback: CallbackQuery):
    """Статистика чата"""
    await callback.message.edit_text(
        "📊 **Статистика чата**\n\n"
        "Функция в разработке. Скоро будет доступна!",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "stats_top_balance")
async def stats_top_balance(callback: CallbackQuery):
    """Топ по балансу"""
    await callback.message.edit_text(
        "🏆 **Топ по балансу**\n\n"
        "Используйте команду /top для просмотра топа",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "stats_top_messages")
async def stats_top_messages(callback: CallbackQuery):
    """Топ по сообщениям"""
    await callback.message.edit_text(
        "💬 **Топ по сообщениям**\n\n"
        "Функция в разработке. Скоро будет доступна!",
        reply_markup=get_back_menu()
    )
    await callback.answer()
