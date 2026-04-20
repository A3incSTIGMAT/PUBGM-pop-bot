"""
Клавиатуры для NEXUS Chat Manager
ПОЛНОСТЬЮ ПРОВЕРЕНО НА NULL
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, List


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню — разбито на категории"""
    if is_admin is None:
        is_admin = False
    
    row1 = [
        InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="vip"),
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")
    ]
    
    row2 = [
        InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
        InlineKeyboardButton(text="🏆 РАНГ", callback_data="rank_menu")
    ]
    
    row3 = [
        InlineKeyboardButton(text="🎮 КРЕСТИКИ-НОЛИКИ", callback_data="game_xo"),
        InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="stats")
    ]
    
    row4 = [
        InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
        InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")
    ]
    
    row5 = [
        InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="relationships_menu"),
        InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="groups_menu")
    ]
    
    row6 = [
        InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="rp_menu"),
        InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="my_tags_menu")
    ]
    
    row7 = [
        InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="top_chats"),
        InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy")
    ]
    
    row8 = [
        InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help"),
        InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate")
    ]
    
    row9 = [
        InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="feedback_menu")
    ]
    
    keyboard = [row1, row2, row3, row4, row5, row6, row7, row8, row9]
    
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_panel_menu() -> InlineKeyboardMarkup:
    """Панель администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷️ УПРАВЛЕНИЕ ТЭГАМИ", callback_data="tag_admin_menu")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data="stats_chat")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def games_category_menu() -> InlineKeyboardMarkup:
    """Подменю ИГРЫ — только крестики-нолики"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 ИГРАТЬ", callback_data="game_xo")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="xo_stats")],
        [InlineKeyboardButton(text="❓ ПРАВИЛА", callback_data="xo_help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def profile_category_menu() -> InlineKeyboardMarkup:
    """Подменю ПРОФИЛЬ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 МОЙ ПРОФИЛЬ", callback_data="profile"),
         InlineKeyboardButton(text="🏆 МОЙ РАНГ", callback_data="rank_menu")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="my_stats")],
        [InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="vip")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def finance_category_menu() -> InlineKeyboardMarkup:
    """Подменю ФИНАНСЫ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
         InlineKeyboardButton(text="🎁 ЕЖЕДНЕВНЫЙ БОНУС", callback_data="daily")],
        [InlineKeyboardButton(text="💸 ПЕРЕВЕСТИ", callback_data="transfer_menu"),
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


# ==================== КЛАВИАТУРЫ КРЕСТИКОВ-НОЛИКОВ ====================

def xo_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню крестиков-ноликов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 ИГРАТЬ С БОТОМ", callback_data="xo_vs_bot")],
        [InlineKeyboardButton(text="👤 ВЫЗВАТЬ ИГРОКА", callback_data="xo_vs_player")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="xo_stats")],
        [InlineKeyboardButton(text="❓ ПРАВИЛА", callback_data="xo_help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def xo_difficulty_keyboard() -> InlineKeyboardMarkup:
    """Выбор сложности бота"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😊 ЛЁГКИЙ", callback_data="xo_diff_easy")],
        [InlineKeyboardButton(text="🤔 СРЕДНИЙ", callback_data="xo_diff_medium")],
        [InlineKeyboardButton(text="🤖 СЛОЖНЫЙ", callback_data="xo_diff_hard")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="xo_vs_bot")]
    ])


def xo_side_choice_keyboard(difficulty: str = "medium") -> InlineKeyboardMarkup:
    """Выбор стороны (X или O) для игры с ботом"""
    if not difficulty:
        difficulty = "medium"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Играть за X (ходить первым)", callback_data=f"xo_side_X_{difficulty}")],
        [InlineKeyboardButton(text="⭕ Играть за O (ходить вторым)", callback_data=f"xo_side_O_{difficulty}")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="xo_vs_bot")]
    ])


def xo_board_keyboard(board: Optional[List] = None, game_id: str = "", can_play: bool = True) -> InlineKeyboardMarkup:
    """Игровое поле 3x3"""
    if board is None:
        board = [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
    if game_id is None:
        game_id = ""
    
    buttons = []
    symbols = {"X": "❌", "O": "⭕", " ": "▫️"}
    
    for r in range(3):
        row = []
        for c in range(3):
            if r < len(board) and c < len(board[r]):
                cell = board[r][c] if board[r][c] is not None else " "
            else:
                cell = " "
            
            text = symbols.get(cell, "▫️")
            
            if can_play and cell == " ":
                callback = f"xo_move_{game_id}_{r}_{c}"
            else:
                callback = "xo_noop"
            
            row.append(InlineKeyboardButton(text=text, callback_data=callback))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="🏳️ СДАТЬСЯ", callback_data=f"xo_surrender_{game_id}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def xo_bet_keyboard() -> InlineKeyboardMarkup:
    """Выбор ставки для PvP"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 БЕЗ СТАВКИ", callback_data="xo_bet_0")],
        [InlineKeyboardButton(text="50 NCoin", callback_data="xo_bet_50"),
         InlineKeyboardButton(text="100 NCoin", callback_data="xo_bet_100")],
        [InlineKeyboardButton(text="200 NCoin", callback_data="xo_bet_200"),
         InlineKeyboardButton(text="500 NCoin", callback_data="xo_bet_500")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="xo_vs_player")]
    ])


# ==================== ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ ====================

def back_button(callback_data: str = "back_to_menu", text: str = "◀️ НАЗАД") -> InlineKeyboardMarkup:
    """Кнопка возврата"""
    if not callback_data:
        callback_data = "back_to_menu"
    if not text:
        text = "◀️ НАЗАД"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=callback_data)]
    ])


def confirm_cancel_keyboard(confirm_data: str = "confirm", cancel_data: str = "back_to_menu") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения/отмены"""
    if not confirm_data:
        confirm_data = "confirm"
    if not cancel_data:
        cancel_data = "back_to_menu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=confirm_data),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data=cancel_data)]
    ])


def ref_menu() -> InlineKeyboardMarkup:
    """Меню реферальной системы"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 МОЯ ССЫЛКА", callback_data="my_ref")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="ref_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def vip_purchase_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура покупки VIP"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥉 БРОНЗА (500)", callback_data="buy_vip_1")],
        [InlineKeyboardButton(text="🥈 СЕРЕБРО (1000)", callback_data="buy_vip_2")],
        [InlineKeyboardButton(text="🥇 ЗОЛОТО (2000)", callback_data="buy_vip_3")],
        [InlineKeyboardButton(text="💎 ПЛАТИНА (5000)", callback_data="buy_vip_4")],
        [InlineKeyboardButton(text="💠 АЛМАЗ (10000)", callback_data="buy_vip_5")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
    ])
