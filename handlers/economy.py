from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, add_user
from utils.helpers import delete_after_response

router = Router()
last_daily = {}

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Команда /balance - показывает баланс"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    
    response = await message.answer(f"💰 Ваш баланс: {balance} NCoin")
    await delete_after_response(response, message, delay=10)

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    """Команда /daily - ежедневный бонус"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    now = datetime.now()
    last_time = last_daily.get(user_id)
    
    if last_time and now - last_time < timedelta(hours=24):
        remaining = 24 - (now - last_time).seconds // 3600
        response = await message.answer(f"⏰ Бонус через {remaining} часов.")
        await delete_after_response(response, message, delay=10)
        return
    
    update_balance(user_id, chat_id, 50)
    last_daily[user_id] = now
    add_user(user_id, chat_id, message.from_user.username)
    
    new_balance = get_balance(user_id, chat_id)
    response = await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+50 NCoin\n"
        f"💰 Баланс: {new_balance} NCoin"
    )
    await delete_after_response(response, message, delay=10)

@router.message(Command("gift"))
async def cmd_gift(message: Message):
    """Команда /gift - подарок"""
    args = message.text.split()
    if len(args) < 3:
        response = await message.answer(
            "🎁 **Подарок NCoin**\n\n"
            "Использование: /gift @username [сумма]\n"
            "Пример: /gift @ivan 50"
        )
        await delete_after_response(response, message, delay=15)
        return
    
    target_username = args[1].replace("@", "")
    try:
        amount = int(args[2])
    except ValueError:
        response = await message.answer("❌ Сумма должна быть числом")
        await delete_after_response(response, message, delay=10)
        return
    
    if amount <= 0:
        response = await message.answer("❌ Сумма должна быть больше 0")
        await delete_after_response(response, message, delay=10)
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    sender_balance = get_balance(user_id, chat_id)
    
    if sender_balance < amount:
        response = await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {sender_balance}")
        await delete_after_response(response, message, delay=10)
        return
    
    response = await message.answer(
        f"🎁 Вы подарили {amount} NCoin пользователю @{target_username}\n\n"
        f"✨ Функция автоматического перевода скоро будет доступна!"
    )
    await delete_after_response(response, message, delay=15)

@router.message(Command("top"))
async def cmd_top(message: Message):
    """Команда /top - топ пользователей"""
    response = await message.answer(
        "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ ПО NCoin** 🏆\n\n"
        "1. 👑 — 5000 NCoin\n"
        "2. ⭐ — 3200 NCoin\n"
        "3. 🔥 — 2100 NCoin\n\n"
        "📊 Скоро будет полноценная таблица!"
    )
    await delete_after_response(response, message, delay=15)
