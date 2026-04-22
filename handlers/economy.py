#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/economy.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Модуль экономики — баланс, daily, переводы, донат
# ИСПРАВЛЕНИЯ: Защита от NULL, FSM с таймаутом, безопасный парсинг callback
# ============================================

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from database import db, DatabaseError
from config import (
    START_BALANCE, ADMIN_IDS, SUPER_ADMIN_IDS,
    DONATE_URL, DONATE_BANK, DONATE_RECEIVER
)
from utils.keyboards import back_button, finance_category_menu

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

# Таймаут для FSM состояний (5 минут)
FSM_TIMEOUT = 300

# Минимальная сумма перевода
MIN_TRANSFER = 10

# Минимальная сумма доната
MIN_DONATE = 10

# Курс доната (1 RUB = 10 NCoin)
DONATE_RATE = 10

# Бонусы за крупные суммы (порог: бонус)
DONATE_BONUSES = {
    10000: 30000,
    5000: 15000,
    2000: 5000,
    1000: 2000,
    500: 800,
    200: 300,
    100: 100,
    50: 30,
}

# Кэш для rate limiting daily
_daily_cache: Dict[int, float] = {}
DAILY_RATE_LIMIT = 5  # секунд между запросами


# ==================== FSM ДЛЯ ДОНАТА ====================

class DonateState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_proof = State()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        import html
        return html.escape(str(text))
    except Exception:
        return ""


