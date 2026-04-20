# ============================================
# ФАЙЛ: handlers/stats.py
# ОПИСАНИЕ: Модуль статистики NEXUS Bot — ОБЪЕДИНЁННАЯ ЛУЧШАЯ ВЕРСИЯ
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# ============================================

import asyncio
import logging
import html
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_number(num: any) -> str:
    """Форматирование числа с разделителями"""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def format_date(date_str: str) -> str:
    """Форматирование даты"""
    if not date_str:
        return "Неизвестно"
    try:
        if len(date_str) >= 10:
            return date_str[:10]
        return date_str
    except:
        return "Неизвестно"


def get_medal(position: int) -> str:
    """Получить медаль для позиции"""
    if position is None:
        return "—"
    if position == 1:
        return "🥇"
    elif position == 2:
        return "🥈"
    elif position == 3:
        return "🥉"
    else:
        return f"{position}."


def safe_get(obj: dict, key: str, default: any = 0) -> any:
    """Безопасное получение значения из словаря"""
    if obj is None:
        return default
    value = obj.get(key)
    return value if value is not None else default


def escape_name(user: dict) -> str:
    """Безопасное получение имени пользователя"""
    if user is None:
        return "Пользователь"
    
    username = user.get("username")
    if username:
        return f"@{html.escape(username)}"
    
    first_name = user.get("first_name")
    if first_name:
        return html.escape(first_name[:20] if len(first_name) > 20 else first_name)
    
    return "Пользователь"


# ==================== КЛАВИАТУРЫ ====================

def stats_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню статистики"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="stats_my")],
        [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


def tops_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню топов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ТОП ПО СООБЩЕНИЯМ", callback_data="top_messages")],
        [InlineKeyboardButton(text="💰 ТОП ПО БАЛАНСУ", callback_data="top_balance")],
        [InlineKeyboardButton(text="🎮 ТОП ПО КРЕСТИКАМ-НОЛИКАМ", callback_data="top_xo")],
        [InlineKeyboardButton(text="🔥 ТОП ПО АКТИВНОСТИ", callback_data="top_activity")],
        [InlineKeyboardButton(text="🎁 ТОП ПО DAILY СТРИКУ", callback_data="top_daily")],
        [InlineKeyboardButton(text="💎 ТОП ДОНАТЕРОВ", callback_data="top_donors")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
    ])


def back_to_stats_keyboard() -> InlineKeyboardMarkup:
    """Кнопка назад к статистике"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
    ])


def back_to_tops_keyboard() -> InlineKeyboardMarkup:
    """Кнопка назад к топам"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_tops")]
    ])


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Показать статистику пользователя"""
    if message is None:
        return
        
    args = message.text.strip().split() if message.text else []
    
    # Если указан @username
    if len(args) > 1 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        if username:
            target_user = await db.get_user_by_username(username)
            if not target_user:
                await message.answer(f"❌ Пользователь @{username} не найден!")
                return
            target_id = target_user.get("user_id")
            if target_id is None:
                await message.answer(f"❌ Пользователь не активировал бота!")
                return
        else:
            target_id = message.from_user.id
    else:
        target_id = message.from_user.id
    
    if target_id is None:
        await message.answer("❌ Не удалось определить пользователя!")
        return
    
    stats = await db.get_user_stats(target_id)
    user = await db.get_user(target_id)
    
    if not stats or not user:
        await message.answer(
            "❌ Статистика не найдена!\n\n"
            "Используйте /start для регистрации.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Формируем ответ
    name_display = escape_name(user)
    first_name = html.escape(user.get("first_name") or "Пользователь")
    
    register_date = format_date(safe_get(stats, "user_register_date", ""))
    days_active = safe_get(stats, "days_active", 0)
    
    text = f"""
📊 <b>СТАТИСТИКА {name_display}</b>

👤 <b>{first_name}</b>
📅 В боте с: {register_date} ({days_active} дней)

━━━━━━━━━━━━━━━━━━━━━

💬 <b>АКТИВНОСТЬ:</b>
├ Всего сообщений: <b>{format_number(safe_get(stats, 'messages_total'))}</b>
├ Сегодня: <b>{format_number(safe_get(stats, 'messages_today'))}</b>
├ За неделю: <b>{format_number(safe_get(stats, 'messages_week'))}</b>
├ За месяц: <b>{format_number(safe_get(stats, 'messages_month'))}</b>
├ Голосовых: <b>{format_number(safe_get(stats, 'total_voice'))}</b>
├ Стикеров: <b>{format_number(safe_get(stats, 'total_stickers'))}</b>
└ Медиа: <b>{format_number(safe_get(stats, 'total_photos', 0) + safe_get(stats, 'total_videos', 0) + safe_get(stats, 'total_gifs', 0))}</b>

