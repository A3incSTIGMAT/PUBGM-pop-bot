"""
Клавиатуры для игр NEXUS бота.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_games_menu() -> InlineKeyboardMarkup:
    """Главное меню игр"""
    buttons = [
        [InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel")],
        [InlineKeyboardButton(text="🪨 Камень-ножницы-бумага", callback_data="game_rps")],
        [InlineKeyboardButton(text="🎲 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton(text="🔫 Русская рулетка", callback_data="game_russian")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="games_close")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_rps_menu() -> InlineKeyboardMarkup:
    """Меню для игры камень-ножницы-бумага"""
    buttons = [
        [InlineKeyboardButton(text="🪨 Камень", callback_data="rps_rock")],
        [InlineKeyboardButton(text="✂️ Ножницы", callback_data="rps_scissors")],
        [InlineKeyboardButton(text="📄 Бумага", callback_data="rps_paper")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="games_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_roulette_menu() -> InlineKeyboardMarkup:
    """Меню для рулетки"""
    buttons = [
        [InlineKeyboardButton(text="🔴 Красное (x2)", callback_data="roulette_red")],
        [InlineKeyboardButton(text="⚫ Черное (x2)", callback_data="roulette_black")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="games_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_bet_amount_menu(game: str) -> InlineKeyboardMarkup:
    """Меню выбора суммы ставки"""
    buttons = [
        [InlineKeyboardButton(text="10", callback_data=f"bet_{game}_10"),
         InlineKeyboardButton(text="50", callback_data=f"bet_{game}_50"),
         InlineKeyboardButton(text="100", callback_data=f"bet_{game}_100")],
        [InlineKeyboardButton(text="250", callback_data=f"bet_{game}_250"),
         InlineKeyboardButton(text="500", callback_data=f"bet_{game}_500"),
         InlineKeyboardButton(text="1000", callback_data=f"bet_{game}_1000")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"game_{game}_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_duel_menu(opponent_id: int, amount: int) -> InlineKeyboardMarkup:
    """Меню для подтверждения дуэли"""
    buttons = [
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"duel_accept_{opponent_id}_{amount}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data="duel_decline")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_russian_roulette_menu() -> InlineKeyboardMarkup:
    """Меню для русской рулетки"""
    buttons = [
        [InlineKeyboardButton(text="🔫 Выстрелить", callback_data="rr_shoot")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data="games_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
