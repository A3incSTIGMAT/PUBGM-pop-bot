from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from handlers.admin import get_user_role

async def get_main_menu(chat_id: int, user_id: int):
    """Возвращает меню в зависимости от роли пользователя"""
    role = await get_user_role(chat_id, user_id)
    
    buttons = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="🎮 Игры"), KeyboardButton(text="🎁 Подарки")]
    ]
    
    if role in ['global_admin', 'creator', 'admin']:
        buttons.append([KeyboardButton(text="🛡 Админ-панель")])
    elif role == 'moderator':
        buttons.append([KeyboardButton(text="🔨 Модерация")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
