#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/vip.py
# ВЕРСИЯ: 3.0.0-production
# ОПИСАНИЕ: VIP статусы, покупка, достижения
# ИСПРАВЛЕНИЯ: Совместимость с aiosqlite, правильная статистика из xo_stats
# ============================================

import html
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db, DatabaseError
from config import START_BALANCE

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

VIP_PRICES = {1: 500, 2: 1000, 3: 2000, 4: 5000, 5: 10000}
VIP_DURATION_DAYS = 30

VIP_NAMES = {
    1: {"name": "🥉 Бронза", "win_bonus": 5, "daily_bonus": 50, "icon": "🥉", "wins_required": 10},
    2: {"name": "🥈 Серебро", "win_bonus": 10, "daily_bonus": 100, "icon": "🥈", "wins_required": 50},
    3: {"name": "🥇 Золото", "win_bonus": 15, "daily_bonus": 150, "icon": "🥇", "wins_required": 100},
    4: {"name": "💎 Платина", "win_bonus": 20, "daily_bonus": 200, "icon": "💎", "wins_required": 200},
    5: {"name": "💠 Алмаз", "win_bonus": 30, "daily_bonus": 300, "icon": "💠", "wins_required": 500},
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict]:
    """
    Получить или создать пользователя.
    
    Args:
        user_id: ID пользователя
        username: Username
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
            logger.info(f"Created user {user_id} in vip module")
        return user
    except DatabaseError as e:
        logger.error(f"Database error in get_or_create_user: {e}")
        return None


async def get_user_xo_stats(user_id: int) -> Tuple[int, int, int]:
    """
    Получить статистику крестиков-ноликов пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        (wins, losses, games_played)
    """
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return (
                stats.get('wins', 0) or 0,
                stats.get('losses', 0) or 0,
                stats.get('games_played', 0) or 0
            )
    except DatabaseError as e:
        logger.error(f"Database error getting XO stats for {user_id}: {e}")
    
    return 0, 0, 0


async def update_user_vip(user_id: int, vip_level: int, days: int = VIP_DURATION_DAYS) -> bool:
    """
    Обновить VIP статус пользователя.
    
    Args:
        user_id: ID пользователя
        vip_level: Уровень VIP
        days: Количество дней
        
    Returns:
        True если успешно
    """
    if user_id is None:
        return False
    
    try:
        new_until = (datetime.now() + timedelta(days=days)).isoformat()
        
        # Используем прямой SQL через aiosqlite
        await db._execute_with_retry(
            "UPDATE users SET vip_level = ?, vip_until = ? WHERE user_id = ?",
            (vip_level, new_until, user_id),
            commit=True
        )
        logger.info(f"Updated VIP for user {user_id} to level {vip_level}")
        return True
    except DatabaseError as e:
        logger.error(f"Failed to update VIP for {user_id}: {e}")
        return False


async def check_and_award_achievement_vip(user_id: int, wins: int) -> Optional[int]:
    """
    Проверить и выдать VIP за достижения.
    
    Args:
        user_id: ID пользователя
        wins: Количество побед
        
    Returns:
        Новый VIP уровень или None
    """
    vip_level = 0
    
    for level in sorted(VIP_NAMES.keys()):
        if wins >= VIP_NAMES[level]['wins_required']:
            vip_level = level
    
    if vip_level > 0:
        try:
            user = await db.get_user(user_id)
            current_vip = user.get('vip_level', 0) if user else 0
            
            if vip_level > current_vip:
                await update_user_vip(user_id, vip_level, VIP_DURATION_DAYS)
                logger.info(f"Awarded achievement VIP level {vip_level} to user {user_id}")
                return vip_level
        except DatabaseError as e:
            logger.error(f"Failed to award achievement VIP: {e}")
    
    return None


def get_vip_privileges(vip_level: int) -> Dict:
    """Получить привилегии для уровня VIP."""
    return VIP_NAMES.get(vip_level, VIP_NAMES[1])


def format_vip_active(
    vip_level: int,
    balance: int,
    wins: int,
    losses: int,
    vip_until: str
) -> str:
    """Форматирует текст для активного VIP."""
    privileges = get_vip_privileges(vip_level)
    
    return (
        f"{privileges['icon']} <b>ВАШ VIP СТАТУС</b> {privileges['icon']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Уровень: <b>{privileges['name']}</b> (Уровень {vip_level})\n"
        f"💰 Баланс: <b>{balance}</b> NCoins\n"
        f"📅 Действует до: {safe_html_escape(vip_until)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Ваша статистика XO:</b>\n"
        f"├ 🏆 Побед: {wins}\n"
        f"└ 📉 Поражений: {losses}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>✨ ВАШИ ПРЕИМУЩЕСТВА:</b>\n\n"
        f"├ 🎮 +{privileges['win_bonus']}% к выигрышам\n"
        f"├ 🎁 +{privileges['daily_bonus']} NCoins к бонусу\n"
        f"├ 👑 Статус в чате\n"
        f"├ 💎 Доступ к VIP-комнатам\n"
        f"└ ⭐ Приоритетная поддержка"
    )


def format_vip_catalog(balance: int, wins: int, losses: int, games: int) -> str:
    """Форматирует каталог VIP статусов."""
    winrate = (wins / games * 100) if games > 0 else 0
    
    text = (
        "⭐ <b>VIP СТАТУСЫ NEXUS</b> ⭐\n\n"
        "Получите эксклюзивные преимущества!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Ваш баланс: {balance} NCoins</b>\n"
        f"🏆 <b>Побед: {wins}</b> | 📉 <b>Поражений: {losses}</b>\n"
        f"📊 <b>Винрейт: {winrate:.1f}%</b> ({games} игр)\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for level in range(1, 6):
        name = VIP_NAMES[level]['name']
        price = VIP_PRICES[level]
        win_bonus = VIP_NAMES[level]['win_bonus']
        daily_bonus = VIP_NAMES[level]['daily_bonus']
        
        text += (
            f"{name} (уровень {level}) — {price} NCoins\n"
            f"├ 🎮 +{win_bonus}% к выигрышам\n"
            f"└ 🎁 +{daily_bonus} NCoins к бонусу\n\n"
        )
    
    text += (
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 <b>БЕСПЛАТНЫЙ VIP ЗА ПОБЕДЫ В XO:</b>\n"
    )
    
    for level in range(1, 5):
        wins_req = VIP_NAMES[level]['wins_required']
        name = VIP_NAMES[level]['name']
        text += f"├ {wins_req} побед → {name}\n"
    text += f"└ {VIP_NAMES[5]['wins_required']} побед → {VIP_NAMES[5]['name']}\n\n"
    
    text += f"📊 <b>Ваш прогресс: {wins} побед</b>"
    
    return text


def format_achievements(
    balance: int,
    wins: int,
    losses: int,
    games: int,
    current_vip: int,
    awarded_vip: Optional[int] = None
) -> str:
    """Форматирует прогресс достижений."""
    winrate = (wins / games * 100) if games > 0 else 0
    
    # Определяем следующий уровень
    next_level = None
    next_wins = 0
    progress = 0
    
    thresholds = [(1, 10), (2, 50), (3, 100), (4, 200), (5, 500)]
    
    for level, required in thresholds:
        if wins < required:
            next_level = VIP_NAMES[level]['name']
            next_wins = required
            
            # Расчет прогресса
            prev_required = thresholds[level - 2][1] if level > 1 else 0
            progress = int(((wins - prev_required) / (required - prev_required)) * 100)
            progress = max(0, min(100, progress))
            break
    
    if next_level is None:
        progress = 100
    
    # Прогресс-бар
    bar_length = 10
    filled = int(bar_length * progress / 100)
    progress_bar = "█" * filled + "░" * (bar_length - filled)
    
    # Статус
    status_msg = ""
    if awarded_vip:
        status_msg = f"✨ <b>Только что получен VIP {awarded_vip} уровня!</b>\n\n"
    elif wins >= 500:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ АЛМАЗА!</b>\n\n"
    elif wins >= 200:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ ПЛАТИНЫ!</b>\n\n"
    elif wins >= 100:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ ЗОЛОТА!</b>\n\n"
    elif wins >= 50:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ СЕРЕБРА!</b>\n\n"
    elif wins >= 10:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ БРОНЗЫ!</b>\n\n"
    
    # Прогресс до следующего уровня
    progress_msg = ""
    if next_level and wins < 500:
        progress_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📈 <b>ДО СЛЕДУЮЩЕГО УРОВНЯ:</b>\n\n"
            f"Цель: <b>{next_level}</b>\n"
            f"Прогресс: {wins}/{next_wins} побед\n"
            f"[{progress_bar}] {progress}%\n\n"
            f"💪 Осталось <b>{next_wins - wins}</b> побед!\n"
        )
    
    return (
        f"🏆 <b>БЕСПЛАТНЫЙ VIP ЗА ДОСТИЖЕНИЯ</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>ВАША СТАТИСТИКА XO:</b>\n\n"
        f"💰 Баланс: <b>{balance} NCoins</b>\n"
        f"🏆 Побед: <b>{wins}</b>\n"
        f"📉 Поражений: <b>{losses}</b>\n"
        f"📊 Винрейт: <b>{winrate:.1f}%</b> ({games} игр)\n"
        f"⭐ Текущий VIP: <b>{current_vip} уровень</b>\n\n"
        f"{status_msg}{progress_msg}"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>ДОСТУПНЫЕ НАГРАДЫ:</b>\n\n"
        f"🥉 10 побед → Бронза VIP\n"
        f"🥈 50 побед → Серебро VIP\n"
        f"🥇 100 побед → Золото VIP\n"
        f"💎 200 побед → Платина VIP\n"
        f"💠 500 побед → Алмаз VIP"
    )


# ==================== ОБРАБОТЧИКИ ====================

@router.message(Command("vip"))
async def cmd_vip(message: Message) -> None:
    """Команда VIP меню."""
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
        balance = await db.get_balance(user_id)
        wins, losses, games = await get_user_xo_stats(user_id)
        
        vip_level = user.get('vip_level', 0) or 0
        vip_until = user.get('vip_until', '')
        
        # Проверка достижений (только если VIP не максимальный)
        awarded_vip = None
        if vip_level < 5:
            awarded_vip = await check_and_award_achievement_vip(user_id, wins)
            if awarded_vip:
                vip_level = awarded_vip
                user = await db.get_user(user_id)
                balance = await db.get_balance(user_id)
        
        # Форматирование даты
        try:
            until_date = datetime.fromisoformat(vip_until).strftime("%d.%m.%Y") if vip_until else "Бессрочно"
        except (ValueError, TypeError):
            until_date = "Бессрочно"
        
        if vip_level > 0:
            text = format_vip_active(vip_level, balance, wins, losses, until_date)
        else:
            text = format_vip_catalog(balance, wins, losses, games)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 КУПИТЬ VIP", callback_data="buy_vip")],
            [InlineKeyboardButton(text="🏆 МОИ ДОСТИЖЕНИЯ", callback_data="vip_achievements")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
    except DatabaseError as e:
        logger.error(f"Database error in cmd_vip: {e}")
        await message.answer("❌ Ошибка загрузки VIP меню.")
    except Exception as e:
        logger.error(f"Unexpected error in cmd_vip: {e}")
        await message.answer("❌ Произошла ошибка.")


@router.callback_query(F.data == "vip")
@router.callback_query(F.data == "vip_menu")
async def vip_callback(callback: CallbackQuery) -> None:
    """Callback для VIP меню."""
    if callback is None:
        return
    await cmd_vip(callback.message)
    await callback.answer()


@router.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: CallbackQuery) -> None:
    """Меню покупки VIP."""
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
        current_vip = user.get('vip_level', 0) or 0
        
        buttons = []
        for level, price in VIP_PRICES.items():
            name = VIP_NAMES[level]['name']
            if level <= current_vip:
                name = f"✅ {name} (куплен)"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{name} ({price} NCoins)",
                    callback_data=f"buy_vip_{level}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")])
        
        await callback.message.edit_text(
            f"💎 <b>ПОКУПКА VIP СТАТУСА</b>\n\n"
            f"💰 Ваш баланс: <b>{balance} NCoins</b>\n"
            f"⭐ Текущий VIP: <b>{current_vip} уровень</b>\n\n"
            f"Выберите уровень VIP:\n\n"
            f"💡 <i>Совет:</i> VIP действует {VIP_DURATION_DAYS} дней",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in buy_vip_menu: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)


@router.callback_query(F.data.startswith("buy_vip_"))
async def buy_vip(callback: CallbackQuery) -> None:
    """Покупка VIP."""
    if callback is None or callback.message is None:
        return
    
    user_id = callback.from_user.id
    
    try:
        level = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Неверный уровень!", show_alert=True)
        return
    
    price = VIP_PRICES.get(level, 500)
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    if not user:
        await callback.answer("❌ Ошибка доступа к БД", show_alert=True)
        return
    
    current_vip = user.get('vip_level', 0) or 0
    
    if level <= current_vip:
        await callback.answer(f"❌ У вас уже есть VIP {current_vip} уровня!", show_alert=True)
        return
    
    try:
        balance = await db.get_balance(user_id)
        
        if balance < price:
            await callback.answer(
                f"❌ Недостаточно средств!\nНужно: {price} NCoins\nБаланс: {balance} NCoins",
                show_alert=True
            )
            return
        
        # Списываем средства и обновляем VIP
        await db.update_balance(user_id, -price, f"Покупка VIP уровня {level}")
        await update_user_vip(user_id, level, VIP_DURATION_DAYS)
        
        new_balance = await db.get_balance(user_id)
        privileges = get_vip_privileges(level)
        
        await callback.message.edit_text(
            f"🎉 <b>ПОЗДРАВЛЯЕМ С ПОКУПКОЙ VIP!</b>\n\n"
            f"{privileges['icon']} Новый уровень: <b>{privileges['name']}</b>\n"
            f"💰 Списано: <b>{price} NCoins</b>\n"
            f"💎 Новый баланс: <b>{new_balance} NCoins</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>✨ НОВЫЕ ПРЕИМУЩЕСТВА:</b>\n"
            f"├ 🎮 +{privileges['win_bonus']}% к выигрышам\n"
            f"├ 🎁 +{privileges['daily_bonus']} NCoins к бонусу\n"
            f"├ 👑 Статус в чате\n"
            f"└ ⭐ Приоритетная поддержка\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 Статус действует <b>{VIP_DURATION_DAYS} дней</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ПОНЯТНО", callback_data="vip")]
            ])
        )
        
        logger.info(f"User {user_id} purchased VIP level {level}")
        
    except DatabaseError as e:
        logger.error(f"VIP purchase failed: {e}")
        await callback.answer("❌ Ошибка при покупке", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in buy_vip: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data == "vip_achievements")
async def vip_achievements(callback: CallbackQuery) -> None:
    """Показать достижения."""
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
        wins, losses, games = await get_user_xo_stats(user_id)
        current_vip = user.get('vip_level', 0) or 0
        
        # Проверяем достижения
        awarded_vip = await check_and_award_achievement_vip(user_id, wins)
        if awarded_vip:
            current_vip = awarded_vip
            balance = await db.get_balance(user_id)
        
        text = format_achievements(balance, wins, losses, games, current_vip, awarded_vip)
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
            ])
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in vip_achievements: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in vip_achievements: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
