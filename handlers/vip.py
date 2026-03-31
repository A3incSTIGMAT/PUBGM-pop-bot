"""
vip.py — VIP статус
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from database import db
from config import ADMIN_IDS
from utils.keyboards import back_button

router = Router()


@router.callback_query(F.data == "vip")
async def vip_menu(callback: CallbackQuery):
    """Меню VIP"""
    text = (
        "⭐ *VIP Статус*\n\n"
        "*Привилегии VIP:*\n"
        "✅ Увеличенные лимиты ставок (до 50000 NCoin)\n"
        "✅ Эксклюзивные стикеры\n"
        "✅ Повышенные множители в играх (x1.5)\n"
        "✅ Ежедневный бонус x2\n\n"
        "💰 Стоимость: 1000 NCoin / месяц\n"
        "💳 Оплата: Озон Банк\n\n"
        "Для покупки: `/buy_vip`"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


@router.message(Command("buy_vip"))
async def buy_vip(message: Message):
    """Покупка VIP за NCoin"""
    user_id = message.from_user.id
    balance = await db.get_balance(user_id)

    if balance >= 1000:
        await db.subtract_balance(user_id, 1000, "Покупка VIP")
        # Здесь логика выдачи VIP (например, запись в БД)
        await message.answer("⭐ *Поздравляем!* Вы стали VIP пользователем!", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Недостаточно NCoin! Нужно 1000, у вас {balance}", parse_mode="Markdown")


@router.message(Command("set_vip"))
async def set_vip_admin(message: Message):
    """Админ-команда выдачи VIP"""
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: `/set_vip [user_id]`")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный ID")
        return

    # Здесь логика выдачи VIP админом
    await message.answer(f"⭐ Пользователю `{user_id}` выдан VIP статус", parse_mode="Markdown")
