#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: utils/keyboards.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Клавиатуры NEXUS Chat Manager
# ============================================

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, List


# ==================== ГЛАВНОЕ МЕНЮ ====================

def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню бота."""
    if is_admin is None:
        is_admin = False
    
    keyboard = [
        [InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="menu_vip"),
         InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="menu_profile")],
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="menu_balance"),
         InlineKeyboardButton(text="🏆 РАНГ", callback_data="menu_rank")],
        [InlineKeyboardButton(text="🎮 КРЕСТИКИ-НОЛИКИ", callback_data="menu_xo"),
         InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="menu_stats")],
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="menu_all"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="menu_ref")],
        [InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="menu_relations"),
         InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="menu_groups")],
        [InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="menu_rp"),
         InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="menu_tags")],
        [InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="menu_topchats"),
         InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="menu_privacy")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="menu_help"),
         InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="menu_donate")],
        [InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="menu_feedback")]
    ]
    
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="menu_admin")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ==================== УНИВЕРСАЛЬНЫЕ ====================

def back_button(callback_data: str = "back_to_menu", text: str = "◀️ НАЗАД") -> InlineKeyboardMarkup:
    """Кнопка возврата."""
    if not callback_data:
        callback_data = "back_to_menu"
    if not text:
        text = "◀️ НАЗАД"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=callback_data)]
    ])


def get_back_keyboard(callback_data: str = "back_to_menu") -> InlineKeyboardMarkup:
    """Алиас для back_button."""
    return back_button(callback_data)


def confirm_cancel_keyboard(confirm_data: str = "confirm", cancel_data: str = "back_to_menu") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения/отмены."""
    if not confirm_data:
        confirm_data = "confirm"
    if not cancel_data:
        cancel_data = "back_to_menu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=confirm_data),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data=cancel_data)]
    ])


# ==================== АДМИН-ПАНЕЛЬ ====================

def admin_panel_menu() -> InlineKeyboardMarkup:
    """Панель администратора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТА", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🧹 ОЧИСТИТЬ ЧАТ", callback_data="admin_cleanup")],
        [InlineKeyboardButton(text="🌅 СВОДКА ДНЯ", callback_data="admin_summary")],
        [InlineKeyboardButton(text="📋 ВСЕ ЧАТЫ", callback_data="admin_chats")],
        [InlineKeyboardButton(text="🏷️ УПРАВЛЕНИЕ ТЭГАМИ", callback_data="tag_admin_menu")],
        [InlineKeyboardButton(text="🔄 ПЕРЕЗАГРУЗКА РП", callback_data="admin_reload")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


# ==================== КАТЕГОРИИ МЕНЮ ====================

def games_category_menu() -> InlineKeyboardMarkup:
    """Подменю ИГРЫ."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 КРЕСТИКИ-НОЛИКИ", callback_data="game_xo")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def profile_category_menu() -> InlineKeyboardMarkup:
    """Подменю ПРОФИЛЬ."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 МОЙ ПРОФИЛЬ", callback_data="profile"),
         InlineKeyboardButton(text="🏆 МОЙ РАНГ", callback_data="rank_menu")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="my_stats")],
        [InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="vip")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def finance_category_menu() -> InlineKeyboardMarkup:
    """Подменю ФИНАНСЫ."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
         InlineKeyboardButton(text="🎁 ЕЖЕДНЕВНЫЙ БОНУС", callback_data="daily")],
        [InlineKeyboardButton(text="💸 ПЕРЕВЕСТИ", callback_data="transfer_menu"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")],
        [InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def social_category_menu() -> InlineKeyboardMarkup:
    """Подменю СОЦИАЛКА."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="relationships_menu"),
         InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="groups_menu")],
        [InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="rp_menu")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def notifications_category_menu() -> InlineKeyboardMarkup:
    """Подменю ОПОВЕЩЕНИЯ."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
         InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="my_tags_menu")],
        [InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="top_chats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def settings_category_menu() -> InlineKeyboardMarkup:
    """Подменю НАСТРОЙКИ."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy"),
         InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="feedback_menu")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


# ==================== ТОПЫ ====================

def tops_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню выбора топов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 ТОП ПО БАЛАНСУ", callback_data="top_balance")],
        [InlineKeyboardButton(text="💬 ТОП ПО СООБЩЕНИЯМ", callback_data="top_messages")],
        [InlineKeyboardButton(text="🎮 ТОП ПО XO", callback_data="top_xo")],
        [InlineKeyboardButton(text="🔥 ТОП ПО АКТИВНОСТИ", callback_data="top_activity")],
        [InlineKeyboardButton(text="🎁 ТОП ПО DAILY", callback_data="top_daily")],
        [InlineKeyboardButton(text="💎 ТОП ДОНАТЕРОВ", callback_data="top_donors")],
        [InlineKeyboardButton(text="👑 ТОП ПО РАНГУ", callback_data="top_ranks")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


# ==================== РАНГИ ====================

def rank_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню рангов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 МОЙ РАНГ", callback_data="rank_menu")],
        [InlineKeyboardButton(text="📊 ТОП ИГРОКОВ", callback_data="top_ranks")],
        [InlineKeyboardButton(text="ℹ️ КАК ПОВЫСИТЬ", callback_data="rank_help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


# ==================== КРЕСТИКИ-НОЛИКИ ====================

def xo_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню крестиков-ноликов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 ИГРАТЬ С БОТОМ", callback_data="xo_vs_bot")],
        [InlineKeyboardButton(text="👤 ВЫЗВАТЬ ИГРОКА", callback_data="xo_vs_player")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="xo_stats")],
        [InlineKeyboardButton(text="❓ ПРАВИЛА", callback_data="xo_help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def xo_difficulty_keyboard() -> InlineKeyboardMarkup:
    """Выбор сложности бота."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😊 ЛЁГКИЙ", callback_data="xo_diff_easy")],
        [InlineKeyboardButton(text="🤔 СРЕДНИЙ", callback_data="xo_diff_medium")],
        [InlineKeyboardButton(text="🤖 СЛОЖНЫЙ", callback_data="xo_diff_hard")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="xo_vs_bot")]
    ])


