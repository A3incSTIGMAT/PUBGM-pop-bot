"""
start.py — Обработчик команды /start и главное меню
"""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from database import db
from utils.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user = message.from_user
    await db.create_user(user.id, user.username, user.full_name)
    await db.update_activity(user.id)

    await message.answer(
        f"🌟 *Добро пожаловать в NEXUS, {user.full_name}!*\n\n"
        f"🎮 Многофункциональный бот для чатов с играми, модерацией и экономикой.\n\n"
        f"Выберите категорию в меню ниже:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        "🏠 *Главное меню NEXUS*\n\nВыберите категорию:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery):
    """Отмена текущего действия"""
    await callback.message.edit_text(
        "✅ Действие отменено.\n\nВозвращаюсь в главное меню.",
        reply_markup=main_menu()
    )
    await callback.answer()
