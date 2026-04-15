from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню (с админ-кнопкой для владельца чата)"""
    keyboard = [
        [InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"),
         InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance")],
        [InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games"),
         InlineKeyboardButton(text="⭐ VIP", callback_data="vip")],
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")],
        [InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate"),
         InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="my_tags_menu")],
        [InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="feedback_menu"),
         InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help")],
    ]
    
    # Кнопка для администратора (только для владельца чата)
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 УПРАВЛЕНИЕ ТЭГАМИ", callback_data="tag_admin_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_menu() -> InlineKeyboardMarkup:
    """Меню администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 УПРАВЛЕНИЕ ТЭГАМИ", callback_data="tag_admin_menu")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def tag_admin_panel() -> InlineKeyboardMarkup:
    """Панель управления тегами для админа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 ВКЛЮЧИТЬ КАТЕГОРИИ", callback_data="tag_enable_categories")],
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


def slot_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для слота (выбор ставки)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 50", callback_data="slot_50"),
         InlineKeyboardButton(text="🎰 100", callback_data="slot_100"),
         InlineKeyboardButton(text="🎰 200", callback_data="slot_200")],
        [InlineKeyboardButton(text="🎰 500", callback_data="slot_500"),
         InlineKeyboardButton(text="🎰 1000", callback_data="slot_1000"),
         InlineKeyboardButton(text="🎰 МАКС", callback_data="slot_max")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
    ])


def roulette_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для рулетки (выбор цвета и ставки)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 50", callback_data="roulette_red_50"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 50", callback_data="roulette_black_50")],
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 100", callback_data="roulette_red_100"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 100", callback_data="roulette_black_100")],
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 200", callback_data="roulette_red_200"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 200", callback_data="roulette_black_200")],
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 500", callback_data="roulette_red_500"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 500", callback_data="roulette_black_500")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
    ])


def rps_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для КНБ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗿 КАМЕНЬ", callback_data="rps_rock"),
         InlineKeyboardButton(text="✂️ НОЖНИЦЫ", callback_data="rps_scissors"),
         InlineKeyboardButton(text="📄 БУМАГА", callback_data="rps_paper")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
    ])


def duel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для дуэли (выбор ставки)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ 100", callback_data="duel_100"),
         InlineKeyboardButton(text="⚔️ 200", callback_data="duel_200"),
         InlineKeyboardButton(text="⚔️ 500", callback_data="duel_500")],
        [InlineKeyboardButton(text="⚔️ 1000", callback_data="duel_1000"),
         InlineKeyboardButton(text="⚔️ 5000", callback_data="duel_5000"),
         InlineKeyboardButton(text="⚔️ МАКС", callback_data="duel_max")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
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