def xo_side_choice_keyboard(difficulty: str = "medium") -> InlineKeyboardMarkup:
    """Выбор стороны для игры с ботом."""
    if not difficulty:
        difficulty = "medium"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Играть за X (первый ход)", callback_data=f"xo_side_X_{difficulty}")],
        [InlineKeyboardButton(text="⭕ Играть за O (второй ход)", callback_data=f"xo_side_O_{difficulty}")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="xo_vs_bot")]
    ])


def xo_board_keyboard(board: Optional[List] = None, game_id: str = "", can_play: bool = True) -> InlineKeyboardMarkup:
    """Игровое поле 3x3."""
    if board is None:
        board = [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
    if game_id is None:
        game_id = ""
    
    buttons = []
    symbols = {"X": "❌", "O": "⭕", " ": "▫️"}
    
    for r in range(3):
        row = []
        for c in range(3):
            cell = board[r][c] if r < len(board) and c < len(board[r]) else " "
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
    """Выбор ставки для PvP."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 БЕЗ СТАВКИ", callback_data="xo_bet_0")],
        [InlineKeyboardButton(text="50 NCoin", callback_data="xo_bet_50"),
         InlineKeyboardButton(text="100 NCoin", callback_data="xo_bet_100")],
        [InlineKeyboardButton(text="200 NCoin", callback_data="xo_bet_200"),
         InlineKeyboardButton(text="500 NCoin", callback_data="xo_bet_500")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="xo_vs_player")]
    ])


# ==================== РЕФЕРАЛЬНАЯ СИСТЕМА ====================

def ref_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню реферальной системы."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 МОЯ ССЫЛКА", callback_data="my_ref")],
        [InlineKeyboardButton(text="📊 ТОП ПРИГЛАСИТЕЛЕЙ", callback_data="ref_top")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


# ==================== VIP ====================

def vip_purchase_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура покупки VIP."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥉 БРОНЗА (500)", callback_data="buy_vip_1")],
        [InlineKeyboardButton(text="🥈 СЕРЕБРО (1000)", callback_data="buy_vip_2")],
        [InlineKeyboardButton(text="🥇 ЗОЛОТО (2000)", callback_data="buy_vip_3")],
        [InlineKeyboardButton(text="💎 ПЛАТИНА (5000)", callback_data="buy_vip_4")],
        [InlineKeyboardButton(text="💠 АЛМАЗ (10000)", callback_data="buy_vip_5")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
    ])


# ==================== ТЕГИ ====================

def tag_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню управления тегами для админа."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 ВКЛЮЧИТЬ КАТЕГОРИИ", callback_data="tag_enable_categories")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ТЕГОВ", callback_data="tag_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_admin_menu")]
    ])


# ==================== АЛИАСЫ ДЛЯ СОВМЕСТИМОСТИ ====================

# Алиасы для старых названий
ref_menu = ref_menu_keyboard
stats_menu_keyboard = tops_menu_keyboard
