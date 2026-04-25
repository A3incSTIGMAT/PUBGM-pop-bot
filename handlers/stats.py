#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/stats.py
# ВЕРСИЯ: 2.2.0-production
# ОПИСАНИЕ: Модуль статистики — ЦЕНТРАЛИЗОВАННЫЙ ИСТОЧНИК
# ИСПРАВЛЕНИЯ V2.2.0: Единый get_full_user_stats, убран дубль трекинга
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
from utils.stats_central import get_full_user_stats

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

TOP_LIMIT = 15
MAX_NAME_LENGTH = 20


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_number(num: Any) -> str:
    if num is None: return "0"
    try: return f"{int(num):,}".replace(",", " ")
    except: return "0"


def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try: return html.escape(str(text))
    except: return ""


def format_date(date_str: Optional[str]) -> str:
    if not date_str: return "Неизвестно"
    try:
        if "T" in date_str: return date_str.split("T")[0]
        return date_str[:10] if len(date_str) >= 10 else date_str
    except: return "Неизвестно"


def get_medal(position: Optional[int]) -> str:
    if position is None: return "—"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(position, f"{position}.")


def safe_get(obj: Optional[Dict], key: str, default: Any = 0) -> Any:
    if obj is None: return default
    value = obj.get(key)
    return value if value is not None else default


def escape_name(user: Optional[Dict]) -> str:
    if user is None: return "Пользователь"
    username = user.get("username")
    if username and username != "None":
        return f"@{safe_html_escape(str(username))}"
    first_name = user.get("first_name")
    if first_name and first_name != "None":
        name = str(first_name)
        truncated = name[:MAX_NAME_LENGTH] if len(name) > MAX_NAME_LENGTH else name
        return safe_html_escape(truncated)
    return "Пользователь"


# ==================== КЛАВИАТУРЫ ====================

def stats_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="stats_my")],
        [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def tops_menu_keyboard() -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])


# ==================== ФОРМАТИРОВАНИЕ ====================

def format_top_list(title: str, users: List[Dict], value_key: str, suffix: str = "", show_extra: bool = False) -> str:
    if not users: return f"📊 {title}\n\nПока нет данных!"
    
    lines = [title, "", "━━━━━━━━━━━━━━━━━━━━━", ""]
    for i, u in enumerate(users, 1):
        if u is None: continue
        medal = get_medal(i)
        name = escape_name(u)
        value = format_number(safe_get(u, value_key, 0))
        extra = ""
        if show_extra:
            if value_key == "balance" and safe_get(u, "vip_level", 0) > 0: extra = " ⭐"
            elif value_key == "total_donated":
                rank = u.get("donor_rank", "💎 Поддерживающий")
                extra = f"\n   {safe_html_escape(str(rank))}"
        lines.append(f"{medal} <b>{name}</b>{extra} — {value}{suffix}")
    return "\n".join(lines)


