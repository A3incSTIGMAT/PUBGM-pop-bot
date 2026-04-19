"""
Модуль профиля и анкеты пользователя
ПОЛНОСТЬЮ ИСПРАВЛЕН — ВСЕ БАЛАНСЫ ЧЕРЕЗ db.get_balance()
"""

import logging
import re
import asyncio
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from config import START_BALANCE

router = Router()
logger = logging.getLogger(__name__)


# ==================== FSM ДЛЯ АНКЕТЫ ====================

class ProfileStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_city = State()
    waiting_for_timezone = State()
    waiting_for_about = State()


profile_states = {}


# ==================== ФИЛЬТРЫ И ВАЛИДАЦИЯ ====================

FORBIDDEN_WORDS = [
    'хуй', 'пизда', 'ебать', 'блять', 'сука', 'нахер', 'похуй',
    'залупа', 'жопа', 'говно', 'пидор', 'пидорас', 'гандон',
    'fuck', 'shit', 'ass', 'bitch', 'dick', 'cunt', 'whore',
    'ебан', 'ёбан', 'сосать', 'трахать', 'конча', 'сперм',
]

MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 30
MIN_CITY_LENGTH = 2
MAX_CITY_LENGTH = 30
MIN_AGE = 12
MAX_AGE = 100
MAX_ABOUT_LENGTH = 200


def contains_forbidden_words(text: str) -> bool:
    if not text:
        return False
    
    text_lower = text.lower()
    cleaned_text = re.sub(r'[^а-яa-z]', '', text_lower)
    
    for word in FORBIDDEN_WORDS:
        if word in cleaned_text or word in text_lower:
            return True
    return False


def validate_name(name: str) -> tuple[bool, str]:
    if not name or len(name.strip()) < MIN_NAME_LENGTH:
        return False, f"❌ Имя должно быть не короче {MIN_NAME_LENGTH} символов"
    
    if len(name) > MAX_NAME_LENGTH:
        return False, f"❌ Имя должно быть не длиннее {MAX_NAME_LENGTH} символов"
    
    if not re.match(r'^[а-яА-Яa-zA-Z\s\-]+$', name):
        return False, "❌ Имя может содержать только буквы, пробелы и дефис"
    
    if contains_forbidden_words(name):
        return False, "❌ Имя содержит недопустимые слова"
    
    return True, ""


def validate_age(age_str: str) -> tuple[bool, int | str]:
    try:
        age = int(age_str.strip())
    except ValueError:
        return False, "❌ Возраст должен быть числом"
    
    if age < MIN_AGE:
        return False, f"❌ Минимальный возраст: {MIN_AGE} лет"
    
    if age > MAX_AGE:
        return False, f"❌ Максимальный возраст: {MAX_AGE} лет"
    
    return True, age


def validate_city(city: str) -> tuple[bool, str]:
    if not city or len(city.strip()) < MIN_CITY_LENGTH:
        return False, f"❌ Название города должно быть не короче {MIN_CITY_LENGTH} символов"
    
    if len(city) > MAX_CITY_LENGTH:
        return False, f"❌ Название города должно быть не длиннее {MAX_CITY_LENGTH} символов"
    
    if not re.match(r'^[а-яА-Яa-zA-Z\s\-\.]+$', city):
        return False, "❌ Город может содержать только буквы, пробелы, точку и дефис"
    
    if contains_forbidden_words(city):
        return False, "❌ Название города содержит недопустимые слова"
    
    return True, ""


def validate_timezone(tz: str) -> tuple[bool, str]:
    if not tz:
        return False, "❌ Укажите часовой пояс"
    
    if not re.match(r'^(UTC|GMT)[+-]\d{1,2}(:\d{2})?$', tz.upper()):
        return False, "❌ Формат: UTC+3, GMT-5, UTC+5:30"
    
    return True, tz.upper()


def validate_about(about: str) -> tuple[bool, str]:
    if not about or len(about.strip()) < 5:
        return False, "❌ Расскажите о себе подробнее (минимум 5 символов)"
    
    if len(about) > MAX_ABOUT_LENGTH:
        return False, f"❌ Текст не должен превышать {MAX_ABOUT_LENGTH} символов"
    
    if contains_forbidden_words(about):
        return False, "❌ Текст содержит недопустимые слова"
    
    return True, ""


def sanitize_text(text: str) -> str:
    if not text:
        return ""
    
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
    return user


