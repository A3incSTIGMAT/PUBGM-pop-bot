# ============================================
# ФАЙЛ: handlers/stats.py
# ОПИСАНИЕ: Модуль статистики — ИСПРАВЛЕННЫЙ
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# ============================================

import asyncio
import logging
import html
from datetime import datetime
from typing import Any, Optional, List, Dict
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_number(num: Any) -> str:
    """Форматирование числа с разделителями"""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def format_date(date_str: Optional[str]) -> str:
    """Форматирование даты"""
    if not date_str:
        return "Неизвестно"
    try:
        if "T" in date_str:
            return date_str.split("T")[0]
        return date_str[:10] if len(date_str) >= 10 else date_str
    except Exception:
        return "Неизвестно"


def get_medal(position: Optional[int]) -> str:
    """Получить медаль для позиции"""
    if position is None:
        return "—"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(position, f"{position}.")


def safe_get(obj: Optional[Dict], key: str, default: Any = 0) -> Any:
    """Безопасное получение значения из словаря"""
    if obj is None:
        return default
    value = obj.get(key)
    return value if value is not None else default


def escape_name(user: Optional[Dict]) -> str:
    """Безопасное получение имени пользователя"""
    if user is None:
        return "Пользователь"
    
    username = user.get("username")
    if username:
        return f"@{html.escape(str(username))}"
    
    first_name = user.get("first_name")
    if first_name:
        name = str(first_name)[:20] if len(str(first_name)) > 20 else str(first_name)
        return html.escape(name)
    
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


# ==================== ФОРМАТТЕРЫ ТЕКСТА ====================

def format_user_stats(user: Dict, stats: Dict) -> str:
    """Формирует текст статистики пользователя"""
    name_display = escape_name(user)
    first_name = html.escape(user.get("first_name") or "Пользователь")
    
    register_date = format_date(safe_get(stats, "user_register_date", ""))
    days_active = safe_get(stats, "days_active", 0)
    
    # Расчёты
    games = safe_get(stats, "games_played", 0)
    wins = safe_get(stats, "wins", 0)
    winrate = (wins / games * 100) if games > 0 else 0
    
    media_count = (safe_get(stats, "total_photos", 0) + 
                   safe_get(stats, "total_videos", 0) + 
                   safe_get(stats, "total_gifs", 0))
    
    return (
        f"📊 <b>СТАТИСТИКА {name_display}</b>\n\n"
        f"👤 <b>{first_name}</b>\n"
        f"📅 В боте с: {register_date} ({days_active} дней)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 <b>АКТИВНОСТЬ:</b>\n"
        f"├ Всего сообщений: <b>{format_number(safe_get(stats, 'messages_total'))}</b>\n"
        f"├ Сегодня: <b>{format_number(safe_get(stats, 'messages_today'))}</b>\n"
        f"├ За неделю: <b>{format_number(safe_get(stats, 'messages_week'))}</b>\n"
        f"├ За месяц: <b>{format_number(safe_get(stats, 'messages_month'))}</b>\n"
        f"├ Голосовых: <b>{format_number(safe_get(stats, 'total_voice'))}</b>\n"
        f"├ Стикеров: <b>{format_number(safe_get(stats, 'total_stickers'))}</b>\n"
        f"└ Медиа: <b>{format_number(media_count)}</b>\n\n"
        f"🔥 <b>СТРИК АКТИВНОСТИ:</b>\n"
        f"├ Дней активности: <b>{format_number(days_active)}</b>\n"
        f"├ Текущий стрик: <b>{format_number(safe_get(stats, 'current_streak'))} дней</b>\n"
        f"└ Макс. стрик: <b>{format_number(safe_get(stats, 'max_streak'))} дней</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>\n"
        f"├ Игр всего: <b>{format_number(games)}</b>\n"
        f"├ Побед: <b>{format_number(wins)}</b>\n"
        f"├ Поражений: <b>{format_number(safe_get(stats, 'losses'))}</b>\n"
        f"├ Ничьих: <b>{format_number(safe_get(stats, 'draws'))}</b>\n"
        f"├ Винрейт: <b>{winrate:.1f}%</b>\n"
        f"├ Побед над ботом: <b>{format_number(safe_get(stats, 'wins_vs_bot'))}</b>\n"
        f"└ Макс. винстрик: <b>{format_number(safe_get(stats, 'max_win_streak'))}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>ЭКОНОМИКА:</b>\n"
        f"├ Баланс: <b>{format_number(safe_get(stats, 'balance'))} NCoin</b>\n"
        f"├ Всего заработано: <b>{format_number(safe_get(stats, 'total_earned'))} NCoin</b>\n"
        f"├ Всего потрачено: <b>{format_number(safe_get(stats, 'total_spent'))} NCoin</b>\n"
        f"├ Daily бонусов: <b>{format_number(safe_get(stats, 'daily_claims'))} раз</b>\n"
        f"└ Daily стрик: <b>{format_number(safe_get(stats, 'daily_streak'))} дней</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💎 <b>ДОНАТ:</b>\n"
        f"├ Задоначено: <b>{format_number(safe_get(stats, 'total_donated_rub'))} ₽</b>\n"
        f"└ Получено NCoin: <b>{format_number(safe_get(stats, 'total_donated_coins'))}</b>"
    )


