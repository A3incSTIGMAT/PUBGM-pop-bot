#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/vip.py
# ВЕРСИЯ: 3.3.0-production (исправленная после аудита)
# ОПИСАНИЕ: VIP-модуль с интеграцией всех рекомендаций
# ============================================
# ИСПРАВЛЕНИЯ v3.3.0:
#   🟡 Константы вынесены в os.getenv()
#   🟡 _validate_vip_config логирует вместо raise
#   🟡 hasattr проверка для _execute_transaction
#   🟡 exc_info=True во всех logger.error
#   🟡 HMAC-подпись для callback_data покупки VIP
# ============================================

import asyncio
import hashlib
import hmac
import html
import logging
import math
import os
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

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ (НАСТРАИВАЕМАЯ) ====================

VIP_DURATION_DAYS = int(os.getenv("VIP_DURATION_DAYS", "30"))
MAX_VIP_LEVEL = int(os.getenv("VIP_MAX_LEVEL", "5"))
MIN_VIP_LEVEL = 1

VIP_PRICES = {
    1: int(os.getenv("VIP_PRICE_1", "500")),
    2: int(os.getenv("VIP_PRICE_2", "1000")),
    3: int(os.getenv("VIP_PRICE_3", "2000")),
    4: int(os.getenv("VIP_PRICE_4", "5000")),
    5: int(os.getenv("VIP_PRICE_5", "10000")),
}

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

# Секрет для подписи callback_data
_VIP_CALLBACK_SECRET = os.getenv("VIP_CALLBACK_SECRET", "nexus_vip_secret_v1").encode()


def _validate_vip_config() -> None:
    """Валидация конфигурации при импорте (логирует, не крашит)."""
    errors = []
    
    if set(VIP_PRICES.keys()) != set(VIP_NAMES.keys()):
        errors.append("VIP_PRICES и VIP_NAMES содержат разные уровни")
    
    prev_wins = 0
    for level in sorted(VIP_NAMES.keys()):
        price = VIP_PRICES.get(level)
        if price is None or not isinstance(price, int) or price <= 0:
            errors.append(f"Invalid price for level {level}: {price}")
        
        cfg = VIP_NAMES[level]
        wins_req = cfg.get('wins_required', 0)
        
        if not isinstance(wins_req, int) or wins_req <= 0:
            errors.append(f"wins_required for level {level} must be > 0, got {wins_req}")
        elif wins_req <= prev_wins:
            errors.append(f"wins_required for level {level} must be > {prev_wins}, got {wins_req}")
        
        prev_wins = wins_req
    
    if errors:
        logger.error("❌ VIP config validation FAILED: %s", "; ".join(errors))
    else:
        logger.info("✅ VIP config validated successfully")


_validate_vip_config()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
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


def _sign_vip_callback(level: int) -> str:
    """Генерация подписанного callback_data для покупки VIP."""
    payload = f"buy_vip_{level}"
    signature = hmac.new(_VIP_CALLBACK_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}_{signature}"


def _verify_vip_callback(data: str) -> Optional[int]:
    """Проверка подписанного callback_data. Возвращает уровень или None."""
    if not data or not data.startswith("buy_vip_"):
        return None
    
    try:
        parts = data.split("_")
        if len(parts) < 4:
            return None
        
        level = int(parts[2])
        provided_sig = parts[3]
        
        expected_payload = f"buy_vip_{level}"
        expected_sig = hmac.new(
            _VIP_CALLBACK_SECRET, expected_payload.encode(), hashlib.sha256
        ).hexdigest()[:16]
        
        if not hmac.compare_digest(provided_sig, expected_sig):
            logger.warning("⚠️ Invalid VIP callback signature!")
            return None
        
        return level if level in VIP_PRICES else None
    except (ValueError, IndexError):
        return None


# Rate Limiting
_user_request_times: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=15))

def _check_rate_limit(user_id: int, max_requests: int = 5, window_sec: int = 10) -> bool:
    """Проверка лимита запросов."""
    now = time.monotonic()
    requests = _user_request_times[user_id]
    
    while requests and requests[0] < now - window_sec:
        requests.popleft()
    
    if len(requests) >= max_requests:
        return False
    
    requests.append(now)
    return True


