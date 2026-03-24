"""
Модуль для работы с ролями пользователей.
"""

from aiogram import Bot
from config import ADMIN_IDS
from database.db import is_chat_moderator

bot: Bot = None

def set_bot(bot_instance: Bot):
    """Установить экземпляр бота"""
    global bot
    bot = bot_instance

async def get_user_role(chat_id: int, user_id: int) -> str:
    if user_id in ADMIN_IDS:
        return 'global_admin'
    
    try:
        chat = await bot.get_chat(chat_id)
        member = await chat.get_member(user_id)
        
        if member.status == 'creator':
            return 'creator'
        if member.status == 'administrator':
            return 'admin'
        if is_chat_moderator(chat_id, user_id):
            return 'moderator'
        
        return 'user'
    except Exception:
        return 'user'

async def can_ban(chat_id: int, user_id: int) -> bool:
    role = await get_user_role(chat_id, user_id)
    return role in ['global_admin', 'creator', 'admin']

async def can_mute(chat_id: int, user_id: int) -> bool:
    role = await get_user_role(chat_id, user_id)
    return role in ['global_admin', 'creator', 'admin', 'moderator']

async def can_configure(chat_id: int, user_id: int) -> bool:
    role = await get_user_role(chat_id, user_id)
    return role in ['global_admin', 'creator', 'admin']

async def can_assign_moderator(chat_id: int, user_id: int) -> bool:
    role = await get_user_role(chat_id, user_id)
    return role in ['global_admin', 'creator', 'admin']
