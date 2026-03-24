"""
Обработчик дней рождения с интерактивным вводом
"""

from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import set_birthday
from utils.logger import log_user

router = Router()

# Состояния для FSM
class BirthdayStates(StatesGroup):
    waiting_for_date = State()

@router.message(Command("setbirthday"))
async def cmd_setbirthday(message: Message, state: FSMContext):
    """Начинаем интерактивную установку дня рождения"""
    await state.set_state(BirthdayStates.waiting_for_date)
    
    # Создаём клавиатуру с примерами
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 15 июля (15.07)", callback_data="birthday_15.07"),
            InlineKeyboardButton(text="📅 3 октября (03.10)", callback_data="birthday_03.10")
        ],
        [
            InlineKeyboardButton(text="📅 1 января (01.01)", callback_data="birthday_01.01"),
            InlineKeyboardButton(text="📅 31 декабря (31.12)", callback_data="birthday_31.12")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="birthday_cancel")
        ]
    ])
    
    await message.answer(
        "🎂 **Установка дня рождения**\n\n"
        "Выберите дату из предложенных ниже или введите свою в формате **ДД.ММ**\n\n"
        "📝 Примеры: 15.07, 03.10, 01.01\n\n"
        "✨ В день рождения вы получите поздравление в чате!",
        reply_markup=keyboard
    )

@router.callback_query(lambda c: c.data.startswith("birthday_"))
async def process_birthday_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора даты из кнопок"""
    date_str = callback.data.replace("birthday_", "")
    
    if date_str == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Установка дня рождения отменена.")
        await callback.answer()
        return
    
    # Сохраняем дату
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    set_birthday(user_id, chat_id, date_str)
    log_user(callback.from_user.full_name, f"/setbirthday {date_str}")
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ **День рождения {date_str} сохранен!**\n\n"
        f"🎉 В этот день я поздравлю вас в чате!"
    )
    await callback.answer()

@router.message(BirthdayStates.waiting_for_date)
async def process_birthday_text(message: Message, state: FSMContext):
    """Обработка ручного ввода даты"""
    birthday = message.text.strip()
    
    # Проверяем формат
    try:
        datetime.strptime(birthday, "%d.%m")
    except ValueError:
        await message.answer(
            "❌ **Неверный формат!**\n\n"
            "Пожалуйста, введите дату в формате **ДД.ММ**\n"
            "Пример: 15.07\n\n"
            "Или используйте кнопки для выбора даты."
        )
        return
    
    # Сохраняем дату
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    set_birthday(user_id, chat_id, birthday)
    log_user(message.from_user.full_name, f"/setbirthday {birthday}")
    
    await state.clear()
    await message.answer(
        f"✅ **День рождения {birthday} сохранен!**\n\n"
        f"🎉 В этот день я поздравлю вас в чате!\n\n"
        f"💡 Для изменения даты используйте `/setbirthday` снова."
    )
