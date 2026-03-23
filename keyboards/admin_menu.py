from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_admin_panel(role: str) -> InlineKeyboardMarkup:
    """Возвращает админ-панель в зависимости от роли"""
    buttons = []
    
    buttons.append([InlineKeyboardButton(text="📊 Статистика чата", callback_data="admin_stats")])
    buttons.append([InlineKeyboardButton(text="📋 Логи действий", callback_data="admin_logs")])
    
    if role in ['global_admin', 'creator', 'admin']:
        buttons.append([InlineKeyboardButton(text="👥 Управление модераторами", callback_data="admin_mods")])
        buttons.append([InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="admin_settings")])
    
    if role == 'moderator':
        buttons.append([InlineKeyboardButton(text="🔨 Модерация", callback_data="admin_moderation")])
    
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