🔥 <b>СТРИК АКТИВНОСТИ:</b>
├ Дней активности: <b>{format_number(days_active)}</b>
├ Текущий стрик: <b>{format_number(safe_get(stats, 'current_streak'))} дней</b>
└ Макс. стрик: <b>{format_number(safe_get(stats, 'max_streak'))} дней</b>

━━━━━━━━━━━━━━━━━━━━━

🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>
├ Игр всего: <b>{format_number(safe_get(stats, 'games_played'))}</b>
├ Побед: <b>{format_number(safe_get(stats, 'wins'))}</b>
├ Поражений: <b>{format_number(safe_get(stats, 'losses'))}</b>
├ Ничьих: <b>{format_number(safe_get(stats, 'draws'))}</b>
├ Побед над ботом: <b>{format_number(safe_get(stats, 'wins_vs_bot'))}</b>
├ Поражений от бота: <b>{format_number(safe_get(stats, 'losses_vs_bot'))}</b>
├ Текущий винстрик: <b>{format_number(safe_get(stats, 'current_win_streak'))}</b>
└ Макс. винстрик: <b>{format_number(safe_get(stats, 'max_win_streak'))}</b>

━━━━━━━━━━━━━━━━━━━━━

💰 <b>ЭКОНОМИКА:</b>
├ Баланс: <b>{format_number(safe_get(stats, 'balance'))} NCoin</b>
├ Всего заработано: <b>{format_number(safe_get(stats, 'total_earned'))} NCoin</b>
├ Всего потрачено: <b>{format_number(safe_get(stats, 'total_spent'))} NCoin</b>
├ Переведено другим: <b>{format_number(safe_get(stats, 'total_transferred'))} NCoin</b>
├ Получено переводов: <b>{format_number(safe_get(stats, 'total_received'))} NCoin</b>
├ Макс. баланс: <b>{format_number(safe_get(stats, 'max_balance'))} NCoin</b>
├ Daily бонусов: <b>{format_number(safe_get(stats, 'daily_claims'))} раз</b>
└ Daily стрик: <b>{format_number(safe_get(stats, 'daily_streak'))} дней</b>

━━━━━━━━━━━━━━━━━━━━━

