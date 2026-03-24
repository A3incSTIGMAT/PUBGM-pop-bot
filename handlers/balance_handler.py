"""
Отдельный обработчик для команд баланса и ежедневного бонуса
"""

from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, add_user

# Создаём роутер
router = Router()

# Хранилище для ежедневных бонусов
last_daily = {}

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Команда /balance - показывает баланс"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    await message.answer(f"💰 Ваш баланс: {balance} NCoin")

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    """Команда /daily - ежедневный бонус"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    now = datetime.now()
    last_time = last_daily.get(user_id)
    
    # Проверяем, получал ли пользователь бонус за последние 24 часа
    if last_time and now - last_time < timedelta(hours=24):
        hours_left = 24 - (now - last_time).seconds // 3600
        minutes_left = (24 * 3600 - (now - last_time).seconds) // 60
        await message.answer(f"⏰ Вы уже получали бонус сегодня! Следующий через {hours_left}ч {minutes_left % 60}мин.")
        return
    
    # Начисляем бонус
    update_balance(user_id, chat_id, 50)
    last_daily[user_id] = now
    add_user(user_id, chat_id, message.from_user.username)
    
    new_balance = get_balance(user_id, chat_id)
    await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+50 NCoin\n"
        f"💰 Ваш баланс: {new_balance} NCoin"
    )
