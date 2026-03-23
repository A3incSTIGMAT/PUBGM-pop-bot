from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Главное меню (Reply-клавиатура)
def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="🎮 Игры"), KeyboardButton(text="🎁 Подарки")]
    ]
    
    if is_admin:
        buttons.append([KeyboardButton(text="🛡 Админ-панель")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Меню игр (Inline-клавиатура)
def get_games_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel")],
        [InlineKeyboardButton(text="🪨 Камень-ножницы-бумага", callback_data="game_rps")],
        [InlineKeyboardButton(text="🎲 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton(text="🔫 Русская рулетка", callback_data="game_russian_roulette")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Меню магазина подарков
def get_shop_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🌹 Роза (10 монет)", callback_data="gift_rose")],
        [InlineKeyboardButton(text="🍰 Торт (50 монет)", callback_data="gift_cake")],
        [InlineKeyboardButton(text="💎 Алмаз (500 монет)", callback_data="gift_diamond")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
