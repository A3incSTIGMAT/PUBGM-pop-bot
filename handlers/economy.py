from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from database import db
from utils.keyboards import back_button

router = Router()

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
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала используйте /start")
        return
    
    # Проверка на ежедневный бонус
    from datetime import datetime
    today = datetime.now().date().isoformat()
    
    if user.get("last_daily") == today:
        await message.answer("⏰ Вы уже получали бонус сегодня!")
        return
    
    # Начисляем бонус
    await db.update_balance(message.from_user.id, 100, "Ежедневный бонус")
    
    # Обновляем дату последнего бонуса
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (today, message.from_user.id))
    conn.commit()
    conn.close()
    
    await message.answer("🎁 +100 NCoin! Завтра будет новый бонус.")

@router.message(Command("transfer"))
async def cmd_transfer(message: Message):
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
    sender = await db.get_user(message.from_user.id)
    if not sender:
        await message.answer("❌ Сначала используйте /start")
        return
    
    if sender["balance"] < amount:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {sender['balance']} NCoin")
        return
    
    # Ищем получателя по username
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (to_user,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{to_user} не найден в базе")
        return
    
    target_id = row[0]
    
    if target_id == message.from_user.id:
        await message.answer("❌ Нельзя перевести монеты самому себе")
        return
    
    # Выполняем перевод
    await db.update_balance(message.from_user.id, -amount, f"Перевод пользователю @{to_user}")
    await db.update_balance(target_id, amount, f"Перевод от @{message.from_user.username or message.from_user.first_name}")
    
    await message.answer(f"✅ Переведено {amount} NCoin пользователю @{to_user}!")

@router.callback_query(F.data == "economy")
async def economy_menu(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
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
