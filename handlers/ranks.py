#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/ranks.py
# ВЕРСИЯ: 1.2.3-production
# ОПИСАНИЕ: Система рангов — 36 уровней, БЕЗ дублирования с users
# ИСПРАВЛЕНИЯ v1.2.3:
#   ✅ Исправлены SyntaxError: current_, new_, rank_, next_rank_
#   ✅ Убран вызов init_ranks_table() из хендлеров (только on_startup)
#   ✅ Убраны _execute_with_retry с commit=True (не поддерживается SQLite)
#   ✅ Все приватные методы заменены на публичные где возможно + hasattr-проверки
#   ✅ lru_cache аннотации для Python 3.9+ (Union вместо |)
#   ✅ Добавлена фильтрация ботов в track_message_activity()
#   ✅ hasattr-проверка для db.update_balance в award_tier_reward()
# ============================================

import html
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional, Dict, List, Tuple, Any, Union

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db, DatabaseError
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# ==================== КОНСТАНТЫ ====================

TOP_RANKS_LIMIT = 15

RANKS: List[Dict[str, Any]] = [
    {"level": 1, "name": "Серебро V", "icon": "🥈", "tier": "silver", "xp_required": 0},
    {"level": 2, "name": "Серебро IV", "icon": "🥈", "tier": "silver", "xp_required": 150},
    {"level": 3, "name": "Серебро III", "icon": "🥈", "tier": "silver", "xp_required": 350},
    {"level": 4, "name": "Серебро II", "icon": "🥈", "tier": "silver", "xp_required": 600},
    {"level": 5, "name": "Серебро I", "icon": "🥈", "tier": "silver", "xp_required": 900},
    {"level": 6, "name": "Золото V", "icon": "🥇", "tier": "gold", "xp_required": 1300},
    {"level": 7, "name": "Золото IV", "icon": "🥇", "tier": "gold", "xp_required": 1800},
    {"level": 8, "name": "Золото III", "icon": "🥇", "tier": "gold", "xp_required": 2400},
    {"level": 9, "name": "Золото II", "icon": "🥇", "tier": "gold", "xp_required": 3100},
    {"level": 10, "name": "Золото I", "icon": "🥇", "tier": "gold", "xp_required": 3900},
    {"level": 11, "name": "Платина V", "icon": "💿", "tier": "platinum", "xp_required": 4800},
    {"level": 12, "name": "Платина IV", "icon": "💿", "tier": "platinum", "xp_required": 5800},
    {"level": 13, "name": "Платина III", "icon": "💿", "tier": "platinum", "xp_required": 6900},
    {"level": 14, "name": "Платина II", "icon": "💿", "tier": "platinum", "xp_required": 8100},
    {"level": 15, "name": "Платина I", "icon": "💿", "tier": "platinum", "xp_required": 9400},
    {"level": 16, "name": "Рубин V", "icon": "🔴", "tier": "ruby", "xp_required": 10800},
    {"level": 17, "name": "Рубин IV", "icon": "🔴", "tier": "ruby", "xp_required": 12300},
    {"level": 18, "name": "Рубин III", "icon": "🔴", "tier": "ruby", "xp_required": 13900},
    {"level": 19, "name": "Рубин II", "icon": "🔴", "tier": "ruby", "xp_required": 15600},
    {"level": 20, "name": "Рубин I", "icon": "🔴", "tier": "ruby", "xp_required": 17400},
    {"level": 21, "name": "Сапфир V", "icon": "🔵", "tier": "sapphire", "xp_required": 19300},
    {"level": 22, "name": "Сапфир IV", "icon": "🔵", "tier": "sapphire", "xp_required": 21300},
    {"level": 23, "name": "Сапфир III", "icon": "🔵", "tier": "sapphire", "xp_required": 23400},
    {"level": 24, "name": "Сапфир II", "icon": "🔵", "tier": "sapphire", "xp_required": 25600},
    {"level": 25, "name": "Сапфир I", "icon": "🔵", "tier": "sapphire", "xp_required": 27900},
    {"level": 26, "name": "Изумруд V", "icon": "🟢", "tier": "emerald", "xp_required": 30300},
    {"level": 27, "name": "Изумруд IV", "icon": "🟢", "tier": "emerald", "xp_required": 32800},
    {"level": 28, "name": "Изумруд III", "icon": "🟢", "tier": "emerald", "xp_required": 35400},
    {"level": 29, "name": "Изумруд II", "icon": "🟢", "tier": "emerald", "xp_required": 38100},
    {"level": 30, "name": "Изумруд I", "icon": "🟢", "tier": "emerald", "xp_required": 40900},
    {"level": 31, "name": "Алмаз V", "icon": "💎", "tier": "diamond", "xp_required": 43800},
    {"level": 32, "name": "Алмаз IV", "icon": "💎", "tier": "diamond", "xp_required": 46800},
    {"level": 33, "name": "Алмаз III", "icon": "💎", "tier": "diamond", "xp_required": 49900},
    {"level": 34, "name": "Алмаз II", "icon": "💎", "tier": "diamond", "xp_required": 53100},
    {"level": 35, "name": "Алмаз I", "icon": "💎", "tier": "diamond", "xp_required": 56400},
    {"level": 36, "name": "БРИЛЛИАНТ", "icon": "👑", "tier": "brilliant", "xp_required": 60000},
]

