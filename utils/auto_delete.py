"""
Модуль автоудаления сообщений
"""

import asyncio
from aiogram import Bot

# Хранилище последних сообщений пользователей
user_last_messages = {}


async def delete_message(bot: Bot, chat_id: int, message_id: int, delay: int = 10):
    """Удалить сообщение через delay секунд"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def safe_delete(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def track_and_delete(bot: Bot, chat_id: int, user_id: int, new_message_id: int, delay: int = 15):
    """Отслеживает и удаляет предыдущее сообщение пользователя, затем удаляет новое через delay секунд"""
    # Удаляем предыдущее сообщение пользователя
    if user_id in user_last_messages:
        prev_chat_id, prev_message_id = user_last_messages[user_id]
        if prev_chat_id == chat_id:
            await safe_delete(bot, prev_chat_id, prev_message_id)
    
    # Сохраняем новое сообщение
    user_last_messages[user_id] = (chat_id, new_message_id)
    
    # Удаляем новое сообщение через delay секунд
    asyncio.create_task(delete_message(bot, chat_id, new_message_id, delay))
