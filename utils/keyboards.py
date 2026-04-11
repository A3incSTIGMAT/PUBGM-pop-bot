from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"),
         InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance")],
        [InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games"),
         InlineKeyboardButton(text="⭐ VIP", callback_data="vip")],
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")],
        [InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy"),
         InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help")],
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
    """Кнопка возврата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
