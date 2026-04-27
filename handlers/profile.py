#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/profile.py
# ВЕРСИЯ: 2.1.1-production
# ОПИСАНИЕ: Профиль и анкета пользователя
# ИСПРАВЛЕНИЯ v2.1.1:
#   ✅ MAX_ABOUT_LENGTH определён локально (не из config)
#   ✅ Добавлена проверка callback.from_user во всех callback'ах
#   ✅ Совместимость с Python 3.9+ (Union вместо |)
#   ✅ Блокировка повторного входа в анкету
#   ✅ Обработка ошибок БД во всех точках сохранения
#   ✅ Очистка _active_profile_states в finally
#   ✅ Усиленная санитизация ввода (защита от XSS)
# ============================================

import html
import logging
import re
from typing import Optional, Dict, Tuple, Union

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db, DatabaseError
from config import START_BALANCE

router = Router()
logger = logging.getLogger(__name__)


# ==================== КОНСТАНТЫ ====================

# Значения по умолчанию (можно переопределить в config.py)
MAX_ABOUT_LENGTH = 300
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 30
MIN_CITY_LENGTH = 2
MAX_CITY_LENGTH = 30
MIN_AGE = 12
MAX_AGE = 100

# Запрещенные слова (можно вынести в config)
FORBIDDEN_WORDS = [
    'хуй', 'пизда', 'ебать', 'блять', 'сука', 'нахер', 'похуй',
    'залупа', 'жопа', 'говно', 'пидор', 'пидорас', 'гандон',
    'fuck', 'shit', 'ass', 'bitch', 'dick', 'cunt', 'whore',
]


# ==================== FSM ДЛЯ АНКЕТЫ ====================

class ProfileStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_city = State()
    waiting_for_timezone = State()
    waiting_for_about = State()


# Отслеживание активных состояний (для предотвращения утечек)
_active_profile_states: Dict[int, bool] = {}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def sanitize_text(text: Optional[str]) -> str:
    """
    Очистка текста от HTML, JS и лишних пробелов.
    Защита от XSS-инъекций.
    """
    if not text:
        return ""
    
    # Удаление HTML-тегов
    text = re.sub(r'<[^>]+>', '', text)
    # Удаление потенциальных JS-векторов
    text = re.sub(r'(javascript|vbscript|on\w+\s*=)', '', text, flags=re.I)
    # Нормализация пробелов
    text = re.sub(r'\s+', ' ', text)
    # Удаление невидимых символов
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    return text.strip()[:500]  # Жёсткий лимит длины


def contains_forbidden_words(text: Optional[str]) -> bool:
    """Проверка на запрещенные слова."""
    if not text:
        return False
    
    text_lower = text.lower()
    # Удаляем спецсимволы для обхода фильтра
    cleaned_text = re.sub(r'[^а-яa-z0-9]', '', text_lower)
    
    for word in FORBIDDEN_WORDS:
        if word in cleaned_text or word in text_lower:
            return True
    return False


def validate_name(name: Optional[str]) -> Tuple[bool, str]:
    """Валидация имени."""
    if not name or len(name.strip()) < MIN_NAME_LENGTH:
        return False, f"❌ Имя должно быть не короче {MIN_NAME_LENGTH} символов"
    
    if len(name) > MAX_NAME_LENGTH:
        return False, f"❌ Имя должно быть не длиннее {MAX_NAME_LENGTH} символов"
    
    if not re.match(r'^[а-яА-Яa-zA-Z\s\-]+$', name):
        return False, "❌ Имя может содержать только буквы, пробелы и дефис"
    
    if contains_forbidden_words(name):
        return False, "❌ Имя содержит недопустимые слова"
    
    return True, ""


def validate_age(age_str: Optional[str]) -> Tuple[bool, Union[int, str]]:
    """Валидация возраста."""
    if not age_str:
        return False, "❌ Введите возраст"
    
    try:
        age = int(age_str.strip())
    except ValueError:
        return False, "❌ Возраст должен быть числом"
    
    if age < MIN_AGE:
        return False, f"❌ Минимальный возраст: {MIN_AGE} лет"
    
    if age > MAX_AGE:
        return False, f"❌ Максимальный возраст: {MAX_AGE} лет"
    
    return True, age


