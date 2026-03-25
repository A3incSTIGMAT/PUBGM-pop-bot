"""
Главное меню бота с категориями
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu(user_role: str = "user") -> InlineKeyboardMarkup:
    """
    Главное меню бота.
    user_role: 'user', 'moderator', 'admin', 'creator', 'global_admin'
    """
    buttons = []
    
    # Ряд 1: Основные категории
    buttons.append([
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"),
        InlineKeyboardButton(text="💰 Экономика", callback_data="menu_economy")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games"),
        InlineKeyboardButton(text="🛡 Модерация", callback_data="menu_moderation")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu_stats"),
        InlineKeyboardButton(text="🎁 Социальное", callback_data="menu_social")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="👑 VIP Статус", callback_data="menu_vip"),
        InlineKeyboardButton(text="🤖 AI Помощник", callback_data="menu_ai")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="menu_stars"),
        InlineKeyboardButton(text="💎 Купить NCoin", callback_data="menu_buy")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help"),
        InlineKeyboardButton(text="ℹ️ О боте", callback_data="menu_about")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_menu() -> InlineKeyboardMarkup:
    """Меню профиля пользователя"""
    buttons = [
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data="profile_balance"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="profile_stats")
        ],
        [
            InlineKeyboardButton(text="🎂 День рождения", callback_data="profile_birthday"),
            InlineKeyboardButton(text="👑 Моя роль", callback_data="profile_role")
        ],
        [
            InlineKeyboardButton(text="⭐ Пополнить Stars", callback_data="profile_stars"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_economy_menu() -> InlineKeyboardMarkup:
    """Меню экономики"""
    buttons = [
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data="eco_balance"),
            InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="eco_daily")
        ],
        [
            InlineKeyboardButton(text="🎁 Подарить NCoin", callback_data="eco_gift"),
            InlineKeyboardButton(text="🏆 Топ богачей", callback_data="eco_top")
        ],
        [
            InlineKeyboardButton(text="💎 Купить NCoin", callback_data="eco_buy"),
            InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="eco_stars")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_buy_ncoin_menu() -> InlineKeyboardMarkup:
    """Меню покупки NCoin за Stars"""
    buttons = [
        [
            InlineKeyboardButton(text="⭐ 10 Stars → 100 NCoin", callback_data="buy_10"),
            InlineKeyboardButton(text="⭐ 50 Stars → 500 NCoin", callback_data="buy_50")
        ],
        [
            InlineKeyboardButton(text="⭐ 100 Stars → 1000 NCoin", callback_data="buy_100"),
            InlineKeyboardButton(text="⭐ 500 Stars → 5000 NCoin", callback_data="buy_500")
        ],
        [
            InlineKeyboardButton(text="⭐ 1000 Stars → 10000 NCoin", callback_data="buy_1000"),
            InlineKeyboardButton(text="⭐ 5000 Stars → 50000 NCoin", callback_data="buy_5000")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_games_menu() -> InlineKeyboardMarkup:
    """Меню игр"""
    buttons = [
        [
            InlineKeyboardButton(text="🪨 Камень-ножницы-бумага", callback_data="game_rps"),
            InlineKeyboardButton(text="🎲 Рулетка", callback_data="game_roulette")
        ],
        [
            InlineKeyboardButton(text="⚔️ Дуэль (скоро)", callback_data="game_duel"),
            InlineKeyboardButton(text="🎰 Слот-машина (скоро)", callback_data="game_slot")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_moderation_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Меню модерации"""
    buttons = []
    
    if is_admin:
        buttons.append([
            InlineKeyboardButton(text="🔨 Забанить", callback_data="mod_ban"),
            InlineKeyboardButton(text="🔇 Заглушить", callback_data="mod_mute")
        ])
        buttons.append([
            InlineKeyboardButton(text="📢 Отметить всех", callback_data="mod_all"),
            InlineKeyboardButton(text="📋 Лог-канал", callback_data="mod_logchannel")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="📢 Отметить всех", callback_data="mod_all"),
            InlineKeyboardButton(text="🛡 Анонимный репорт", callback_data="mod_report")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_stats_menu() -> InlineKeyboardMarkup:
    """Меню статистики"""
    buttons = [
        [
            InlineKeyboardButton(text="👤 Моя статистика", callback_data="stats_my"),
            InlineKeyboardButton(text="📊 Активность чата", callback_data="stats_chat")
        ],
        [
            InlineKeyboardButton(text="🏆 Топ по балансу", callback_data="stats_top_balance"),
            InlineKeyboardButton(text="💬 Топ по сообщениям", callback_data="stats_top_messages")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_social_menu() -> InlineKeyboardMarkup:
    """Меню социальных функций"""
    buttons = [
        [
            InlineKeyboardButton(text="🎁 Подарить NCoin", callback_data="social_gift"),
            InlineKeyboardButton(text="🛡 Анонимный репорт", callback_data="social_report")
        ],
        [
            InlineKeyboardButton(text="👥 Пригласить друга", callback_data="social_invite"),
            InlineKeyboardButton(text="🎂 День рождения", callback_data="social_birthday")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_stars_menu() -> InlineKeyboardMarkup:
    """Меню Telegram Stars"""
    buttons = [
        [
            InlineKeyboardButton(text="⭐ Купить Stars", callback_data="stars_buy"),
            InlineKeyboardButton(text="💰 Баланс Stars", callback_data="stars_balance")
        ],
        [
            InlineKeyboardButton(text="💎 Обменять на NCoin", callback_data="stars_exchange"),
            InlineKeyboardButton(text="🎁 Подарить Stars", callback_data="stars_gift")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_menu() -> InlineKeyboardMarkup:
    """Меню настроек (только для админов)"""
    buttons = [
        [
            InlineKeyboardButton(text="📝 Приветствие", callback_data="settings_welcome"),
            InlineKeyboardButton(text="📋 Лог-канал", callback_data="settings_logchannel")
        ],
        [
            InlineKeyboardButton(text="🔞 Фильтр мата", callback_data="settings_profanity"),
            InlineKeyboardButton(text="🤖 Антиспам", callback_data="settings_antispam")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_management_menu() -> InlineKeyboardMarkup:
    """Меню управления (только для админов)"""
    buttons = [
        [
            InlineKeyboardButton(text="👥 Модераторы", callback_data="manage_mods"),
            InlineKeyboardButton(text="➕ Назначить модератора", callback_data="manage_addmod")
        ],
        [
            InlineKeyboardButton(text="➖ Удалить модератора", callback_data="manage_removemod"),
            InlineKeyboardButton(text="📊 Статистика жалоб", callback_data="manage_reports")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_help_menu() -> InlineKeyboardMarkup:
    """Меню помощи"""
    buttons = [
        [
            InlineKeyboardButton(text="📖 Команды", callback_data="help_commands"),
            InlineKeyboardButton(text="🎮 Игры", callback_data="help_games")
        ],
        [
            InlineKeyboardButton(text="💰 Экономика", callback_data="help_economy"),
            InlineKeyboardButton(text="🛡 Модерация", callback_data="help_moderation")
        ],
        [
            InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="help_stars"),
            InlineKeyboardButton(text="🤖 AI Помощник", callback_data="help_ai")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_menu() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    buttons = [
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
