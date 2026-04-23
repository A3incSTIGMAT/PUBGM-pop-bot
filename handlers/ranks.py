#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/ranks.py
# ВЕРСИЯ: 1.0.0-production
# ОПИСАНИЕ: Система рангов NEXUS Bot — 36 уровней (Серебро → Бриллиант)
# ============================================

import asyncio
import html
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()


# ==================== КОНСТАНТЫ ====================

# 36 рангов от Серебра V до Бриллианта
RANKS: List[Dict[str, Any]] = [
    # Серебро (1-5)
    {"level": 1, "name": "Серебро V", "icon": "🥈", "tier": "silver", "xp_required": 0},
    {"level": 2, "name": "Серебро IV", "icon": "🥈", "tier": "silver", "xp_required": 150},
    {"level": 3, "name": "Серебро III", "icon": "🥈", "tier": "silver", "xp_required": 350},
    {"level": 4, "name": "Серебро II", "icon": "🥈", "tier": "silver", "xp_required": 600},
    {"level": 5, "name": "Серебро I", "icon": "🥈", "tier": "silver", "xp_required": 900},
    
    # Золото (6-10)
    {"level": 6, "name": "Золото V", "icon": "🥇", "tier": "gold", "xp_required": 1300},
    {"level": 7, "name": "Золото IV", "icon": "🥇", "tier": "gold", "xp_required": 1800},
    {"level": 8, "name": "Золото III", "icon": "🥇", "tier": "gold", "xp_required": 2400},
    {"level": 9, "name": "Золото II", "icon": "🥇", "tier": "gold", "xp_required": 3100},
    {"level": 10, "name": "Золото I", "icon": "🥇", "tier": "gold", "xp_required": 3900},
    
    # Платина (11-15)
    {"level": 11, "name": "Платина V", "icon": "💿", "tier": "platinum", "xp_required": 4800},
    {"level": 12, "name": "Платина IV", "icon": "💿", "tier": "platinum", "xp_required": 5800},
    {"level": 13, "name": "Платина III", "icon": "💿", "tier": "platinum", "xp_required": 6900},
    {"level": 14, "name": "Платина II", "icon": "💿", "tier": "platinum", "xp_required": 8100},
    {"level": 15, "name": "Платина I", "icon": "💿", "tier": "platinum", "xp_required": 9400},
    
    # Рубин (16-20)
    {"level": 16, "name": "Рубин V", "icon": "🔴", "tier": "ruby", "xp_required": 10800},
    {"level": 17, "name": "Рубин IV", "icon": "🔴", "tier": "ruby", "xp_required": 12300},
    {"level": 18, "name": "Рубин III", "icon": "🔴", "tier": "ruby", "xp_required": 13900},
    {"level": 19, "name": "Рубин II", "icon": "🔴", "tier": "ruby", "xp_required": 15600},
    {"level": 20, "name": "Рубин I", "icon": "🔴", "tier": "ruby", "xp_required": 17400},
    
    # Сапфир (21-25)
    {"level": 21, "name": "Сапфир V", "icon": "🔵", "tier": "sapphire", "xp_required": 19300},
    {"level": 22, "name": "Сапфир IV", "icon": "🔵", "tier": "sapphire", "xp_required": 21300},
    {"level": 23, "name": "Сапфир III", "icon": "🔵", "tier": "sapphire", "xp_required": 23400},
    {"level": 24, "name": "Сапфир II", "icon": "🔵", "tier": "sapphire", "xp_required": 25600},
    {"level": 25, "name": "Сапфир I", "icon": "🔵", "tier": "sapphire", "xp_required": 27900},
    
    # Изумруд (26-30)
    {"level": 26, "name": "Изумруд V", "icon": "🟢", "tier": "emerald", "xp_required": 30300},
    {"level": 27, "name": "Изумруд IV", "icon": "🟢", "tier": "emerald", "xp_required": 32800},
    {"level": 28, "name": "Изумруд III", "icon": "🟢", "tier": "emerald", "xp_required": 35400},
    {"level": 29, "name": "Изумруд II", "icon": "🟢", "tier": "emerald", "xp_required": 38100},
    {"level": 30, "name": "Изумруд I", "icon": "🟢", "tier": "emerald", "xp_required": 40900},
    
    # Алмаз (31-35)
    {"level": 31, "name": "Алмаз V", "icon": "💎", "tier": "diamond", "xp_required": 43800},
    {"level": 32, "name": "Алмаз IV", "icon": "💎", "tier": "diamond", "xp_required": 46800},
    {"level": 33, "name": "Алмаз III", "icon": "💎", "tier": "diamond", "xp_required": 49900},
    {"level": 34, "name": "Алмаз II", "icon": "💎", "tier": "diamond", "xp_required": 53100},
    {"level": 35, "name": "Алмаз I", "icon": "💎", "tier": "diamond", "xp_required": 56400},
    
    # Бриллиант (36)
    {"level": 36, "name": "БРИЛЛИАНТ", "icon": "👑", "tier": "brilliant", "xp_required": 60000},
]

