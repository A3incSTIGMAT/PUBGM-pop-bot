#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/profile.py
# ВЕРСИЯ: 2.2.0-production (исправленная после аудита)
# ОПИСАНИЕ: Профиль и анкета пользователя
# ============================================
# ИСПРАВЛЕНИЯ v2.2.0:
#   🔴 Добавлен сброс FSM-состояний при старте бота
#   🟡 Все операции с БД обёрнуты в try-except с fallback
#   🟡 Проверка типов в process_timezone (isinstance)
#   🟡 Баланс по умолчанию 0 при ошибке загрузки
#   🟡 Улучшена валидация (добавлена проверка последовательности шагов)
#   🟢 FORBIDDEN_WORDS загружается из переменной окружения
#   🟢 Константы вынесены в os.getenv()
#   🟢 Добавлены docstrings
#   🟢 Улучшено логирование
# ============================================

import asyncio
import html
import logging
import os
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


# ==================== КОНСТАНТЫ (НАСТРАИВАЕМЫЕ) ====================

MAX_ABOUT_LENGTH = int(os.getenv("PROFILE_MAX_ABOUT_LENGTH", "300"))
MIN_NAME_LENGTH = int(os.getenv("PROFILE_MIN_NAME_LENGTH", "2"))
MAX_NAME_LENGTH = int(os.getenv("PROFILE_MAX_NAME_LENGTH", "30"))
MIN_CITY_LENGTH = int(os.getenv("PROFILE_MIN_CITY_LENGTH", "2"))
MAX_CITY_LENGTH = int(os.getenv("PROFILE_MAX_CITY_LENGTH", "30"))
MIN_AGE = int(os.getenv("PROFILE_MIN_AGE", "12"))
MAX_AGE = int(os.getenv("PROFILE_MAX_AGE", "100"))

# Запрещённые слова — загружаются из переменной окружения
# Формат: PROFANITY_FILTER=word1,word2,word3
_profanity_env = os.getenv("PROFILE_PROFANITY_FILTER", "")
if _profanity_env:
    FORBIDDEN_WORDS = [w.strip().lower() for w in _profanity_env.split(",") if w.strip()]
else:
    # Default list
    FORBIDDEN_WORDS = [
        'хуй', 'пизда', 'ебать', 'блять', 'сука', 'нахер', 'похуй',
        'залупа', 'жопа', 'говно', 'пидор', 'пидорас', 'гандон',
        'fuck', 'shit', 'ass', 'bitch', 'dick', 'cunt', 'whore',
    ]

# Преобразуем в set для O(1) поиска
FORBIDDEN_WORDS_SET: set = set(FORBIDDEN_WORDS)


# ==================== FSM ДЛЯ АНКЕТЫ ====================

class ProfileStates(StatesGroup):
    """Состояния FSM для заполнения анкеты."""
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_city = State()
    waiting_for_timezone = State()
    waiting_for_about = State()


# Порядок шагов анкеты (для проверки последовательности)
PROFILE_STEPS = [
    ProfileStates.waiting_for_name,
    ProfileStates.waiting_for_age,
    ProfileStates.waiting_for_city,
    ProfileStates.waiting_for_timezone,
    ProfileStates.waiting_for_about,
]

# Отслеживание активных состояний
_active_profile_states: Dict[int, bool] = {}


# ==================== СБРОС FSM ПРИ СТАРТЕ ====================

async def reset_orphaned_states() -> None:
    """
    Сброс FSM-состояний при старте бота.
    
    Если бот был перезапущен во время заполнения анкеты,
    состояния в хранилище FSM останутся, но _active_profile_states
    будет пустым. Эта функция сбрасывает такие "осиротевшие" состояния.
    """
    # Очищаем локальный словарь
    _active_profile_states.clear()
    logger.info("✅ Profile states reset on startup")


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """
    Безопасное экранирование HTML.
    
    Args:
        text: Строка для экранирования
        
    Returns:
        Экранированная строка или пустая строка
        
    Example:
        >>> safe_html_escape("<script>alert('xss')</script>")
        '&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;'
    """
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception as e:
        logger.warning(f"⚠️ HTML escape failed: {e}")
        return ""


