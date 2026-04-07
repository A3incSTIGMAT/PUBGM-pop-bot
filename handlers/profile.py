from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from database import db
from utils.keyboards import back_button

router = Router()

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user: return
    text = f"👤 *Профиль*\n💰 Баланс: {user.get('balance',0)} NCoin\n🎮 Игр: {user.get('total_games',0)}\n🏆 Побед: {user.get('total_wins',0)}"
    await message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data == "profile")
async def profile_menu(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    text = f"👤 *Профиль*\n💰 Баланс: {user.get('balance',0)} NCoin" if user else "Ошибка"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()
