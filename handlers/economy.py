from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, add_user

# Создаём роутер — обязательный элемент для регистрации команд
router = Router()

# Хранилище для отслеживания времени последнего получения бонуса
last_daily = {}

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """
    Команда /balance - показывает текущий баланс пользователя в NCoin.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Получаем баланс из базы данных
    balance = get_balance(user_id, chat_id)
    
    # Отправляем ответ
    await message.answer(f"💰 Ваш баланс: {balance} NCoin")

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    """
    Команда /daily - начисляет 50 NCoin раз в 24 часа.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    now = datetime.now()
    last_time = last_daily.get(user_id)
    
    # Проверяем, получал ли пользователь бонус за последние 24 часа
    if last_time and now - last_time < timedelta(hours=24):
        # Вычисляем оставшееся время
        seconds_left = 24 * 3600 - (now - last_time).seconds
        hours_left = seconds_left // 3600
        minutes_left = (seconds_left % 3600) // 60
        await message.answer(
            f"⏰ Вы уже получали ежедневный бонус!\n"
            f"Следующий бонус через {hours_left}ч {minutes_left}мин."
        )
        return
    
    # Начисляем бонус 50 NCoin
    update_balance(user_id, chat_id, 50)
    last_daily[user_id] = now
    
    # Добавляем пользователя в БД, если его там ещё нет
    add_user(user_id, chat_id, message.from_user.username)
    
    # Получаем обновлённый баланс
    new_balance = get_balance(user_id, chat_id)
    
    await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+50 NCoin\n"
        f"💰 Ваш баланс: {new_balance} NCoin"
    )

@router.message(Command("gift"))
async def cmd_gift(message: Message):
    """
    Команда /gift - перевод NCoin другому пользователю.
    Формат: /gift @username сумма
    """
    args = message.text.split()
    
    # Проверяем правильность формата
    if len(args) < 3:
        await message.answer(
            "🎁 **Подарок NCoin**\n\n"
            "Использование: /gift @username [сумма]\n"
            "Пример: /gift @ivan 50\n\n"
            "💰 Валюта: NCoin"
        )
        return
    
    # Извлекаем получателя и сумму
    target_username = args[1].replace("@", "")
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    # Проверяем сумму
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    
    # Проверяем баланс отправителя
    user_id = message.from_user.id
    chat_id = message.chat.id
    sender_balance = get_balance(user_id, chat_id)
    
    if sender_balance < amount:
        await message.answer(
            f"❌ Недостаточно NCoin.\n"
            f"💰 Ваш баланс: {sender_balance} NCoin\n"
            f"🎁 Требуется: {amount} NCoin"
        )
        return
    
    # TODO: Реализовать полноценный перевод между пользователями
    # Сейчас отправляем заглушку
    await message.answer(
        f"🎁 Вы подарили {amount} NCoin пользователю @{target_username}\n\n"
        f"✨ Функция автоматического перевода скоро будет доступна!\n"
        f"Пока что ваш баланс не изменился."
    )

@router.message(Command("top"))
async def cmd_top(message: Message):
    """
    Команда /top - показывает топ пользователей по балансу.
    """
    # TODO: Реализовать реальный топ из базы данных
    await message.answer(
        "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ ПО NCoin** 🏆\n\n"
        "1. 👑 — 5000 NCoin\n"
        "2. ⭐ — 3200 NCoin\n"
        "3. 🔥 — 2100 NCoin\n"
        "4. 💎 — 1500 NCoin\n"
        "5. 🎯 — 1200 NCoin\n\n"
        "📊 Полноценная таблица с реальными данными появится в следующем обновлении!"
    )