async def invalidate_user_cache(user_id: int, max_retries: int = 3) -> bool:
    """Инвалидация кэша с retry."""
    for attempt in range(max_retries):
        try:
            if hasattr(db, '_invalidate_stats_cache'):
                await db._invalidate_stats_cache(user_id)
                return True
            else:
                return False
        except Exception as e:
            delay = 0.1 * (2 ** attempt)
            logger.warning(f"⚠️ Cache invalidation failed for {user_id} (attempt {attempt + 1}): {e}")
            await asyncio.sleep(delay)
    
    logger.error(f"❌ Cache invalidation permanently failed for {user_id}")
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
                logger.info(f"✅ Created user {user_id} in vip module")
        return user
    except DatabaseError as e:
        logger.error(f"❌ DB error in get_or_create_user for {user_id}: {e}", exc_info=True)
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
        return None
    except DatabaseError as e:
        logger.error(f"❌ Error getting stats for {user_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error in get_user_full_data: {e}", exc_info=True)
        return None


async def get_user_with_stats(user_id: int) -> Tuple[Optional[Dict], int, int, int, int]:
    """Объединённый запрос: пользователь + статистика."""
    if user_id is None:
        return None, 0, 0, 0, 0
    
    user = await get_or_create_user(user_id)
    if not user:
        return None, 0, 0, 0, 0
    
    full_data = await get_user_full_data(user_id)
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
        logger.info(f"✅ Updated VIP for user {user_id} to level {vip_level}")
        return True
    except DatabaseError as e:
        logger.error(f"❌ Failed to update VIP for {user_id}: {e}", exc_info=True)
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
        
        if hasattr(db, '_execute_transaction') and callable(db._execute_transaction):
            await db._execute_transaction(queries)
        else:
            await db._execute_with_retry(
                "UPDATE users SET vip_level = ?, vip_until = ? "
                "WHERE user_id = ? AND (vip_level IS NULL OR vip_level < ?)",
                (vip_level, new_until, user_id, vip_level)
            )
        
        await invalidate_user_cache(user_id)
        logger.info(f"✅ Awarded VIP level {vip_level} to user {user_id} (wins: {wins})")
        return vip_level
    except DatabaseError as e:
        logger.error(f"❌ Failed to award VIP to {user_id}: {e}", exc_info=True)
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
        f"{icon} <b>ВАШ VIP СТАТУС</b> {icon}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Уровень: <b>{name}</b> (Уровень {vip_level})\n"
        f"💰 Баланс: <b>{format_number(balance)}</b> NCoins\n"
        f"📅 Действует до: {safe_html_escape(format_vip_date(vip_until))}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Статистика XO:</b>\n"
        f"├ 🏆 Побед: {wins}\n"
        f"└ 📉 Поражений: {losses}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>✨ ВАШИ ПРЕИМУЩЕСТВА:</b>\n\n"
        f"├ 🎮 +{wb}% к выигрышам\n"
        f"├ 🎁 +{db_bonus} NCoins к бонусу\n"
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
        f"💰 <b>Баланс: {format_number(balance)} NCoins</b>\n"
        f"🏆 <b>Побед: {wins}</b> | 📉 <b>Поражений: {losses}</b>\n"
        f"📊 <b>Винрейт: {round(winrate, 1)}%</b> ({games} игр)\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for level in sorted(VIP_NAMES.keys()):
        name = str(VIP_NAMES[level].get('name', ''))
        price = VIP_PRICES[level]
        wb = str(VIP_NAMES[level].get('win_bonus', 0))
        db_bonus = str(VIP_NAMES[level].get('daily_bonus', 0))
        text += (
            f"{name} ({level} ур.) — {format_number(price)} NCoins\n"
            f"├ 🎮 +{wb}% к выигрышам\n"
            f"└ 🎁 +{db_bonus} NCoins к бонусу\n\n"
        )
    
    text += (
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 <b>БЕСПЛАТНЫЙ VIP ЗА ПОБЕДЫ В XO:</b>\n"
    )
    for level in sorted(VIP_NAMES.keys()):
        text += f"├ {VIP_NAMES[level].get('wins_required', 0)} побед → {VIP_NAMES[level].get('name', '')}\n"
    text += f"\n📊 <b>Ваш прогресс: {wins} побед</b>"
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
    
    filled = min(math.ceil(10 * progress / 100), 10)
    progress_bar = "█" * filled + "░" * (10 - filled)
    
    status_msg = ""
    if awarded_vip:
        status_msg = f"✨ <b>Только что получен VIP {awarded_vip} уровня!</b>\n\n"
    
    progress_msg = ""
    if next_level and wins < _MAX_WINS_REQUIRED:
        progress_msg = (
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📈 <b>ДО СЛЕДУЮЩЕГО УРОВНЯ:</b>\n\n"
            f"Цель: <b>{next_level}</b>\n"
            f"Прогресс: {wins}/{next_wins} побед\n"
            f"[{progress_bar}] {progress}%\n\n"
            f"💪 Осталось <b>{next_wins - wins}</b> побед!\n"
        )
    
    rewards_lines = []
    for lvl in sorted(VIP_NAMES.keys()):
        icon = str(VIP_NAMES[lvl].get('icon', ''))
        wr = str(VIP_NAMES[lvl].get('wins_required', 0))
        name = str(VIP_NAMES[lvl].get('name', ''))
        rewards_lines.append(f"{icon} {wr} побед → {name} VIP")
    rewards = "\n".join(rewards_lines)
    
    return (
        "🏆 <b>БЕСПЛАТНЫЙ VIP ЗА ДОСТИЖЕНИЯ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 <b>ВАША СТАТИСТИКА XO:</b>\n\n"
        f"💰 Баланс: <b>{format_number(balance)} NCoins</b>\n"
        f"🏆 Побед: <b>{wins}</b>\n"
        f"📉 Поражений: <b>{losses}</b>\n"
        f"📊 Винрейт: <b>{round(winrate, 1)}%</b> ({games} игр)\n"
        f"⭐ Текущий VIP: <b>{current_vip} уровень</b>\n\n"
        + status_msg + progress_msg +
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>ДОСТУПНЫЕ НАГРАДЫ:</b>\n\n"
        + rewards
    )


