"""
Модуль автоудаления сообщений БОТА
Удаляет только сообщения, отправленные ботом
"""

import asyncio
from aiogram import Bot

# Хранилище последних сообщений бота для каждого пользователя
bot_last_messages = {}


async def delete_message(bot: Bot, chat_id: int, message_id: int, delay: int = 10):
    """Удалить сообщение бота через delay секунд"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def safe_delete(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения бота"""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def track_and_delete_bot_message(bot: Bot, chat_id: int, user_id: int, bot_message_id: int, delay: int = 15):
    """
    Отслеживает и удаляет ПРЕДЫДУЩЕЕ сообщение бота для этого пользователя,
    затем удаляет НОВОЕ сообщение бота через delay секунд
    """
    # Удаляем предыдущее сообщение бота для этого пользователя
    if user_id in bot_last_messages:
        prev_chat_id, prev_message_id = bot_last_messages[user_id]
        if prev_chat_id == chat_id:
            await safe_delete(bot, prev_chat_id, prev_message_id)
    
    # Сохраняем новое сообщение бота
    bot_last_messages[user_id] = (chat_id, bot_message_id)
    
    # Удаляем новое сообщение бота через delay секунд
    asyncio.create_task(delete_message(bot, chat_id, bot_message_id, delay))


async def delete_bot_message_after(bot: Bot, chat_id: int, message_id: int, delay: int = 10):
    """Просто удалить сообщение бота через delay секунд (без отслеживания предыдущих)"""
    asyncio.create_task(delete_message(bot, chat_id, message_id, delay))


# ============ АЛИАСЫ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ============
# Чтобы избежать ошибок импорта, добавляем старые названия функций
track_and_delete = track_and_delete_bot_message
delete_after = delete_bot_message_after
