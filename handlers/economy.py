"""
economy.py — Экономика: баланс, переводы, ежедневный бонус
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime
from database import db
from utils.keyboards import back_button
from utils.helpers import extract_username, extract_amount

router = Router()


async def cmd_balance_smart(message: Message):
    """Смарт-версия команды баланса"""
    balance = await db.get_balance(message.from_user.id)
    await message.answer(f"💰 Ваш баланс: *{balance} NCoin*", parse_mode="Markdown")


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    await cmd_balance_smart(message)


async def cmd_daily_smart(message: Message):
    """Смарт-версия команды ежедневного бонуса"""
    user_id = message.from_user.id

    # Проверка на получение бонуса (упрощённо)
    await db.add_balance(user_id, 100, "Ежедневный бонус")
    await message.answer("🎁 Вы получили *100 NCoin*! Заберите завтра снова.", parse_mode="Markdown")


@router.message(Command("daily"))
async def cmd_daily(message: Message):
    await cmd_daily_smart(message)


async def cmd_transfer_smart(message: Message, to_user: str = None, amount: int = None):
    """Смарт-версия команды перевода"""
    if to_user is None:
        to_user = extract_username(message.text)
    if amount is None:
        amount = extract_amount(message.text)

    if not to_user or not amount:
        await message.answer("❌ Использование: `перевести @username 100`", parse_mode="Markdown")
        return

    # Поиск пользователя
    target_user = None
    async with db._db.execute('SELECT user_id FROM users WHERE username = ?', (to_user,)) as cursor:
        row = await cursor.fetchone()
        if row:
            target_user = row[0]

    if not target_user:
        await message.answer(f"❌ Пользователь @{to_user} не найден")
        return

    if target_user == message.from_user.id:
        await message.answer("❌ Нельзя перевести самому себе")
        return

    balance = await db.get_balance(message.from_user.id)
    if balance < amount:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {balance} NCoin")
        return

    await db.subtract_balance(message.from_user.id, amount, f"Перевод @{to_user}")
    await db.add_balance(target_user, amount, f"Перевод от @{message.from_user.username}")

    await message.answer(f"✅ Переведено *{amount} NCoin* пользователю @{to_user}", parse_mode="Markdown")


@router.message(Command("transfer"))
async def cmd_transfer(message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ Использование: `/transfer @username 100`")
        return

    to_user = args[1].replace('@', '')
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return

    await cmd_transfer_smart(message, to_user, amount)


@router.callback_query(F.data == "economy")
async def economy_menu(callback: CallbackQuery):
    """Меню экономики"""
    balance = await db.get_balance(callback.from_user.id)
    text = (
        f"💰 *Экономика NEXUS*\n\n"
        f"Ваш баланс: `{balance} NCoin`\n\n"
        f"📅 `/daily` — ежедневный бонус\n"
        f"💸 `/transfer @username 100` — перевод средств\n"
        f"🛍️ `/shop` — магазин NCoin"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()