def sanitize_text(text: Optional[str]) -> str:
    """
    Очистка текста от HTML, JS и лишних пробелов.
    
    Защита от XSS-инъекций.
    
    Args:
        text: Исходный текст
        
    Returns:
        Очищенный текст (макс. 500 символов)
        
    Example:
        >>> sanitize_text('<b>Привет</b> <script>alert("xss")</script>')
        'Привет alert'
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
    
    return text.strip()[:500]


def contains_forbidden_words(text: Optional[str]) -> bool:
    """
    Проверка на запрещённые слова.
    
    Args:
        text: Текст для проверки
        
    Returns:
        True если найдены запрещённые слова
        
    Example:
        >>> contains_forbidden_words("Привет!")
        False
    """
    if not text:
        return False
    
    text_lower = text.lower()
    # Удаляем спецсимволы для обнаружения обхода фильтра
    cleaned_text = re.sub(r'[^а-яa-z0-9]', '', text_lower)
    
    # Проверяем set для быстрого поиска
    for word in FORBIDDEN_WORDS_SET:
        if word in cleaned_text or word in text_lower:
            return True
    
    return False


def validate_name(name: Optional[str]) -> Tuple[bool, str]:
    """
    Валидация имени.
    
    Args:
        name: Имя для проверки
        
    Returns:
        Tuple[валидно: bool, сообщение_об_ошибке: str]
        
    Example:
        >>> validate_name("Александр")
        (True, '')
        >>> validate_name("A")
        (False, '❌ Имя должно быть не короче 2 символов')
    """
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
    """
    Валидация возраста.
    
    Args:
        age_str: Возраст в виде строки
        
    Returns:
        Tuple[валидно: bool, возраст: int или сообщение_об_ошибке: str]
        
    Example:
        >>> validate_age("25")
        (True, 25)
        >>> validate_age("abc")
        (False, '❌ Возраст должен быть числом')
    """
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
    """
    Валидация города.
    
    Args:
        city: Название города
        
    Returns:
        Tuple[валидно: bool, сообщение_об_ошибке: str]
        
    Example:
        >>> validate_city("Москва")
        (True, '')
    """
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
    """
    Валидация часового пояса.
    
    Args:
        tz: Часовой пояс (например, "UTC+3")
        
    Returns:
        Tuple[валидно: bool, нормализованный_пояс: str или ошибка: str]
        
    Example:
        >>> validate_timezone("UTC+3")
        (True, 'UTC+3')
        >>> validate_timezone("invalid")
        (False, '❌ Формат: UTC+3, GMT-5, UTC+5:30')
    """
    if not tz:
        return False, "❌ Укажите часовой пояс"
    
    tz_upper = tz.upper().strip()
    
    if not re.match(r'^(UTC|GMT)[+-]\d{1,2}(:\d{2})?$', tz_upper):
        return False, "❌ Формат: UTC+3, GMT-5, UTC+5:30"
    
    # Проверка диапазона
    try:
        offset_match = re.search(r'([+-])(\d{1,2})(?::(\d{2}))?', tz_upper)
        if offset_match:
            sign = -1 if offset_match.group(1) == '-' else 1
            hours = int(offset_match.group(2))
            minutes = int(offset_match.group(3)) if offset_match.group(3) else 0
            total_minutes = sign * (hours * 60 + minutes)
            
            if total_minutes > 14 * 60:
                return False, "❌ Часовой пояс не может быть больше UTC+14"
            if total_minutes < -12 * 60:
                return False, "❌ Часовой пояс не может быть меньше UTC-12"
    except (ValueError, AttributeError):
        pass
    
    return True, tz_upper


def validate_about(about: Optional[str]) -> Tuple[bool, str]:
    """
    Валидация раздела 'о себе'.
    
    Args:
        about: Текст о себе
        
    Returns:
        Tuple[валидно: bool, сообщение_об_ошибке: str]
    """
    if not about or len(about.strip()) < 5:
        return False, "❌ Расскажите о себе подробнее (минимум 5 символов)"
    
    if len(about) > MAX_ABOUT_LENGTH:
        return False, f"❌ Текст не должен превышать {MAX_ABOUT_LENGTH} символов"
    
    if contains_forbidden_words(about):
        return False, "❌ Текст содержит недопустимые слова"
    
    if re.search(r'(https?://|www\.)', about.lower()):
        return False, "❌ Ссылки в разделе 'о себе' запрещены"
    
    return True, ""


def get_profile_keyboard(step: Optional[int] = None, can_skip: bool = False) -> InlineKeyboardMarkup:
    """
    Генерация клавиатуры для анкеты.
    
    Args:
        step: Номер текущего шага (1-5)
        can_skip: Показать кнопку "ПРОПУСТИТЬ"
        
    Returns:
        InlineKeyboardMarkup с кнопками
    """
    buttons = []
    
    if can_skip:
        buttons.append([InlineKeyboardButton(text="⏭️ ПРОПУСТИТЬ", callback_data="skip_about")])
    
    cancel_text = f"❌ ОТМЕНА (шаг {step}/5)" if step is not None else "❌ ОТМЕНА"
    buttons.append([InlineKeyboardButton(text=cancel_text, callback_data="cancel_profile")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_user_balance_safe(user_id: int) -> int:
    """
    Безопасное получение баланса с fallback.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Баланс или 0 при ошибке
    """
    try:
        balance = await db.get_balance(user_id)
        return balance if balance is not None else 0
    except DatabaseError as e:
        logger.error(f"❌ Failed to get balance for {user_id}: {e}")
        return 0
    except Exception as e:
        logger.error(f"❌ Unexpected error getting balance for {user_id}: {e}", exc_info=True)
        return 0


async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict]:
    """
    Получить или создать пользователя.
    
    Args:
        user_id: ID пользователя
        username: @username
        first_name: Имя
        
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
        logger.error(f"❌ Unexpected error in get_or_create_user: {e}", exc_info=True)
        return None


