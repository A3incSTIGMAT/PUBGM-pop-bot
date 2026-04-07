from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from database import db
from utils.keyboards import back_button

router = Router()

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    balance = await db.get_balance(message.from_user.id)
    await message.answer(f"💰 Баланс: *{balance} NCoin*", parse_mode="Markdown")

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    await db.add_balance(message.from_user.id, 100, "Ежедневный бонус")
    await message.answer("🎁 +100 NCoin!")

@router.message(Command("transfer"))
async def cmd_transfer(message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ /transfer @username 100")
        return
    to_user = args[1].replace('@', '')
    try:
        amount = int(args[2])
    except:
        await message.answer("❌ Сумма числом")
        return
    async with db._db.execute('SELECT user_id FROM users WHERE username = ?', (to_user,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            await message.answer(f"❌ @{to_user} не найден")
            return
        target_id = row[0]
    if target_id == message.from_user.id:
        await message.answer("❌ Себе нельзя")
        return
    balance = await db.get_balance(message.from_user.id)
    if balance < amount:
        await message.answer(f"❌ Не хватает")
        return
    await db.subtract_balance(message.from_user.id, amount, f"Перевод @{to_user}")
    await db.add_balance(target_id, amount, f"Перевод от @{message.from_user.username}")
    await message.answer(f"✅ Переведено {amount} NCoin @{to_user}")

@router.callback_query(F.data == "economy")
async def economy_menu(callback: CallbackQuery):
    balance = await db.get_balance(callback.from_user.id)
    await callback.message.edit_text(f"💰 *Экономика*\nВаш баланс: {balance} NCoin", parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()