def _escape_html(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ==================== ПРОСМОТР ПРОФИЛЯ ====================

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    profile = await db.get_profile(user_id)
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(user_id)
    
    if not profile:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 ЗАПОЛНИТЬ АНКЕТУ", callback_data="fill_profile")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await message.answer(
            "👤 <b>ПРОФИЛЬ</b>\n\n"
            "У вас пока нет анкеты.\n"
            "Хотите заполнить?",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        return
    
    text = (
        f"👤 <b>АНКЕТА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"📛 Имя: <b>{_escape_html(profile.get('full_name', 'Не указано'))}</b>\n"
        f"🎂 Возраст: <b>{profile.get('age', 'Не указано')}</b>\n"
        f"🏙️ Город: <b>{_escape_html(profile.get('city', 'Не указано'))}</b>\n"
        f"🌍 Часовой пояс: <b>{_escape_html(profile.get('timezone', 'Не указано'))}</b>\n"
        f"📝 О себе: {_escape_html(profile.get('about', 'Не указано'))}\n\n"
        f"💰 Баланс: <b>{balance}</b> NCoin\n"
        f"🏆 Побед: {user.get('wins', 0)} | Поражений: {user.get('losses', 0)}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ АНКЕТУ", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    await cmd_profile(callback.message)
    await callback.answer()


# ==================== ЗАПОЛНЕНИЕ АНКЕТЫ ====================

@router.callback_query(F.data == "fill_profile")
async def start_fill_profile(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    profile_states[user_id] = True
    
    await state.set_state(ProfileStates.waiting_for_name)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_profile")]
    ])
    
    await callback.message.edit_text(
        "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
        "Шаг 1 из 5\n\n"
        f"<b>Как вас зовут?</b>\n"
        f"├ Мин. длина: {MIN_NAME_LENGTH} символов\n"
        f"├ Макс. длина: {MAX_NAME_LENGTH} символов\n"
        f"└ Только буквы\n\n"
        "Введите ваше имя:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()


@router.message(ProfileStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    name = sanitize_text(message.text)
    is_valid, error_msg = validate_name(name)
    
    if not is_valid:
        await message.answer(error_msg + "\n\nПопробуйте ещё раз:")
        return
    
    await state.update_data(full_name=name)
    await state.set_state(ProfileStates.waiting_for_age)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_profile")]
    ])
    
    await message.answer(
        "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
        "Шаг 2 из 5\n\n"
        f"<b>Сколько вам лет?</b>\n"
        f"├ От {MIN_AGE} до {MAX_AGE} лет\n"
        f"└ Только число\n\n"
        "Введите ваш возраст:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.message(ProfileStates.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    is_valid, result = validate_age(message.text)
    
    if not is_valid:
        await message.answer(result + "\n\nПопробуйте ещё раз:")
        return
    
    await state.update_data(age=result)
    await state.set_state(ProfileStates.waiting_for_city)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_profile")]
    ])
    
    await message.answer(
        "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
        "Шаг 3 из 5\n\n"
        f"<b>Из какого вы города?</b>\n"
        f"├ Мин. длина: {MIN_CITY_LENGTH} символов\n"
        f"└ Только буквы\n\n"
        "Введите ваш город:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.message(ProfileStates.waiting_for_city)
async def process_city(message: types.Message, state: FSMContext):
    city = sanitize_text(message.text)
    is_valid, error_msg = validate_city(city)
    
    if not is_valid:
        await message.answer(error_msg + "\n\nПопробуйте ещё раз:")
        return
    
    await state.update_data(city=city)
    await state.set_state(ProfileStates.waiting_for_timezone)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_profile")]
    ])
    
    await message.answer(
        "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
        "Шаг 4 из 5\n\n"
        "<b>Ваш часовой пояс?</b>\n\n"
        "Примеры:\n"
        "• <code>UTC+3</code> (Москва)\n"
        "• <code>UTC+5</code> (Екатеринбург)\n"
        "• <code>UTC+7</code> (Новосибирск)\n"
        "• <code>GMT-5</code> (Нью-Йорк)\n\n"
        "Введите часовой пояс:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.message(ProfileStates.waiting_for_timezone)
async def process_timezone(message: types.Message, state: FSMContext):
    tz = message.text.strip()
    is_valid, result = validate_timezone(tz)
    
    if not is_valid:
        await message.answer(result + "\n\nПопробуйте ещё раз:")
        return
    
    await state.update_data(timezone=result)
    await state.set_state(ProfileStates.waiting_for_about)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ ПРОПУСТИТЬ", callback_data="skip_about")],
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_profile")]
    ])
    
    await message.answer(
        "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
        "Шаг 5 из 5\n\n"
        f"<b>Расскажите немного о себе:</b>\n"
        f"├ Мин. длина: 5 символов\n"
        f"├ Макс. длина: {MAX_ABOUT_LENGTH} символов\n"
        f"└ Без нецензурных слов\n\n"
        "Пример: Люблю игры и программирование",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.message(ProfileStates.waiting_for_about)
async def process_about(message: types.Message, state: FSMContext):
    about = sanitize_text(message.text)
    is_valid, error_msg = validate_about(about)
    
    if not is_valid:
        await message.answer(error_msg + "\n\nПопробуйте ещё раз или нажмите 'ПРОПУСТИТЬ':")
        return
    
    await save_profile(message, state, about)


@router.callback_query(F.data == "skip_about")
async def skip_about(callback: types.CallbackQuery, state: FSMContext):
    await save_profile(callback.message, state, "")
    await callback.answer()


async def save_profile(event: types.Message | types.CallbackQuery, state: FSMContext, about: str):
    if isinstance(event, types.CallbackQuery):
        message = event.message
        user_id = event.from_user.id
    else:
        message = event
        user_id = event.from_user.id
    
    data = await state.get_data()
    
    full_name = data.get('full_name', '')
    age = data.get('age', 0)
    city = data.get('city', '')
    timezone = data.get('timezone', 'UTC+3')
    about_text = about if about else data.get('about', '')
    
    full_name = sanitize_text(full_name)
    city = sanitize_text(city)
    about_text = sanitize_text(about_text)
    
    await db.save_profile(user_id, full_name, age, city, timezone, about_text)
    
    profile_states.pop(user_id, None)
    await state.clear()
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(user_id)
    
    text = (
        f"✅ <b>АНКЕТА СОХРАНЕНА!</b>\n\n"
        f"📛 Имя: <b>{_escape_html(full_name)}</b>\n"
        f"🎂 Возраст: <b>{age}</b>\n"
        f"🏙️ Город: <b>{_escape_html(city)}</b>\n"
        f"🌍 Часовой пояс: <b>{_escape_html(timezone)}</b>\n"
        f"📝 О себе: {_escape_html(about_text) if about_text else '<i>не указано</i>'}\n\n"
        f"💰 Баланс: <b>{balance}</b> NCoin\n\n"
        f"Используйте /profile для просмотра анкеты"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data == "cancel_profile")
async def cancel_profile(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    profile_states.pop(user_id, None)
    await state.clear()
    
    await callback.message.edit_text(
        "❌ Заполнение анкеты отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
    )
    await callback.answer()


@router.message(Command("cancel_profile"))
async def cmd_cancel_profile(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    profile_states.pop(user_id, None)
    await state.clear()
    await message.answer("❌ Заполнение анкеты отменено.")


# ==================== СТАТИСТИКА ====================

@router.callback_query(F.data == "my_stats")
async def my_stats_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(user_id)
    
    conn = await db._get_connection_async()
    cursor = await conn.execute(
        """SELECT slots_played, roulette_played, rps_played, duel_played 
           FROM user_game_stats WHERE user_id = ?""",
        (user_id,)
    )
    row = await cursor.fetchone()
    await conn.close()
    
    slots = row[0] if row else 0
    roulette = row[1] if row else 0
    rps = row[2] if row else 0
    duel = row[3] if row else 0
    
    first_name = user.get('first_name', 'Не указано')
    wins = user.get('wins', 0)
    losses = user.get('losses', 0)
    
    text = f"""
📊 <b>ВАША СТАТИСТИКА</b>

━━━━━━━━━━━━━━━━━━━━━

👤 Имя: {_escape_html(first_name)}
💰 Баланс: <b>{balance}</b> NCoin
🏆 Побед: {wins} | Поражений: {losses}

━━━━━━━━━━━━━━━━━━━━━

<b>ИГРЫ:</b>
🎰 Слот: {slots} игр
🎡 Рулетка: {roulette} игр
✂️ КНБ: {rps} игр
⚔️ Дуэль: {duel} игр

━━━━━━━━━━━━━━━━━━━━━

💡 <i>Играйте больше, чтобы повысить ранг!</i>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()
