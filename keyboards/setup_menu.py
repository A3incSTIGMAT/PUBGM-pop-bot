from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_setup_menu() -> InlineKeyboardMarkup:
    """Главное меню настройки"""
    buttons = [
        [InlineKeyboardButton(text="🛡 Настроить анонимные репорты", callback_data="setup_reports")],
        [InlineKeyboardButton(text="📋 Настроить лог-канал", callback_data="setup_logchannel")],
        [InlineKeyboardButton(text="🔐 Безопасная зона", callback_data="setup_safezone")],
        [InlineKeyboardButton(text="📖 Что такое анонимные репорты?", callback_data="setup_help_reports")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="setup_close")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_reports_setup_menu() -> InlineKeyboardMarkup:
    """Меню настройки анонимных репортов"""
    buttons = [
        [InlineKeyboardButton(text="✅ Включить анонимные репорты", callback_data="reports_enable")],
        [InlineKeyboardButton(text="📋 Настроить канал для жалоб", callback_data="setup_logchannel")],
        [InlineKeyboardButton(text="📊 Статистика жалоб", callback_data="reports_stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="setup_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_safezone_menu() -> InlineKeyboardMarkup:
    """Меню настройки безопасной зоны"""
    buttons = [
        [InlineKeyboardButton(text="🌙 Ночной режим (23:00-07:00)", callback_data="safezone_night")],
        [InlineKeyboardButton(text="🚫 Блокировка ссылок", callback_data="safezone_links")],
        [InlineKeyboardButton(text="📵 Блокировка медиа", callback_data="safezone_media")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="setup_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