💎 <b>ДОНАТ:</b>
├ Задоначено: <b>{format_number(safe_get(stats, 'total_donated_rub'))} ₽</b>
└ Получено NCoin: <b>{format_number(safe_get(stats, 'total_donated_coins'))}</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
        [InlineKeyboardButton(text="◀️ В МЕНЮ", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(Command("top"))
async def cmd_top(message: types.Message):
    """Меню топов"""
    if message is None:
        return
        
    await message.answer(
        "🏆 <b>ТОПЫ NEXUS</b>\n\n"
        "Выберите категорию:",
        parse_mode=ParseMode.HTML,
        reply_markup=tops_menu_keyboard()
    )


# ==================== ОБРАБОТЧИКИ КНОПОК СТАТИСТИКИ ====================

@router.callback_query(F.data == "stats_menu")
async def stats_menu_callback(callback: types.CallbackQuery):
    """Меню статистики"""
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "📊 <b>СТАТИСТИКА</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=stats_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "stats_my")
async def stats_my_callback(callback: types.CallbackQuery):
    """Моя статистика"""
    if callback is None or callback.message is None:
        return
        
    target_id = callback.from_user.id
    if target_id is None:
        await callback.answer("❌ Не удалось определить пользователя!", show_alert=True)
        return
        
    stats = await db.get_user_stats(target_id)
    user = await db.get_user(target_id)
    
    if not stats or not user:
        await callback.message.edit_text(
            "❌ Статистика не найдена!\n\n"
            "Используйте /start для регистрации.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_stats_keyboard()
        )
        await callback.answer()
        return
    
    name_display = escape_name(user)
    first_name = html.escape(user.get("first_name") or "Пользователь")
    
    register_date = format_date(safe_get(stats, "user_register_date", ""))
    days_active = safe_get(stats, "days_active", 0)
    
    # Винрейт
    games = safe_get(stats, "games_played", 0)
    wins = safe_get(stats, "wins", 0)
    winrate = (wins / games * 100) if games > 0 else 0
    
    text = f"""
📊 <b>СТАТИСТИКА {name_display}</b>

👤 <b>{first_name}</b>
📅 В боте с: {register_date} ({days_active} дней)

━━━━━━━━━━━━━━━━━━━━━

💬 <b>АКТИВНОСТЬ:</b>
├ Всего сообщений: <b>{format_number(safe_get(stats, 'messages_total'))}</b>
├ Сегодня: <b>{format_number(safe_get(stats, 'messages_today'))}</b>
├ За неделю: <b>{format_number(safe_get(stats, 'messages_week'))}</b>
└ За месяц: <b>{format_number(safe_get(stats, 'messages_month'))}</b>

🔥 <b>СТРИК АКТИВНОСТИ:</b>
├ Дней активности: <b>{format_number(days_active)}</b>
├ Текущий стрик: <b>{format_number(safe_get(stats, 'current_streak'))} дней</b>
└ Макс. стрик: <b>{format_number(safe_get(stats, 'max_streak'))} дней</b>

━━━━━━━━━━━━━━━━━━━━━

🎮 <b>КРЕСТИКИ-НОЛИКИ:</b>
├ Игр всего: <b>{format_number(games)}</b>
├ Побед: <b>{format_number(wins)}</b>
├ Поражений: <b>{format_number(safe_get(stats, 'losses'))}</b>
├ Ничьих: <b>{format_number(safe_get(stats, 'draws'))}</b>
├ Винрейт: <b>{winrate:.1f}%</b>
├ Текущий винстрик: <b>{format_number(safe_get(stats, 'current_win_streak'))}</b>
└ Макс. винстрик: <b>{format_number(safe_get(stats, 'max_win_streak'))}</b>

━━━━━━━━━━━━━━━━━━━━━

💰 <b>ЭКОНОМИКА:</b>
├ Баланс: <b>{format_number(safe_get(stats, 'balance'))} NCoin</b>
├ Всего заработано: <b>{format_number(safe_get(stats, 'total_earned'))} NCoin</b>
├ Всего потрачено: <b>{format_number(safe_get(stats, 'total_spent'))} NCoin</b>
├ Daily бонусов: <b>{format_number(safe_get(stats, 'daily_claims'))} раз</b>
└ Daily стрик: <b>{format_number(safe_get(stats, 'daily_streak'))} дней</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 ТОПЫ", callback_data="stats_tops")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="stats_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "stats_tops")
async def stats_tops_callback(callback: types.CallbackQuery):
    """Меню топов"""
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "🏆 <b>ТОПЫ NEXUS</b>\n\n"
        "Выберите категорию:",
        parse_mode=ParseMode.HTML,
        reply_markup=tops_menu_keyboard()
    )
    await callback.answer()


# ==================== ОБРАБОТЧИКИ ТОПОВ ====================

@router.callback_query(F.data == "top_messages")
async def top_messages_callback(callback: types.CallbackQuery):
    """Топ по сообщениям"""
    if callback is None or callback.message is None:
        return
        
    top_users = await db.get_top_messages(15)
    
    if not top_users:
        await callback.message.edit_text(
            "📊 Пока нет данных!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_tops_keyboard()
        )
        await callback.answer()
        return
    
    text = "💬 <b>ТОП-15 ПО СООБЩЕНИЯМ</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, u in enumerate(top_users, 1):
        if u is None:
            continue
        medal = get_medal(i)
        name = escape_name(u)
        messages = format_number(u.get("messages_total", 0))
        text += f"{medal} <b>{name}</b> — {messages} сообщ.\n"
    
    user_id = callback.from_user.id
    if user_id:
        user_stats = await db.get_user_stats(user_id)
        user_messages = safe_get(user_stats, "messages_total", 0) if user_stats else 0
        if user_messages > 0:
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n📊 Ваши сообщения: <b>{format_number(user_messages)}</b>"
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_tops_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "top_balance")
async def top_balance_callback(callback: types.CallbackQuery):
    """Топ по балансу"""
    if callback is None or callback.message is None:
        return
        
    top_users = await db.get_top_balance(15)
    
    if not top_users:
        await callback.message.edit_text(
            "📊 Пока нет данных!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_tops_keyboard()
        )
        await callback.answer()
        return
    
    text = "💰 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, u in enumerate(top_users, 1):
        if u is None:
            continue
        medal = get_medal(i)
        name = escape_name(u)
        balance = format_number(u.get("balance", 0))
        vip = " ⭐" if safe_get(u, "vip_level", 0) > 0 else ""
        text += f"{medal} <b>{name}</b>{vip} — {balance} NCoin\n"
    
    user_id = callback.from_user.id
    if user_id:
        user_balance = await db.get_balance(user_id)
        if user_balance > 0:
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n💰 Ваш баланс: <b>{format_number(user_balance)} NCoin</b>"
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_tops_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "top_xo")
async def top_xo_callback(callback: types.CallbackQuery):
    """Топ по крестикам-ноликам"""
    if callback is None or callback.message is None:
        return
        
    top_users = await db.get_top_xo(15)
    
    if not top_users:
        await callback.message.edit_text(
            "📊 Пока нет данных! Сыграйте хотя бы 3 игры.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_tops_keyboard()
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
    if user_id:
        user_stats = await db.get_user_stats(user_id)
        if user_stats:
            user_wins = safe_get(user_stats, "wins", 0)
            user_games = safe_get(user_stats, "games_played", 0)
            if user_games > 0:
                user_winrate = (user_wins / user_games * 100) if user_games > 0 else 0
                text += f"\n━━━━━━━━━━━━━━━━━━━━━\n🎮 Ваши победы: <b>{user_wins}</b> ({user_games} игр, {user_winrate:.1f}%)"
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_tops_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "top_activity")
async def top_activity_callback(callback: types.CallbackQuery):
    """Топ по активности"""
    if callback is None or callback.message is None:
        return
        
    top_users = await db.get_top_activity(15)
    
    if not top_users:
        await callback.message.edit_text(
            "📊 Пока нет данных!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_tops_keyboard()
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
    if user_id:
        user_stats = await db.get_user_stats(user_id)
        if user_stats:
            user_days = safe_get(user_stats, "days_active", 0)
            user_streak = safe_get(user_stats, "current_streak", 0)
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n📊 Ваша активность: <b>{user_days} дней (стрик {user_streak})</b>"
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_tops_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "top_daily")
async def top_daily_callback(callback: types.CallbackQuery):
    """Топ по daily стрику"""
    if callback is None or callback.message is None:
        return
        
    top_users = await db.get_top_daily_streak(15)
    
    if not top_users:
        await callback.message.edit_text(
            "📊 Пока нет данных! Получите ежедневный бонус.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_tops_keyboard()
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
    if user_id:
        user = await db.get_user(user_id)
        if user:
            user_streak = safe_get(user, "daily_streak", 0)
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n🎁 Ваш стрик: <b>{user_streak} дней</b>"
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_tops_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "top_donors")
async def top_donors_callback(callback: types.CallbackQuery):
    """Топ донатеров"""
    if callback is None or callback.message is None:
        return
        
    top_users = await db.get_top_donors(15)
    
    if not top_users:
        await callback.message.edit_text(
            "📊 Пока нет донатов. Будьте первым!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_tops_keyboard()
        )
        await callback.answer()
        return
    
    text = "💎 <b>ТОП-15 ДОНАТЕРОВ</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, u in enumerate(top_users, 1):
        if u is None:
            continue
        medal = get_medal(i)
        name = escape_name(u)
        donated = format_number(safe_get(u, "total_donated", 0))
        rank = u.get("donor_rank", "💎 Поддерживающий") or "💎 Поддерживающий"
        text += f"{medal} <b>{name}</b> — {donated} ₽\n   {rank}\n\n"
    
    text += "━━━━━━━━━━━━━━━━━━━━━\n❤️ <i>Спасибо за поддержку проекта!</i>"
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_tops_keyboard()
    )
    await callback.answer()


# ==================== ИНТЕГРАЦИЯ С ГЛАВНЫМ МЕНЮ ====================

@router.callback_query(F.data == "stats")
async def stats_main_callback(callback: types.CallbackQuery):
    """Кнопка СТАТИСТИКА из главного меню"""
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "📊 <b>СТАТИСТИКА</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=stats_menu_keyboard()
    )
    await callback.answer()


# ==================== ФУНКЦИИ ДЛЯ ИНТЕГРАЦИИ ====================

async def track_message(user_id: int, message: types.Message):
    """Отслеживание сообщения (вызывать из smart_commands)"""
    if user_id is None or message is None:
        return
    
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


async def track_xo_game(user_id: int, result_type: str, bet: int = 0, won: int = 0):
    """Отслеживание игры в крестики-нолики"""
    if user_id is None:
        return
    
    await db.update_xo_stats(user_id, result_type, bet if bet is not None else 0, won if won is not None else 0)
    await db.track_user_activity(user_id, "xo_game", 1)


async def update_all_streaks():
    """Обновление стриков всех пользователей (вызывать раз в день)"""
    await db.update_user_streaks()
    logger.info("✅ Стрики активности обновлены")


async def reset_daily_counters():
    """Сброс дневных счётчиков (вызывать в полночь)"""
    await db.reset_daily_counters()
    logger.info("✅ Дневные счётчики сброшены")
