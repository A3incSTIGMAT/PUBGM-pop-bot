"""
help.py — Помощь и список команд
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from utils.keyboards import back_button

router = Router()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    text = get_help_text()
    await message.answer(text, parse_mode="Markdown")


@router.callback_query(F.data == "help")
async def help_menu(callback: CallbackQuery):
    """Меню помощи"""
    text = get_help_text()
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


def get_help_text() -> str:
    """Текст помощи"""
    return (
        "❓ *ПОМОЩЬ NEXUS*\n\n"
        "🎮 *Игры:*\n"
        "• `/slot` — слот-машина\n"
        "• `/duel [сумма]` — дуэль (ответом на сообщение)\n"
        "• `/roulette [сумма] [цвет]` — рулетка\n"
        "• `/rps [выбор]` — камень-ножницы-бумага\n"
        "• `/history` — история игр\n\n"
        "💰 *Экономика:*\n"
        "• `/balance` — баланс\n"
        "• `/daily` — ежедневный бонус\n"
        "• `/transfer @username [сумма]` — перевод NCoin\n\n"
        "🛡️ *Модерация:*\n"
        "• `/ban`, `/unban` — бан/разбан\n"
        "• `/mute`, `/unmute` — мут/размут\n"
        "• `/warn`, `/warns` — предупреждения\n\n"
        "⭐ *VIP:*\n"
        "• `/buy_vip` — купить VIP\n\n"
        "🤖 *AI:*\n"
        "• `/ask [вопрос]` — спросить у ИИ\n\n"
        "💳 *Оплата:*\n"
        "• `/shop` — магазин NCoin\n\n"
        "💡 *Совет:* можно писать команды простым текстом!\n"
        "Например: `сыграй в слот`, `рулетка 100 красный`, `обнять @username`"
    )
