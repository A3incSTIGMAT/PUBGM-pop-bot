from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, add_user, get_last_bonus, set_last_bonus
from utils.helpers import delete_after_response

router = Router()

# Время обновления бонуса (по Москве)
BONUS_RESET_HOUR = 3  # 3:00 MSK
BONUS_RESET_MINUTE = 0

def get_next_bonus_time() -> datetime:
    """Возвращает дату и время следующего начисления бонуса"""
    now = datetime.now()
    reset_time = now.replace(hour=BONUS_RESET_HOUR, minute=BONUS_RESET_MINUTE, second=0, microsecond=0)
    
    if now >= reset_time:
        reset_time += timedelta(days=1)
    
    return reset_time

def get_time_until_next_bonus() -> tuple:
    """Возвращает (часы, минуты) до следующего бонуса"""
    next_time = get_next_bonus_time()
    now = datetime.now()
    delta = next_time - now
    
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    
    return hours, minutes

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
    """Команда /daily - ежедневный бонус (обновление в 03:00 МСК)"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    last_bonus = get_last_bonus(user_id, chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Проверяем, получал ли пользователь бонус сегодня
    if last_bonus and last_bonus == today:
        hours, minutes = get_time_until_next_bonus()
        response = await message.answer(
            f"⏰ **Вы уже получали ежедневный бонус сегодня!**\n\n"
            f"🎁 Следующий бонус будет доступен в **{BONUS_RESET_HOUR:02d}:{BONUS_RESET_MINUTE:02d} МСК**\n"
            f"⏳ Осталось: {hours}ч {minutes}мин"
        )
        await delete_after_response(response, message, delay=10)
        return
    
    # Начисляем бонус
    update_balance(user_id, chat_id, 50)
    set_last_bonus(user_id, chat_id, today)
    add_user(user_id, chat_id, message.from_user.username)
    
    new_balance = get_balance(user_id, chat_id)
    hours, minutes = get_time_until_next_bonus()
    
    response = await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+50 NCoin\n"
        f"💰 Ваш баланс: {new_balance} NCoin\n\n"
        f"⏳ Следующий бонус: **{BONUS_RESET_HOUR:02d}:{BONUS_RESET_MINUTE:02d} МСК**\n"
        f"(через {hours}ч {minutes}мин)"
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
        "📊 Скоро будет полноценная таблица с реальными данными!"
    )
    await delete_after_response(response, message, delay=15)