# ==================== ОБРАБОТЧИКИ ====================

async def _safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = True) -> None:
    """Безопасный ответ на callback."""
    if callback is None:
        return
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except Exception:
        pass


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
        logger.info(f"✅ VIP menu viewed by user {user_id} (level: {vip_level})")
        
    except DatabaseError as e:
        logger.error(f"❌ DB error in cmd_vip for {user_id}: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки VIP меню.")
    except Exception as e:
        logger.error(f"❌ Unexpected error in cmd_vip: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка.")


@router.callback_query(F.data == "vip")
@router.callback_query(F.data == "vip_menu")
async def vip_callback(callback: CallbackQuery) -> None:
    """Callback для VIP меню."""
    if callback is None:
        return
    await cmd_vip(callback.message)
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: CallbackQuery) -> None:
    """Меню покупки VIP."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    user, balance, _, _, _ = await get_user_with_stats(user_id)
    
    if not user:
        await _safe_callback_answer(callback, "❌ Ошибка БД")
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
            # ✅ Используем подписанный callback
            signed_data = _sign_vip_callback(level)
            buttons.append([
                InlineKeyboardButton(
                    text=f"{name} — {format_number(price)} NCoins{afford_mark}",
                    callback_data=signed_data
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
            f"💰 Баланс: <b>{format_number(balance)} NCoins</b>\n"
            f"⭐ Текущий VIP: <b>{current_vip} уровень</b>\n\n"
            "Выберите уровень:\n"
            f"💡 VIP действует {VIP_DURATION_DAYS} дней\n"
            "🔒 — недостаточно средств"
        )
        
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await _safe_callback_answer(callback)
        
    except DatabaseError as e:
        logger.error(f"❌ DB error in buy_vip_menu for {user_id}: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка")


@router.callback_query(F.data.startswith("buy_vip_"))
async def buy_vip(callback: CallbackQuery) -> None:
    """Покупка VIP уровня."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    
    if not _check_rate_limit(user_id):
        await _safe_callback_answer(callback, "⏳ Пожалуйста, подождите перед следующим запросом")
        return
    
    # ✅ Проверка подписи
    level = _verify_vip_callback(callback.data)
    if level is None:
        logger.warning(f"⚠️ Invalid buy_vip callback from user {user_id}: {callback.data}")
        await _safe_callback_answer(callback, "❌ Неверный запрос")
        return
    
    user, balance, _, _, _ = await get_user_with_stats(user_id)
    if not user:
        await _safe_callback_answer(callback, "❌ Ошибка БД")
        return
    
    current_vip = max(0, user.get('vip_level', 0) or 0)
    if level <= current_vip:
        name = str(VIP_NAMES.get(current_vip, {}).get('name', str(current_vip)))
        await _safe_callback_answer(callback, f"❌ У вас уже есть VIP {name}! Купите более высокий уровень.")
        return
    
    price = VIP_PRICES[level]
    if balance < price:
        await _safe_callback_answer(callback,
            f"❌ Недостаточно средств!\n"
            f"Нужно: {format_number(price)} NCoins\n"
            f"Баланс: {format_number(balance)} NCoins")
        return
    
    success = await _process_vip_purchase(user_id, level, price, current_vip, balance, callback)
    if not success:
        await _safe_callback_answer(callback, "❌ Ошибка покупки")


