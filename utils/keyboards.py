"""
keyboards.py — Генерация клавиатур
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    buttons = [
        ("👤 Профиль", "profile"),
        ("💰 Экономика", "economy"),
        ("🎮 Игры", "games"),
        ("🛡️ Модерация", "moderation"),
        ("📊 Статистика", "stats"),
        ("🤝 Социальное", "social"),
        ("⭐ VIP Статус", "vip"),
        ("🤖 AI Помощник", "ai"),
        ("💳 Озон Банк", "ozon_payment"),
        ("🛍️ Купить NCoin", "shop"),
        ("❓ Помощь", "help"),
        ("ℹ️ О боте", "about"),
    ]
    for text, callback in buttons:
        builder.add(InlineKeyboardButton(text=text, callback_data=callback))
    builder.adjust(2)
    return builder.as_markup()


def back_button() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])


def back_and_cancel() -> InlineKeyboardMarkup:
    """Кнопки назад и отмена"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ])


def game_buttons() -> InlineKeyboardMarkup:
    """Кнопки игр"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🎰 Слот", callback_data="game_slot"))
    builder.add(InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel"))
    builder.add(InlineKeyboardButton(text="🎲 Рулетка", callback_data="game_roulette"))
    builder.add(InlineKeyboardButton(text="✊ КНБ", callback_data="game_rps"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    builder.adjust(2)
    return builder.as_markup()


def duel_buttons(duel_id: str) -> InlineKeyboardMarkup:
    """Кнопки для дуэли"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"duel_accept_{duel_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"duel_decline_{duel_id}")
        ],
        [InlineKeyboardButton(text="💰 Увеличить ставку", callback_data=f"duel_increase_{duel_id}")]
    ])


def roulette_buttons() -> InlineKeyboardMarkup:
    """Кнопки для рулетки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 RED (x2)", callback_data="roulette_red"),
            InlineKeyboardButton(text="⚫ BLACK (x2)", callback_data="roulette_black")
        ],
        [InlineKeyboardButton(text="🟢 GREEN (x36)", callback_data="roulette_green")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


def rps_buttons() -> InlineKeyboardMarkup:
    """Кнопки для КНБ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✊ Камень", callback_data="rps_rock"),
            InlineKeyboardButton(text="✌️ Ножницы", callback_data="rps_scissors"),
            InlineKeyboardButton(text="✋ Бумага", callback_data="rps_paper")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


def payment_menu() -> InlineKeyboardMarkup:
    """Меню оплаты"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить через СБП", url="https://qr.nspk.ru/...")],
        [
            InlineKeyboardButton(text="✅ Я оплатил", callback_data="payment_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="payment_cancel")
        ]
    ])


def shop_buttons() -> InlineKeyboardMarkup:
    """Кнопки магазина"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="500 NCoin (50 ₽)", callback_data="shop_500"))
    builder.add(InlineKeyboardButton(text="1000 NCoin (100 ₽)", callback_data="shop_1000"))
    builder.add(InlineKeyboardButton(text="2500 NCoin (200 ₽)", callback_data="shop_2500"))
    builder.add(InlineKeyboardButton(text="5000 NCoin (350 ₽)", callback_data="shop_5000"))
    builder.add(InlineKeyboardButton(text="10000 NCoin (600 ₽)", callback_data="shop_10000"))
    builder.add(InlineKeyboardButton(text="⭐ Купить VIP", callback_data="shop_vip"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    builder.adjust(1)
    return builder.as_markup()
