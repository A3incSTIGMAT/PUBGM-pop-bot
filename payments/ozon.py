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
        buttons.append([InlineKeyboardButton(text="📱 СБП (QR-код)", url=OZON_SBP_QR_URL)])
    buttons.append([InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"pay_confirm_{order_id}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("pay"))
async def cmd_pay(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("💎 /pay [сумма]\nПример: /pay 500")
        return
    
    try:
        amount = int(args[1])
        if amount < 50:
            await message.answer("❌ Минимум 50 ₽")
            return
    except:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    order_id = f"ORD_{message.from_user.id}_{int(time.time())}_{secrets.token_hex(4)}"
    pending_payments[order_id] = {"user_id": message.from_user.id, "amount": amount}
    
    text = f"💳 **Реквизиты**\n🏦 {OZON_BANK_NAME}\n💳 •••• {OZON_CARD_LAST4}\n👤 {OZON_RECEIVER}\n💰 {amount} ₽\n📝 Заказ: {order_id}"
    await message.answer(text, reply_markup=get_payment_menu(order_id))
