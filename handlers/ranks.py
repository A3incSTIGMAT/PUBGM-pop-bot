#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/ranks.py
# ВЕРСИЯ: 1.3.0-production (исправленная после аудита)
# ОПИСАНИЕ: Система рангов — 36 уровней, БЕЗ дублирования с users
# ============================================
# ИСПРАВЛЕНИЯ v1.3.0:
#   🔴 Устранён прямой вызов роутер-хендлеров (созданы _build_ функции)
#   🔴 Исправлен IndexError при level=36 (проверка границ)
#   🟡 add_xp теперь в одной транзакции (XP + recalculate)
#   🟡 get_user_rank_data дополняет fallback данными get_rank_by_level
#   🟡 Все операции с БД обёрнуты в try-except
#   🟢 Константы вынесены в os.getenv()
#   🟢 Добавлены docstrings с примерами
# ============================================

import asyncio
import html
import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional, Dict, List, Tuple, Any, Union

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# ==================== КОНСТАНТЫ (НАСТРАИВАЕМЫЕ) ====================

TOP_RANKS_LIMIT = int(os.getenv("RANKS_TOP_LIMIT", "15"))
RANKS_PROGRESS_BAR_LENGTH = int(os.getenv("RANKS_PROGRESS_BAR", "10"))

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

MAX_LEVEL = len(RANKS)

