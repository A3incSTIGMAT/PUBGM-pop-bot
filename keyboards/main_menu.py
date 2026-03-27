"""
Главное меню NEXUS — полная версия с реквизитами Озон Банка
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OZON_CARD_LAST4, OZON_BANK_NAME

def get_main_menu(user_role: str = "user") -> InlineKeyboardMarkup:
    """
    Главное меню бота.
    user_role: 'user', 'moderator', 'admin', 'creator', 'global_admin'
    """
    buttons = []
    
    # Ряд 1: Профиль и Экономика
    buttons.append([
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"),
        InlineKeyboardButton(text="💰 Экономика", callback_data="menu_economy")
    ])
    
    # Ряд 2: Игры и Модерация
    buttons.append([
        InlineKeyboardButton(text="🎮 Игры", callback_data="menu_games"),
        InlineKeyboardButton(text="🛡 Модерация", callback_data="menu_moderation")
    ])
    
    # Ряд 3: Статистика и Социальное
    buttons.append([
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu_stats"),
        InlineKeyboardButton(text="🎁 Социальное", callback_data="menu_social")
    ])
    
    # Ряд 4: VIP и AI
    buttons.append([
        InlineKeyboardButton(text="👑 VIP Статус", callback_data="menu_vip"),
        InlineKeyboardButton(text="🤖 AI Помощник", callback_data="menu_ai")
    ])
    
    # Ряд 5: Реквизиты и Покупка
    buttons.append([
        InlineKeyboardButton(text="💳 Реквизиты", callback_data="menu_requisites"),
        InlineKeyboardButton(text="💎 Купить NCoin", callback_data="menu_buy")
    ])
    
    # Ряд 6: Помощь и О боте
    buttons.append([
        InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help"),
        InlineKeyboardButton(text="ℹ️ О боте", callback_data="menu_about")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_requisites_menu() -> InlineKeyboardMarkup:
    """Меню с реквизитами Озон Банка"""
    buttons = [
        [InlineKeyboardButton(text="📋 Скопировать реквизиты", callback_data="copy_requisites")],
        [InlineKeyboardButton(text="📱 Оплатить по QR", callback_data="pay_qr")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_buy_menu() -> InlineKeyboardMarkup:
    """Меню покупки NCoin"""
    buttons = [
        [InlineKeyboardButton(text="100 NCoin — 100 ₽", callback_data="buy_100")],
        [InlineKeyboardButton(text="500 NCoin — 500 ₽", callback_data="buy_500")],
        [InlineKeyboardButton(text="1000 NCoin — 1000 ₽", callback_data="buy_1000")],
        [InlineKeyboardButton(text="5000 NCoin — 5000 ₽", callback_data="buy_5000")],
        [InlineKeyboardButton(text="10000 NCoin — 10000 ₽", callback_data="buy_10000")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_menu() -> InlineKeyboardMarkup:
    """Меню профиля"""
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
            InlineKeyboardButton(text="💳 Реквизиты", callback_data="eco_requisites")
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
        buttons.append([
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="mod_settings"),
            InlineKeyboardButton(text="👥 Модераторы", callback_data="mod_moderators")
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


def get_vip_menu() -> InlineKeyboardMarkup:
    """Меню VIP-статуса"""
    buttons = [
        [
            InlineKeyboardButton(text="👑 Купить VIP", callback_data="vip_buy"),
            InlineKeyboardButton(text="❓ Что даёт VIP?", callback_data="vip_info")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_ai_menu() -> InlineKeyboardMarkup:
    """Меню AI-помощника"""
    buttons = [
        [
            InlineKeyboardButton(text="🤖 Задать вопрос", callback_data="ai_ask"),
            InlineKeyboardButton(text="💬 Начать диалог", callback_data="ai_chat")
        ],
        [
            InlineKeyboardButton(text="📊 История", callback_data="ai_history"),
            InlineKeyboardButton(text="🗑️ Очистить память", callback_data="ai_clear")
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
            InlineKeyboardButton(text="💳 Реквизиты", callback_data="help_requisites"),
            InlineKeyboardButton(text="🤖 AI Помощник", callback_data="help_ai")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_requisites_text() -> str:
    """Текст с реквизитами Озон Банка"""
    return f"""
💳 **РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ**

🏦 **Банк:** {OZON_BANK_NAME}
💳 **Карта:** •••• {OZON_CARD_LAST4}
👤 **Получатель:** Александр Б.

📝 **Назначение платежа:** Пополнение NEXUS

💡 **Как оплатить:**
1. Переведите сумму на указанную карту
2. В назначении платежа укажите: "Пополнение NEXUS"
3. Нажмите кнопку "Я оплатил(а)" ниже
4. Администратор проверит оплату и начислит NCoin

🔗 **СБП:** отсканируйте QR-код в приложении банка
"""


def get_back_menu() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    buttons = [
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
