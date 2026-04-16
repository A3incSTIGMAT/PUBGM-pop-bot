from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню — разбито на категории, админ-кнопка только для админов"""
    
    # КАТЕГОРИЯ 1: ОСНОВНОЕ
    row1 = [
        InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="vip"),
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")
    ]
    
    # КАТЕГОРИЯ 2: ФИНАНСЫ И РАНГ
    row2 = [
        InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
        InlineKeyboardButton(text="🏆 РАНГ", callback_data="rank_menu")
    ]
    
    # КАТЕГОРИЯ 3: ИГРЫ
    row3 = [
        InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games"),
        InlineKeyboardButton(text="🎮 ЛИЧНЫЕ ИГРЫ", callback_data="private_games")
    ]
    
    # КАТЕГОРИЯ 4: ОПОВЕЩЕНИЯ
    row4 = [
        InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
        InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")
    ]
    
    # КАТЕГОРИЯ 5: СОЦИАЛКА
    row5 = [
        InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="relationships_menu"),
        InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="groups_menu")
    ]
    
    # КАТЕГОРИЯ 6: РП И ТЕГИ
    row6 = [
        InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="rp_menu"),
        InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="my_tags_menu")
    ]
    
    # КАТЕГОРИЯ 7: ИНФО
    row7 = [
        InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="top_chats"),
        InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy")
    ]
    
    # КАТЕГОРИЯ 8: ПОМОЩЬ И ПОДДЕРЖКА
    row8 = [
        InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help"),
        InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate")
    ]
    
    # КАТЕГОРИЯ 9: ОБРАТНАЯ СВЯЗЬ
    row9 = [
        InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="feedback_menu")
    ]
    
    # Собираем все строки
    keyboard = [row1, row2, row3, row4, row5, row6, row7, row8, row9]
    
    # Админ-панель (только для администраторов)
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_panel_menu() -> InlineKeyboardMarkup:
    """Панель администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 УПРАВЛЕНИЕ ТЭГАМИ", callback_data="tag_admin_menu")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data="stats_chat")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def games_category_menu() -> InlineKeyboardMarkup:
    """Подменю ИГРЫ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 СЛОТ", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 РУЛЕТКА", callback_data="game_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="game_rps"),
         InlineKeyboardButton(text="⚔️ ДУЭЛЬ", callback_data="game_duel")],
        [InlineKeyboardButton(text="🎮 ЛИЧНЫЕ ИГРЫ", callback_data="private_games")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def profile_category_menu() -> InlineKeyboardMarkup:
    """Подменю ПРОФИЛЬ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 МОЙ ПРОФИЛЬ", callback_data="profile"),
         InlineKeyboardButton(text="🏆 МОЙ РАНГ", callback_data="rank_menu")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="my_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def finance_category_menu() -> InlineKeyboardMarkup:
    """Подменю ФИНАНСЫ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")],
        [InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def social_category_menu() -> InlineKeyboardMarkup:
    """Подменю СОЦИАЛКА"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="relationships_menu"),
         InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="groups_menu")],
        [InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="rp_menu")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def notifications_category_menu() -> InlineKeyboardMarkup:
    """Подменю ОПОВЕЩЕНИЯ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
         InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="my_tags_menu")],
        [InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="top_chats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def settings_category_menu() -> InlineKeyboardMarkup:
    """Подменю НАСТРОЙКИ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy"),
         InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="feedback_menu")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def games_menu() -> InlineKeyboardMarkup:
    """Меню игр (для обратной совместимости)"""
    return games_category_menu()


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
        [InlineKeyboardButton(text="📊 ТОП ПРИГЛАСИТЕЛЕЙ", callback_data="ref_top")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def private_games_menu() -> InlineKeyboardMarkup:
    """Меню личных игр"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 СЛОТ", callback_data="private_slot"),
         InlineKeyboardButton(text="🎡 РУЛЕТКА", callback_data="private_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="private_rps"),
         InlineKeyboardButton(text="⚔️ ДУЭЛЬ", callback_data="private_duel")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="private_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def admin_menu() -> InlineKeyboardMarkup:
    """Меню администратора (устаревшее)"""
    return admin_panel_menu()