def format_top_list(title: str, users: List[Dict], value_key: str, 
                    suffix: str = "", show_extra: bool = False) -> str:
    """Формирует текст топ-листа"""
    if not users:
        return f"📊 {title}\n\nПока нет данных!"
    
    text = f"{title}\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
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
                extra = f"\n   {u.get('donor_rank', '💎 Поддерживающий')}"
        
        text += f"{medal} <b>{name}</b>{extra} — {value}{suffix}\n"
    
    return text


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Показать статистику пользователя"""
    try:
        args = message.text.strip().split() if message.text else []
        target_id = message.from_user.id
        
        # Проверка упоминания другого пользователя
        if len(args) > 1 and args[1].startswith('@'):
            username = args[1].lstrip('@')
            if username:
                target = await db.get_user_by_username(username)
                if target:
                    target_id = target.get("user_id", target_id)
        
        user = await db.get_user(target_id)
        if not user:
            await message.answer(
                "❌ Пользователь не найден!\nИспользуйте /start для регистрации.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # 🔥 ПОЛУЧАЕМ РЕАЛЬНУЮ СТАТИСТИКУ ИЗ БД
        stats = await db.get_user_stats(target_id)
        
        if not stats:
            # Если статистики нет — создаём базовую
            stats = {
                "balance": await db.get_balance(target_id),
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
        
        text = format_user_stats(user, stats)
        
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=stats_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error in /stats: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при загрузке статистики.")


@router.message(Command("top"))
async def cmd_top(message: types.Message):
    """Меню топов"""
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
async def stats_menu_callback(callback: types.CallbackQuery):
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
async def stats_my_callback(callback: types.CallbackQuery):
    try:
        target_id = callback.from_user.id
        user = await db.get_user(target_id)
        
        if not user:
            await callback.message.edit_text(
                "❌ Статистика не найдена!\nИспользуйте /start для регистрации.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_menu")
            )
            await callback.answer()
            return
        
        # 🔥 ПОЛУЧАЕМ РЕАЛЬНУЮ СТАТИСТИКУ ИЗ БД
        stats = await db.get_user_stats(target_id)
        
        if not stats:
            stats = {
                "balance": await db.get_balance(target_id),
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
        
        text = format_user_stats(user, stats)
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
            ])
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in stats_my: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "stats_tops")
async def stats_tops_callback(callback: types.CallbackQuery):
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
async def top_messages_callback(callback: types.CallbackQuery):
    """Топ по сообщениям"""
    try:
        top_users = await db.get_top_messages(15)
        
        if not top_users:
            await callback.message.edit_text(
                "💬 <b>ТОП ПО СООБЩЕНИЯМ</b>\n\nПока нет данных!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        text = format_top_list(
            "💬 <b>ТОП-15 ПО СООБЩЕНИЯМ</b>",
            top_users,
            value_key="messages_total",
            suffix=" сообщ."
        )
        
        user_id = callback.from_user.id
        user_stats = await db.get_user_stats(user_id)
        if user_stats:
            user_messages = safe_get(user_stats, "messages_total", 0)
            text += f"\n\n━━━━━━━━━━━━━━━━━━━━━\n📊 Ваши сообщения: <b>{format_number(user_messages)}</b>"
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in top_messages: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_balance")
async def top_balance_callback(callback: types.CallbackQuery):
    """Топ по балансу"""
    try:
        top_users = await db.get_top_balance(15)
        
        if not top_users:
            await callback.message.edit_text(
                "💰 <b>ТОП ПО БАЛАНСУ</b>\n\nПока нет данных!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        text = format_top_list(
            "💰 <b>ТОП-15 ПО БАЛАНСУ</b>",
            top_users,
            value_key="balance",
            suffix=" NCoin",
            show_extra=True
        )
        
        user_id = callback.from_user.id
        user_balance = await db.get_balance(user_id)
        if user_balance > 0:
            text += f"\n\n━━━━━━━━━━━━━━━━━━━━━\n💰 Ваш баланс: <b>{format_number(user_balance)} NCoin</b>"
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in top_balance: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_xo")
async def top_xo_callback(callback: types.CallbackQuery):
    """Топ по крестикам-ноликам"""
    try:
        top_users = await db.get_top_xo(15)
        
        if not top_users:
            await callback.message.edit_text(
                "🎮 <b>ТОП ПО КРЕСТИКАМ-НОЛИКАМ</b>\n\nПока нет данных! Сыграйте хотя бы 3 игры.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        text = "🎮 <b>ТОП-15 ПО КРЕСТИКАМ-НОЛИКАМ</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, u in enumerate(top_users, 1):
            if u is None:
                continue
            medal = get_medal(i)
            name = escape_name(u)
            wins = safe_get(u, "wins", 0)
            games = safe_get(u, "games_played", 0)
            text += f"{medal} <b>{name}</b> — {wins} побед ({games} игр)\n"
        
        user_id = callback.from_user.id
        user_stats = await db.get_user_stats(user_id)
        if user_stats:
            user_wins = safe_get(user_stats, "wins", 0)
            user_games = safe_get(user_stats, "games_played", 0)
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n🎮 Ваши победы: <b>{user_wins}</b> ({user_games} игр)"
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in top_xo: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_activity")
async def top_activity_callback(callback: types.CallbackQuery):
    """Топ по активности"""
    try:
        top_users = await db.get_top_activity(15)
        
        if not top_users:
            await callback.message.edit_text(
                "🔥 <b>ТОП ПО АКТИВНОСТИ</b>\n\nПока нет данных!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        text = "🔥 <b>ТОП-15 ПО АКТИВНОСТИ</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, u in enumerate(top_users, 1):
            if u is None:
                continue
            medal = get_medal(i)
            name = escape_name(u)
            days = safe_get(u, "days_active", 0)
            streak = safe_get(u, "current_streak", 0)
            text += f"{medal} <b>{name}</b> — {days} дней (стрик {streak})\n"
        
        user_id = callback.from_user.id
        user_stats = await db.get_user_stats(user_id)
        if user_stats:
            user_days = safe_get(user_stats, "days_active", 0)
            user_streak = safe_get(user_stats, "current_streak", 0)
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n📊 Ваша активность: <b>{user_days} дней (стрик {user_streak})</b>"
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in top_activity: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_daily")
async def top_daily_callback(callback: types.CallbackQuery):
    """Топ по daily стрику"""
    try:
        top_users = await db.get_top_daily_streak(15)
        
        if not top_users:
            await callback.message.edit_text(
                "🎁 <b>ТОП ПО DAILY СТРИКУ</b>\n\nПока нет данных! Получите ежедневный бонус.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        text = "🎁 <b>ТОП-15 ПО DAILY СТРИКУ</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, u in enumerate(top_users, 1):
            if u is None:
                continue
            medal = get_medal(i)
            name = escape_name(u)
            streak = safe_get(u, "daily_streak", 0)
            text += f"{medal} <b>{name}</b> — {streak} дней\n"
        
        user_id = callback.from_user.id
        user = await db.get_user(user_id)
        if user:
            user_streak = safe_get(user, "daily_streak", 0)
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n🎁 Ваш стрик: <b>{user_streak} дней</b>"
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in top_daily: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "top_donors")
async def top_donors_callback(callback: types.CallbackQuery):
    """Топ донатеров"""
    try:
        top_users = await db.get_top_donors(15)
        
        if not top_users:
            await callback.message.edit_text(
                "💎 <b>ТОП ДОНАТЕРОВ</b>\n\nПока нет донатов. Будьте первым!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard("stats_tops")
            )
            await callback.answer()
            return
        
        text = format_top_list(
            "💎 <b>ТОП-15 ДОНАТЕРОВ</b>",
            top_users,
            value_key="total_donated",
            suffix=" ₽",
            show_extra=True
        )
        text += "\n\n━━━━━━━━━━━━━━━━━━━━━\n❤️ <i>Спасибо за поддержку проекта!</i>"
        
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard("stats_tops")
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in top_donors: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ИНТЕГРАЦИОННЫЕ ФУНКЦИИ ====================

async def track_message(user_id: int, message: types.Message):
    """Отслеживание сообщения"""
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
        logger.debug(f"Message tracked: user={user_id}, type={activity_type}")
    except Exception as e:
        logger.error(f"Error tracking message: {e}")


async def track_xo_game(user_id: int, result_type: str, bet: int = 0, won: int = 0):
    """Отслеживание игры в крестики-нолики"""
    try:
        await db.update_xo_stats(user_id, result_type, bet, won)
        await db.track_user_activity(user_id, "xo_game", 1)
        logger.debug(f"XO game tracked: user={user_id}, result={result_type}")
    except Exception as e:
        logger.error(f"Error tracking XO game: {e}")


async def update_all_streaks():
    """Обновление стриков всех пользователей"""
    try:
        await db.update_user_streaks()
        logger.info("✅ Стрики активности обновлены")
    except Exception as e:
        logger.error(f"Error updating streaks: {e}")


async def reset_daily_counters():
    """Сброс дневных счётчиков"""
    try:
        await db.reset_daily_counters()
        logger.info("✅ Дневные счётчики сброшены")
    except Exception as e:
        logger.error(f"Error resetting daily counters: {e}")