XP_ACTIONS: Dict[str, int] = {
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

TIER_REWARDS: Dict[str, Dict[str, Union[int, str]]] = {
    "silver": {"coins": 500},
    "gold": {"coins": 1000, "vip_days": 3},
    "platinum": {"coins": 2000, "vip_days": 7},
    "ruby": {"coins": 3000},
    "sapphire": {"coins": 5000, "vip_days": 14},
    "emerald": {"coins": 7500},
    "diamond": {"coins": 10000, "vip_days": 30},
    "brilliant": {"coins": 25000, "vip_days": 90},
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML-символов."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return str(text) if text else ""


def safe_int(value: Any, default: int = 0) -> int:
    """Безопасное преобразование значения в int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def format_number(num: Any) -> str:
    """Форматирование числа с разделителями тысяч (1 234 567)."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


@lru_cache(maxsize=36)
def get_rank_by_level(level: int) -> Dict[str, Any]:
    """Получить ранг по номеру уровня (1-36) с кэшированием."""
    if level < 1:
        level = 1
    if level > 36:
        level = 36
    return RANKS[level - 1].copy()


@lru_cache(maxsize=100)
def get_rank_by_xp(xp: int) -> Tuple[Dict[str, Any], int, int]:
    """Определить текущий ранг по XP с кэшированием."""
    current_rank = RANKS[0]
    next_rank = RANKS[1] if len(RANKS) > 1 else None
    
    for i, rank in enumerate(RANKS):
        if xp >= rank["xp_required"]:
            current_rank = rank
            next_rank = RANKS[i + 1] if i + 1 < len(RANKS) else None
        else:
            break
    
    xp_to_next = next_rank["xp_required"] - xp if next_rank else 0
    return current_rank.copy(), xp, xp_to_next


def calculate_level_progress(xp: int, current: Dict[str, Any], next_rank: Optional[Dict[str, Any]]) -> float:
    """Расчёт прогресса в процентах до следующего уровня."""
    if next_rank is None:
        return 100.0
    xp_range = next_rank["xp_required"] - current["xp_required"]
    if xp_range <= 0:
        return 100.0
    return min(100.0, max(0.0, (xp - current["xp_required"]) / xp_range * 100))


def generate_progress_bar(progress: float, length: int = 10) -> str:
    """Генерация прогресс-бара из символов █ и ░."""
    if length <= 0:
        return ""
    filled = int(length * progress / 100)
    return "█" * filled + "░" * (length - filled)


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

async def init_ranks_table() -> None:
    """Инициализация системы рангов. Вызывать ТОЛЬКО в on_startup() бота!"""
    if db is None:
        logger.warning("⚠️ Database not initialized, skipping ranks init")
        return
    
    try:
        row = await db._execute_with_retry(
            "SELECT xp, rank FROM users WHERE user_id = ?",
            (1,), fetch_one=True
        )
        if row is not None:
            logger.info("✅ Ranks system ready (using users.xp/users.rank)")
        else:
            logger.warning("⚠️ Could not verify ranks columns, proceeding anyway")
    except DatabaseError as e:
        logger.error(f"❌ Ranks init error: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error in ranks init: {e}")


# ==================== ПОЛУЧЕНИЕ РАНГА ====================

async def get_user_rank_data(user_id: int) -> Optional[Dict[str, Any]]:
    """Получение данных о ранге пользователя. Совместимо с database.py v3.3.1."""
    if db is None or user_id is None:
        return None
    
    try:
        if hasattr(db, 'get_user_rank') and callable(db.get_user_rank):
            return await db.get_user_rank(user_id)
        
        user = await db._execute_with_retry(
            "SELECT user_id, xp, rank FROM users WHERE user_id = ?",
            (user_id,), fetch_one=True
        )
        
        if user:
            rank_info = get_rank_by_level(user.get("rank", 1))
            return {
                "user_id": user_id,
                "xp": user.get("xp", 0) or 0,
                "level": user.get("rank", 1) or 1,
                "rank_name": rank_info["name"],
                "tier": rank_info["tier"],
            }
        
        return None
    except DatabaseError as e:
        logger.error(f"❌ Get rank error for {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error getting rank for {user_id}: {e}")
        return None


async def add_xp(user_id: int, amount: int, reason: str = "activity") -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Добавление XP пользователю с автоматическим пересчётом ранга."""
    if db is None or user_id is None or amount <= 0:
        return None, None
    
    try:
        current_data = await get_user_rank_data(user_id)
        if not current_data:
            return None, None
        
        old_level = current_data["level"]
        
        if hasattr(db, 'add_xp') and callable(db.add_xp):
            success = await db.add_xp(user_id, amount, reason)
            if success and hasattr(db, 'recalculate_user_rank'):
                await db.recalculate_user_rank(user_id)
        else:
            await db._execute_with_retry(
                "UPDATE users SET xp = COALESCE(xp, 0) + ? WHERE user_id = ?",
                (amount, user_id)
            )
            if hasattr(db, 'recalculate_user_rank'):
                await db.recalculate_user_rank(user_id)
        
        new_data = await get_user_rank_data(user_id)
        if not new_data:
            return None, None
        
        new_level = new_data["level"]
        
        if new_level > old_level:
            logger.info(f"⭐ User {user_id} leveled up: {old_level} -> {new_level}")
            return new_level, get_rank_by_level(new_level)
        
        return None, None
        
    except DatabaseError as e:
        logger.error(f"❌ Add XP error for {user_id}: {e}")
        return None, None
    except Exception as e:
        logger.error(f"❌ Unexpected error adding XP for {user_id}: {e}")
        return None, None


async def award_tier_reward(user_id: int, tier: str) -> bool:
    """Выдача награды за достижение нового тира."""
    if tier not in TIER_REWARDS:
        logger.warning(f"⚠️ Unknown tier: {tier}")
        return False
    
    reward = TIER_REWARDS[tier]
    
    try:
        if "coins" in reward and hasattr(db, 'update_balance'):
            await db.update_balance(user_id, reward["coins"], f"Награда за ранг: {tier}")
            logger.info(f"💰 Awarded {reward['coins']} coins to {user_id} for tier {tier}")
        
        if "vip_days" in reward:
            vip_until = (datetime.now() + timedelta(days=reward["vip_days"])).isoformat()
            await db._execute_with_retry(
                """UPDATE users SET vip_level = MAX(COALESCE(vip_level, 0), 1), 
                   vip_until = ? WHERE user_id = ?""",
                (vip_until, user_id)
            )
            logger.info(f"⭐ Awarded {reward['vip_days']} VIP days to {user_id} for tier {tier}")
        
        return True
    except DatabaseError as e:
        logger.error(f"❌ Award error for {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error awarding tier {tier} to {user_id}: {e}")
        return False


# ==================== ОТСЛЕЖИВАНИЕ АКТИВНОСТИ ====================

async def track_activity(user_id: int, action: str, value: int = 1) -> None:
    """Отслеживание активности пользователя и начисление XP."""
    if action not in XP_ACTIONS:
        return
    
    xp_amount = XP_ACTIONS[action] * value
    new_level, new_rank = await add_xp(user_id, xp_amount, action)
    
    if new_level and new_rank and new_rank["name"].endswith("I"):
        await award_tier_reward(user_id, new_rank["tier"])


async def track_message_activity(user_id: int, message: Message) -> None:
    """Определение типа сообщения и начисление соответствующего XP."""
    if message is None or (message.from_user and message.from_user.is_bot):
        return
    
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
    elif message.text and len(message.text.strip()) >= 3:
        await track_activity(user_id, "message")


async def track_game_result(user_id: int, won: bool) -> None:
    """Начисление XP за результат игры."""
    await track_activity(user_id, "game_win" if won else "game_loss")


async def track_daily_bonus(user_id: int) -> None:
    """Начисление XP за получение ежедневного бонуса."""
    await track_activity(user_id, "daily")


async def track_referral(user_id: int) -> None:
    """Начисление XP за приглашённого реферала."""
    await track_activity(user_id, "referral")


# ==================== КОМАНДЫ ====================

@router.message(Command("rank"))
async def cmd_rank(message: Message) -> None:
    """Показать ранг и прогресс пользователя."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    
    rank_data = await get_user_rank_data(user_id)
    if not rank_data:
        await message.answer("❌ Ошибка загрузки ранга. Попробуйте позже.")
        return
    
    xp = rank_data.get("xp", 0) or 0
    current_rank, _, xp_to_next = get_rank_by_xp(xp)
    next_level = current_rank["level"] + 1 if current_rank["level"] < 36 else None
    next_rank_data = RANKS[next_level - 1] if next_level else None
    
    progress = calculate_level_progress(xp, current_rank, next_rank_data)
    progress_bar = generate_progress_bar(progress)
    
    user = await db.get_user(user_id) if db else None
    first_name = safe_html_escape(
        user.get("first_name") if user and user.get("first_name") else message.from_user.first_name or "Игрок"
    )
    
    text = (
        f"{current_rank['icon']} <b>{current_rank['name']}</b>\n\n"
        f"👤 Игрок: {first_name}\n"
        f"📊 Уровень: <b>{current_rank['level']}/36</b>\n"
        f"✨ XP: <b>{format_number(xp)}</b>\n\n"
        f"📈 Прогресс:\n[{progress_bar}] {progress:.1f}%\n"
    )
    
    if next_rank_data:
        text += (
            f"⏫ Следующий: {next_rank_data['icon']} {next_rank_data['name']} "
            f"(ещё {format_number(xp_to_next)} XP)"
        )
    else:
        text += "🏆 <b>МАКСИМАЛЬНЫЙ УРОВЕНЬ!</b>"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 ТОП ИГРОКОВ", callback_data="top_ranks")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")],
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    logger.info(f"✅ Rank viewed by user {user_id}")


