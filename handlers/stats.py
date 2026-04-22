#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/stats.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Модуль статистики — все топы с защитой от NULL
# ИСПРАВЛЕНИЯ: Обработка DatabaseError, защита от XSS, DRY
# ============================================

import html
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db, DatabaseError

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

TOP_LIMIT = 15  # Количество пользователей в топах
MAX_NAME_LENGTH = 20  # Максимальная длина имени


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_number(num: Any) -> str:
    """Форматирование числа с разделителями."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def format_date(date_str: Optional[str]) -> str:
    """Форматирование даты."""
    if not date_str or date_str == "":
        return "Неизвестно"
    try:
        if "T" in date_str:
            return date_str.split("T")[0]
        return date_str[:10] if len(date_str) >= 10 else date_str
    except Exception:
        return "Неизвестно"


def get_medal(position: Optional[int]) -> str:
    """Получить медаль для позиции."""
    if position is None:
        return "—"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(position, f"{position}.")


def safe_get(obj: Optional[Dict], key: str, default: Any = 0) -> Any:
    """Безопасное получение значения из словаря."""
    if obj is None:
        return default
    value = obj.get(key)
    return value if value is not None else default


def escape_name(user: Optional[Dict]) -> str:
    """Безопасное получение имени пользователя с защитой от XSS."""
    if user is None:
        return "Пользователь"
    
    username = user.get("username")
    if username and username != "None":
        return f"@{safe_html_escape(str(username))}"
    
    first_name = user.get("first_name")
    if first_name and first_name != "None":
        name = str(first_name)
        truncated = name[:MAX_NAME_LENGTH] if len(name) > MAX_NAME_LENGTH else name
        return safe_html_escape(truncated)
    
    return "Пользователь"


async def get_user_stats_safe(user_id: int) -> Optional[Dict]:
    """
    Безопасное получение статистики пользователя с fallback.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Словарь со статистикой или None при ошибке БД
    """
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return stats
        
        # Если статистика не найдена, создаем базовую из users
        user = await db.get_user(user_id)
        if not user:
            return None
        
        balance = await db.get_balance(user_id)
        
        return {
            "balance": balance,
            "vip_level": user.get("vip_level", 0) or 0,
            "daily_streak": user.get("daily_streak", 0) or 0,
            "user_register_date": user.get("register_date", ""),
            "messages_total": 0, "messages_today": 0, "messages_week": 0, "messages_month": 0,
            "total_voice": 0, "total_stickers": 0, "total_photos": 0, "total_videos": 0, "total_gifs": 0,
            "days_active": 0, "current_streak": 0, "max_streak": 0,
            "games_played": 0, "wins": 0, "losses": 0, "draws": 0,
            "wins_vs_bot": 0, "losses_vs_bot": 0, "max_win_streak": 0,
            "total_earned": 0, "total_spent": 0, "daily_claims": 0,
            "total_donated_rub": 0, "total_donated_coins": 0,
        }
    except DatabaseError as e:
        logger.error(f"Database error getting stats for {user_id}: {e}")
        return None


# ==================== КЛАВИАТУРЫ ====================

def stats_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню статистики."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="stats_my")],
        [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def tops_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню топов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ТОП ПО СООБЩЕНИЯМ", callback_data="top_messages")],
        [InlineKeyboardButton(text="💰 ТОП ПО БАЛАНСУ", callback_data="top_balance")],
        [InlineKeyboardButton(text="🎮 ТОП ПО КРЕСТИКАМ-НОЛИКАМ", callback_data="top_xo")],
        [InlineKeyboardButton(text="🔥 ТОП ПО АКТИВНОСТИ", callback_data="top_activity")],
        [InlineKeyboardButton(text="🎁 ТОП ПО DAILY", callback_data="top_daily")],
        [InlineKeyboardButton(text="💎 ТОП ДОНАТЕРОВ", callback_data="top_donors")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
    ])


def back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])


# ==================== ФОРМАТИРОВАНИЕ ====================

def format_top_list(
    title: str,
    users: List[Dict],
    value_key: str,
    suffix: str = "",
    show_extra: bool = False
) -> str:
    """
    Формирует текст топ-листа.
    
    Args:
        title: Заголовок
        users: Список пользователей
        value_key: Ключ для значения
        suffix: Суффикс после значения
        show_extra: Показывать ли дополнительную информацию
        
    Returns:
        Отформатированный текст
    """
    if not users:
        return f"📊 {title}\n\nПока нет данных!"
    
    lines = [title, "", "━━━━━━━━━━━━━━━━━━━━━", ""]
    
    for i, u in enumerate(users, 1):
        if u is None:
            continue
        
        medal = get_medal(i)
        name = escape_name(u)
        value = format_number(safe_get(u, value_key, 0))
        extra = ""
        
        if show_extra:
            if value_key == "balance" and safe_get(u, "vip_level", 0) > 0:
                extra = " ⭐"
            elif value_key == "total_donated":
                rank = u.get("donor_rank", "💎 Поддерживающий")
                extra = f"\n   {safe_html_escape(str(rank))}"
        
        lines.append(f"{medal} <b>{name}</b>{extra} — {value}{suffix}")
    
    return "\n".join(lines)


def format_user_stats(user: Dict, stats: Dict) -> str:
    """
    Формирует текст статистики пользователя.
    
    Args:
        user: Данные пользователя
        stats: Статистика пользователя
        
    Returns:
        Отформатированный текст
    """
    name_display = escape_name(user)
    first_name = safe_html_escape(user.get("first_name") or "Пользователь")
    register_date = format_date(safe_get(stats, "user_register_date", ""))
    days_active = safe_get(stats, "days_active", 0)
    
    # Игры
    games = safe_get(stats, "games_played", 0)
    wins = safe_get(stats, "wins", 0)
    winrate = (wins / games * 100) if games > 0 else 0
    
    # Медиа
    media_count = (
        safe_get(stats, "total_photos", 0) +
        safe_get(stats, "total_videos", 0) +
        safe_get(stats, "total_gifs", 0)
    )
    
    # Формируем секции
    sections = [
        f"📊 <b>СТАТИСТИКА {name_display}</b>",
        "",
        f"👤 <b>{first_name}</b>",
        f"📅 В боте с: {register_date} ({days_active} дней)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "💬 <b>АКТИВНОСТЬ:</b>",
        f"├ Всего сообщений: <b>{format_number(safe_get(stats, 'messages_total'))}</b>",
        f"├ Сегодня: <b>{format_number(safe_get(stats, 'messages_today'))}</b>",
        f"├ За неделю: <b>{format_number(safe_get(stats, 'messages_week'))}</b>",
        f"├ За месяц: <b>{format_number(safe_get(stats, 'messages_month'))}</b>",
        f"├ Голосовых: <b>{format_number(safe_get(stats, 'total_voice'))}</b>",
        f"├ Стикеров: <b>{format_number(safe_get(stats, 'total_stickers'))}</b>",
        f"└ Медиа: <b>{format_number(media_count)}</b>",
        "",
        "🔥 <b>СТРИК АКТИВНОСТИ:</b>",
        f"├ Дней активности: <b>{format_number(days_active)}</b>",
        f"├ Текущий стрик: <b>{format_number(safe_get(stats, 'current_streak'))} дней</b>",
        f"└ Макс. стрик: <b>{format_number(safe_get(stats, 'max_streak'))} дней</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>",
        f"├ Игр всего: <b>{format_number(games)}</b>",
        f"├ Побед: <b>{format_number(wins)}</b>",
        f"├ Поражений: <b>{format_number(safe_get(stats, 'losses'))}</b>",
        f"├ Ничьих: <b>{format_number(safe_get(stats, 'draws'))}</b>",
        f"├ Винрейт: <b>{winrate:.1f}%</b>",
        f"├ Побед над ботом: <b>{format_number(safe_get(stats, 'wins_vs_bot'))}</b>",
        f"└ Макс. винстрик: <b>{format_number(safe_get(stats, 'max_win_streak'))}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "💰 <b>ЭКОНОМИКА:</b>",
        f"├ Баланс: <b>{format_number(safe_get(stats, 'balance'))} NCoin</b>",
        f"├ Всего заработано: <b>{format_number(safe_get(stats, 'total_earned'))} NCoin</b>",
        f"├ Всего потрачено: <b>{format_number(safe_get(stats, 'total_spent'))} NCoin</b>",
        f"├ Daily бонусов: <b>{format_number(safe_get(stats, 'daily_claims'))} раз</b>",
        f"└ Daily стрик: <b>{format_number(safe_get(stats, 'daily_streak'))} дней</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "💎 <b>ДОНАТ:</b>",
        f"├ Задоначено: <b>{format_number(safe_get(stats, 'total_donated_rub'))} ₽</b>",
        f"└ Получено NCoin: <b>{format_number(safe_get(stats, 'total_donated_coins'))}</b>"
    ]
    
    return "\n".join(sections)


async def show_user_stats(
    target_id: int,
    message_or_callback: Message | CallbackQuery,
    is_callback: bool = False
) -> None:
    """
    Универсальная функция для показа статистики пользователя.
    
    Args:
        target_id: ID пользователя
        message_or_callback: Сообщение или callback
        is_callback: True если передан callback
    """
    try:
        user = await db.get_user(target_id)
        if not user:
            text = "❌ Пользователь не найден!\nИспользуйте /start для регистрации."
            if is_callback:
                await message_or_callback.message.edit_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_menu")
                )
            else:
                await message_or_callback.answer(text, parse_mode=ParseMode.HTML)
            return
        
        stats = await get_user_stats_safe(target_id)
        if stats is None:
            text = "❌ Ошибка при загрузке статистики. Попробуйте позже."
            if is_callback:
                await message_or_callback.message.edit_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_menu")
                )
            else:
                await message_or_callback.answer(text, parse_mode=ParseMode.HTML)
            return
        
        text = format_user_stats(user, stats)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            await message_or_callback.answer()
        else:
            await message_or_callback.answer(text, parse_mode=ParseMode.HTML, reply_markup=stats_menu_keyboard())
            
    except DatabaseError as e:
        logger.error(f"Database error in show_user_stats: {e}")
        text = "❌ Ошибка базы данных. Попробуйте позже."
        if is_callback:
            await message_or_callback.message.edit_text(text, parse_mode=ParseMode.HTML)
            await message_or_callback.answer("❌ Ошибка", show_alert=True)
        else:
            await message_or_callback.answer(text, parse_mode=ParseMode.HTML)


async def show_top_list(
    callback: CallbackQuery,
    title: str,
    fetch_func,
    value_key: str,
    suffix: str = "",
    show_extra: bool = False,
    empty_message: str = "Пока нет данных!",
    user_stats_func = None
) -> None:
    """
    Универсальная функция для показа топ-листа.
    
    Args:
        callback: Callback запрос
        title: Заголовок топа
        fetch_func: Функция для получения данных
        value_key: Ключ значения
        suffix: Суффикс
        show_extra: Показывать доп. информацию
        empty_message: Сообщение при пустом списке
        user_stats_func: Функция для получения статистики пользователя
    """
    try:
        top_users = await fetch_func(TOP_LIMIT)
        
        if not top_users:
            await callback.message.edit_text(
                f"{title}\n\n{empty_message}",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        text = format_top_list(title, top_users, value_key, suffix, show_extra)
        
        # Добавляем статистику текущего пользователя
        if user_stats_func:
            user_id = callback.from_user.id
            user_stats = await user_stats_func(user_id)
            if user_stats:
                value = safe_get(user_stats, value_key, 0)
                text += f"\n\n━━━━━━━━━━━━━━━━━━━━━\n📊 Ваш результат: <b>{format_number(value)}{suffix}</b>"
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in show_top_list ({title}): {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in show_top_list ({title}): {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Показать статистику пользователя."""
    if message is None or message.from_user is None:
        return
    
    try:
        args = message.text.strip().split() if message.text else []
        target_id = message.from_user.id
        
        if len(args) > 1 and args[1].startswith('@'):
            username = args[1].lstrip('@')
            if username:
                target = await db.get_user_by_username(username)
                if target:
                    target_id = target.get("user_id", target_id)
        
        await show_user_stats(target_id, message, is_callback=False)
        
    except DatabaseError as e:
        logger.error(f"Database error in /stats: {e}")
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Unexpected error in /stats: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при загрузке статистики.")


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    """Меню топов."""
    if message is None:
        return
    
    try:
        await message.answer(
            "🏆 <b>ТОПЫ NEXUS</b>\n\nВыберите категорию:",
            parse_mode=ParseMode.HTML,
            reply_markup=tops_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in /top: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке топов.")


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(F.data == "stats_menu")
@router.callback_query(F.data == "stats")
async def stats_menu_callback(callback: CallbackQuery) -> None:
    """Меню статистики."""
    if callback is None or callback.message is None:
        return
    
    try:
        await callback.message.edit_text(
            "📊 <b>СТАТИСТИКА</b>\n\nВыберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=stats_menu_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in stats_menu: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "stats_my")
async def stats_my_callback(callback: CallbackQuery) -> None:
    """Показать мою статистику."""
    if callback is None or callback.message is None:
        return
    
    await show_user_stats(callback.from_user.id, callback, is_callback=True)


@router.callback_query(F.data == "stats_tops")
async def stats_tops_callback(callback: CallbackQuery) -> None:
    """Меню топов."""
    if callback is None or callback.message is None:
        return
    
    try:
        await callback.message.edit_text(
            "🏆 <b>ТОПЫ NEXUS</b>\n\nВыберите категорию:",
            parse_mode=ParseMode.HTML,
            reply_markup=tops_menu_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in stats_tops: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ТОПЫ ====================

@router.callback_query(F.data == "top_messages")
async def top_messages_callback(callback: CallbackQuery) -> None:
    """Топ по сообщениям."""
    if callback is None:
        return
    
    await show_top_list(
        callback,
        title="💬 <b>ТОП-15 ПО СООБЩЕНИЯМ</b>",
        fetch_func=db.get_top_messages,
        value_key="messages_total",
        suffix=" сообщ.",
        empty_message="Пока нет данных! Начните общаться.",
        user_stats_func=db.get_user_stats
    )


@router.callback_query(F.data == "top_balance")
async def top_balance_callback(callback: CallbackQuery) -> None:
    """Топ по балансу."""
    if callback is None:
        return
    
    async def get_user_balance(user_id: int) -> Optional[Dict]:
        balance = await db.get_balance(user_id)
        return {"balance": balance} if balance else None
    
    await show_top_list(
        callback,
        title="💰 <b>ТОП-15 ПО БАЛАНСУ</b>",
        fetch_func=db.get_top_balance,
        value_key="balance",
        suffix=" NCoin",
        show_extra=True,
        empty_message="Пока нет данных! Заработайте NCoin.",
        user_stats_func=get_user_balance
    )


@router.callback_query(F.data == "top_xo")
async def top_xo_callback(callback: CallbackQuery) -> None:
    """Топ по крестикам-ноликам."""
    if callback is None or callback.message is None:
        return
    
    try:
        top_users = await db.get_top_xo(TOP_LIMIT)
        
        if not top_users:
            await callback.message.edit_text(
                "🎮 <b>ТОП ПО КРЕСТИКАМ-НОЛИКАМ</b>\n\nПока нет данных! Сыграйте хотя бы 3 игры.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        lines = [
            "🎮 <b>ТОП-15 ПО КРЕСТИКАМ-НОЛИКАМ</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        
        for i, u in enumerate(top_users, 1):
            if u is None:
                continue
            medal = get_medal(i)
            name = escape_name(u)
            wins = safe_get(u, "wins", 0)
            games = safe_get(u, "games_played", 0)
            lines.append(f"{medal} <b>{name}</b> — {wins} побед ({games} игр)")
        
        # Статистика текущего пользователя
        user_id = callback.from_user.id
        user_stats = await get_user_stats_safe(user_id)
        if user_stats:
            user_wins = safe_get(user_stats, "wins", 0)
            user_games = safe_get(user_stats, "games_played", 0)
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"🎮 Ваши победы: <b>{user_wins}</b> ({user_games} игр)"
            ])
        
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in top_xo: {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.error(f"Error in top_xo: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_activity")
async def top_activity_callback(callback: CallbackQuery) -> None:
    """Топ по активности."""
    if callback is None or callback.message is None:
        return
    
    try:
        top_users = await db.get_top_activity(TOP_LIMIT)
        
        if not top_users:
            await callback.message.edit_text(
                "🔥 <b>ТОП ПО АКТИВНОСТИ</b>\n\nПока нет данных!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        lines = [
            "🔥 <b>ТОП-15 ПО АКТИВНОСТИ</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        
        for i, u in enumerate(top_users, 1):
            if u is None:
                continue
            medal = get_medal(i)
            name = escape_name(u)
            days = safe_get(u, "days_active", 0)
            streak = safe_get(u, "current_streak", 0)
            lines.append(f"{medal} <b>{name}</b> — {days} дней (стрик {streak})")
        
        user_id = callback.from_user.id
        user_stats = await get_user_stats_safe(user_id)
        if user_stats:
            user_days = safe_get(user_stats, "days_active", 0)
            user_streak = safe_get(user_stats, "current_streak", 0)
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"📊 Ваша активность: <b>{user_days} дней (стрик {user_streak})</b>"
            ])
        
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in top_activity: {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.error(f"Error in top_activity: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_daily")
async def top_daily_callback(callback: CallbackQuery) -> None:
    """Топ по daily стрику."""
    if callback is None or callback.message is None:
        return
    
    try:
        top_users = await db.get_top_daily_streak(TOP_LIMIT)
        
        if not top_users:
            await callback.message.edit_text(
                "🎁 <b>ТОП ПО DAILY СТРИКУ</b>\n\nПока нет данных! Получите ежедневный бонус.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        lines = [
            "🎁 <b>ТОП-15 ПО DAILY СТРИКУ</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        
        for i, u in enumerate(top_users, 1):
            if u is None:
                continue
            medal = get_medal(i)
            name = escape_name(u)
            streak = safe_get(u, "daily_streak", 0)
            lines.append(f"{medal} <b>{name}</b> — {streak} дней")
        
        user_id = callback.from_user.id
        user = await db.get_user(user_id)
        if user:
            user_streak = safe_get(user, "daily_streak", 0)
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"🎁 Ваш стрик: <b>{user_streak} дней</b>"
            ])
        
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Database error in top_daily: {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.error(f"Error in top_daily: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_donors")
async def top_donors_callback(callback: CallbackQuery) -> None:
    """Топ донатеров."""
    if callback is None:
        return
    
    await show_top_list(
        callback,
        title="💎 <b>ТОП-15 ДОНАТЕРОВ</b>",
        fetch_func=db.get_top_donors,
        value_key="total_donated",
        suffix=" ₽",
        show_extra=True,
        empty_message="Пока нет донатов. Будьте первым!"
    )


# ==================== ИНТЕГРАЦИОННЫЕ ФУНКЦИИ ====================

async def track_message(user_id: int, message: Message) -> None:
    """
    Отслеживание сообщения для статистики.
    
    Args:
        user_id: ID пользователя
        message: Сообщение
    """
    if user_id is None or message is None:
        return
    
    try:
        activity_type = "message"
        if message.sticker:
            activity_type = "sticker"
        elif message.voice:
            activity_type = "voice"
        elif message.video:
            activity_type = "video"
        elif message.photo:
            activity_type = "photo"
        elif message.animation:
            activity_type = "gif"
        
        await db.track_user_activity(user_id, activity_type, 1)
        logger.debug(f"Activity tracked: user={user_id}, type={activity_type}")
        
    except DatabaseError as e:
        logger.error(f"Database error tracking activity: {e}")
    except Exception as e:
        logger.error(f"Unexpected error tracking activity: {e}")


async def track_xo_game(user_id: int, result_type: str, bet: int = 0, won: int = 0) -> None:
    """
    Отслеживание игры в крестики-нолики.
    
    Args:
        user_id: ID пользователя
        result_type: Тип результата (win/loss/draw)
        bet: Ставка
        won: Выигрыш
    """
    if user_id is None or user_id == "bot":
        return
    
    try:
        await db.update_xo_stats(user_id, result_type, bet or 0, won or 0)
        await db.track_user_activity(user_id, "xo_game", 1)
        logger.debug(f"XO game tracked: user={user_id}, result={result_type}")
        
    except DatabaseError as e:
        logger.error(f"Database error tracking XO game: {e}")
    except Exception as e:
        logger.error(f"Unexpected error tracking XO game: {e}")


async def update_all_streaks() -> None:
    """Обновление стриков всех пользователей."""
    try:
        await db.update_user_streaks()
        logger.info("✅ Activity streaks updated")
    except DatabaseError as e:
        logger.error(f"Database error updating streaks: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating streaks: {e}")


async def reset_daily_counters() -> None:
    """Сброс дневных счётчиков."""
    try:
        await db.reset_daily_counters()
        logger.info("✅ Daily counters reset")
    except DatabaseError as e:
        logger.error(f"Database error resetting daily counters: {e}")
    except Exception as e:
        logger.error(f"Unexpected error resetting daily counters: {e}")
