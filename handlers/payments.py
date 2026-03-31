"""
payments.py — Оплата через Озон Банк
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime
from config import OZON_CARD_LAST4, OZON_BANK_NAME, OZON_RECEIVER, OZON_SBP_QR_URL, ADMIN_IDS
from database import db
from utils.keyboards import back_button, payment_menu

router = Router()


@router.callback_query(F.data == "ozon_payment")
async def ozon_payment_info(callback: CallbackQuery):
    """Информация об оплате через Озон Банк"""
    text = (
        f"💳 *Оплата через Озон Банк*\n\n"
        f"🏦 Банк: {OZON_BANK_NAME}\n"
        f"💳 Карта: **** **** **** {OZON_CARD_LAST4}\n"
        f"👤 Получатель: {OZON_RECEIVER}\n\n"
        f"*Как оплатить:*\n"
        f"1️⃣ Переведите сумму через СБП по QR-коду\n"
        f"2️⃣ Нажмите «Я оплатил»\n"
        f"3️⃣ Администратор проверит платёж и начислит NCoin\n\n"
        f"📱 *СБП QR-код:*\n"
        f"{OZON_SBP_QR_URL}\n\n"
        f"💸 *Курс:* 1 ₽ = 10 NCoin\n"
        f"💰 Минимальная сумма: 50 ₽\n\n"
        f"Для оплаты нажмите кнопку ниже 👇"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=payment_menu())
    await callback.answer()


@router.callback_query(F.data == "payment_confirm")
async def payment_confirm(callback: CallbackQuery):
    """Подтверждение оплаты"""
    await callback.message.edit_text(
        "✅ *Ваша заявка на пополнение принята!*\n\n"
        "Администратор проверит платёж в ближайшее время.\n"
        "После подтверждения NCoin поступят на ваш баланс.\n\n"
        "Для ускорения вы можете отправить чек администратору: @A3incSTIGMAT",
        parse_mode="Markdown",
        reply_markup=back_button()
    )

    # Уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                admin_id,
                f"💰 *Новая заявка на пополнение!*\n\n"
                f"👤 Пользователь: {callback.from_user.full_name} (@{callback.from_user.username})\n"
                f"🆔 ID: `{callback.from_user.id}`\n"
                f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"После проверки платежа начислите NCoin командой:\n"
                f"`/add_ncoin {callback.from_user.id} [сумма в NCoin]`",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data == "payment_cancel")
async def payment_cancel(callback: CallbackQuery):
    """Отмена оплаты"""
    await callback.message.edit_text("❌ Оплата отменена", reply_markup=back_button())
    await callback.answer()


@router.message(Command("add_ncoin"))
async def add_ncoin_admin(message: Message):
    """Админ-команда начисления NCoin"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🔒 Только для администраторов")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ Использование: `/add_ncoin [user_id] [сумма в NCoin]`")
        return

    try:
        user_id = int(args[1])
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Неверный формат")
        return

    await db.add_balance(user_id, amount, f"Пополнение через Озон Банк ({amount} NCoin)")
    await message.answer(f"✅ Пользователю `{user_id}` начислено {amount} NCoin", parse_mode="Markdown")

    # Уведомляем пользователя
    try:
        await message.bot.send_message(
            user_id,
            f"💳 *Ваш баланс пополнен!*\n"
            f"💰 Начислено: {amount} NCoin\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
    except Exception:
        pass
