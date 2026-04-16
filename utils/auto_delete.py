"""
Модуль автоудаления сообщений БОТА
Удаляет только сообщения, отправленные ботом
"""

import asyncio
from aiogram import Bot

# ==================== КОНФИГУРАЦИЯ ЗАДЕРЖЕК ====================
DELAYS = {
    "menu": 120,           # Главное меню — 2 минуты
    "game_result": 20,     # Результат игры — 20 секунд
    "balance": 15,         # Баланс — 15 секунд
    "daily": 15,           # Ежедневный бонус — 15 секунд
    "transfer": 15,        # Перевод — 15 секунд
    "profile": 30,         # Профиль — 30 секунд
    "rank": 30,            # Ранг — 30 секунд
    "stats": 20,           # Статистика — 20 секунд
    "donate": 60,          # Донат — 1 минута
    "feedback": 30,        # Обратная связь — 30 секунд
    "privacy": 45,         # Политика — 45 секунд
    "help": 30,            # Помощь — 30 секунд
    "error": 10,           # Сообщение об ошибке — 10 секунд
    "default": 15,         # По умолчанию — 15 секунд
}

# Хранилище последних сообщений бота для каждого пользователя
bot_last_messages = {}


async def delete_bot_message(bot: Bot, chat_id: int, message_id: int, delay: int = DELAYS["default"]):
    """Удалить сообщение бота через delay секунд"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def safe_delete_bot_message(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения бота"""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def track_and_delete_bot_message(bot: Bot, chat_id: int, user_id: int, bot_message_id: int, delay: int = DELAYS["default"]):
    """
    Отслеживает и удаляет ПРЕДЫДУЩЕЕ сообщение бота для этого пользователя,
    затем удаляет НОВОЕ сообщение бота через delay секунд
    """
    # Удаляем предыдущее сообщение бота для этого пользователя
    if user_id in bot_last_messages:
        prev_chat_id, prev_message_id = bot_last_messages[user_id]
        if prev_chat_id == chat_id:
            await safe_delete_bot_message(bot, prev_chat_id, prev_message_id)
    
    # Сохраняем новое сообщение бота
    bot_last_messages[user_id] = (chat_id, bot_message_id)
    
    # Удаляем новое сообщение бота через delay секунд
    asyncio.create_task(delete_bot_message(bot, chat_id, bot_message_id, delay))


async def delete_bot_message_after(bot: Bot, chat_id: int, message_id: int, delay: int = DELAYS["default"]):
    """Просто удалить сообщение бота через delay секунд (без отслеживания предыдущих)"""
    asyncio.create_task(delete_bot_message(bot, chat_id, message_id, delay))


async def delete_all_user_messages(bot: Bot, user_id: int, chat_id: int):
    """Удалить все сообщения бота для пользователя"""
    if user_id in bot_last_messages:
        prev_chat_id, prev_message_id = bot_last_messages[user_id]
        if prev_chat_id == chat_id:
            await safe_delete_bot_message(bot, prev_chat_id, prev_message_id)
            del bot_last_messages[user_id]


# ==================== АЛИАСЫ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ====================
track_and_delete = track_and_delete_bot_message
delete_after = delete_bot_message_after