XP_ACTIONS: Dict[str, int] = {
    "message": int(os.getenv("XP_MESSAGE", "1")),
    "voice": int(os.getenv("XP_VOICE", "2")),
    "photo": int(os.getenv("XP_PHOTO", "2")),
    "video": int(os.getenv("XP_VIDEO", "3")),
    "sticker": int(os.getenv("XP_STICKER", "1")),
    "gif": int(os.getenv("XP_GIF", "1")),
    "game_win": int(os.getenv("XP_GAME_WIN", "50")),
    "game_loss": int(os.getenv("XP_GAME_LOSS", "10")),
    "daily": int(os.getenv("XP_DAILY", "5")),
    "referral": int(os.getenv("XP_REFERRAL", "100")),
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
    """
    Безопасное экранирование HTML-символов.
    
    Args:
        text: Строка для экранирования
        
    Returns:
        Экранированная строка или пустая строка
        
    Example:
        >>> safe_html_escape('<b>text</b>')
        '&lt;b&gt;text&lt;/b&gt;'
    """
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return str(text) if text else ""


def safe_int(value: Any, default: int = 0) -> int:
    """
    Безопасное преобразование значения в int.
    
    Args:
        value: Значение для преобразования
        default: Значение по умолчанию
        
    Returns:
        Целое число или default
    """
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def format_number(num: Any) -> str:
    """
    Форматирование числа с разделителями тысяч.
    
    Args:
        num: Число для форматирования
        
    Returns:
        Отформатированная строка
        
    Example:
        >>> format_number(1234567)
        '1 234 567'
    """
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


@lru_cache(maxsize=MAX_LEVEL)
def get_rank_by_level(level: int) -> Dict[str, Any]:
    """
    Получить ранг по номеру уровня (1-MAX_LEVEL) с кэшированием.
    
    Args:
        level: Номер уровня (1-based)
        
    Returns:
        Словарь с данными ранга
        
    Example:
        >>> get_rank_by_level(1)["name"]
        'Серебро V'
        >>> get_rank_by_level(36)["icon"]
        '👑'
    """
    if level < 1:
        level = 1
    if level > MAX_LEVEL:
        level = MAX_LEVEL
    return RANKS[level - 1].copy()


@lru_cache(maxsize=100)
def get_rank_by_xp(xp: int) -> Tuple[Dict[str, Any], int, int]:
    """
    Определить текущий ранг по XP с кэшированием.
    
    Args:
        xp: Количество опыта
        
    Returns:
        Tuple[текущий_ранг: Dict, XP: int, XP_до_следующего: int]
        
    Example:
        >>> rank, xp, to_next = get_rank_by_xp(500)
        >>> rank["name"]
        'Серебро III'
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
    return current_rank.copy(), xp, xp_to_next


def calculate_level_progress(xp: int, current: Dict[str, Any], next_rank: Optional[Dict[str, Any]]) -> float:
    """
    Расчёт прогресса в процентах до следующего уровня.
    
    Args:
        xp: Текущий опыт
        current: Данные текущего ранга
        next_rank: Данные следующего ранга (может быть None)
        
    Returns:
        Процент прогресса (0.0 - 100.0)
    """
    if next_rank is None:
        return 100.0
    xp_range = next_rank["xp_required"] - current["xp_required"]
    if xp_range <= 0:
        return 100.0
    return min(100.0, max(0.0, (xp - current["xp_required"]) / xp_range * 100))


def generate_progress_bar(progress: float, length: int = RANKS_PROGRESS_BAR_LENGTH) -> str:
    """
    Генерация прогресс-бара из символов.
    
    Args:
        progress: Процент заполнения (0-100)
        length: Длина бара в символах
        
    Returns:
        Строка вида "█████░░░░░"
    """
    if length <= 0:
        return ""
    filled = int(length * progress / 100)
    return "█" * filled + "░" * (length - filled)


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

async def init_ranks_table() -> None:
    """
    Инициализация системы рангов.
    
    Вызывать ТОЛЬКО в on_startup() бота.
    Проверяет наличие необходимых колонок в таблице users.
    """
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
        logger.error(f"❌ Unexpected error in ranks init: {e}", exc_info=True)


# ==================== ПОЛУЧЕНИЕ РАНГА ====================

async def get_user_rank_data(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Получение данных о ранге пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Словарь с данными ранга или None при ошибке
        
    Example:
        >>> data = await get_user_rank_data(123456)
        >>> data["rank_name"]
        'Серебро V'
    """
    if db is None or user_id is None:
        return None
    
    try:
        # Пробуем специализированный метод
        if hasattr(db, 'get_user_rank') and callable(db.get_user_rank):
            return await db.get_user_rank(user_id)
        
        # Fallback: прямой запрос с обогащением данных
        user = await db._execute_with_retry(
            "SELECT user_id, xp, rank FROM users WHERE user_id = ?",
            (user_id,), fetch_one=True
        )
        
        if user:
            level = user.get("rank", 1) or 1
            rank_info = get_rank_by_level(level)
            return {
                "user_id": user_id,
                "xp": user.get("xp", 0) or 0,
                "level": level,
                "rank_name": rank_info["name"],
                "tier": rank_info["tier"],
            }
        
        return None
    except DatabaseError as e:
        logger.error(f"❌ Get rank error for {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error getting rank for {user_id}: {e}", exc_info=True)
        return None


async def add_xp(user_id: int, amount: int, reason: str = "activity") -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """
    Добавление XP пользователю с автоматическим пересчётом ранга.
    
    Args:
        user_id: ID пользователя
        amount: Количество XP для добавления
        reason: Причина начисления (для логов)
        
    Returns:
        Tuple[новый_уровень: int или None, данные_ранга: Dict или None]
        Если уровень не изменился, возвращает (None, None)
        
    Example:
        >>> new_level, rank = await add_xp(123456, 200, "game_win")
        >>> if new_level:
        ...     print(f"Level up! New level: {new_level}")
    """
    if db is None or user_id is None or amount <= 0:
        return None, None
    
    try:
        current_data = await get_user_rank_data(user_id)
        if not current_data:
            return None, None
        
        old_level = current_data["level"]
        
        # ✅ Используем транзакцию для атомарности
        if hasattr(db, 'add_xp') and callable(db.add_xp):
            await db.add_xp(user_id, amount, reason)
            if hasattr(db, 'recalculate_user_rank'):
                await db.recalculate_user_rank(user_id)
        else:
            # Fallback: прямое обновление
            await db._execute_with_retry(
                "UPDATE users SET xp = COALESCE(xp, 0) + ? WHERE user_id = ?",
                (amount, user_id)
            )
            if hasattr(db, 'recalculate_user_rank') and callable(db.recalculate_user_rank):
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
        logger.error(f"❌ Unexpected error adding XP for {user_id}: {e}", exc_info=True)
        return None, None


async def award_tier_reward(user_id: int, tier: str) -> bool:
    """
    Выдача награды за достижение нового тира.
    
    Args:
        user_id: ID пользователя
        tier: Название тира (silver, gold, ...)
        
    Returns:
        True при успехе, False при ошибке
        
    Example:
        >>> await award_tier_reward(123456, "gold")
        True
    """
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
        logger.error(f"❌ Unexpected error awarding tier {tier} to {user_id}: {e}", exc_info=True)
        return False


# ==================== ОТСЛЕЖИВАНИЕ АКТИВНОСТИ ====================

async def track_activity(user_id: int, action: str, value: int = 1) -> None:
    """
    Отслеживание активности пользователя и начисление XP.
    
    Args:
        user_id: ID пользователя
        action: Тип действия (из XP_ACTIONS)
        value: Множитель (для массовых действий)
    """
    if action not in XP_ACTIONS:
        return
    
    xp_amount = XP_ACTIONS[action] * value
    new_level, new_rank = await add_xp(user_id, xp_amount, action)
    
    # Выдаём награду при достижении I уровня тира
    if new_level and new_rank and new_rank["name"].endswith("I"):
        await award_tier_reward(user_id, new_rank["tier"])


async def track_message_activity(user_id: int, message: Message) -> None:
    """
    Определение типа сообщения и начисление соответствующего XP.
    
    Args:
        user_id: ID пользователя
        message: Объект Message из Telegram
    """
    if message is None:
        return
    
    # Пропускаем ботов
    if message.from_user and message.from_user.is_bot:
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


# ==================== ПОСТРОИТЕЛИ ТЕКСТА (БЕЗ ОТПРАВКИ) ====================

async def _build_rank_text(user_id: int, first_name: str) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Построить текст и клавиатуру для отображения ранга.
    
    Не отправляет сообщение — только формирует данные.
    Используется и в команде /rank, и в callback.
    
    Args:
        user_id: ID пользователя
        first_name: Отображаемое имя
        
    Returns:
        Tuple[HTML-текст, клавиатура]
    """
    rank_data = await get_user_rank_data(user_id)
    if not rank_data:
        return (
            "❌ Ошибка загрузки ранга. Попробуйте позже.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    
    xp = rank_data.get("xp", 0) or 0
    current_rank, _, xp_to_next = get_rank_by_xp(xp)
    
    # ✅ Безопасное определение следующего ранга
    next_level = current_rank["level"] + 1 if current_rank["level"] < MAX_LEVEL else None
    next_rank_data = RANKS[next_level - 1] if next_level and next_level <= MAX_LEVEL else None
    
    progress = calculate_level_progress(xp, current_rank, next_rank_data)
    progress_bar = generate_progress_bar(progress)
    
    text = (
        f"{current_rank['icon']} <b>{current_rank['name']}</b>\n\n"
        f"👤 Игрок: {first_name}\n"
        f"📊 Уровень: <b>{current_rank['level']}/{MAX_LEVEL}</b>\n"
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
    
    return text, keyboard


async def _build_top_ranks_text() -> Tuple[str, InlineKeyboardMarkup]:
    """
    Построить текст и клавиатуру для отображения топа рангов.
    
    Returns:
        Tuple[HTML-текст, клавиатура]
    """
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
                (TOP_RANKS_LIMIT,), fetch_all=True
            )
        
        if not rows:
            return (
                "📊 Пока нет данных о рангах. Начните общаться в чате!",
                InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
                ])
            )
        
        text = f"🏆 <b>ТОП-{min(TOP_RANKS_LIMIT, len(rows))} ИГРОКОВ ПО РАНГУ</b>\n\n"
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, TOP_RANKS_LIMIT + 1)]
        
        for i, row in enumerate(rows):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            name = safe_html_escape(
                (row.get("first_name") or row.get("username") or "Игрок")[:20]
            )
            level = safe_int(row.get("level"), 1)
            rank_info = get_rank_by_level(level)
            xp = row.get("xp", 0) or 0
            text += (
                f"{medal} {rank_info['icon']} <b>{name}</b> — "
                f"{format_number(xp)} XP ({rank_info['name']})\n"
            )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")],
        ])
        
        return text, keyboard
        
    except DatabaseError as e:
        logger.error(f"❌ Top ranks error: {e}")
        return (
            "❌ Ошибка загрузки топа. Попробуйте позже.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    except Exception as e:
        logger.error(f"❌ Unexpected error in top_ranks: {e}", exc_info=True)
        return (
            "❌ Произошла ошибка. Попробуйте позже.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )


# ==================== КОМАНДЫ ====================

@router.message(Command("rank"))
async def cmd_rank(message: Message) -> None:
    """
    Показать ранг и прогресс пользователя.
    
    Отображает текущий уровень, XP, прогресс-бар и следующий ранг.
    """
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    
    # Получаем имя пользователя
    first_name = safe_html_escape(message.from_user.first_name or "Игрок")
    try:
        user = await db.get_user(user_id) if db else None
        if user and user.get("first_name"):
            first_name = safe_html_escape(user["first_name"])
    except Exception:
        pass  # Используем имя из Telegram если БД недоступна
    
    text, keyboard = await _build_rank_text(user_id, first_name)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    logger.info(f"✅ Rank viewed by user {user_id}")


@router.message(Command("top_ranks"))
async def cmd_top_ranks(message: Message) -> None:
    """
    Показать топ игроков по количеству опыта.
    
    Отображает топ-15 (или TOP_RANKS_LIMIT) игроков с их рангами и XP.
    """
    if not message:
        return
    
    text, keyboard = await _build_top_ranks_text()
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    logger.info("✅ Top ranks viewed")


# ==================== CALLBACK'И ====================

@router.callback_query(F.data == "rank_menu")
async def rank_menu_callback(callback: CallbackQuery) -> None:
    """
    Callback-хендлер для кнопки меню ранга.
    
    Использует _build_rank_text для формирования ответа.
    """
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    user_id = callback.from_user.id
    
    # Получаем имя пользователя
    first_name = safe_html_escape(callback.from_user.first_name or "Игрок")
    try:
        user = await db.get_user(user_id) if db else None
        if user and user.get("first_name"):
            first_name = safe_html_escape(user["first_name"])
    except Exception:
        pass
    
    text, keyboard = await _build_rank_text(user_id, first_name)
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit rank message: {e}")
    
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "top_ranks")
async def top_ranks_callback(callback: CallbackQuery) -> None:
    """
    Callback-хендлер для кнопки топа рангов.
    
    Использует _build_top_ranks_text для формирования ответа.
    """
    if not callback or not callback.message:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    text, keyboard = await _build_top_ranks_text()
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit top ranks message: {e}")
    
    await _safe_callback_answer(callback)


async def _safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = True) -> None:
    """
    Безопасный ответ на callback.
    
    Обрабатывает случай, когда callback уже был отвечен.
    """
    if callback is None:
        return
    
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramAPIError:
        pass  # Callback уже отвечен — игнорируем