@router.message(Command("top_ranks"))
async def cmd_top_ranks(message: Message) -> None:
    """Показать топ-15 игроков по количеству опыта."""
    if not message:
        return
    
    try:
        if hasattr(db, 'get_top_users') and callable(db.get_top_users):
            rows = await db.get_top_users(limit=TOP_RANKS_LIMIT, order_by="xp")
        else:
            rows = await db._execute_with_retry(
                """SELECT u.user_id, u.xp, u.rank as level, u.first_name, u.username
                   FROM users u
                   WHERE COALESCE(u.xp, 0) > 0
                   ORDER BY u.xp DESC
                   LIMIT ?""",
                (TOP_RANKS_LIMIT,), fetch_all=True)
        
        if not rows:
            await message.answer("📊 Пока нет данных о рангах. Начните общаться в чате!")
            return
        
        text = "🏆 <b>ТОП-15 ИГРОКОВ ПО РАНГУ</b>\n\n"
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 16)]
        
        for i, row in enumerate(rows):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            name = safe_html_escape(
                (row.get("first_name") or row.get("username") or "Игрок")[:20]
            )
            level = row.get("level", 1) or 1
            rank_info = get_rank_by_level(level)
            xp = row.get("xp", 0) or 0
            text += (
                f"{medal} {rank_info['icon']} <b>{name}</b> — "
                f"{format_number(xp)} XP ({rank_info['name']})\n"
            )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")],
        ])
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        logger.info("✅ Top ranks viewed")
        
    except DatabaseError as e:
        logger.error(f"❌ Top ranks error: {e}")
        await message.answer("❌ Ошибка загрузки топа. Попробуйте позже.")
    except Exception as e:
        logger.error(f"❌ Unexpected error in top_ranks: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "rank_menu")
async def rank_menu_callback(callback: CallbackQuery) -> None:
    """Callback-хендлер для кнопки меню ранга."""
    if not callback or not callback.message or not callback.from_user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await cmd_rank(callback.message)
    await callback.answer()


@router.callback_query(F.data == "top_ranks")
async def top_ranks_callback(callback: CallbackQuery) -> None:
    """Callback-хендлер для кнопки топа рангов."""
    if not callback or not callback.message:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await cmd_top_ranks(callback.message)
    await callback.answer()
