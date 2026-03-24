from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, add_user

router = Router()

last_daily = {}

@router.message(Command("balance"))
async def show_balance(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    await message.answer(f"💰 Ваш баланс: {balance} NCoin")

@router.message(Command("daily"))
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    now = datetime.now()
    last_time = last_daily.get(user_id)
    
    if last_time and now - last_time < timedelta(hours=24):
        remaining = 24 - (now - last_time).seconds // 3600
        await message.answer(f"⏰ Бонус через {remaining} часов.")
        return
    
    update_balance(user_id, chat_id, 50)
    last_daily[user_id] = now
    add_user(user_id, chat_id, message.from_user.username)
    
    await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+50 NCoin\n"
        f"💰 Баланс: {get_balance(user_id, chat_id)} NCoin"
    )

@router.message(Command("gift"))
async def send_gift(message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "🎁 **Подарок NCoin**\n\n"
            "Использование: /gift @username [сумма]\n"
            "Пример: /gift @ivan 50"
        )
        return
    
    target_username = args[1].replace("@", "")
    try:
        amount = int(args[2])
    except:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    sender_balance = get_balance(user_id, chat_id)
    
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {sender_balance}")
        return
    
    await message.answer(
        f"🎁 Вы подарили {amount} NCoin пользователю @{target_username}\n\n"
        f"✨ Функция автоматического перевода скоро будет доступна!"
    )

@router.message(Command("top"))
async def show_top(message: Message):
    await message.answer(
        "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ ПО NCoin** 🏆\n\n"
        "1. 👑 — 5000 NCoin\n"
        "2. ⭐ — 3200 NCoin\n"
        "3. 🔥 — 2100 NCoin\n\n"
        "📊 Скоро будет полноценная таблица с реальными данными!"
    )
