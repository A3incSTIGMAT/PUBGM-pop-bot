#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/vip.py
# ВЕРСИЯ: 3.2.5-production (исправленная)
# ОПИСАНИЕ: VIP-модуль с интеграцией всех рекомендаций
# ИСПРАВЛЕНИЯ v3.2.5:
#   ✅ Исправлен SyntaxError: def _parse_buy_vip_callback( str) → (data: str)
#   ✅ Исправлен SyntaxError: if full_ → if full_data
#   ✅ Возврат Optional[Tuple] в get_user_full_data
#   ✅ Все f-строки без \n (Python 3.9+)
# ============================================

import html
import logging
import math
import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple, Deque

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db, DatabaseError
from config import START_BALANCE

# Метрики (graceful fallback)
try:
    from prometheus_client import Counter, Histogram
    _METRICS_AVAILABLE = True
    vip_purchase_counter = Counter('vip_purchases_total', 'Total VIP purchases', ['level', 'status', 'user_tier'])
    vip_purchase_duration = Histogram('vip_purchase_duration_seconds', 'Time spent on VIP purchase', ['level'])
    cache_invalidate_counter = Counter('cache_invalidations_total', 'Cache invalidation attempts', ['status'])
    rate_limit_counter = Counter('rate_limit_exceeded_total', 'Rate limit exceeded attempts', ['endpoint'])
except ImportError:
    _METRICS_AVAILABLE = False
    vip_purchase_counter = None
    vip_purchase_duration = None
    cache_invalidate_counter = None
    rate_limit_counter = None

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

VIP_PRICES = {1: 500, 2: 1000, 3: 2000, 4: 5000, 5: 10000}
VIP_DURATION_DAYS = 30
MAX_VIP_LEVEL = 5
MIN_VIP_LEVEL = 1

VIP_NAMES: Dict[int, Dict[str, object]] = {
    1: {"name": "🥉 Бронза", "win_bonus": 5, "daily_bonus": 50, "icon": "🥉", "wins_required": 10},
    2: {"name": "🥈 Серебро", "win_bonus": 10, "daily_bonus": 100, "icon": "🥈", "wins_required": 50},
    3: {"name": "🥇 Золото", "win_bonus": 15, "daily_bonus": 150, "icon": "🥇", "wins_required": 100},
    4: {"name": "💎 Платина", "win_bonus": 20, "daily_bonus": 200, "icon": "💎", "wins_required": 200},
    5: {"name": "💠 Алмаз", "win_bonus": 30, "daily_bonus": 300, "icon": "💠", "wins_required": 500},
}

_VIP_THRESHOLDS: list = sorted(
    [(lvl, int(VIP_NAMES[lvl]['wins_required'])) for lvl in VIP_NAMES],
    key=lambda x: x[1]
)
_MAX_WINS_REQUIRED: int = max(int(VIP_NAMES[lvl]['wins_required']) for lvl in VIP_NAMES)


def _validate_vip_config() -> None:
    """Расширенная валидация конфигурации при импорте."""
    errors = []
    
    if set(VIP_PRICES.keys()) != set(VIP_NAMES.keys()):
        errors.append("VIP_PRICES и VIP_NAMES содержат разные уровни")
    
    prev_wins = 0
    for level in sorted(VIP_NAMES.keys()):
        price = VIP_PRICES.get(level)
        if price is None or not isinstance(price, int) or price <= 0:
            errors.append("Invalid price for level " + str(level) + ": " + str(price))
        
        cfg = VIP_NAMES[level]
        wins_req = cfg.get('wins_required', 0)
        
        if not isinstance(wins_req, int) or wins_req <= 0:
            errors.append("wins_required for level " + str(level) + " must be > 0, got " + str(wins_req))
        elif wins_req <= prev_wins:
            errors.append(
                "wins_required for level " + str(level) + " must be > "
                + str(prev_wins) + ", got " + str(wins_req)
            )
        
        prev_wins = wins_req
    
    if errors:
        error_msg = "VIP config validation FAILED: " + "; ".join(errors)
        logger.critical(error_msg)
        raise ValueError(error_msg)

_validate_vip_config()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception as e:
        logger.warning("HTML escape failed: %s", e)
        return "[ошибка]"