def validate_city(city: Optional[str]) -> Tuple[bool, str]:
    """Валидация города."""
    if not city or len(city.strip()) < MIN_CITY_LENGTH:
        return False, f"❌ Название города должно быть не короче {MIN_CITY_LENGTH} символов"
    
    if len(city) > MAX_CITY_LENGTH:
        return False, f"❌ Название города должно быть не длиннее {MAX_CITY_LENGTH} символов"
    
    if not re.match(r'^[а-яА-Яa-zA-Z\s\-\.]+$', city):
        return False, "❌ Город может содержать только буквы, пробелы, точку и дефис"
    
    if contains_forbidden_words(city):
        return False, "❌ Название города содержит недопустимые слова"
    
    return True, ""


def validate_timezone(tz: Optional[str]) -> Tuple[bool, str]:
    """Валидация часового пояса."""
    if not tz:
        return False, "❌ Укажите часовой пояс"
    
    tz_upper = tz.upper().strip()
    
    if not re.match(r'^(UTC|GMT)[+-]\d{1,2}(:\d{2})?$', tz_upper):
        return False, "❌ Формат: UTC+3, GMT-5, UTC+5:30"
    
    # Дополнительная проверка диапазона
    try:
        offset = re.search(r'[+-](\d{1,2})(?::(\d{2}))?', tz_upper)
        if offset:
            hours = int(offset.group(1))
            minutes = int(offset.group(2)) if offset.group(2) else 0
            if hours > 14 or (hours == 14 and minutes > 0):
                return False, "❌ Часовой пояс не может быть больше UTC+14"
            if hours < -12:
                return False, "❌ Часовой пояс не может быть меньше UTC-12"
    except:
        pass
    
    return True, tz_upper


def validate_about(about: Optional[str]) -> Tuple[bool, str]:
    """Валидация раздела 'о себе'."""
    if not about or len(about.strip()) < 5:
        return False, "❌ Расскажите о себе подробнее (минимум 5 символов)"
    
    if len(about) > MAX_ABOUT_LENGTH:
        return False, f"❌ Текст не должен превышать {MAX_ABOUT_LENGTH} символов"
    
    if contains_forbidden_words(about):
        return False, "❌ Текст содержит недопустимые слова"
    
    # Проверка на потенциальный код/ссылки
    if re.search(r'(https?://|www\.|\.ru|\.com|\.org)', about.lower()):
        return False, "❌ Ссылки в разделе 'о себе' запрещены"
    
    return True, ""


