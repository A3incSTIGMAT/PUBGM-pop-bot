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
    """Обработчик команды /balance"""
    print("🔥🔥🔥 [DEBUG] КОМАНДА /balance ВЫЗВАНА 🔥🔥🔥")
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    print(f"[DEBUG] user_id: {user_id}, chat_id: {chat_id}")
    
    balance = get_balance(user_id, chat_id)
    
    print(f"[DEBUG] balance: {balance}")
    
    await message.answer(f"💰 Ваш баланс: {balance} NCoin")
    print("✅ [DEBUG] Ответ отправлен")

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    """Обработчик команды /daily"""
    print("🔥🔥🔥 [DEBUG] КОМАНДА /daily ВЫЗВАНА 🔥🔥🔥")
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    print(f"[DEBUG] user_id: {user_id}, chat_id: {chat_id}")
    
    now = datetime.now()
    last_time = last_daily.get(user_id)
    
    if last_time and now - last_time < timedelta(hours=24):
        remaining = 24 - (now - last_time).seconds // 3600
        print(f"[DEBUG] Бонус уже получен, ждать {remaining} часов")
        await message.answer(f"⏰ Бонус через {remaining} часов.")
        return
    
    print("[DEBUG] Начисляем бонус 50 NCoin")
    update_balance(user_id, chat_id, 50)
    last_daily[user_id] = now
    add_user(user_id, chat_id, message.from_user.username)
    
    new_balance = get_balance(user_id, chat_id)
    print(f"[DEBUG] Новый баланс: {new_balance}")
    
    await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+50 NCoin\n"
        f"💰 Баланс: {new_balance} NCoin"
    )
    print("✅ [DEBUG] Ответ отправлен")

@router.message(Command("gift"))
async def cmd_gift(message: Message):
    """Обработчик команды /gift"""
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
    except ValueError:
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
async def cmd_top(message: Message):
    """Обработчик команды /top"""
    await message.answer(
        "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ ПО NCoin** 🏆\n\n"
        "1. 👑 — 5000 NCoin\n"
        "2. ⭐ — 3200 NCoin\n"
        "3. 🔥 — 2100 NCoin\n\n"
        "📊 Скоро будет полноценная таблица с реальными данными!"
    )