def format_number(num: Optional[int]) -> str:
    """Форматирование числа с разделителями."""
    if num is None:
        return "0"
    try:
        value = int(num)
        if value < 0:
            return "-" + f"{abs(value):,}".replace(",", " ")
        return f"{value:,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def get_vip_expiry_date(days: int = VIP_DURATION_DAYS) -> str:
    """Расчёт даты окончания VIP (UTC)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def format_vip_date(vip_until: Optional[str]) -> str:
    """Форматирование даты окончания VIP."""
    if not vip_until:
        return "Бессрочно"
    try:
        dt = datetime.fromisoformat(str(vip_until).replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return "Бессрочно"


# Rate Limiting
_user_request_times: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=15))

def _check_rate_limit(user_id: int, max_requests: int = 5, window_sec: int = 10) -> bool:
    """Проверка лимита запросов."""
    now = time.monotonic()
    requests = _user_request_times[user_id]
    
    while requests and requests[0] < now - window_sec:
        requests.popleft()
    
    if len(requests) >= max_requests:
        if _METRICS_AVAILABLE:
            rate_limit_counter.labels(endpoint="vip_handlers").inc()
        return False
    
    requests.append(now)
    return True


async def invalidate_user_cache(user_id: int, max_retries: int = 3) -> bool:
    """Инвалидация кэша с retry."""
    for attempt in range(max_retries):
        try:
            if hasattr(db, '_invalidate_stats_cache'):
                await db._invalidate_stats_cache(user_id)
                if _METRICS_AVAILABLE:
                    cache_invalidate_counter.labels(status='success').inc()
                return True
            else:
                logger.warning("_invalidate_stats_cache not found in db")
                if _METRICS_AVAILABLE:
                    cache_invalidate_counter.labels(status='method_missing').inc()
                return False
        except Exception as e:
            delay = 0.1 * (2 ** attempt)
            logger.warning(
                "Cache invalidation failed for user %s (attempt %d/%d): %s",
                user_id, attempt + 1, max_retries, e
            )
            await asyncio.sleep(delay)
    
    logger.error("Cache invalidation permanently failed for user %s", user_id)
    if _METRICS_AVAILABLE:
        cache_invalidate_counter.labels(status='error').inc()
    return False


async def get_or_create_user(
    user_id: int, username: Optional[str] = None, first_name: Optional[str] = None
) -> Optional[Dict]:
    """Получить или создать пользователя."""
    if user_id is None:
        return None
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            if user:
                logger.info("Created user %s in vip module", user_id)
        return user
    except DatabaseError as e:
        logger.error("DB error in get_or_create_user for %s: %s", user_id, e)
        return None


async def get_user_full_data(user_id: int) -> Optional[Tuple[int, int, int, int]]:
    """Единый источник статистики. Возвращает None при ошибке."""
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return (
                stats.get('balance', 0) or 0,
                stats.get('wins', 0) or 0,
                stats.get('losses', 0) or 0,
                stats.get('games_played', 0) or 0
            )
        logger.warning("No stats found for user %s", user_id)
        return None
    except DatabaseError as e:
        logger.error("Error getting stats for %s: %s", user_id, e)
        return None
    except Exception as e:
        logger.error("Unexpected error in get_user_full_data: %s", e)
        return None


async def get_user_with_stats(user_id: int) -> Tuple[Optional[Dict], int, int, int, int]:
    """Объединённый запрос: пользователь + статистика."""
    if user_id is None:
        return None, 0, 0, 0, 0
    
    user = await get_or_create_user(user_id)
    if not user:
        return None, 0, 0, 0, 0
    
    full_data = await get_user_full_data(user_id)
    # ✅ Исправлено: if full_ → if full_data
    if full_data:
        return user, full_data[0], full_data[1], full_data[2], full_data[3]
    
    return user, 0, 0, 0, 0


async def update_user_vip(user_id: int, vip_level: int, days: int = VIP_DURATION_DAYS) -> bool:
    """Обновление VIP статуса."""
    if user_id is None or not (MIN_VIP_LEVEL <= vip_level <= MAX_VIP_LEVEL):
        return False
    try:
        new_until = get_vip_expiry_date(days)
        await db._execute_with_retry(
            "UPDATE users SET vip_level = ?, vip_until = ? WHERE user_id = ?",
            (vip_level, new_until, user_id)
        )
        await invalidate_user_cache(user_id)
        logger.info("Updated VIP for user %s to level %s", user_id, vip_level)
        return True
    except DatabaseError as e:
        logger.error("Failed to update VIP for %s: %s", user_id, e)
        return False


async def check_and_award_achievement_vip(user_id: int, wins: int) -> Optional[int]:
    """Атомарная выдача VIP за достижения."""
    vip_level = 0
    for level in sorted(VIP_NAMES.keys()):
        if wins >= int(VIP_NAMES[level]['wins_required']):
            vip_level = level
    
    if vip_level <= 0:
        return None
    
    try:
        new_until = get_vip_expiry_date(VIP_DURATION_DAYS)
        queries = [
            ("UPDATE users SET vip_level = ?, vip_until = ? "
             "WHERE user_id = ? AND (vip_level IS NULL OR vip_level < ?)",
             (vip_level, new_until, user_id, vip_level)),
        ]
        if await db._execute_transaction(queries):
            await invalidate_user_cache(user_id)
            logger.info("Awarded VIP level %s to user %s (wins: %s)", vip_level, user_id, wins)
            return vip_level
        return None
    except DatabaseError as e:
        logger.error("Failed to award VIP to %s: %s", user_id, e)
    return None


# ✅ Исправлено: def _parse_buy_vip_callback( str) → (data: str)
def _parse_buy_vip_callback(data: str) -> Optional[int]:
    """Безопасный парсинг callback_data."""
    if not data or not isinstance(data, str):
        return None
    parts = data.split("_")
    if len(parts) != 3 or parts[0] != "buy" or parts[1] != "vip":
        return None
    try:
        level = int(parts[2])
        return level if level in VIP_PRICES else None
    except ValueError:
        return None


def get_vip_privileges(vip_level: int) -> Dict:
    """Получить привилегии уровня."""
    return VIP_NAMES.get(vip_level, VIP_NAMES[1])


# ==================== ФОРМАТИРОВАНИЕ ====================

def format_vip_active(vip_level: int, balance: int, wins: int, losses: int, vip_until: str) -> str:
    """Форматирование активного VIP статуса."""
    priv = get_vip_privileges(vip_level)
    icon = str(priv.get('icon', ''))
    name = str(priv.get('name', ''))
    wb = str(priv.get('win_bonus', 0))
    db_bonus = str(priv.get('daily_bonus', 0))
    
    return (
        icon + " <b>ВАШ VIP СТАТУС</b> " + icon + "\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📛 Уровень: <b>" + name + "</b> (Уровень " + str(vip_level) + ")\n"
        "💰 Баланс: <b>" + format_number(balance) + "</b> NCoins\n"
        "📅 Действует до: " + safe_html_escape(format_vip_date(vip_until)) + "\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 <b>Статистика XO:</b>\n"
        "├ 🏆 Побед: " + str(wins) + "\n"
        "└ 📉 Поражений: " + str(losses) + "\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>✨ ВАШИ ПРЕИМУЩЕСТВА:</b>\n\n"
        "├ 🎮 +" + wb + "% к выигрышам\n"
        "├ 🎁 +" + db_bonus + " NCoins к бонусу\n"
        "├ 👑 Статус в чате\n"
        "├ 💎 Доступ к VIP-комнатам\n"
        "└ ⭐ Приоритетная поддержка"
    )


def format_vip_catalog(balance: int, wins: int, losses: int, games: int) -> str:
    """Форматирование каталога VIP статусов."""
    winrate = (wins / games * 100) if games > 0 else 0
    
    text = (
        "⭐ <b>VIP СТАТУСЫ NEXUS</b> ⭐\n\n"
        "Получите эксклюзивные преимущества!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>Баланс: " + format_number(balance) + " NCoins</b>\n"
        "🏆 <b>Побед: " + str(wins) + "</b> | 📉 <b>Поражений: " + str(losses) + "</b>\n"
        "📊 <b>Винрейт: " + str(round(winrate, 1)) + "%</b> (" + str(games) + " игр)\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for level in sorted(VIP_NAMES.keys()):
        name = str(VIP_NAMES[level].get('name', ''))
        price = VIP_PRICES[level]
        wb = str(VIP_NAMES[level].get('win_bonus', 0))
        db_bonus = str(VIP_NAMES[level].get('daily_bonus', 0))
        text += (
            name + " (" + str(level) + " ур.) — " + format_number(price) + " NCoins\n"
            "├ 🎮 +" + wb + "% к выигрышам\n"
            "└ 🎁 +" + db_bonus + " NCoins к бонусу\n\n"
        )
    
    text += (
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 <b>БЕСПЛАТНЫЙ VIP ЗА ПОБЕДЫ В XO:</b>\n"
    )
    for level in sorted(VIP_NAMES.keys()):
        if level >= MAX_VIP_LEVEL:
            break
        text += (
            "├ " + str(VIP_NAMES[level].get('wins_required', 0))
            + " побед → " + str(VIP_NAMES[level].get('name', '')) + "\n"
        )
    text += (
        "└ " + str(VIP_NAMES[MAX_VIP_LEVEL].get('wins_required', 0))
        + " побед → " + str(VIP_NAMES[MAX_VIP_LEVEL].get('name', '')) + "\n\n"
        "📊 <b>Ваш прогресс: " + str(wins) + " побед</b>"
    )
    return text


def format_achievements(
    balance: int, wins: int, losses: int, games: int,
    current_vip: int, awarded_vip: Optional[int] = None
) -> str:
    """Форматирование достижений."""
    winrate = (wins / games * 100) if games > 0 else 0
    next_level = None
    next_wins = 0
    progress = 0
    
    for i, (level, required) in enumerate(_VIP_THRESHOLDS):
        if wins < required:
            next_level = VIP_NAMES[level].get('name', '')
            next_wins = required
            prev = _VIP_THRESHOLDS[i - 1][1] if i > 0 else 0
            progress = max(0, min(100, int(((wins - prev) / (required - prev)) * 100)))
            break
    
    if next_level is None:
        progress = 100
    
    filled = math.ceil(10 * progress / 100)
    filled = min(filled, 10)
    progress_bar = "█" * filled + "░" * (10 - filled)
    
    status_msg = ""
    if awarded_vip:
        status_msg = (
            "✨ <b>Только что получен VIP " + str(awarded_vip) + " уровня!</b>\n\n"
        )
    
    progress_msg = ""
    if next_level and wins < _MAX_WINS_REQUIRED:
        progress_msg = (
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📈 <b>ДО СЛЕДУЮЩЕГО УРОВНЯ:</b>\n\n"
            "Цель: <b>" + str(next_level) + "</b>\n"
            "Прогресс: " + str(wins) + "/" + str(next_wins) + " побед\n"
            "[" + progress_bar + "] " + str(progress) + "%\n\n"
            "💪 Осталось <b>" + str(next_wins - wins) + "</b> побед!\n"
        )
    
    rewards_lines = []
    for lvl in sorted(VIP_NAMES.keys()):
        icon = str(VIP_NAMES[lvl].get('icon', ''))
        wr = str(VIP_NAMES[lvl].get('wins_required', 0))
        name = str(VIP_NAMES[lvl].get('name', ''))
        rewards_lines.append(icon + " " + wr + " побед → " + name + " VIP")
    rewards = "\n".join(rewards_lines)
    
    return (
        "🏆 <b>БЕСПЛАТНЫЙ VIP ЗА ДОСТИЖЕНИЯ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 <b>ВАША СТАТИСТИКА XO:</b>\n\n"
        "💰 Баланс: <b>" + format_number(balance) + " NCoins</b>\n"
        "🏆 Побед: <b>" + str(wins) + "</b>\n"
        "📉 Поражений: <b>" + str(losses) + "</b>\n"
        "📊 Винрейт: <b>" + str(round(winrate, 1)) + "%</b> (" + str(games) + " игр)\n"
        "⭐ Текущий VIP: <b>" + str(current_vip) + " уровень</b>\n\n"
        + status_msg + progress_msg
        + "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>ДОСТУПНЫЕ НАГРАДЫ:</b>\n\n"
        + rewards
    )


# ==================== ОБРАБОТЧИКИ ====================

@router.message(Command("vip"))
async def cmd_vip(message: Message) -> None:
    """Показать VIP меню."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    user, balance, wins, losses, games = await get_user_with_stats(user_id)
    
    if not user:
        await message.answer("❌ Ошибка доступа.")
        return
    
    try:
        vip_level = max(0, user.get('vip_level', 0) or 0)
        vip_until = str(user.get('vip_until', ''))
        
        awarded_vip = None
        if vip_level < MAX_VIP_LEVEL and wins > 0:
            awarded_vip = await check_and_award_achievement_vip(user_id, wins)
            if awarded_vip:
                vip_level = awarded_vip
                updated_user = await db.get_user(user_id)
                if updated_user:
                    vip_level = max(vip_level, updated_user.get('vip_level', 0) or 0)
        
        if vip_level > 0:
            text = format_vip_active(vip_level, balance, wins, losses, vip_until)
        else:
            text = format_vip_catalog(balance, wins, losses, games)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 КУПИТЬ VIP", callback_data="buy_vip")],
            [InlineKeyboardButton(text="🏆 МОИ ДОСТИЖЕНИЯ", callback_data="vip_achievements")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        logger.info("VIP menu viewed by user %s (level: %s)", user_id, vip_level)
        
    except DatabaseError as e:
        logger.error("DB error in cmd_vip for %s: %s", user_id, e)
        await message.answer("❌ Ошибка загрузки VIP меню.")
    except Exception as e:
        logger.error("Unexpected error in cmd_vip: %s", e, exc_info=True)
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
    if not callback or not callback.message:
        return
    
    user_id = callback.from_user.id
    user, balance, _, _, _ = await get_user_with_stats(user_id)
    
    if not user:
        await callback.answer("❌ Ошибка БД", show_alert=True)
        return
    
    try:
        current_vip = max(0, user.get('vip_level', 0) or 0)
        buttons = []
        
        for level in sorted(VIP_PRICES.keys()):
            if level <= current_vip:
                continue
            name = str(VIP_NAMES[level].get('name', ''))
            price = VIP_PRICES[level]
            afford_mark = "" if balance >= price else " 🔒"
            buttons.append([
                InlineKeyboardButton(
                    text=name + " — " + format_number(price) + " NCoins" + afford_mark,
                    callback_data="buy_vip_" + str(level)
                )
            ])
        
        if not buttons:
            buttons.append([
                InlineKeyboardButton(text="✅ Все уровни куплены!", callback_data="vip")
            ])
        buttons.append([
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")
        ])
        
        text = (
            "💎 <b>ПОКУПКА VIP</b>\n\n"
            "💰 Баланс: <b>" + format_number(balance) + " NCoins</b>\n"
            "⭐ Текущий VIP: <b>" + str(current_vip) + " уровень</b>\n\n"
            "Выберите уровень:\n"
            "💡 VIP действует " + str(VIP_DURATION_DAYS) + " дней\n"
            "🔒 — недостаточно средств"
        )
        
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error("DB error in buy_vip_menu for %s: %s", user_id, e)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("buy_vip_"))
async def buy_vip(callback: CallbackQuery) -> None:
    """Покупка VIP уровня."""
    if not callback or not callback.message:
        return
    
    user_id = callback.from_user.id
    
    if not _check_rate_limit(user_id):
        await callback.answer("⏳ Пожалуйста, подождите перед следующим запросом", show_alert=True)
        return
    
    level = _parse_buy_vip_callback(callback.data)
    if level is None:
        logger.warning("Invalid buy_vip callback from user %s: %s", user_id, callback.data)
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return
    
    user, balance, _, _, _ = await get_user_with_stats(user_id)
    if not user:
        await callback.answer("❌ Ошибка БД", show_alert=True)
        return
    
    current_vip = max(0, user.get('vip_level', 0) or 0)
    if level <= current_vip:
        name = str(VIP_NAMES.get(current_vip, {}).get('name', str(current_vip)))
        await callback.answer(
            "❌ У вас уже есть VIP " + name + "! Купите более высокий уровень.",
            show_alert=True
        )
        return
    
    price = VIP_PRICES[level]
    if balance < price:
        await callback.answer(
            "❌ Недостаточно средств!\n"
            "Нужно: " + format_number(price) + " NCoins\n"
            "Баланс: " + format_number(balance) + " NCoins",
            show_alert=True
        )
        return
    
    if _METRICS_AVAILABLE:
        with vip_purchase_duration.labels(level=str(level)).time():
            success = await _process_vip_purchase(user_id, level, price, current_vip, balance, callback)
    else:
        success = await _process_vip_purchase(user_id, level, price, current_vip, balance, callback)
    
    if _METRICS_AVAILABLE:
        status = 'success' if success else 'failed'
        tier = 'vip' if current_vip > 0 else 'free'
        vip_purchase_counter.labels(level=str(level), status=status, user_tier=tier).inc()
    
    await callback.answer()


