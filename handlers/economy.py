from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import (
    get_balance, update_balance, add_user, get_last_bonus, set_last_bonus,
    get_free_balance, get_paid_balance, add_free_balance, spend_balance
)
from utils.helpers import delete_after_response
from handlers.vip import is_vip_active

router = Router()

# Время обновления бонуса (UTC)
BONUS_RESET_HOUR = 0  # 00:00 UTC
BONUS_RESET_MINUTE = 0

def get_next_bonus_time() -> datetime:
    """Возвращает дату и время следующего начисления бонуса (UTC)"""
    now = datetime.utcnow()
    reset_time = now.replace(hour=BONUS_RESET_HOUR, minute=BONUS_RESET_MINUTE, second=0, microsecond=0)
    
    if now >= reset_time:
        reset_time += timedelta(days=1)
    
    return reset_time

def get_time_until_next_bonus() -> tuple:
    """Возвращает (часы, минуты) до следующего бонуса"""
    next_time = get_next_bonus_time()
    now = datetime.utcnow()
    delta = next_time - now
    
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    
    return hours, minutes

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Команда /balance - показывает общий баланс"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    free = get_free_balance(user_id, chat_id)
    paid = get_paid_balance(user_id, chat_id)
    
    response = await message.answer(
        f"💰 **Ваш баланс:** {balance} NCoin\n\n"
        f"🎁 Бесплатные: {free} NCoin\n"
        f"💎 Платные: {paid} NCoin\n\n"
        f"💡 Платные NCoin можно получить через /buy"
    )
    await delete_after_response(response, message, delay=10)

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    """Команда /daily - ежедневный бонус (UTC 00:00)"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    last_bonus = get_last_bonus(user_id, chat_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Проверяем, получал ли пользователь бонус сегодня
    if last_bonus and last_bonus == today:
        hours, minutes = get_time_until_next_bonus()
        response = await message.answer(
            f"⏰ **Вы уже получали ежедневный бонус сегодня!**\n\n"
            f"🎁 Следующий бонус будет доступен в **00:00 UTC**\n"
            f"⏳ Осталось: {hours}ч {minutes}мин"
        )
        await delete_after_response(response, message, delay=10)
        return
    
    # Базовый бонус
    bonus = 50
    
    # Проверяем VIP бонус
    if is_vip_active(user_id, chat_id):
        bonus = int(bonus * 1.25)  # +25% для VIP
    
    # Начисляем бесплатные NCoin
    add_free_balance(user_id, chat_id, bonus)
    set_last_bonus(user_id, chat_id, today)
    add_user(user_id, chat_id, message.from_user.username)
    
    new_balance = get_balance(user_id, chat_id)
    hours, minutes = get_time_until_next_bonus()
    
    vip_text = " (VIP +25%)" if bonus > 50 else ""
    
    response = await message.answer(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"+{bonus} NCoin{vip_text}\n"
        f"💰 Ваш баланс: {new_balance} NCoin\n\n"
        f"⏳ Следующий бонус: **00:00 UTC**\n"
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
    
    # Находим пользователя
    target_id = None
    target_name = target_username
    try:
        async for member in message.chat.get_members():
            if member.user.username and member.user.username.lower() == target_username.lower():
                target_id = member.user.id
                target_name = member.user.full_name
                break
    except:
        pass
    
    if not target_id:
        response = await message.answer(f"❌ Пользователь @{target_username} не найден в чате.")
        await delete_after_response(response, message, delay=10)
        return
    
    # Списываем NCoin
    if not spend_balance(user_id, chat_id, amount):
        response = await message.answer("❌ Ошибка при списании средств.")
        await delete_after_response(response, message, delay=10)
        return
    
    # Начисляем получателю
    add_free_balance(target_id, chat_id, amount)
    
    response = await message.answer(
        f"🎁 **Вы подарили {amount} NCoin пользователю @{target_username}!**\n\n"
        f"💰 Ваш баланс: {get_balance(user_id, chat_id)} NCoin"
    )
    await delete_after_response(response, message, delay=15)
    
    # Уведомляем получателя
    try:
        await bot.send_message(
            target_id,
            f"🎁 **Вам подарили NCoin!**\n\n"
            f"{message.from_user.full_name} подарил(а) вам {amount} NCoin\n"
            f"💰 Ваш баланс: {get_balance(target_id, chat_id)} NCoin"
        )
    except:
        pass

@router.message(Command("top"))
async def cmd_top(message: Message):
    """Команда /top - топ пользователей по общему балансу"""
    from database.db import get_db
    
    chat_id = message.chat.id
    
    with get_db() as conn:
        results = conn.execute("""
            SELECT username, (free_balance + paid_balance) as total_balance
            FROM users
            WHERE chat_id = ? AND (free_balance + paid_balance) > 0
            ORDER BY total_balance DESC
            LIMIT 10
        """, (chat_id,)).fetchall()
    
    if not results:
        response = await message.answer("🏆 **Топ богачей**\n\nПока никого нет. Будьте первым!")
        await delete_after_response(response, message, delay=15)
        return
    
    top_text = "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ ПО NCoin** 🏆\n\n"
    for i, row in enumerate(results, 1):
        name = row["username"] or f"user_{i}"
        top_text += f"{i}. {name} — {row['total_balance']} NCoin\n"
    
    response = await message.answer(top_text)
    await delete_after_response(response, message, delay=15)
