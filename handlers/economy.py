import time
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, add_user, init_db

router = Router()

# Инициализируем базу
init_db()

# Словарь для хранения времени последнего бонуса (временное решение)
last_daily = {}

# Баланс пользователя
@router.message(Command("balance"))
async def show_balance(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    await message.answer(f"💰 Ваш баланс: {balance} NCoin")

# Ежедневный бонус
@router.message(Command("daily"))
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    now = datetime.now()
    
    # Проверяем, когда пользователь получал бонус
    last_time = last_daily.get(user_id)
    
    if last_time:
        time_diff = now - last_time
        if time_diff < timedelta(hours=24):
            remaining_hours = 24 - (time_diff.total_seconds() // 3600)
            remaining_minutes = int((24 * 3600 - time_diff.total_seconds()) // 60)
            await message.answer(
                f"⏰ Вы уже получали ежедневный бонус!\n"
                f"Следующий бонус через {int(remaining_hours)}ч {remaining_minutes % 60}мин.\n\n"
                f"💎 Бонус: 50 NCoin"
            )
            return
    
    # Начисляем бонус 50 NCoin
    update_balance(user_id, chat_id, 50)
    last_daily[user_id] = now
    
    # Добавляем пользователя в БД если его нет
    add_user(user_id, chat_id, message.from_user.username)
    
    new_balance = get_balance(user_id, chat_id)
    
    await message.answer(
        f"🎁 ЕЖЕДНЕВНЫЙ БОНУС!\n\n"
        f"Вам начислено 50 NCoin.\n"
        f"💰 Ваш баланс: {new_balance} NCoin\n\n"
        f"✨ Заходите завтра снова!"
    )

# Подарок пользователю
@router.message(Command("gift"))
async def send_gift(message: Message):
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer(
            "🎁 Подарок NCoin\n\n"
            "Использование: /gift @username [сумма]\n"
            "Пример: /gift @ivan 50\n\n"
            "💰 Валюта: NCoin"
        )
        return
    
    # Получаем username получателя
    target_username = args[1].replace("@", "")
    try:
        amount = int(args[2])
    except:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    
    sender_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем баланс отправителя
    sender_balance = get_balance(sender_id, chat_id)
    
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {sender_balance} NCoin")
        return
    
    # TODO: Здесь будет поиск пользователя по username и перевод
    # Пока заглушка
    await message.answer(
        f"🎁 Вы подарили {amount} NCoin пользователю @{target_username}\n\n"
        f"✨ Функция автоматического перевода скоро будет доступна!"
    )

# Топ пользователей по NCoin
@router.message(Command("top"))
async def show_top(message: Message):
    # TODO: Реальная выгрузка из БД
    await message.answer(
        "🏆 ТОП ПОЛЬЗОВАТЕЛЕЙ ПО NCoin 🏆\n\n"
        "1. 👑 — 5000 NCoin\n"
        "2. ⭐ — 3200 NCoin\n"
        "3. 🔥 — 2100 NCoin\n"
        "4. 💎 — 1500 NCoin\n"
        "5. 🎯 — 1200 NCoin\n\n"
        "📊 Скоро будет полноценная таблица с реальными данными!"
    )
