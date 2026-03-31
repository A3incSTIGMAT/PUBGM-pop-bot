"""
profile.py — Профиль пользователя, статистика
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from database import db
from utils.keyboards import back_button

router = Router()


async def get_profile_text(user_id: int) -> str:
    """Формирует текст профиля"""
    user = await db.get_user(user_id)
    if not user:
        return "❌ Ошибка загрузки профиля"

    balance = user.get('balance', 0)
    total_games = user.get('total_games', 0)
    total_wins = user.get('total_wins', 0)
    total_bets = user.get('total_bets', 0)
    total_won = user.get('total_won', 0)
    is_vip = user.get('is_vip', False)

    win_rate = (total_wins / total_games * 100) if total_games > 0 else 0

    text = (
        f"👤 *Ваш профиль*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 Баланс: `{balance} NCoin`\n"
        f"⭐ VIP: {'✅ Активен' if is_vip else '❌ Не активен'}\n"
        f"🎮 Игр сыграно: `{total_games}`\n"
        f"🏆 Побед: `{total_wins}`\n"
        f"📈 Процент побед: `{win_rate:.1f}%`\n"
        f"💸 Всего поставлено: `{total_bets} NCoin`\n"
        f"🎁 Всего выиграно: `{total_won} NCoin`"
    )
    return text


async def cmd_profile_smart(message: Message):
    """Смарт-версия команды профиля"""
    text = await get_profile_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    await cmd_profile_smart(message)


@router.callback_query(F.data == "profile")
async def profile_menu(callback: CallbackQuery):
    text = await get_profile_text(callback.from_user.id)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()
