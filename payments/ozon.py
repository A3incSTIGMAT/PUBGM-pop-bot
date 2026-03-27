"""
NEXUS Payments — Озон Банк
"""

import secrets
import time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import OZON_CARD_LAST4, OZON_BANK_NAME, OZON_RECEIVER, OZON_SBP_QR_URL

router = Router()
pending_payments = {}

def get_payment_menu(order_id: str) -> InlineKeyboardMarkup:
    buttons = []
    
    if OZON_SBP_QR_URL:
        buttons.append([InlineKeyboardButton(
            text="📱 Оплатить по QR-коду (СБП)",
            url=OZON_SBP_QR_URL
        )])
    
    buttons.append([InlineKeyboardButton(
        text="✅ Я оплатил(а)",
        callback_data=f"pay_confirm_{order_id}"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="pay_cancel"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("pay"))
async def cmd_pay(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "💎 **Покупка NCoin**\n\n"
            "Использование: /pay [сумма]\n"
            "Пример: /pay 500\n\n"
            "💰 Минимум 50 ₽, максимум 50 000 ₽\n"
            "💳 1 ₽ = 1 NCoin\n\n"
            f"🏦 **Реквизиты:**\n"
            f"Банк: {OZON_BANK_NAME}\n"
            f"Карта: •••• {OZON_CARD_LAST4}\n"
            f"Получатель: {OZON_RECEIVER}"
        )
        return
    
    try:
        amount = int(args[1])
        if amount < 50:
            await message.answer("❌ Минимальная сумма 50 ₽")
            return
        if amount > 50000:
            await message.answer("❌ Максимальная сумма 50 000 ₽")
            return
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    order_id = f"ORD_{message.from_user.id}_{int(time.time())}_{secrets.token_hex(4)}"
    
    pending_payments[order_id] = {
        "user_id": message.from_user.id,
        "user_name": message.from_user.full_name,
        "amount": amount,
        "status": "pending"
    }
    
    text = (
        f"💎 **Заказ #{order_id}**\n\n"
        f"💰 Сумма: {amount} ₽ → {amount} NCoin\n\n"
        f"🏦 **Реквизиты оплаты:**\n"
        f"Банк: {OZON_BANK_NAME}\n"
        f"Карта: •••• {OZON_CARD_LAST4}\n"
        f"Получатель: {OZON_RECEIVER}\n\n"
        f"📝 **Назначение платежа:** Пополнение NEXUS (заказ #{order_id})\n\n"
        f"💳 **СБП:** отсканируйте QR-код ниже или переведите по реквизитам"
    )
    
    await message.answer(text, reply_markup=get_payment_menu(order_id))