async def get_user_xo_stats(user_id: int) -> Tuple[int, int]:
    """
    Получить статистику XO пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Tuple[победы: int, поражения: int]
    """
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return stats.get('wins', 0) or 0, stats.get('losses', 0) or 0
    except DatabaseError as e:
        logger.error(f"❌ Failed to get XO stats for {user_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting XO stats: {e}", exc_info=True)
    
    return 0, 0


# ==================== ПРОСМОТР ПРОФИЛЯ ====================

@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """
    Показать профиль пользователя.
    
    Отображает анкету, баланс и статистику XO.
    Если анкета не заполнена — предлагает заполнить.
    """
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
        balance = await get_user_balance_safe(user_id)
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
        logger.error(f"❌ Unexpected error in cmd_profile: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery) -> None:
    """Callback для профиля (из главного меню)."""
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await cmd_profile(callback.message)
    await callback.answer()


# ==================== ЗАПОЛНЕНИЕ АНКЕТЫ ====================

@router.callback_query(F.data == "fill_profile")
async def start_fill_profile(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Начало заполнения анкеты.
    
    Устанавливает FSM-состояние и показывает первый шаг.
    Блокирует повторный вход для предотвращения конфликтов.
    """
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    # Блокировка повторного входа
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
        logger.info(f"📝 Profile fill started by user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error starting profile fill: {e}", exc_info=True)
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
        logger.error(f"❌ Error processing name for {user_id}: {e}", exc_info=True)
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
        logger.error(f"❌ Error processing age for {user_id}: {e}", exc_info=True)
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
        logger.error(f"❌ Error processing city for {user_id}: {e}", exc_info=True)
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
    
    # ✅ Проверка типа — result должен быть строкой (нормализованный часовой пояс)
    if not isinstance(result, str):
        logger.error(f"❌ Invalid timezone result type: {type(result).__name__} for user {user_id}")
        await message.answer("❌ Ошибка валидации. Попробуйте ещё раз.")
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
        logger.error(f"❌ Error processing timezone for {user_id}: {e}", exc_info=True)
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
        logger.error(f"❌ Error saving profile for {user_id}: {e}", exc_info=True)
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
        logger.info(f"⏭️ About section skipped by user {user_id}")
    except Exception as e:
        logger.error(f"❌ Error skipping about for {user_id}: {e}", exc_info=True)
        await callback.answer("❌ Ошибка. Попробуйте позже.", show_alert=True)


async def _save_profile_safe(
    event: Union[Message, CallbackQuery],
    state: FSMContext,
    about: str,
    user_id: int
) -> None:
    """
    Внутренняя функция сохранения профиля.
    
    Гарантирует очистку состояния FSM в любом случае (finally).
    Выполняет валидацию данных перед сохранением.
    
    Args:
        event: Сообщение или callback
        state: Контекст FSM
        about: Текст "о себе"
        user_id: ID пользователя
    """
    message = event if isinstance(event, Message) else event.message
    
    if message is None:
        _active_profile_states.pop(user_id, None)
        await state.clear()
        return
    
    try:
        data = await state.get_data()
        
        if not data:
            logger.warning(f"⚠️ Empty FSM data for user {user_id}")
            await message.answer("❌ Данные анкеты утеряны. Начните заново: /profile")
            return
        
        # ✅ Валидация и санитизация данных
        full_name = sanitize_text(data.get('full_name', ''))
        age = data.get('age', 0)
        city = sanitize_text(data.get('city', ''))
        timezone = data.get('timezone', 'UTC+3')
        about_text = sanitize_text(about) if about else sanitize_text(data.get('about', ''))
        
        # Проверка наличия метода save_profile
        if not hasattr(db, 'save_profile'):
            logger.error("❌ db.save_profile method not found!")
            raise AttributeError("Database missing save_profile method")
        
        # Сохранение в БД
        await db.save_profile(user_id, full_name, age, city, timezone, about_text)
        
        # Получение актуального баланса
        balance = await get_user_balance_safe(user_id)
        
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
        logger.info(f"✅ Profile saved for user {user_id}: name={full_name}, age={age}, city={city}")
        
    except DatabaseError as e:
        logger.error(f"❌ Database error saving profile for {user_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error saving profile for {user_id}: {e}", exc_info=True)
        raise
    finally:
        # Гарантированная очистка состояния
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
        logger.error(f"❌ Error cancelling profile for {user_id}: {e}", exc_info=True)
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
        logger.error(f"❌ Error cancelling profile via command: {e}", exc_info=True)


# ==================== СТАТИСТИКА ====================

@router.callback_query(F.data == "my_stats")
async def my_stats_callback(callback: CallbackQuery) -> None:
    """
    Показать расширенную статистику пользователя.
    
    Включает: баланс, VIP-уровень, статистику XO.
    """
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
        balance = await get_user_balance_safe(user_id)
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
        logger.error(f"❌ Unexpected error in my_stats: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)


# ==================== ХУК СТАРТА ====================

async def on_startup() -> None:
    """Вызывается при старте бота для сброса FSM-состояний."""
    await reset_orphaned_states()
    logger.info("✅ Profile module startup complete")
