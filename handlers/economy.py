from datetime import datetime, timedelta, time
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, add_user
from utils.helpers import delete_after_response

router = Router()

# Время обновления бонуса (по Москве)
BONUS_RESET_HOUR = 3  # 3:00 MSK
BONUS_RESET_MINUTE = 0

def get_next_bonus_time() -> datetime:
    """
    Возвращает дату и время следующего начисления бонуса.
    Если сейчас позже времени сброса, то следующий сброс будет завтра.
    """
    now = datetime.now()
    reset_time = now.replace(hour=BONUS_RESET_HOUR, minute=BONUS_RESET_MINUTE, second=0, microsecond=0)
    
    if now >= reset_time:
        reset_time += timedelta(days=1)
    
    return reset_time

def get_time_until_next_bonus() -> tuple:
    """
    Возвращает (часы, минуты) до следующего бонуса.
    """
    next_time = get_next_bonus_time()
    now = datetime.now()
    delta = next_time - now
    
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    
    return hours, minutes

def has_received_bonus_today(user_id: int, last_bonus_date: str) -> bool:
    """
    Проверяет, получал ли пользователь бонус сегодня.
    """
    if not last_bonus_date:
        return False
    
    today = datetime.now().strftime("%Y-%m-%d")
    return last_bonus_date == today

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    """
    Команда /daily - ежедневный бонус.
    Обновляется в 03:00 по Москве.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Получаем информацию о последнем бонусе пользователя
    from database.db import get_last_bonus, set_last_bonus
    
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
    
    # Рассчитываем время до следующего бонуса
    hours, minutes = get_time_until_next_bonus()
    
    response = await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+50 NCoin\n"
        f"💰 Ваш баланс: {new_balance} NCoin\n\n"
        f"⏳ Следующий бонус: **{BONUS_RESET_HOUR:02d}:{BONUS_RESET_MINUTE:02d} МСК**\n"
        f"(через {hours}ч {minutes}мин)"
    )
    await delete_after_response(response, message, delay=10)
