"""
Вспомогательные функции для бота
"""

import asyncio
from aiogram.types import Message

async def delete_message(message: Message, delay: int = 5):
    """
    Удаляет сообщение через указанное количество секунд.
    
    Args:
        message: Сообщение для удаления
        delay: Задержка в секундах (по умолчанию 5)
    """
    if not message:
        return
    
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        # Игнорируем ошибки (сообщение уже удалено или нет прав)
        pass

async def delete_after_response(bot_message: Message, user_message: Message, delay: int = 5):
    """
    Удаляет и ответ бота, и сообщение пользователя
    """
    tasks = []
    if bot_message:
        tasks.append(delete_message(bot_message, delay))
    if user_message:
        tasks.append(delete_message(user_message, delay))
    await asyncio.gather(*tasks, return_exceptions=True)