def format_number(num: Any) -> str:
    """Форматирование числа с разделителями."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def calculate_donate_coins(amount_rub: int) -> int:
    """
    Автоматический расчёт NCoin за любую сумму.
    
    Args:
        amount_rub: Сумма в рублях
        
    Returns:
        Количество NCoin
    """
    if amount_rub is None or amount_rub <= 0:
        return 0
    
    base_coins = amount_rub * DONATE_RATE
    bonus = 0
    
    for threshold, bonus_amount in sorted(DONATE_BONUSES.items(), reverse=True):
        if amount_rub >= threshold:
            bonus = bonus_amount
            break
    
    return base_coins + bonus


async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict]:
    """
    Получить или создать пользователя с защитой от ошибок БД.
    
    Args:
        user_id: ID пользователя
        username: Username
        first_name: Имя
        
    Returns:
        Словарь с данными пользователя или None при ошибке
    """
    if user_id is None:
        logger.warning("get_or_create_user called with None user_id")
        return None
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            logger.info(f"Created new user: {user_id}")
        return user
    except DatabaseError as e:
        logger.error(f"Database error in get_or_create_user: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_or_create_user: {e}")
        return None


async def check_daily_rate_limit(user_id: int) -> bool:
    """
    Проверка rate limiting для daily.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        True если запрос разрешен, False если слишком часто
    """
    now = datetime.now().timestamp()
    last_request = _daily_cache.get(user_id, 0)
    
    if now - last_request < DAILY_RATE_LIMIT:
        return False
    
    _daily_cache[user_id] = now
    return True


def parse_donate_callback(data: str) -> Optional[Dict[str, int]]:
    """
    Безопасный парсинг callback_data для доната.
    
    Args:
        data: Строка callback_data
        
    Returns:
        Словарь с user_id, amount_rub, coins или None при ошибке
    """
    # Формат: confirm_donate_USERID_AMOUNT_COINS
    parts = data.split("_")
    
    if len(parts) < 5 or parts[0] != "confirm" or parts[1] != "donate":
        return None
    
    try:
        return {
            "user_id": int(parts[2]),
            "amount_rub": int(parts[3]),
            "coins": int(parts[4])
        }
    except (ValueError, IndexError):
        return None


# ==================== КОМАНДА /balance ====================

@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    """Показать баланс пользователя."""
    if message is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    if not user:
        await message.answer("❌ Ошибка доступа к базе данных. Попробуйте позже.")
        return
    
    try:
        balance = await db.get_balance(user_id)
        xo_stats = await db.get_user_stats(user_id)
        
        xo_wins = xo_stats.get('wins', 0) if xo_stats else 0
        xo_losses = xo_stats.get('losses', 0) if xo_stats else 0
        xo_games = xo_stats.get('games_played', 0) if xo_stats else 0
        
        text = (
            f"💰 <b>ВАШ БАЛАНС</b>\n\n"
            f"└ <b>{format_number(balance)}</b> NCoin\n\n"
            f"🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>\n"
            f"├ Игр: {format_number(xo_games)}\n"
            f"├ Побед: {format_number(xo_wins)}\n"
            f"└ Поражений: {format_number(xo_losses)}"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except DatabaseError as e:
        logger.error(f"Database error in cmd_balance: {e}")
        await message.answer("❌ Ошибка при получении баланса.")
    except Exception as e:
        logger.error(f"Unexpected error in cmd_balance: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "balance")
async def balance_callback(callback: CallbackQuery) -> None:
    """Callback для показа баланса."""
    if callback is None or callback.message is None:
        return
    
    user_id = callback.from_user.id
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    if not user:
        await callback.answer("❌ Ошибка доступа к БД", show_alert=True)
        return
    
    try:
        balance = await db.get_balance(user_id)
        xo_stats = await db.get_user_stats(user_id)
        
        xo_wins = xo_stats.get('wins', 0) if xo_stats else 0
        xo_losses = xo_stats.get('losses', 0) if xo_stats else 0
        xo_games = xo_stats.get('games_played', 0) if xo_stats else 0
        
        winrate = (xo_wins / xo_games * 100) if xo_games > 0 else 0
        
        text = (
            f"💰 <b>ВАШ БАЛАНС</b>\n\n"
            f"└ <b>{format_number(balance)}</b> NCoin\n\n"
            f"🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>\n"
            f"├ Игр: {format_number(xo_games)}\n"
            f"├ Побед: {format_number(xo_wins)}\n"
            f"├ Поражений: {format_number(xo_losses)}\n"
            f"└ Винрейт: <b>{winrate:.1f}%</b>\n\n"
            f"💡 <i>Используйте /daily для получения бонуса!</i>"
        )
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_button()
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in balance_callback: {e}")
        await callback.answer("❌ Ошибка БД", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in balance_callback: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== КОМАНДА /daily ====================

@router.message(Command("daily"))
async def cmd_daily(message: Message) -> None:
    """Ежедневный бонус."""
    if message is None or message.from_user is None:
        return
    
    user_id = message.from_user.id
    
    # Rate limiting
    if not await check_daily_rate_limit(user_id):
        await message.answer("⏰ Пожалуйста, не так часто! Подождите немного.")
        return
    
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    if not user:
        await message.answer("❌ Ошибка регистрации. Используйте /start")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    
    if last_daily == today:
        await message.answer(
            f"⏰ <b>БОНУС УЖЕ ПОЛУЧЕН!</b>\n\n"
            f"🔥 Стрик: <b>{user.get('daily_streak', 0) or 0}</b> дней\n"
            f"⏰ Следующий бонус: <b>завтра</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        streak = user.get("daily_streak", 0) or 0
        
        if last_daily:
            try:
                last_date = datetime.strptime(last_daily, "%Y-%m-%d").date()
                yesterday = datetime.now().date() - timedelta(days=1)
                streak = streak + 1 if last_date == yesterday else 1
            except (ValueError, TypeError):
                streak = 1
        else:
            streak = 1
        
        base_bonus = 100 + (streak * 50)
        vip_level = user.get("vip_level", 0) or 0
        vip_bonus = vip_level * 50 if vip_level > 0 else 0
        total_bonus = base_bonus + vip_bonus
        
        # Проверяем наличие метода
        if hasattr(db, 'claim_daily_bonus'):
            result = await db.claim_daily_bonus(
                user_id, total_bonus, streak, today, "Ежедневный бонус"
            )
            if not result.get("success", False):
                raise DatabaseError("Failed to claim daily bonus")
            new_balance = result.get("new_balance", 0)
        else:
            # Fallback для старой версии
            await db.update_balance(user_id, total_bonus, "Ежедневный бонус")
            await db.update_daily_streak(user_id, streak)
            new_balance = await db.get_balance(user_id)
        
        # Эмодзи для стрика
        if streak >= 30:
            emoji = "🔥🔥🔥"
        elif streak >= 7:
            emoji = "🔥🔥"
        elif streak >= 3:
            emoji = "🔥"
        else:
            emoji = "⭐"
        
        text = (
            f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС ПОЛУЧЕН!</b>\n\n"
            f"💰 Начислено: <b>+{format_number(total_bonus)} NCoin</b>\n"
        )
        
        if vip_bonus > 0:
            text += f"   ├ Базовый: {format_number(base_bonus)} NCoin\n"
            text += f"   └ VIP бонус: +{format_number(vip_bonus)} NCoin\n"
        
        text += (
            f"\n{emoji} Стрик: <b>{streak}</b> дней\n"
            f"💎 Новый баланс: <b>{format_number(new_balance)} NCoin</b>"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        logger.info(f"Daily claimed: user={user_id}, bonus={total_bonus}, streak={streak}")
        
    except DatabaseError as e:
        logger.error(f"Database error in daily: {e}")
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Unexpected error in daily: {e}", exc_info=True)
        await message.answer("❌ Ошибка при начислении бонуса. Попробуйте позже.")


@router.callback_query(F.data == "daily")
async def daily_callback(callback: CallbackQuery) -> None:
    """Callback для daily."""
    if callback is None:
        return
    
    if callback.message:
        await cmd_daily(callback.message)
    await callback.answer()


# ==================== КОМАНДА /transfer ====================

@router.message(Command("transfer"))
async def cmd_transfer(message: Message) -> None:
    """Перевод монет другому пользователю."""
    if message is None or message.text is None or message.from_user is None:
        return
    
    # Парсинг аргументов
    args = message.text.strip().split()
    if len(args) != 3:
        await message.answer(
            "❌ Использование: <code>/transfer @username 100</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    target_username = args[1].lstrip("@")
    
    # Валидация username
    if not re.match(r'^[a-zA-Z0-9_]{3,32}$', target_username):
        await message.answer("❌ Некорректный username!")
        return
    
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть целым числом!")
        return
    
    if amount < MIN_TRANSFER:
        await message.answer(f"❌ Минимальная сумма перевода: {MIN_TRANSFER} NCoin")
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
        balance = await db.get_balance(user_id)
        
        if balance < amount:
            await message.answer(
                f"❌ Недостаточно средств!\n"
                f"Ваш баланс: {format_number(balance)} NCoin"
            )
            return
        
        # Проверяем, что не самому себе
        if target_username.lower() == (message.from_user.username or "").lower():
            await message.answer("❌ Нельзя перевести самому себе!")
            return
        
        success = await db.transfer_coins(user_id, target_username, amount, "transfer")
        
        if not success:
            await message.answer(f"❌ Пользователь @{target_username} не найден!")
            return
        
        new_balance = await db.get_balance(user_id)
        
        await message.answer(
            f"✅ <b>ПЕРЕВОД ВЫПОЛНЕН!</b>\n\n"
            f"📤 Отправлено: {format_number(amount)} NCoin\n"
            f"📥 Получатель: @{safe_html_escape(target_username)}\n"
            f"💰 Новый баланс: {format_number(new_balance)} NCoin",
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Transfer: {user_id} -> @{target_username}, amount={amount}")
        
    except DatabaseError as e:
        logger.error(f"Database error in transfer: {e}")
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Unexpected error in transfer: {e}")
        await message.answer("❌ Произошла ошибка при переводе.")


# ==================== ДОНАТ ====================

@router.message(Command("donate"))
async def cmd_donate(message: Message) -> None:
    """Главное меню доната."""
    if message is None:
        return
    
    # Проверяем наличие конфигурации
    if not DONATE_URL:
        await message.answer("❌ Донат временно недоступен.")
        return
    
    text = (
        "❤️ <b>ПОДДЕРЖКА ПРОЕКТА NEXUS</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>⚠️ ВАЖНО:</b>\n"
        "Все функции бота <b>АБСОЛЮТНО БЕСПЛАТНЫ</b>!\n"
        "Донат — это добровольная поддержка.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎁 АВТОМАТИЧЕСКИЙ РАСЧЁТ:</b>\n"
        f"• 1 ₽ = {DONATE_RATE} NCoin\n"
        "• Бонусы за крупные суммы!\n\n"
        "<b>📊 ПРИМЕРЫ:</b>\n"
    )
    
    # Примеры расчёта
    examples = [10, 50, 100, 500, 1000, 5000]
    for amount in examples:
        coins = calculate_donate_coins(amount)
        text += f"├ {amount} ₽ → {coins} NCoin\n"
    text += "└ ... и больше!\n\n"
    
    text += (
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>Выберите действие:</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 ВЫБРАТЬ СУММУ", callback_data="donate_select_amount")],
        [InlineKeyboardButton(text="💰 ВВЕСТИ СВОЮ СУММУ", callback_data="donate_custom_amount")],
        [InlineKeyboardButton(text="💳 РЕКВИЗИТЫ СБП", callback_data="donate_sbp")],
        [InlineKeyboardButton(text="📋 КАК ПОЛУЧИТЬ NCOINS", callback_data="donate_help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data == "donate_menu")
async def donate_menu_callback(callback: CallbackQuery) -> None:
    """Callback для меню доната."""
    if callback is None or callback.message is None:
        return
    
    # Конвертируем callback.message в Message для cmd_donate
    await cmd_donate(callback.message)
    await callback.answer()


@router.callback_query(F.data == "donate_select_amount")
async def donate_select_amount(callback: CallbackQuery) -> None:
    """Выбор из фиксированных сумм."""
    if callback is None or callback.message is None:
        return
    
    text = (
        "💎 <b>ВЫБЕРИТЕ СУММУ ДОНАТА</b>\n\n"
        "Нажмите на сумму ниже:\n\n"
        "💰 <i>После выбора вам нужно будет прикрепить скриншот</i>"
    )
    
    # Генерируем кнопки из DONATE_BONUSES
    amounts = [10, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
    keyboard_rows = []
    
    for amount in amounts:
        coins = calculate_donate_coins(amount)
        keyboard_rows.append([
            InlineKeyboardButton(
                text=f"{amount} ₽ → {coins} NCoin",
                callback_data=f"donate_fixed_{amount}"
            )
        ])
    
    keyboard_rows.append([
        InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate_menu")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("donate_fixed_"))
async def donate_fixed_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал фиксированную сумму."""
    if callback is None:
        return
    
    try:
        amount = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    
    await _process_donate_amount(callback.message, state, amount)
    await callback.answer()