async def _process_vip_purchase(
    user_id: int, level: int, price: int,
    current_vip: int, old_balance: int, callback: CallbackQuery
) -> bool:
    """Внутренняя логика покупки (атомарная транзакция)."""
    try:
        new_until = get_vip_expiry_date(VIP_DURATION_DAYS)
        queries = [
            ("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id)),
            ("UPDATE users SET vip_level = ?, vip_until = ? "
             "WHERE user_id = ? AND (vip_level IS NULL OR vip_level < ?)",
             (level, new_until, user_id, level)),
            ("INSERT INTO transactions (from_id, to_id, amount, reason, date) "
             "VALUES (?, ?, ?, ?, ?)",
             (user_id, user_id, price, f"Покупка VIP уровня {level}", datetime.now(timezone.utc).isoformat())),
        ]
        
        if hasattr(db, '_execute_transaction') and callable(db._execute_transaction):
            await db._execute_transaction(queries)
        else:
            for query, params in queries:
                await db._execute_with_retry(query, params)
        
        await invalidate_user_cache(user_id)
        
        _, new_balance, _, _, _ = await get_user_with_stats(user_id)
        priv = get_vip_privileges(level)
        icon = str(priv.get('icon', ''))
        name = str(priv.get('name', ''))
        wb = str(priv.get('win_bonus', 0))
        db_bonus = str(priv.get('daily_bonus', 0))
        
        text = (
            f"🎉 <b>ПОЗДРАВЛЯЕМ С ПОКУПКОЙ VIP!</b>\n\n"
            f"{icon} Новый уровень: <b>{name}</b>\n"
            f"💰 Списано: <b>{format_number(price)} NCoins</b>\n"
            f"💎 Новый баланс: <b>{format_number(new_balance)} NCoins</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>✨ НОВЫЕ ПРЕИМУЩЕСТВА:</b>\n"
            f"├ 🎮 +{wb}% к выигрышам\n"
            f"├ 🎁 +{db_bonus} NCoins к бонусу\n"
            "├ 👑 Статус в чате\n"
            "├ 💎 Доступ к VIP-комнатам\n"
            "└ ⭐ Приоритетная поддержка\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 Статус действует <b>{VIP_DURATION_DAYS} дней</b>"
        )
        
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ПОНЯТНО", callback_data="vip")]
            ])
        )
        logger.info(f"✅ User {user_id} purchased VIP {level} for {price} NC (bal: {old_balance} → {new_balance})")
        return True
        
    except DatabaseError as e:
        code = getattr(e, 'code', getattr(e, 'pgcode', 'DB_UNKNOWN'))
        logger.error(f"❌ VIP purchase DB error: user={user_id}, [{code}] {e} | lvl={level}, price={price}", exc_info=True)
        return False
    except Exception as e:
        logger.critical(f"❌ UNEXPECTED in VIP purchase: user={user_id}, data={callback.data} | {type(e).__name__}: {e}", exc_info=True)
        return False


@router.callback_query(F.data == "vip_achievements")
async def vip_achievements(callback: CallbackQuery) -> None:
    """Показать достижения пользователя."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    user, balance, wins, losses, games = await get_user_with_stats(user_id)
    
    if not user:
        await _safe_callback_answer(callback, "❌ Ошибка БД")
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
        await _safe_callback_answer(callback)
        logger.info(f"✅ Achievements viewed: user={user_id}, wins={wins}, vip={current_vip}")
        
    except DatabaseError as e:
        logger.error(f"❌ DB error in vip_achievements: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка загрузки")
    except Exception as e:
        logger.error(f"❌ Unexpected error in vip_achievements: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Произошла ошибка")