# XP за действия
XP_ACTIONS = {
    "message": 1,
    "voice": 2,
    "photo": 2,
    "video": 3,
    "sticker": 1,
    "gif": 1,
    "game_win": 50,
    "game_loss": 10,
    "daily": 5,
    "referral": 100,
}

# Награды за достижение I ранга в каждой категории
TIER_REWARDS = {
    "silver": {"coins": 500, "message": "🎉 500 NCoin за достижение Серебро I!"},
    "gold": {"coins": 1000, "vip_days": 3, "message": "🎉 1000 NCoin + VIP 3 дня за Золото I!"},
    "platinum": {"coins": 2000, "vip_days": 7, "message": "🎉 2000 NCoin + VIP 7 дней за Платина I!"},
    "ruby": {"coins": 3000, "message": "🎉 3000 NCoin за Рубин I!"},
    "sapphire": {"coins": 5000, "vip_days": 14, "message": "🎉 5000 NCoin + VIP 14 дней за Сапфир I!"},
    "emerald": {"coins": 7500, "message": "🎉 7500 NCoin за Изумруд I!"},
    "diamond": {"coins": 10000, "vip_days": 30, "message": "🎉 10000 NCoin + VIP 30 дней за Алмаз I!"},
    "brilliant": {"coins": 25000, "vip_days": 90, "message": "👑 25000 NCoin + VIP 90 дней + Особая роль за БРИЛЛИАНТ!"},
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


def safe_int(value: Any, default: int = 0) -> int:
    """Безопасное преобразование в int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def format_number(num: Any) -> str:
    """Форматирование числа с разделителями."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def get_rank_by_level(level: int) -> Dict[str, Any]:
    """Получить данные ранга по уровню."""
    if level < 1:
        level = 1
    if level > 36:
        level = 36
    return RANKS[level - 1]


def get_rank_by_xp(xp: int) -> Tuple[Dict[str, Any], int, int]:
    """
    Определить ранг по XP.
    
    Returns:
        (текущий_ранг, текущий_xp, XP_до_следующего_уровня)
    """
    current_rank = RANKS[0]
    next_rank = RANKS[1] if len(RANKS) > 1 else None
    
    for i, rank in enumerate(RANKS):
        if xp >= rank["xp_required"]:
            current_rank = rank
            next_rank = RANKS[i + 1] if i + 1 < len(RANKS) else None
        else:
            break
    
    xp_to_next = next_rank["xp_required"] - xp if next_rank else 0
    
    return current_rank, xp, xp_to_next


def calculate_level_progress(xp: int, current_rank: Dict[str, Any], next_rank: Optional[Dict[str, Any]]) -> float:
    """Рассчитать процент прогресса до следующего уровня."""
    if next_rank is None:
        return 100.0
    
    xp_current = current_rank["xp_required"]
    xp_next = next_rank["xp_required"]
    xp_range = xp_next - xp_current
    
    if xp_range <= 0:
        return 100.0
    
    progress = (xp - xp_current) / xp_range * 100
    return min(100.0, max(0.0, progress))


def generate_progress_bar(progress: float, length: int = 10) -> str:
    """Сгенерировать прогресс-бар."""
    filled = int(length * progress / 100)
    empty = length - filled
    return "█" * filled + "░" * empty


# ==================== РАБОТА С БАЗОЙ ДАННЫХ ====================

async def init_ranks_table() -> None:
    """Создать таблицу рангов если не существует."""
    if db is None:
        return
    
    try:
        await db._execute_with_retry("""
            CREATE TABLE IF NOT EXISTS user_ranks (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                rank_name TEXT DEFAULT 'Серебро V',
                tier TEXT DEFAULT 'silver',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("✅ Ranks table initialized")
    except DatabaseError as e:
        logger.error(f"Failed to create ranks table: {e}")


async def get_user_rank(user_id: int) -> Optional[Dict[str, Any]]:
    """Получить ранг пользователя."""
    if db is None or user_id is None:
        return None
    
    try:
        row = await db._execute_with_retry(
            "SELECT * FROM user_ranks WHERE user_id = ?",
            (user_id,),
            fetch_one=True
        )
        
        if row:
            return dict(row)
        
        # Создаем запись если нет
        await db._execute_with_retry(
            "INSERT INTO user_ranks (user_id, xp, level, rank_name, tier) VALUES (?, 0, 1, 'Серебро V', 'silver')",
            (user_id,),
            commit=True
        )
        
        return {
            "user_id": user_id,
            "xp": 0,
            "level": 1,
            "rank_name": "Серебро V",
            "tier": "silver",
        }
    except DatabaseError as e:
        logger.error(f"Error getting user rank: {e}")
        return None


async def add_xp(user_id: int, amount: int, reason: str = "activity") -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """
    Добавить XP пользователю.
    
    Returns:
        (новый_уровень_если_повысился, данные_ранга)
    """
    if db is None or user_id is None or amount <= 0:
        return None, None
    
    try:
        # Получаем текущий ранг
        rank_data = await get_user_rank(user_id)
        if not rank_data:
            return None, None
        
        old_level = rank_data["level"]
        old_xp = rank_data["xp"]
        new_xp = old_xp + amount
        
        # Определяем новый ранг
        new_rank, _, _ = get_rank_by_xp(new_xp)
        new_level = new_rank["level"]
        
        # Обновляем в БД
        await db._execute_with_retry(
            """UPDATE user_ranks 
               SET xp = ?, level = ?, rank_name = ?, tier = ?, updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ?""",
            (new_xp, new_level, new_rank["name"], new_rank["tier"], user_id),
            commit=True
        )
        
        logger.info(f"Added {amount} XP to user {user_id} (reason: {reason})")
        
        # Если уровень повысился
        if new_level > old_level:
            return new_level, new_rank
        
        return None, None
        
    except DatabaseError as e:
        logger.error(f"Error adding XP: {e}")
        return None, None


async def award_tier_reward(user_id: int, tier: str) -> bool:
    """Выдать награду за достижение I ранга."""
    if tier not in TIER_REWARDS:
        return False
    
    reward = TIER_REWARDS[tier]
    
    try:
        # Начисляем монеты
        if "coins" in reward:
            await db.update_balance(user_id, reward["coins"], f"Награда за ранг: {tier}")
        
        # Выдаем VIP
        if "vip_days" in reward:
            vip_until = (datetime.now() + timedelta(days=reward["vip_days"])).isoformat()
            await db._execute_with_retry(
                "UPDATE users SET vip_level = MAX(COALESCE(vip_level, 0), 1), vip_until = ? WHERE user_id = ?",
                (vip_until, user_id),
                commit=True
            )
        
        logger.info(f"Awarded tier reward to user {user_id}: {tier}")
        return True
        
    except DatabaseError as e:
        logger.error(f"Error awarding tier reward: {e}")
        return False


# ==================== ОТСЛЕЖИВАНИЕ АКТИВНОСТИ ====================

async def track_activity(user_id: int, action: str, value: int = 1) -> None:
    """Отследить активность и начислить XP."""
    if action not in XP_ACTIONS:
        return
    
    xp_amount = XP_ACTIONS[action] * value
    new_level, new_rank = await add_xp(user_id, xp_amount, action)
    
    # Если уровень повысился до I ранга — выдаем награду
    if new_level and new_rank:
        if new_rank["name"].endswith("I"):
            await award_tier_reward(user_id, new_rank["tier"])


# ==================== КОМАНДЫ ====================

@router.message(Command("rank"))
async def cmd_rank(message: Message) -> None:
    """Показать текущий ранг пользователя."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    
    # Инициализируем таблицу
    await init_ranks_table()
    
    rank_data = await get_user_rank(user_id)
    if not rank_data:
        await message.answer("❌ Ошибка загрузки ранга.")
        return
    
    xp = rank_data["xp"]
    current_rank, _, xp_to_next = get_rank_by_xp(xp)
    next_level = current_rank["level"] + 1 if current_rank["level"] < 36 else None
    next_rank = RANKS[next_level - 1] if next_level else None
    
    progress = calculate_level_progress(xp, current_rank, next_rank)
    progress_bar = generate_progress_bar(progress)
    
    # Получаем данные пользователя
    user = await db.get_user(user_id) if db else None
    first_name = safe_html_escape(user.get("first_name") if user else message.from_user.first_name)
    
    text = (
        f"{current_rank['icon']} <b>{current_rank['name']}</b>\n\n"
        f"👤 Игрок: {first_name}\n"
        f"📊 Уровень: <b>{current_rank['level']}/36</b>\n"
        f"✨ XP: <b>{format_number(xp)}</b>\n\n"
        f"📈 Прогресс до следующего уровня:\n"
        f"[{progress_bar}] {progress:.1f}%\n"
    )
    
    if next_rank:
        text += f"⏫ Следующий: {next_rank['icon']} {next_rank['name']} (ещё {format_number(xp_to_next)} XP)"
    else:
        text += "🏆 <b>МАКСИМАЛЬНЫЙ УРОВЕНЬ!</b>"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 ТОП ИГРОКОВ", callback_data="top_ranks")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(Command("top_ranks"))
async def cmd_top_ranks(message: Message) -> None:
    """Топ игроков по рангу."""
    if not message:
        return
    
    await init_ranks_table()
    
    try:
        rows = await db._execute_with_retry("""
            SELECT ur.user_id, ur.xp, ur.level, ur.rank_name, u.first_name, u.username
            FROM user_ranks ur
            LEFT JOIN users u ON ur.user_id = u.user_id
            WHERE ur.xp > 0
            ORDER BY ur.xp DESC
            LIMIT 15
        """, fetch_all=True)
        
        if not rows:
            await message.answer("📊 Пока нет данных о рангах.")
            return
        
        text = "🏆 <b>ТОП-15 ИГРОКОВ ПО РАНГУ</b>\n\n"
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 16)]
        
        for i, row in enumerate(rows):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            name = row["first_name"] or row["username"] or "Игрок"
            safe_name = safe_html_escape(name)[:20]
            rank_icon = get_rank_by_level(row["level"])["icon"]
            
            text += f"{medal} {rank_icon} <b>{safe_name}</b> — {format_number(row['xp'])} XP ({row['rank_name']})\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
    except DatabaseError as e:
        logger.error(f"Error getting top ranks: {e}")
        await message.answer("❌ Ошибка загрузки топа.")


