from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню (с опциональной кнопкой админа)"""
    kb = [
        [InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"),
         InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance")],
        [InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games"),
         InlineKeyboardButton(text="⭐ VIP", callback_data="vip")],
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")]
    ]
    
    if is_admin:
        kb.append([InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="admin_menu")])
    
    kb.append([
        InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy"),
        InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_menu() -> InlineKeyboardMarkup:
    """Меню администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 УПРАВЛЕНИЕ ТЭГАМИ", callback_data="tagadmin_menu")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data="stats_chat")],
        [InlineKeyboardButton(text="⚙️ НАСТРОЙКИ БОТА", callback_data="bot_settings")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def tag_admin_panel() -> InlineKeyboardMarkup:
    """Панель управления тегами для админа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="tagadmin_categories")],
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="tagadmin_add")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="tagadmin_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_menu")]
    ])


def games_menu() -> InlineKeyboardMarkup:
    """Меню игр"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 СЛОТ", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 РУЛЕТКА", callback_data="game_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="game_rps"),
         InlineKeyboardButton(text="⚔️ ДУЭЛЬ", callback_data="game_duel")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def back_button() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def ref_menu() -> InlineKeyboardMarkup:
    """Меню реферальной системы"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 МОЯ ССЫЛКА", callback_data="my_ref")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="ref_stats_chat")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