def get_profile_keyboard(step: Optional[int] = None, can_skip: bool = False) -> InlineKeyboardMarkup:
    """Генерация клавиатуры для анкеты."""
    buttons = []
    
    if can_skip:
        buttons.append([InlineKeyboardButton(text="⏭️ ПРОПУСТИТЬ", callback_data="skip_about")])
    
    cancel_text = f"❌ ОТМЕНА (шаг {step}/5)" if step is not None else "❌ ОТМЕНА"
    buttons.append([InlineKeyboardButton(text=cancel_text, callback_data="cancel_profile")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict]:
    """
    Получить или создать пользователя.
    
    Returns:
        Словарь с данными пользователя или None при ошибке
    """
    if user_id is None:
        return None
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            if user:
                logger.info(f"✅ Created user {user_id} in profile module")
        return user
    except DatabaseError as e:
        logger.error(f"❌ Database error in get_or_create_user: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error in get_or_create_user: {e}")
        return None


async def get_user_xo_stats(user_id: int) -> Tuple[int, int]:
    """Получить статистику XO пользователя."""
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return stats.get('wins', 0) or 0, stats.get('losses', 0) or 0
    except DatabaseError as e:
        logger.error(f"❌ Failed to get XO stats for {user_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting XO stats: {e}")
    
    return 0, 0


# ==================== ПРОСМОТР ПРОФИЛЯ ====================

@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """Показать профиль пользователя."""
    if message is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    if not user:
        await message.answer("❌ Ошибка доступа к базе данных.")
        return
    
    try:
        profile = await db.get_profile(user_id)
        balance = await db.get_balance(user_id)
        wins, losses = await get_user_xo_stats(user_id)
        
        if not profile:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 ЗАПОЛНИТЬ АНКЕТУ", callback_data="fill_profile")],
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
            
            await message.answer(
                "👤 <b>ПРОФИЛЬ</b>\n\n"
                f"💰 Баланс: <b>{balance}</b> NCoin\n"
                f"🎮 XO: {wins} побед | {losses} поражений\n\n"
                "У вас пока нет анкеты.\n"
                "Хотите заполнить?",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return
        
        text = (
            f"👤 <b>АНКЕТА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"📛 Имя: <b>{safe_html_escape(profile.get('full_name', 'Не указано'))}</b>\n"
            f"🎂 Возраст: <b>{profile.get('age', 'Не указано')}</b>\n"
            f"🏙️ Город: <b>{safe_html_escape(profile.get('city', 'Не указано'))}</b>\n"
            f"🌍 Часовой пояс: <b>{safe_html_escape(profile.get('timezone', 'Не указано'))}</b>\n"
            f"📝 О себе: {safe_html_escape(profile.get('about', 'Не указано'))}\n\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"🎮 XO: {wins} побед | {losses} поражений"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ АНКЕТУ", callback_data="fill_profile")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        logger.info(f"✅ Profile viewed by user {user_id}")
        
    except DatabaseError as e:
        logger.error(f"❌ Database error in cmd_profile: {e}")
        await message.answer("❌ Ошибка загрузки профиля.")
    except Exception as e:
        logger.error(f"❌ Unexpected error in cmd_profile: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery) -> None:
    """Callback для профиля."""
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await cmd_profile(callback.message)
    await callback.answer()


# ==================== ЗАПОЛНЕНИЕ АНКЕТЫ ====================

@router.callback_query(F.data == "fill_profile")
async def start_fill_profile(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало заполнения анкеты."""
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    # ✅ Блокировка повторного входа в анкету
    if _active_profile_states.get(user_id):
        await callback.answer("⏳ Анкета уже заполняется. Завершите текущую или отмените.", show_alert=True)
        return
    
    _active_profile_states[user_id] = True
    
    try:
        await state.set_state(ProfileStates.waiting_for_name)
        
        keyboard = get_profile_keyboard(step=1)
        
        await callback.message.edit_text(
            "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
            "Шаг 1 из 5\n\n"
            f"<b>Как вас зовут?</b>\n"
            f"├ Мин. длина: {MIN_NAME_LENGTH} символов\n"
            f"├ Макс. длина: {MAX_NAME_LENGTH} символов\n"
            f"└ Только буквы, пробелы и дефис\n\n"
            "Введите ваше имя:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error starting profile fill: {e}")
        _active_profile_states.pop(user_id, None)
        await callback.answer("❌ Ошибка начала заполнения анкеты", show_alert=True)


@router.message(ProfileStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext) -> None:
    """Обработка имени."""
    if message is None or message.text is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    name = sanitize_text(message.text)
    is_valid, error_msg = validate_name(name)
    
    if not is_valid:
        await message.answer(
            f"{safe_html_escape(error_msg)}\n\nПопробуйте ещё раз:",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await state.update_data(full_name=name)
        await state.set_state(ProfileStates.waiting_for_age)
        
        keyboard = get_profile_keyboard(step=2)
        
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
    except Exception as e:
        logger.error(f"❌ Error processing name for {user_id}: {e}")
        await message.answer("❌ Ошибка. Попробуйте ещё раз.")


@router.message(ProfileStates.waiting_for_age)
async def process_age(message: Message, state: FSMContext) -> None:
    """Обработка возраста."""
    if message is None or message.text is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    is_valid, result = validate_age(message.text)
    
    if not is_valid:
        error_msg = str(result) if isinstance(result, str) else "❌ Ошибка валидации"
        await message.answer(
            f"{safe_html_escape(error_msg)}\n\nПопробуйте ещё раз:",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await state.update_data(age=result)
        await state.set_state(ProfileStates.waiting_for_city)
        
        keyboard = get_profile_keyboard(step=3)
        
        await message.answer(
            "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
            "Шаг 3 из 5\n\n"
            f"<b>Из какого вы города?</b>\n"
            f"├ Мин. длина: {MIN_CITY_LENGTH} символов\n"
            f"└ Только буквы, пробелы, точка и дефис\n\n"
            "Введите ваш город:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"❌ Error processing age for {user_id}: {e}")
        await message.answer("❌ Ошибка. Попробуйте ещё раз.")


@router.message(ProfileStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext) -> None:
    """Обработка города."""
    if message is None or message.text is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    city = sanitize_text(message.text)
    is_valid, error_msg = validate_city(city)
    
    if not is_valid:
        await message.answer(
            f"{safe_html_escape(error_msg)}\n\nПопробуйте ещё раз:",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await state.update_data(city=city)
        await state.set_state(ProfileStates.waiting_for_timezone)
        
        keyboard = get_profile_keyboard(step=4)
        
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
    except Exception as e:
        logger.error(f"❌ Error processing city for {user_id}: {e}")
        await message.answer("❌ Ошибка. Попробуйте ещё раз.")


@router.message(ProfileStates.waiting_for_timezone)
async def process_timezone(message: Message, state: FSMContext) -> None:
    """Обработка часового пояса."""
    if message is None or message.text is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    tz = message.text.strip()
    is_valid, result = validate_timezone(tz)
    
    if not is_valid:
        error_msg = str(result) if isinstance(result, str) else "❌ Ошибка валидации"
        await message.answer(
            f"{safe_html_escape(error_msg)}\n\nПопробуйте ещё раз:",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await state.update_data(timezone=result)
        await state.set_state(ProfileStates.waiting_for_about)
        
        keyboard = get_profile_keyboard(step=5, can_skip=True)
        
        await message.answer(
            "📝 <b>ЗАПОЛНЕНИЕ АНКЕТЫ</b>\n"
            "Шаг 5 из 5 (последний!)\n\n"
            f"<b>Расскажите немного о себе:</b>\n"
            f"├ Мин. длина: 5 символов\n"
            f"├ Макс. длина: {MAX_ABOUT_LENGTH} символов\n"
            f"└ Без нецензурных слов и ссылок\n\n"
            "Пример: Люблю игры, программирование и путешествовать",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"❌ Error processing timezone for {user_id}: {e}")
        await message.answer("❌ Ошибка. Попробуйте ещё раз.")


@router.message(ProfileStates.waiting_for_about)
async def process_about(message: Message, state: FSMContext) -> None:
    """Обработка раздела 'о себе'."""
    if message is None or message.text is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    about = sanitize_text(message.text)
    is_valid, error_msg = validate_about(about)
    
    if not is_valid:
        await message.answer(
            f"{safe_html_escape(error_msg)}\n\nПопробуйте ещё раз или нажмите 'ПРОПУСТИТЬ':",
            parse_mode=ParseMode.HTML,
            reply_markup=get_profile_keyboard(step=5, can_skip=True)
        )
        return
    
    try:
        await _save_profile_safe(message, state, about, user_id)
    except Exception as e:
        logger.error(f"❌ Error saving profile for {user_id}: {e}")
        await message.answer("❌ Ошибка сохранения. Попробуйте позже.")


@router.callback_query(F.data == "skip_about")
async def skip_about(callback: CallbackQuery, state: FSMContext) -> None:
    """Пропустить раздел 'о себе'."""
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    try:
        await _save_profile_safe(callback.message, state, "", user_id)
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Error skipping about for {user_id}: {e}")
        await callback.answer("❌ Ошибка. Попробуйте позже.", show_alert=True)


async def _save_profile_safe(
    event: Union[Message, CallbackQuery],
    state: FSMContext,
    about: str,
    user_id: int
) -> None:
    """Внутренняя функция сохранения профиля с гарантированной очисткой состояния."""
    message = event if isinstance(event, Message) else event.message
    
    if message is None:
        return
    
    try:
        data = await state.get_data()
        
        full_name = sanitize_text(data.get('full_name', ''))
        age = data.get('age', 0)
        city = sanitize_text(data.get('city', ''))
        timezone = data.get('timezone', 'UTC+3')
        about_text = sanitize_text(about) if about else sanitize_text(data.get('about', ''))
        
        # Сохранение в БД
        await db.save_profile(user_id, full_name, age, city, timezone, about_text)
        
        # Получение актуального баланса
        balance = await db.get_balance(user_id)
        
        # Формирование ответа
        text = (
            f"✅ <b>АНКЕТА СОХРАНЕНА!</b>\n\n"
            f"📛 Имя: <b>{safe_html_escape(full_name)}</b>\n"
            f"🎂 Возраст: <b>{age}</b>\n"
            f"🏙️ Город: <b>{safe_html_escape(city)}</b>\n"
            f"🌍 Часовой пояс: <b>{safe_html_escape(timezone)}</b>\n"
            f"📝 О себе: {safe_html_escape(about_text) if about_text else '<i>не указано</i>'}\n\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n\n"
            f"Используйте /profile для просмотра анкеты"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
        ])
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        logger.info(f"✅ Profile saved for user {user_id}")
        
    except DatabaseError as e:
        logger.error(f"❌ Database error saving profile for {user_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error saving profile for {user_id}: {e}")
        raise
    finally:
        # ✅ Гарантированная очистка состояния в любом случае
        _active_profile_states.pop(user_id, None)
        await state.clear()


@router.callback_query(F.data == "cancel_profile")
async def cancel_profile(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена заполнения анкеты."""
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    try:
        _active_profile_states.pop(user_id, None)
        await state.clear()
        
        await callback.message.edit_text(
            "❌ Заполнение анкеты отменено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
        logger.info(f"✅ Profile fill cancelled by user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error cancelling profile for {user_id}: {e}")
    finally:
        await callback.answer()


@router.message(Command("cancel_profile"))
async def cmd_cancel_profile(message: Message, state: FSMContext) -> None:
    """Команда отмены заполнения анкеты."""
    if message is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    
    try:
        _active_profile_states.pop(user_id, None)
        await state.clear()
        await message.answer("❌ Заполнение анкеты отменено.")
        logger.info(f"✅ Profile fill cancelled via command by user {user_id}")
    except Exception as e:
        logger.error(f"❌ Error cancelling profile via command: {e}")


# ==================== СТАТИСТИКА ====================

@router.callback_query(F.data == "my_stats")
async def my_stats_callback(callback: CallbackQuery) -> None:
    """Показать статистику пользователя."""
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    if not user:
        await callback.answer("❌ Ошибка загрузки", show_alert=True)
        return
    
    try:
        balance = await db.get_balance(user_id)
        wins, losses = await get_user_xo_stats(user_id)
        
        stats = await db.get_user_stats(user_id)
        
        games_played = stats.get('games_played', 0) if stats else 0
        winrate = (wins / games_played * 100) if games_played > 0 else 0
        
        first_name = safe_html_escape(user.get('first_name', 'Не указано'))
        vip_level = user.get('vip_level', 0) or 0
        
        text = (
            f"📊 <b>ВАША СТАТИСТИКА</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Имя: {first_name}\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"⭐ VIP: {vip_level} уровень\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>🎮 КРЕСТИКИ-НОЛИКИ:</b>\n"
            f"├ Игр: {games_played}\n"
            f"├ Побед: {wins}\n"
            f"├ Поражений: {losses}\n"
            f"└ Винрейт: <b>{winrate:.1f}%</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 <i>Играйте больше, чтобы повысить статистику!</i>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await callback.answer()
        logger.info(f"✅ Stats viewed by user {user_id}")
        
    except DatabaseError as e:
        logger.error(f"❌ Database error in my_stats: {e}")
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)
    except Exception as e:
        logger.error(f"❌ Unexpected error in my_stats: {e}")
        await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
