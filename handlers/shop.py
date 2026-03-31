"""
shop.py — Магазин NCoin
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime
from config import OZON_CARD_LAST4, OZON_BANK_NAME, OZON_RECEIVER, OZON_SBP_QR_URL, ADMIN_IDS
from database import db
from utils.keyboards import back_button, shop_buttons

router = Router()


@router.callback_query(F.data == "shop")
async def shop_menu(callback: CallbackQuery):
    """Меню магазина"""
    text = (
        "🛍️ *Магазин NCoin*\n\n"
        "💰 *Тарифы:*\n"
        "• 500 NCoin — 50 ₽\n"
        "• 1000 NCoin — 100 ₽\n"
        "• 2500 NCoin — 200 ₽\n"
        "• 5000 NCoin — 350 ₽\n"
        "• 10000 NCoin — 600 ₽\n\n"
        "⭐ *VIP статус:* 1000 NCoin / месяц\n\n"
        "💳 *Оплата через Озон Банк*\n"
        f"🏦 {OZON_BANK_NAME} | Карта **** {OZON_CARD_LAST4}\n"
        f"👤 Получатель: {OZON_RECEIVER}\n\n"
        "💸 *Курс:* 1 ₽ = 10 NCoin\n\n"
        "Выберите сумму для покупки 👇"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=shop_buttons())
    await callback.answer()


@router.callback_query(F.data.startswith("shop_"))
async def shop_purchase(callback: CallbackQuery):
    """Обработка покупки"""
    amount = callback.data.split("_")[1]

    price_map = {
        "500": 50,
        "1000": 100,
        "2500": 200,
        "5000": 350,
        "10000": 600
    }

    if amount == "vip":
        ncoin = 1000
        price = 100
        text = (
            "⭐ *Покупка VIP статуса*\n\n"
            f"💰 Стоимость: 1000 NCoin (100 ₽)\n\n"
            f"💳 *Реквизиты для оплаты:*\n"
            f"🏦 Банк: {OZON_BANK_NAME}\n"
            f"💳 Карта: **** **** **** {OZON_CARD_LAST4}\n"
            f"👤 Получатель: {OZON_RECEIVER}\n"
            f"📱 СБП QR: {OZON_SBP_QR_URL}\n\n"
            "После оплаты нажмите кнопку ниже"
        )
    else:
        ncoin = int(amount)
        price = price_map.get(amount, 0)
        text = (
            f"🛍️ *Покупка {ncoin} NCoin*\n\n"
            f"💰 Сумма: {price} ₽\n\n"
            f"💳 *Реквизиты для оплаты:*\n"
            f"🏦 Банк: {OZON_BANK_NAME}\n"
            f"💳 Карта: **** **** **** {OZON_CARD_LAST4}\n"
            f"👤 Получатель: {OZON_RECEIVER}\n"
            f"📱 СБП QR: {OZON_SBP_QR_URL}\n\n"
            "После оплаты нажмите кнопку ниже"
        )

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"confirm_{ncoin}_{price}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="shop")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_"))
async def confirm_purchase(callback: CallbackQuery):
    """Подтверждение покупки"""
    _, ncoin, price = callback.data.split("_")

    await callback.message.edit_text(
        f"✅ *Заявка на пополнение создана!*\n\n"
        f"💰 NCoin: {ncoin}\n"
        f"💵 Сумма: {price} ₽\n\n"
        f"📤 Отправьте чек об оплате администратору @A3incSTIGMAT\n"
        f"После проверки средства поступят на ваш баланс.",
        parse_mode="Markdown",
        reply_markup=back_button()
    )

    # Уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                admin_id,
                f"💰 *Новая заявка на пополнение*\n\n"
                f"👤 Пользователь: {callback.from_user.full_name} (@{callback.from_user.username})\n"
                f"🆔 ID: `{callback.from_user.id}`\n"
                f"💵 Сумма: {price} ₽\n"
                f"💰 NCoin: {ncoin}\n"
                f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"После проверки платежа начислите NCoin командой:\n"
                f"`/add_ncoin {callback.from_user.id} {ncoin}`",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await callback.answer()


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    """Команда /shop"""
    await shop_menu(message)
