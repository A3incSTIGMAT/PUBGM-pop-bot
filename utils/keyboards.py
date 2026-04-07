from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = [
        ("👤 Профиль", "profile"), ("💰 Экономика", "economy"),
        ("🎮 Игры", "games"), ("🛡️ Модерация", "moderation"),
        ("📊 Статистика", "stats"), ("🤝 Социальное", "social"),
        ("⭐ VIP", "vip"), ("🤖 AI", "ai"), ("💳 Озон Банк", "ozon_payment"),
        ("🛍️ Магазин", "shop"), ("❓ Помощь", "help"), ("ℹ️ О боте", "about")
    ]
    for text, callback in buttons:
        builder.add(InlineKeyboardButton(text=text, callback_data=callback))
    builder.adjust(2)
    return builder.as_markup()

def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]])

def game_buttons() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🎰 Слот", callback_data="game_slot"))
    builder.add(InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel"))
    builder.add(InlineKeyboardButton(text="🎲 Рулетка", callback_data="game_roulette"))
    builder.add(InlineKeyboardButton(text="✊ КНБ", callback_data="game_rps"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    builder.adjust(2)
    return builder.as_markup()