def format_user_stats(stats: Dict) -> str:
    """Форматирование статистики из единого источника."""
    name_display = escape_name(stats)
    first_name = safe_html_escape(stats.get("first_name") or "Пользователь")
    register_date = format_date(safe_get(stats, "user_register_date", ""))
    days_active = safe_get(stats, "days_active", 0)
    games = safe_get(stats, "games_played", 0)
    wins = safe_get(stats, "wins", 0)
    winrate = (wins / games * 100) if games > 0 else 0
    media_count = safe_get(stats, "total_photos", 0) + safe_get(stats, "total_videos", 0) + safe_get(stats, "total_gifs", 0)
    
    sections = [
        f"📊 <b>СТАТИСТИКА {name_display}</b>", "",
        f"👤 <b>{first_name}</b>",
        f"📅 В боте с: {register_date} ({days_active} дней)", "",
        "━━━━━━━━━━━━━━━━━━━━━", "",
        "💬 <b>АКТИВНОСТЬ:</b>",
        f"├ Всего сообщений: <b>{format_number(safe_get(stats, 'messages_total'))}</b>",
        f"├ Сегодня: <b>{format_number(safe_get(stats, 'messages_today'))}</b>",
        f"├ За неделю: <b>{format_number(safe_get(stats, 'messages_week'))}</b>",
        f"├ За месяц: <b>{format_number(safe_get(stats, 'messages_month'))}</b>",
        f"├ Голосовых: <b>{format_number(safe_get(stats, 'total_voice'))}</b>",
        f"├ Стикеров: <b>{format_number(safe_get(stats, 'total_stickers'))}</b>",
        f"└ Медиа: <b>{format_number(media_count)}</b>", "",
        "🔥 <b>СТРИК АКТИВНОСТИ:</b>",
        f"├ Дней активности: <b>{format_number(days_active)}</b>",
        f"├ Текущий стрик: <b>{format_number(safe_get(stats, 'current_streak'))} дней</b>",
        f"└ Макс. стрик: <b>{format_number(safe_get(stats, 'max_streak'))} дней</b>", "",
        "━━━━━━━━━━━━━━━━━━━━━", "",
        "🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>",
        f"├ Игр всего: <b>{format_number(games)}</b>",
        f"├ Побед: <b>{format_number(wins)}</b>",
        f"├ Поражений: <b>{format_number(safe_get(stats, 'losses'))}</b>",
        f"├ Ничьих: <b>{format_number(safe_get(stats, 'draws'))}</b>",
        f"├ Винрейт: <b>{winrate:.1f}%</b>",
        f"├ Побед над ботом: <b>{format_number(safe_get(stats, 'wins_vs_bot'))}</b>",
        f"└ Макс. винстрик: <b>{format_number(safe_get(stats, 'max_win_streak'))}</b>", "",
        "━━━━━━━━━━━━━━━━━━━━━", "",
        "💰 <b>ЭКОНОМИКА:</b>",
        f"├ Баланс: <b>{format_number(safe_get(stats, 'balance'))} NCoin</b>",
        f"├ Всего заработано: <b>{format_number(safe_get(stats, 'total_earned'))} NCoin</b>",
        f"├ Всего потрачено: <b>{format_number(safe_get(stats, 'total_spent'))} NCoin</b>",
        f"├ Daily бонусов: <b>{format_number(safe_get(stats, 'daily_claims'))} раз</b>",
        f"└ Daily стрик: <b>{format_number(safe_get(stats, 'daily_streak'))} дней</b>", "",
        "━━━━━━━━━━━━━━━━━━━━━", "",
        "💎 <b>ДОНАТ:</b>",
        f"├ Задоначено: <b>{format_number(safe_get(stats, 'total_donated_rub'))} ₽</b>",
        f"└ Получено NCoin: <b>{format_number(safe_get(stats, 'total_donated_coins'))}</b>"
    ]
    return "\n".join(sections)


async def show_user_stats(target_id: int, target: Message | CallbackQuery, is_callback: bool = False) -> None:
    """Показать статистику пользователя из единого источника."""
    try:
        stats = await get_full_user_stats(target_id)
        if not stats:
            text = "❌ Пользователь не найден!\nИспользуйте /start для регистрации."
            if is_callback:
                await target.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_menu"))
            else:
                await target.answer(text, parse_mode=ParseMode.HTML)
            return
        
        text = format_user_stats(stats)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
        ])
        
        if is_callback:
            await target.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            await target.answer()
        else:
            await target.answer(text, parse_mode=ParseMode.HTML, reply_markup=stats_menu_keyboard())
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        text = "❌ Ошибка базы данных."
        if is_callback:
            await target.message.edit_text(text, parse_mode=ParseMode.HTML)
            await target.answer("❌ Ошибка", show_alert=True)
        else:
            await target.answer(text, parse_mode=ParseMode.HTML)


