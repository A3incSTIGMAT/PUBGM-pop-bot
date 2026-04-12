from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime
import sqlite3

from database import db
from utils.keyboards import back_button

router = Router()

# Импортируем profile_states для проверки заполнения анкеты
from handlers.profile import profile_states


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала используйте /start")
        return
    balance = user["balance"]
    await message.answer(f"💰 Баланс: *{balance} NCoin*", parse_mode="Markdown")


@router.message(Command("daily"))
async def cmd_daily(message: Message):
    user_id = message.from_user.id
    
    # Проверяем, не заполняет ли пользователь анкету
    if user_id in profile_states:
        await message.answer("❌ Сначала завершите заполнение анкеты командой /cancel_profile")
        return
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Сначала используйте /start")
        return
    
    today = datetime.now().date().isoformat()
    
    if user.get("last_daily") == today:
        await message.answer("⏰ Вы уже получали бонус сегодня! Возвращайтесь завтра.")
        return
    
    # Начисляем бонус
    await db.update_balance(user_id, 100, "Ежедневный бонус")
    
    # Обновляем дату последнего бонуса
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (today, user_id))
    conn.commit()
    conn.close()
    
    # Получаем новый баланс
    updated_user = await db.get_user(user_id)
    new_balance = updated_user["balance"] if updated_user else 0
    
    await message.answer(f"🎁 +100 NCoin! Завтра будет новый бонус.\n\n💰 Новый баланс: {new_balance} NCoin")


@router.message(Command("transfer"))
async def cmd_transfer(message: Message):
    user_id = message.from_user.id
    
    # Проверяем, не заполняет ли пользователь анкету
    if user_id in profile_states:
        await message.answer("❌ Сначала завершите заполнение анкеты командой /cancel_profile")
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ Использование: /transfer @username 100")
        return
    
    to_user = args[1].replace('@', '')
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной")
        return
    
    # Получаем отправителя
    sender = await db.get_user(user_id)
    if not sender:
        await message.answer("❌ Сначала используйте /start")
        return
    
    if sender["balance"] < amount:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {sender['balance']} NCoin")
        return
    
    # Ищем получателя по username
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (to_user,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{to_user} не найден в базе")
        return
    
    target_id = row[0]
    
    if target_id == user_id:
        await message.answer("❌ Нельзя перевести монеты самому себе")
        return
    
    # Выполняем перевод
    await db.update_balance(user_id, -amount, f"Перевод пользователю @{to_user}")
    await db.update_balance(target_id, amount, f"Перевод от @{message.from_user.username or message.from_user.first_name}")
    
    # Получаем новый баланс
    updated_sender = await db.get_user(user_id)
    new_balance = updated_sender["balance"] if updated_sender else 0
    
    await message.answer(f"✅ Переведено {amount} NCoin пользователю @{to_user}!\n\n💰 Ваш новый баланс: {new_balance} NCoin")


@router.callback_query(F.data == "economy")
async def economy_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    # Проверяем, не заполняет ли пользователь анкету
    if user_id in profile_states:
        await callback.answer("❌ Сначала завершите заполнение анкеты", show_alert=True)
        return
    
    user = await db.get_user(user_id)
    balance = user["balance"] if user else 0
    
    await callback.message.edit_text(
        f"💰 *Экономика*\n\nВаш баланс: {balance} NCoin\n\n"
        f"📌 Доступные команды:\n"
        f"/balance - проверить баланс\n"
        f"/daily - получить бонус\n"
        f"/transfer @user 100 - перевести монеты",
        parse_mode="Markdown",
        reply_markup=back_button()
    )
    await callback.answer()
