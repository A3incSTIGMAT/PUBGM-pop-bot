def get_games_menu() -> InlineKeyboardMarkup:
    """Меню игр"""
    buttons = [
        [
            InlineKeyboardButton(text="🪨 Камень-ножницы-бумага", callback_data="game_rps"),
            InlineKeyboardButton(text="🎲 Рулетка", callback_data="game_roulette")
        ],
        [
            InlineKeyboardButton(text="🎰 Слот-машина", callback_data="game_slot"),
            InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
