"""
stats.py — Статистика бота
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from database import db
from config import ADMIN_IDS
from utils.keyboards import back_button

router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика бота (только админы)"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🔒 Только для администраторов")
        return

    await show_stats(message)


@router.callback_query(F.data == "stats")
async def stats_menu(callback: CallbackQuery):
    """Меню статистики"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🔒 Только для администраторов", show_alert=True)
        return

    await show_stats(callback.message)
    await callback.answer()


async def show_stats(message: Message):
    """Показать статистику"""
    total_users = await db.get_total_users()
    total_games = await db.get_total_games()
    total_bets = await db.get_total_bets()
    total_wins = await db.get_total_wins()

    profit = total_bets - total_wins
    house_edge = (profit / total_bets * 100) if total_bets > 0 else 0

    text = (
        f"📊 *СТАТИСТИКА NEXUS*\n\n"
        f"👥 Пользователей: `{total_users}`\n"
        f"🎮 Всего игр: `{total_games}`\n"
        f"💰 Всего ставок: `{total_bets} NCoin`\n"
        f"💸 Всего выигрышей: `{total_wins} NCoin`\n"
        f"📈 Прибыль бота: `{profit} NCoin`\n"
        f"🎲 Преимущество казино: `{house_edge:.2f}%`"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=back_button())
