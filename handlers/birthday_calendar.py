"""
Интерактивный календарь для выбора дня рождения
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

# Состояния
class BirthdayStates(StatesGroup):
    selecting_month = State()
    selecting_day = State()

# Словарь месяцев
MONTHS = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь"
}

# Количество дней в месяцах
DAYS_IN_MONTH = {
    1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
}

def get_months_keyboard(current_month: int = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора месяца"""
    buttons = []
    row = []
    
    for month_num, month_name in MONTHS.items():
        # Если это текущий месяц, подсвечиваем
        if current_month == month_num:
            text = f"✅ {month_name}"
        else:
            text = month_name
        
        row.append(InlineKeyboardButton(text=text, callback_data=f"bday_month_{month_num}"))
        
        if len(row) == 3:  # 3 месяца в строке
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bday_cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_days_keyboard(month: int, current_day: int = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора дня месяца"""
    days_in_month = DAYS_IN_MONTH.get(month, 31)
    buttons = []
    row = []
    
    for day in range(1, days_in_month + 1):
        if current_day == day:
            text = f"✅ {day}"
        else:
            text = str(day)
        
        row.append(InlineKeyboardButton(text=text, callback_data=f"bday_day_{day}"))
        
        if len(row) == 7:  # 7 дней в строке
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад к месяцам", callback_data="bday_back_to_months"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="bday_cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("setbirthday"))
async def cmd_setbirthday(message: Message, state: FSMContext):
    """Начинаем выбор дня рождения"""
    await state.set_state(BirthdayStates.selecting_month)
    
    await message.answer(
        "🎂 **Установка дня рождения**\n\n"
        "Выберите месяц:",
        reply_markup=get_months_keyboard()
    )

@router.callback_query(lambda c: c.data.startswith("bday_month_"))
async def process_month_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора месяца"""
    month = int(callback.data.replace("bday_month_", ""))
    
    await state.update_data(month=month)
    await state.set_state(BirthdayStates.selecting_day)
    
    await callback.message.edit_text(
        f"🎂 **Установка дня рождения**\n\n"
        f"📅 Выбран месяц: **{MONTHS[month]}**\n\n"
        f"Выберите день:",
        reply_markup=get_days_keyboard(month)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("bday_day_"))
async def process_day_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора дня"""
    day = int(callback.data.replace("bday_day_", ""))
    
    data = await state.get_data()
    month = data.get("month")
    
    if not month:
        await state.clear()
        await callback.message.edit_text("❌ Ошибка. Попробуйте снова /setbirthday")
        await callback.answer()
        return
    
    # Форматируем дату
    birthday = f"{day:02d}.{month:02d}"
    
    # Сохраняем в базу
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    set_birthday(user_id, chat_id, birthday)
    log_user(callback.from_user.full_name, f"/setbirthday {birthday}")
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ **День рождения {birthday} сохранен!**\n\n"
        f"🎉 В этот день я поздравлю вас в чате!\n\n"
        f"💡 Для изменения даты используйте `/setbirthday` снова."
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "bday_back_to_months")
async def back_to_months(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору месяца"""
    await state.set_state(BirthdayStates.selecting_month)
    
    await callback.message.edit_text(
        "🎂 **Установка дня рождения**\n\n"
        "Выберите месяц:",
        reply_markup=get_months_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "bday_cancel")
async def cancel_birthday(callback: CallbackQuery, state: FSMContext):
    """Отмена установки дня рождения"""
    await state.clear()
    await callback.message.edit_text("❌ Установка дня рождения отменена.")
    await callback.answer()