@router.callback_query(F.data == "donate_custom_amount")
async def donate_custom_amount(callback: CallbackQuery, state: FSMContext) -> None:
    """Ввод своей суммы."""
    if callback is None or callback.message is None:
        return
    
    await state.set_state(DonateState.waiting_for_amount)
    
    # Устанавливаем таймаут для состояния
    asyncio.create_task(_auto_cancel_state(state, FSM_TIMEOUT))
    
    text = (
        "💰 <b>ВВЕДИТЕ СУММУ ДОНАТА</b>\n\n"
        f"Напишите сумму в рублях (целое число, минимум {MIN_DONATE} ₽):\n\n"
        f"Пример: <code>1500</code>\n\n"
        f"🪙 Расчёт: 1 ₽ = {DONATE_RATE} NCoin + бонусы!\n\n"
        "❌ Для отмены: /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="donate_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


async def _auto_cancel_state(state: FSMContext, timeout: int) -> None:
    """Автоматическая отмена состояния FSM по таймауту."""
    await asyncio.sleep(timeout)
    current_state = await state.get_state()
    if current_state in [DonateState.waiting_for_amount, DonateState.waiting_for_proof]:
        await state.clear()
        logger.debug(f"FSM state auto-cancelled after {timeout}s")


async def _process_donate_amount(message: Message, state: FSMContext, amount: int) -> None:
    """Обработка выбранной суммы доната."""
    if message is None:
        return
    
    coins = calculate_donate_coins(amount)
    
    await state.update_data(donate_amount=amount, donate_coins=coins)
    await state.set_state(DonateState.waiting_for_proof)
    
    # Устанавливаем таймаут
    asyncio.create_task(_auto_cancel_state(state, FSM_TIMEOUT))
    
    text = (
        f"💳 <b>ДОНАТ НА {amount} ₽</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Банк: <b>{DONATE_BANK or 'Озон Банк'}</b>\n"
        f"👤 Получатель: <b>{DONATE_RECEIVER or 'NEXUS'}</b>\n\n"
    )
    
    if DONATE_URL:
        text += (
            f"📱 <b>Ссылка СБП:</b>\n"
            f"<code>{DONATE_URL}</code>\n\n"
        )
    
    text += (
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📸 ПРИКРЕПИТЕ СКРИНШОТ ПЕРЕВОДА:</b>\n\n"
        f"1. Переведите <b>{amount} ₽</b> по ссылке\n"
        f"2. Сделайте скриншот\n"
        f"3. <b>Отправьте скриншот прямо сейчас</b>\n\n"
        f"🪙 Вы получите: <b>{coins} NCoin</b>\n\n"
        f"❌ Для отмены: /cancel"
    )
    
    keyboard_rows = []
    if DONATE_URL:
        keyboard_rows.append([InlineKeyboardButton(text="💳 ОТКРЫТЬ СБП", url=DONATE_URL)])
    keyboard_rows.append([InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="donate_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(DonateState.waiting_for_amount)
async def process_custom_amount(message: Message, state: FSMContext) -> None:
    """Обработка введённой суммы."""
    if message is None or message.text is None:
        return
    
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число!\nПопробуйте ещё раз:")
        return
    
    if amount < MIN_DONATE:
        await message.answer(f"❌ Минимальная сумма доната: {MIN_DONATE} ₽\nПопробуйте ещё раз:")
        return
    
    # Отправляем сообщение с реквизитами
    coins = calculate_donate_coins(amount)
    
    await state.update_data(donate_amount=amount, donate_coins=coins)
    await state.set_state(DonateState.waiting_for_proof)
    
    text = (
        f"💳 <b>ДОНАТ НА {amount} ₽</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Банк: <b>{DONATE_BANK or 'Озон Банк'}</b>\n"
        f"👤 Получатель: <b>{DONATE_RECEIVER or 'NEXUS'}</b>\n\n"
    )
    
    if DONATE_URL:
        text += (
            f"📱 <b>Ссылка СБП:</b>\n"
            f"<code>{DONATE_URL}</code>\n\n"
        )
    
    text += (
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📸 ПРИКРЕПИТЕ СКРИНШОТ ПЕРЕВОДА:</b>\n\n"
        f"1. Переведите <b>{amount} ₽</b> по ссылке\n"
        f"2. Сделайте скриншот\n"
        f"3. <b>Отправьте скриншот прямо сейчас</b>\n\n"
        f"🪙 Вы получите: <b>{coins} NCoin</b>\n\n"
        f"❌ Для отмены: /cancel"
    )
    
    keyboard_rows = []
    if DONATE_URL:
        keyboard_rows.append([InlineKeyboardButton(text="💳 ОТКРЫТЬ СБП", url=DONATE_URL)])
    keyboard_rows.append([InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="donate_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(DonateState.waiting_for_proof, F.photo | F.document)
async def process_donate_proof(message: Message, state: FSMContext) -> None:
    """Получение скриншота доната."""
    if message is None or message.from_user is None:
        return
    
    data = await state.get_data()
    amount = data.get("donate_amount", 0)
    coins = data.get("donate_coins", 0)
    
    await state.clear()
    
    # Проверяем наличие админов
    all_admin_ids = list(set(ADMIN_IDS + SUPER_ADMIN_IDS))
    
    if not all_admin_ids:
        logger.warning("No admin IDs configured for donate notifications!")
        await message.answer(
            "❌ Нет доступных администраторов для проверки доната.\n"
            "Пожалуйста, свяжитесь с разработчиком."
        )
        return
    
    # Отправляем админам
    sent_count = 0
    for admin_id in all_admin_ids:
        if admin_id is None:
            continue
        
        try:
            admin_text = (
                f"💰 <b>НОВЫЙ ДОНАТ!</b>\n\n"
                f"👤 От: {safe_html_escape(message.from_user.full_name)}\n"
                f"🆔 ID: <code>{message.from_user.id}</code>\n"
                f"📛 Username: @{safe_html_escape(message.from_user.username or 'нет')}\n"
                f"💵 Сумма: {amount} ₽\n"
                f"🪙 К начислению: {coins} NCoin\n\n"
                f"<b>Действия:</b>"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ ПОДТВЕРДИТЬ",
                        callback_data=f"confirm_donate_{message.from_user.id}_{amount}_{coins}"
                    ),
                    InlineKeyboardButton(
                        text="❌ ОТКЛОНИТЬ",
                        callback_data=f"reject_donate_{message.from_user.id}"
                    )
                ]
            ])
            
            if message.photo:
                await message.bot.send_photo(
                    admin_id,
                    photo=message.photo[-1].file_id,
                    caption=admin_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            elif message.document:
                await message.bot.send_document(
                    admin_id,
                    document=message.document.file_id,
                    caption=admin_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            
            sent_count += 1
            
        except TelegramForbiddenError:
            logger.warning(f"Admin {admin_id} blocked the bot")
        except TelegramAPIError as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")
    
    if sent_count == 0:
        await message.answer(
            "❌ Не удалось отправить заявку администраторам.\n"
            "Пожалуйста, попробуйте позже."
        )
        return
    
    await message.answer(
        f"✅ <b>ЗАЯВКА ОТПРАВЛЕНА!</b>\n\n"
        f"💵 Сумма: {amount} ₽\n"
        f"🪙 Ожидаемое начисление: {coins} NCoin\n\n"
        f"Администратор проверит платёж в ближайшее время.\n"
        f"Спасибо за поддержку! ❤️",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
        ])
    )
    
    logger.info(f"Donate request: user={message.from_user.id}, amount={amount}, coins={coins}")


@router.message(DonateState.waiting_for_proof)
async def donate_waiting_for_photo(message: Message) -> None:
    """Напоминание, что нужен скриншот."""
    if message is None:
        return
    
    await message.answer(
        "📸 <b>Прикрепите скриншот перевода!</b>\n\n"
        "Просто отправьте фото или файл.\n"
        "❌ Для отмены: /cancel",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("cancel"))
async def cancel_donate(message: Message, state: FSMContext) -> None:
    """Отмена доната."""
    if message is None:
        return
    
    current_state = await state.get_state()
    if current_state in [DonateState.waiting_for_amount, DonateState.waiting_for_proof]:
        await state.clear()
        await message.answer("❌ Донат отменён.")
    else:
        await message.answer("ℹ️ Нет активной операции.")


@router.callback_query(F.data == "donate_sbp")
async def donate_sbp_callback(callback: CallbackQuery) -> None:
    """Показать реквизиты СБП."""
    if callback is None or callback.message is None:
        return
    
    text = (
        "💳 <b>РЕКВИЗИТЫ СБП</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Банк: <b>{DONATE_BANK or 'Озон Банк'}</b>\n"
        f"👤 Получатель: <b>{DONATE_RECEIVER or 'NEXUS'}</b>\n\n"
    )
    
    if DONATE_URL:
        text += (
            f"📱 <b>Ссылка на оплату:</b>\n"
            f"<code>{DONATE_URL}</code>\n\n"
        )
    
    text += (
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <i>Нажмите на ссылку или скопируйте её</i>"
    )
    
    keyboard_rows = []
    if DONATE_URL:
        keyboard_rows.append([InlineKeyboardButton(text="💳 ОТКРЫТЬ СБП", url=DONATE_URL)])
    keyboard_rows.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "donate_help")
async def donate_help_callback(callback: CallbackQuery) -> None:
    """Помощь по донату."""
    if callback is None or callback.message is None:
        return
    
    text = (
        "📋 <b>КАК ПОЛУЧИТЬ NCOINS ЗА ДОНАТ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>1️⃣ Выберите сумму</b>\n"
        "Нажмите на кнопку с суммой или введите свою\n\n"
        "<b>2️⃣ Переведите деньги</b>\n"
        f"По реквизитам СБП ({DONATE_BANK or 'Озон Банк'})\n\n"
        "<b>3️⃣ Сделайте скриншот</b>\n"
        "Подтверждения перевода\n\n"
        "<b>4️⃣ Отправьте скриншот</b>\n"
        "Прямо в чат с ботом\n\n"
        "<b>5️⃣ Ожидайте проверки</b>\n"
        "Администратор проверит и начислит NCoin\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>💰 АВТОРАСЧЁТ:</b>\n"
        f"• 1 ₽ = {DONATE_RATE} NCoin\n"
        "• Бонусы за крупные суммы!\n\n"
        "⏰ Обычно проверка занимает до 24 часов.\n"
        "💝 Спасибо за поддержку!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


# ==================== ПОДТВЕРЖДЕНИЕ ДОНАТА АДМИНОМ ====================

@router.callback_query(F.data.startswith("confirm_donate_"))
async def confirm_donate_callback(callback: CallbackQuery) -> None:
    """Админ подтверждает донат."""
    if callback is None or callback.from_user is None:
        return
    
    # Проверка прав
    if callback.from_user.id not in ADMIN_IDS and callback.from_user.id not in SUPER_ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    parsed = parse_donate_callback(callback.data)
    if not parsed:
        await callback.answer("❌ Ошибка данных!", show_alert=True)
        return
    
    user_id = parsed["user_id"]
    amount_rub = parsed["amount_rub"]
    coins = parsed["coins"]
    
    try:
        await db.update_balance(user_id, coins, f"Донат {amount_rub} ₽")
        
        if hasattr(db, 'update_donor_stats'):
            await db.update_donor_stats(user_id, amount_rub)
        
        # Обновляем сообщение
        if callback.message:
            new_caption = f"{callback.message.caption or callback.message.text or ''}\n\n✅ <b>ПОДТВЕРЖДЕНО!</b>\nНачислено {coins} NCoin пользователю."
            
            if callback.message.caption:
                await callback.message.edit_caption(
                    caption=new_caption,
                    parse_mode=ParseMode.HTML
                )
            else:
                await callback.message.edit_text(
                    new_caption,
                    parse_mode=ParseMode.HTML
                )
        
        # Уведомляем пользователя
        try:
            await callback.bot.send_message(
                user_id,
                f"🎉 <b>ДОНАТ ПОДТВЕРЖДЁН!</b>\n\n"
                f"💵 Сумма: {amount_rub} ₽\n"
                f"🪙 Начислено: <b>{coins} NCoin</b>\n\n"
                f"Спасибо за поддержку! ❤️",
                parse_mode=ParseMode.HTML
            )
        except TelegramAPIError:
            logger.warning(f"Could not notify user {user_id} about confirmed donate")
        
        await callback.answer("✅ Донат подтверждён!")
        logger.info(f"Donate confirmed by {callback.from_user.id}: user={user_id}, amount={amount_rub}, coins={coins}")
        
    except DatabaseError as e:
        logger.error(f"Database error confirming donate: {e}")
        await callback.answer("❌ Ошибка БД", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error confirming donate: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("reject_donate_"))
async def reject_donate_callback(callback: CallbackQuery) -> None:
    """Админ отклоняет донат."""
    if callback is None or callback.from_user is None:
        return
    
    # Проверка прав
    if callback.from_user.id not in ADMIN_IDS and callback.from_user.id not in SUPER_ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    
    try:
        user_id = int(parts[2])
    except ValueError:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    
    # Обновляем сообщение
    if callback.message:
        new_caption = f"{callback.message.caption or callback.message.text or ''}\n\n❌ <b>ОТКЛОНЕНО</b>"
        
        if callback.message.caption:
            await callback.message.edit_caption(
                caption=new_caption,
                parse_mode=ParseMode.HTML
            )
        else:
            await callback.message.edit_text(
                new_caption,
                parse_mode=ParseMode.HTML
            )
    
    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            user_id,
            f"❌ <b>ДОНАТ НЕ ПОДТВЕРЖДЁН</b>\n\n"
            f"Платёж не найден или скриншот недействителен.\n"
            f"Свяжитесь с разработчиком для уточнения.",
            parse_mode=ParseMode.HTML
        )
    except TelegramAPIError:
        logger.warning(f"Could not notify user {user_id} about rejected donate")
    
    await callback.answer("❌ Донат отклонён")
    logger.info(f"Donate rejected by {callback.from_user.id}: user={user_id}")


# ==================== МЕНЮ ФИНАНСОВ ====================

@router.callback_query(F.data == "finance_category")
async def finance_category_callback(callback: CallbackQuery) -> None:
    """Меню финансов."""
    if callback is None or callback.message is None:
        return
    
    user_id = callback.from_user.id
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    if not user:
        await callback.answer("❌ Ошибка доступа к БД", show_alert=True)
        return
    
    try:
        balance = await db.get_balance(user_id)
        
        today = datetime.now().strftime("%Y-%m-%d")
        last_daily = user.get("last_daily")
        can_claim = not last_daily or last_daily != today
        daily_status = "✅ ДОСТУПЕН" if can_claim else "⏰ УЖЕ ПОЛУЧЕН"
        
        text = (
            f"💰 <b>ФИНАНСЫ И ЭКОНОМИКА</b>\n\n"
            f"💎 Баланс: <b>{format_number(balance)} NCoin</b>\n"
            f"⭐ VIP: <b>{user.get('vip_level', 0) or 0}</b>\n"
            f"🔥 Стрик: <b>{user.get('daily_streak', 0) or 0}</b> дней\n"
            f"🎁 Бонус: {daily_status}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Доступные действия:</b>\n"
            f"├ /balance — баланс\n"
            f"├ /daily — бонус\n"
            f"├ /transfer — перевод\n"
            f"└ /donate — поддержать"
        )
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=finance_category_menu()
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in finance_category: {e}")
        await callback.answer("❌ Ошибка БД", show_alert=True)


@router.callback_query(F.data == "transfer_menu")
async def transfer_menu_callback(callback: CallbackQuery) -> None:
    """Меню перевода."""
    if callback is None or callback.message is None:
        return
    
    text = (
        "💸 <b>ПЕРЕВОД МОНЕТ</b>\n\n"
        f"<code>/transfer @username 100</code>\n\n"
        f"⚠️ Минимум: {MIN_TRANSFER} NCoin"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()