async def show_top_list(callback: CallbackQuery, title: str, fetch_func, value_key: str, suffix: str = "", show_extra: bool = False, empty_message: str = "Пока нет данных!") -> None:
    try:
        top_users = await fetch_func(TOP_LIMIT)
        if not top_users:
            await callback.message.edit_text(f"{title}\n\n{empty_message}", parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
            await callback.answer(); return
        
        text = format_top_list(title, top_users, value_key, suffix, show_extra)
        user_stats = await get_full_user_stats(callback.from_user.id)
        if user_stats:
            value = safe_get(user_stats, value_key, 0)
            text += f"\n\n━━━━━━━━━━━━━━━━━━━━━\n📊 Ваш результат: <b>{format_number(value)}{suffix}</b>"
        
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
        await callback.answer()
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not message or not message.from_user: return
    try:
        args = message.text.strip().split() if message.text else []
        target_id = message.from_user.id
        if len(args) > 1 and args[1].startswith('@'):
            username = args[1].lstrip('@')
            if username:
                target = await db.get_user_by_username(username)
                if target: target_id = target.get("user_id", target_id)
        await show_user_stats(target_id, message)
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        await message.answer("❌ Ошибка базы данных.")


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    if not message: return
    try:
        await message.answer("🏆 <b>ТОПЫ NEXUS</b>\n\nВыберите категорию:", parse_mode=ParseMode.HTML, reply_markup=tops_menu_keyboard())
    except Exception as e:
        logger.error(f"Error: {e}")


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(F.data == "stats_menu")
@router.callback_query(F.data == "menu_stats")
async def stats_menu_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message: return
    try:
        await callback.message.edit_text("📊 <b>СТАТИСТИКА</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=stats_menu_keyboard())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "stats_my")
async def stats_my_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message: return
    await show_user_stats(callback.from_user.id, callback, is_callback=True)


@router.callback_query(F.data == "stats_tops")
async def stats_tops_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message: return
    try:
        await callback.message.edit_text("🏆 <b>ТОПЫ NEXUS</b>\n\nВыберите категорию:", parse_mode=ParseMode.HTML, reply_markup=tops_menu_keyboard())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ТОПЫ ====================

@router.callback_query(F.data == "top_messages")
async def top_messages_callback(callback: CallbackQuery):
    if not callback: return
    await show_top_list(callback, "💬 <b>ТОП-15 ПО СООБЩЕНИЯМ</b>", db.get_top_messages, "messages_total", " сообщ.")

@router.callback_query(F.data == "top_balance")
async def top_balance_callback(callback: CallbackQuery):
    if not callback: return
    await show_top_list(callback, "💰 <b>ТОП-15 ПО БАЛАНСУ</b>", db.get_top_balance, "balance", " NCoin", True)

@router.callback_query(F.data == "top_xo")
async def top_xo_callback(callback: CallbackQuery):
    if not callback or not callback.message: return
    try:
        top_users = await db.get_top_xo(TOP_LIMIT)
        if not top_users:
            await callback.message.edit_text("🎮 <b>ТОП ПО КРЕСТИКАМ-НОЛИКАМ</b>\n\nПока нет данных!", parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
            await callback.answer(); return
        
        lines = ["🎮 <b>ТОП-15 ПО КРЕСТИКАМ-НОЛИКАМ</b>", "", "━━━━━━━━━━━━━━━━━━━━━", ""]
        for i, u in enumerate(top_users, 1):
            if u is None: continue
            lines.append(f"{get_medal(i)} <b>{escape_name(u)}</b> — {safe_get(u,'wins',0)} побед ({safe_get(u,'games_played',0)} игр)")
        
        user_stats = await get_full_user_stats(callback.from_user.id)
        if user_stats:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", f"🎮 Ваши победы: <b>{safe_get(user_stats,'wins',0)}</b> ({safe_get(user_stats,'games_played',0)} игр)"])
        
        await callback.message.edit_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
        await callback.answer()
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    except Exception as e:
        logger.error(f"Error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "top_activity")
async def top_activity_callback(callback: CallbackQuery):
    if not callback or not callback.message: return
    try:
        top_users = await db.get_top_activity(TOP_LIMIT)
        if not top_users:
            await callback.message.edit_text("🔥 <b>ТОП ПО АКТИВНОСТИ</b>\n\nПока нет данных!", parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
            await callback.answer(); return
        
        lines = ["🔥 <b>ТОП-15 ПО АКТИВНОСТИ</b>", "", "━━━━━━━━━━━━━━━━━━━━━", ""]
        for i, u in enumerate(top_users, 1):
            if u is None: continue
            lines.append(f"{get_medal(i)} <b>{escape_name(u)}</b> — {safe_get(u,'days_active',0)} дней (стрик {safe_get(u,'current_streak',0)})")
        
        user_stats = await get_full_user_stats(callback.from_user.id)
        if user_stats:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", f"📊 Ваша активность: <b>{safe_get(user_stats,'days_active',0)} дней (стрик {safe_get(user_stats,'current_streak',0)})</b>"])
        
        await callback.message.edit_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
        await callback.answer()
    except DatabaseError as e:
        logger.error(f"Error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    except Exception as e:
        logger.error(f"Error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "top_daily")
async def top_daily_callback(callback: CallbackQuery):
    if not callback or not callback.message: return
    try:
        top_users = await db.get_top_daily_streak(TOP_LIMIT)
        if not top_users:
            await callback.message.edit_text("🎁 <b>ТОП ПО DAILY СТРИКУ</b>\n\nПока нет данных!", parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
            await callback.answer(); return
        
        lines = ["🎁 <b>ТОП-15 ПО DAILY СТРИКУ</b>", "", "━━━━━━━━━━━━━━━━━━━━━", ""]
        for i, u in enumerate(top_users, 1):
            if u is None: continue
            lines.append(f"{get_medal(i)} <b>{escape_name(u)}</b> — {safe_get(u,'daily_streak',0)} дней")
        
        user = await db.get_user(callback.from_user.id)
        if user:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", f"🎁 Ваш стрик: <b>{safe_get(user,'daily_streak',0)} дней</b>"])
        
        await callback.message.edit_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_keyboard("stats_tops"))
        await callback.answer()
    except DatabaseError as e:
        logger.error(f"Error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    except Exception as e:
        logger.error(f"Error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "top_donors")
async def top_donors_callback(callback: CallbackQuery):
    if not callback: return
    await show_top_list(callback, "💎 <b>ТОП-15 ДОНАТЕРОВ</b>", db.get_top_donors, "total_donated", " ₽", True, "Пока нет донатов!")


# ==================== ИНТЕГРАЦИОННЫЕ ФУНКЦИИ ====================

async def track_message(user_id: int, message: Message) -> None:
    """Отслеживание сообщения для статистики. Вызывается из bot.py."""
    if user_id is None or message is None or message.chat is None:
        return
    
    chat_id = message.chat.id
    
    try:
        activity_type = "message"
        if message.sticker: activity_type = "sticker"
        elif message.voice: activity_type = "voice"
        elif message.video: activity_type = "video"
        elif message.photo: activity_type = "photo"
        elif message.animation: activity_type = "gif"
        
        await db.track_user_activity(user_id, chat_id, activity_type, 1)
    except DatabaseError as e:
        logger.error(f"Database error tracking activity: {e}")
    except Exception as e:
        logger.error(f"Unexpected error tracking activity: {e}")


async def track_xo_game(user_id: int, result_type: str, bet: int = 0, won: int = 0) -> None:
    """Отслеживание игры в крестики-нолики."""
    if user_id is None or user_id == "bot": return
    try:
        await db.update_xo_stats(user_id, result_type, bet or 0, won or 0)
        await db.track_user_activity(user_id, 0, "xo_game", 1)
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


async def update_all_streaks() -> None:
    """Обновление стриков всех пользователей."""
    try:
        await db.update_user_streaks()
        logger.info("✅ Activity streaks updated")
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


async def reset_daily_counters() -> None:
    """Сброс дневных счётчиков."""
    try:
        await db.reset_daily_counters()
        logger.info("✅ Daily counters reset")
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
