from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games"),
         InlineKeyboardButton(text="🛒 Магазин", callback_data="shop")],
        [InlineKeyboardButton(text="⭐ VIP", callback_data="vip"),
         InlineKeyboardButton(text="📢 Тэги", callback_data="tag_menu")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
         InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
    ])


def games_menu() -> InlineKeyboardMarkup:
    """Меню игр"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Слот", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="game_rps"),
         InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])


def back_button() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])


def tag_menu() -> InlineKeyboardMarkup:
    """Меню тэгов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Тэгнуть всех", callback_data="confirm_all")],
        [InlineKeyboardButton(text="🔔 Как пользоваться", callback_data="tag_help")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