async def _process_vip_purchase(
    user_id: int, level: int, price: int,
    current_vip: int, old_balance: int, callback: CallbackQuery
) -> bool:
    """Внутренняя логика покупки (атомарная транзакция)."""
    try:
        new_until = get_vip_expiry_date(VIP_DURATION_DAYS)
        queries = [
            ("UPDATE users SET balance = balance - ? WHERE user_id = ?",
             (price, user_id)),
            ("UPDATE users SET vip_level = ?, vip_until = ? "
             "WHERE user_id = ? AND (vip_level IS NULL OR vip_level < ?)",
             (level, new_until, user_id, level)),
            ("INSERT INTO transactions (from_id, to_id, amount, reason, date) "
             "VALUES (?, ?, ?, ?, ?)",
             (user_id, user_id, price,
              "Покупка VIP уровня " + str(level),
              datetime.now(timezone.utc).isoformat())),
        ]
        
        success = await db._execute_transaction(queries)
        
        if not success:
            await callback.answer("❌ Ошибка транзакции: не удалось завершить покупку", show_alert=True)
            return False
        
        await invalidate_user_cache(user_id)
        
        _, new_balance, _, _, _ = await get_user_with_stats(user_id)
        priv = get_vip_privileges(level)
        icon = str(priv.get('icon', ''))
        name = str(priv.get('name', ''))
        wb = str(priv.get('win_bonus', 0))
        db_bonus = str(priv.get('daily_bonus', 0))
        
        text = (
            "🎉 <b>ПОЗДРАВЛЯЕМ С ПОКУПКОЙ VIP!</b>\n\n"
            + icon + " Новый уровень: <b>" + name + "</b>\n"
            "💰 Списано: <b>" + format_number(price) + " NCoins</b>\n"
            "💎 Новый баланс: <b>" + format_number(new_balance) + " NCoins</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>✨ НОВЫЕ ПРЕИМУЩЕСТВА:</b>\n"
            "├ 🎮 +" + wb + "% к выигрышам\n"
            "├ 🎁 +" + db_bonus + " NCoins к бонусу\n"
            "├ 👑 Статус в чате\n"
            "├ 💎 Доступ к VIP-комнатам\n"
            "└ ⭐ Приоритетная поддержка\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📅 Статус действует <b>" + str(VIP_DURATION_DAYS) + " дней</b>"
        )
        
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ПОНЯТНО", callback_data="vip")]
            ])
        )
        logger.info(
            "User %s purchased VIP %s for %s NC (bal: %s → %s)",
            user_id, level, price, old_balance, new_balance
        )
        return True
        
    except DatabaseError as e:
        code = getattr(e, 'code', getattr(e, 'pgcode', 'DB_UNKNOWN'))
        logger.error(
            "VIP purchase DB error: user=%s, [%s] %s | lvl=%s, price=%s",
            user_id, code, e, level, price, exc_info=True
        )
        await callback.answer("❌ Ошибка базы данных: " + str(code), show_alert=True)
        return False
    except Exception as e:
        logger.critical(
            "UNEXPECTED in VIP purchase: user=%s, data=%s | %s: %s",
            user_id, callback.data, type(e).__name__, e, exc_info=True
        )
        await callback.answer("❌ Внутренняя ошибка. Администратор уведомлен.", show_alert=True)
        return False