@router.callback_query(F.data == "rank_menu")
async def rank_menu_callback(callback: CallbackQuery) -> None:
    """Кнопка РАНГ из главного меню."""
    if not callback or not callback.message:
        return
    
    await cmd_rank(callback.message)
    await callback.answer()


@router.callback_query(F.data == "top_ranks")
async def top_ranks_callback(callback: CallbackQuery) -> None:
    """Кнопка ТОП ИГРОКОВ."""
    if not callback or not callback.message:
        return
    
    await cmd_top_ranks(callback.message)
    await callback.answer()


# ==================== ИНТЕГРАЦИЯ ====================

async def track_message_activity(user_id: int, message: Message) -> None:
    """Отслеживание активности из других модулей."""
    if message.voice:
        await track_activity(user_id, "voice")
    elif message.video:
        await track_activity(user_id, "video")
    elif message.photo:
        await track_activity(user_id, "photo")
    elif message.sticker:
        await track_activity(user_id, "sticker")
    elif message.animation:
        await track_activity(user_id, "gif")
    elif message.text:
        await track_activity(user_id, "message")


async def track_game_result(user_id: int, won: bool) -> None:
    """Отслеживание результата игры."""
    action = "game_win" if won else "game_loss"
    await track_activity(user_id, action)


async def track_daily_bonus(user_id: int) -> None:
    """Отслеживание получения daily бонуса."""
    await track_activity(user_id, "daily")


async def track_referral(user_id: int) -> None:
    """Отслеживание приглашения друга."""
    await track_activity(user_id, "referral")