@router.callback_query(F.data == "vip_achievements")
async def vip_achievements(callback: CallbackQuery) -> None:
    """Показать достижения пользователя."""
    if not callback or not callback.message:
        return
    
    user_id = callback.from_user.id
    user, balance, wins, losses, games = await get_user_with_stats(user_id)
    
    if not user:
        await callback.answer("❌ Ошибка БД", show_alert=True)
        return
    
    try:
        current_vip = max(0, user.get('vip_level', 0) or 0)
        
        awarded_vip = None
        if wins > 0 and current_vip < MAX_VIP_LEVEL:
            awarded_vip = await check_and_award_achievement_vip(user_id, wins)
            if awarded_vip:
                current_vip = awarded_vip
        
        text = format_achievements(balance, wins, losses, games, current_vip, awarded_vip)
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
            ])
        )
        await callback.answer()
        logger.info("Achievements viewed: user=%s, wins=%s, vip=%s", user_id, wins, current_vip)
        
    except DatabaseError as e:
        code = getattr(e, 'code', getattr(e, 'pgcode', 'DB_UNKNOWN'))
        logger.error("DB error in vip_achievements: [%s] %s", code, e)
        await callback.answer("❌ Ошибка загрузки: " + str(code), show_alert=True)
    except Exception as e:
        logger.error("Unexpected error in vip_achievements: %s", e, exc_info=True)
        await callback.answer("❌ Произошла ошибка", show_alert=True)
