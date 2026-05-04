#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/referral.py
# ВЕРСИЯ: 2.2.0-production (исправленная после аудита)
# ОПИСАНИЕ: Реферальная система
# ============================================
# ИСПРАВЛЕНИЯ v2.2.0:
#   🔴 Устранены прямые вызовы роутер-хендлеров
#   🔴 Добавлены индексы для БД
#   🟡 Кэширование bot_username
#   🟡 Валидация ref_code из deep linking
#   🟡 Вынесена общая логика форматирования
#   🟡 Все ошибки логируются
#   🟢 Константы вынесены в os.getenv()
#   🟢 Добавлены docstrings
# ============================================

import asyncio
import html
import logging
import os
import re
import secrets
import string
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError

logger = logging.getLogger(__name__)
router = Router()

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

_bot: Optional[Bot] = None
_cached_bot_username: Optional[str] = None
_username_lock: asyncio.Lock = asyncio.Lock()


def set_bot(bot_instance: Bot) -> None:
    """Установка экземпляра бота."""
    global _bot
    _bot = bot_instance


async def _get_bot_username() -> Optional[str]:
    """
    Получение username бота с кэшированием.
    
    Returns:
        Username бота или None
    """
    global _cached_bot_username
    
    if _cached_bot_username:
        return _cached_bot_username
    
    async with _username_lock:
        if _cached_bot_username:
            return _cached_bot_username
        
        if _bot:
            try:
                me = await _bot.get_me()
                _cached_bot_username = me.username
                logger.info(f"✅ Cached bot username: @{_cached_bot_username}")
            except TelegramAPIError as e:
                logger.error(f"❌ Failed to get bot username: {e}")
    
    return _cached_bot_username


# ==================== КОНСТАНТЫ (НАСТРАИВАЕМЫЕ) ====================

REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "100"))
REF_CODE_LENGTH = int(os.getenv("REF_CODE_LENGTH", "8"))

REWARDS: Dict[int, int] = {
    1: int(os.getenv("REF_REWARD_1", "100")),
    5: int(os.getenv("REF_REWARD_5", "500")),
    10: int(os.getenv("REF_REWARD_10", "1000")),
    25: int(os.getenv("REF_REWARD_25", "3000")),
    50: int(os.getenv("REF_REWARD_50", "7000")),
    100: int(os.getenv("REF_REWARD_100", "15000")),
    250: int(os.getenv("REF_REWARD_250", "50000")),
    500: int(os.getenv("REF_REWARD_500", "150000")),
    1000: int(os.getenv("REF_REWARD_1000", "500000")),
}

# Всегда держим отсортированным
REWARDS_SORTED = sorted(REWARDS.keys())

# Медали для топа
MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """
    Безопасное экранирование HTML.
    
    Args:
        text: Строка для экранирования
        
    Returns:
        Экранированная строка
    """
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def generate_ref_code(length: int = REF_CODE_LENGTH) -> str:
    """
    Генерация уникального реферального кода.
    
    Args:
        length: Длина кода
        
    Returns:
        Строка из заглавных букв и цифр
        
    Example:
        >>> code = generate_ref_code()
        >>> len(code)
        8
    """
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def validate_ref_code(code: str) -> bool:
    """
    Валидация реферального кода.
    
    Args:
        code: Строка для проверки
        
    Returns:
        True если код валиден
    """
    if not code:
        return False
    return bool(re.match(rf'^[A-Z0-9]{{{REF_CODE_LENGTH}}}$', code))


async def is_chat_owner(bot: Bot, user_id: int, chat_id: int) -> bool:
    """
    Проверка, является ли пользователь создателем чата.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        True если создатель
    """
    if bot is None or user_id is None or chat_id is None:
        return False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status == 'creator'
    except TelegramAPIError as e:
        logger.warning(f"⚠️ is_chat_owner check failed for {user_id} in {chat_id}: {e}")
        return False


async def is_bot_admin(bot: Bot, chat_id: int) -> bool:
    """
    Проверка, является ли бот администратором чата.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        
    Returns:
        True если бот админ
    """
    if bot is None or chat_id is None:
        return False
    try:
        bot_id = (await bot.get_me()).id
        member = await bot.get_chat_member(chat_id, bot_id)
        return member.status in ['creator', 'administrator']
    except TelegramAPIError as e:
        logger.warning(f"⚠️ is_bot_admin check failed for {chat_id}: {e}")
        return False


async def init_ref_tables() -> None:
    """Инициализация таблиц реферальной системы."""
    if db is None:
        return
    try:
        await db._execute_with_retry("""CREATE TABLE IF NOT EXISTS ref_settings (
            chat_id INTEGER PRIMARY KEY, enabled BOOLEAN DEFAULT 0, ref_link TEXT,
            bonus_amount INTEGER DEFAULT 100, created_at TEXT)""")
        await db._execute_with_retry("""CREATE TABLE IF NOT EXISTS ref_links (
            user_id INTEGER, chat_id INTEGER, ref_code TEXT UNIQUE, invited_count INTEGER DEFAULT 0,
            earned_coins INTEGER DEFAULT 0, created_at TEXT, PRIMARY KEY (user_id, chat_id))""")
        await db._execute_with_retry("""CREATE TABLE IF NOT EXISTS ref_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT, inviter_id INTEGER, invited_id INTEGER,
            chat_id INTEGER, invited_at TEXT)""")
        await db._execute_with_retry("""CREATE TABLE IF NOT EXISTS ref_milestones (
            user_id INTEGER, chat_id INTEGER, milestone INTEGER, awarded BOOLEAN DEFAULT 0,
            awarded_at TIMESTAMP, PRIMARY KEY (user_id, chat_id, milestone))""")
        
        # Индексы для производительности
        await db._execute_with_retry(
            "CREATE INDEX IF NOT EXISTS idx_ref_invites_chat ON ref_invites(chat_id)")
        await db._execute_with_retry(
            "CREATE INDEX IF NOT EXISTS idx_ref_links_chat ON ref_links(chat_id, invited_count DESC)")
        await db._execute_with_retry(
            "CREATE INDEX IF NOT EXISTS idx_ref_milestones_user ON ref_milestones(user_id, chat_id)")
        
        logger.info("✅ Referral tables initialized")
    except DatabaseError as e:
        logger.error(f"❌ Init ref tables error: {e}", exc_info=True)


async def check_milestone_reward(inviter_id: int, invited_count: int, chat_id: int) -> None:
    """
    Проверка и выдача наград за достижения.
    
    Args:
        inviter_id: ID пригласившего
        invited_count: Количество приглашённых
        chat_id: ID чата
    """
    if db is None:
        return
    try:
        for milestone in REWARDS_SORTED:
            if invited_count >= milestone:
                row = await db._execute_with_retry(
                    "SELECT awarded FROM ref_milestones WHERE user_id=? AND chat_id=? AND milestone=?",
                    (inviter_id, chat_id, milestone), fetch_one=True
                )
                if not row or not row.get("awarded"):
                    reward = REWARDS[milestone]
                    await db._execute_with_retry(
                        "INSERT OR REPLACE INTO ref_milestones (user_id,chat_id,milestone,awarded,awarded_at) VALUES (?,?,?,1,?)",
                        (inviter_id, chat_id, milestone, datetime.now().isoformat()))
                    await db.update_balance(inviter_id, reward, f"Реферальная награда за {milestone} приглашений")
                    
                    # Попытка начислить XP
                    try:
                        from handlers.ranks import track_referral
                        await track_referral(inviter_id)
                    except ImportError:
                        logger.debug("Ranks module not available for referral XP")
                    
                    # Уведомление пользователю
                    if _bot:
                        try:
                            next_milestones = [m for m in REWARDS_SORTED if m > milestone]
                            next_goal = next_milestones[0] if next_milestones else "МАКСИМУМ"
                            await _bot.send_message(
                                inviter_id,
                                f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                                f"Вы пригласили {milestone} друзей!\n"
                                f"💰 Награда: +{reward} NCoins!\n"
                                f"📊 Следующая цель: {next_goal} приглашений",
                                parse_mode=ParseMode.HTML)
                        except TelegramAPIError as e:
                            logger.warning(f"⚠️ Could not notify {inviter_id}: {e}")
    except DatabaseError as e:
        logger.error(f"❌ Milestone error for {inviter_id}: {e}", exc_info=True)


def _format_user_name(user: Optional[Dict], user_id: int) -> str:
    """
    Форматирование имени пользователя для отображения.
    
    Args:
        user: Данные пользователя из БД
        user_id: ID пользователя (fallback)
        
    Returns:
        Отформатированное имя
    """
    if user and user.get('username'):
        return f"@{safe_html_escape(user['username'])}"
    elif user and user.get('first_name'):
        return safe_html_escape(user['first_name'][:20])
    return f"ID {user_id}"


def _get_medal(index: int) -> str:
    """Получить медаль по индексу."""
    return MEDALS[index] if index < len(MEDALS) else f"{index+1}."


# ==================== ПОСТРОИТЕЛИ ТЕКСТА ====================

async def _build_my_ref_text(user_id: int, chat_id: int) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """
    Построить текст и клавиатуру для реферальной ссылки пользователя.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        Tuple[HTML-текст, клавиатура или None]
    """
    await init_ref_tables()
    
    setting = await db._execute_with_retry(
        "SELECT enabled,bonus_amount FROM ref_settings WHERE chat_id=?",
        (chat_id,), fetch_one=True
    )
    
    if not setting or not setting['enabled']:
        return (
            "❌ Реферальная система не включена в этом чате!",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    
    user_ref = await db._execute_with_retry(
        "SELECT ref_code,invited_count,earned_coins FROM ref_links WHERE user_id=? AND chat_id=?",
        (user_id, chat_id), fetch_one=True
    )
    
    if not user_ref:
        ref_code = generate_ref_code()
        await db._execute_with_retry(
            "INSERT INTO ref_links (user_id,chat_id,ref_code,created_at) VALUES (?,?,?,?)",
            (user_id, chat_id, ref_code, datetime.now().isoformat())
        )
        user_ref = {"ref_code": ref_code, "invited_count": 0, "earned_coins": 0}
    else:
        ref_code = user_ref['ref_code']
    
    # Получаем достижения
    milestones_rows = await db._execute_with_retry(
        "SELECT milestone FROM ref_milestones WHERE user_id=? AND chat_id=? AND awarded=1 ORDER BY milestone",
        (user_id, chat_id), fetch_all=True
    )
    awarded = {r['milestone'] for r in (milestones_rows or [])}
    
    # Формируем текст достижений
    rewards_text = ""
    for m in REWARDS_SORTED:
        r = REWARDS[m]
        if m in awarded:
            rewards_text += f"✅ {m} пригл. — +{r} NCoins\n"
        elif user_ref['invited_count'] >= m:
            rewards_text += f"🎉 {m} пригл. — +{r} NCoins (доступно!)\n"
        else:
            remaining = m - user_ref['invited_count']
            rewards_text += f"🔜 {m} пригл. — +{r} NCoins (ещё {remaining})\n"
    
    bot_username = await _get_bot_username()
    if not bot_username:
        return (
            "❌ Ошибка: не удалось получить username бота.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    
    ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
    
    text = (
        f"🔗 <b>ВАША ССЫЛКА</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>СТАТИСТИКА:</b>\n"
        f"├ 👥 Приглашено: {user_ref['invited_count']}\n"
        f"└ 💰 Заработано: {user_ref['earned_coins']}\n\n"
        f"💰 <b>БОНУС:</b> +{setting['bonus_amount']} NCoins\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🏆 ДОСТИЖЕНИЯ:</b>\n{rewards_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 Чем больше друзей — тем выше награда!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ", url=f"https://t.me/share/url?url={ref_link}")],
        [InlineKeyboardButton(text="📊 ТОП", callback_data="ref_top")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    return text, keyboard


async def _build_top_referrals_text(chat_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Построить текст и клавиатуру для топа пригласителей.
    
    Args:
        chat_id: ID чата
        
    Returns:
        Tuple[HTML-текст, клавиатура]
    """
    top = await db._execute_with_retry(
        "SELECT user_id,invited_count,earned_coins FROM ref_links WHERE chat_id=? ORDER BY invited_count DESC LIMIT 10",
        (chat_id,), fetch_all=True
    )
    
    if not top:
        return (
            "🏆 <b>ТОП ПРИГЛАСИТЕЛЕЙ</b>\n\nПока нет приглашений!",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="ref_menu")]
            ])
        )
    
    text = "🏆 <b>ТОП ПРИГЛАСИТЕЛЕЙ</b>\n\n"
    for i, row in enumerate(top):
        medal = _get_medal(i)
        user = await db.get_user(row['user_id'])
        name = _format_user_name(user, row['user_id'])
        text += f"{medal} {name} — {row['invited_count']} пригл. (+{row['earned_coins']})\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="ref_menu")]
    ])
    
    return text, keyboard


# ==================== КОМАНДЫ ВЛАДЕЛЬЦА ====================

@router.message(Command("enable_ref"))
async def enable_referral(message: Message) -> None:
    """
    Включение реферальной системы в чате.
    
    Только для создателя чата. Генерирует реферальную ссылку.
    """
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id, user_id = message.chat.id, message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Только в группах!")
        return
    if not await is_bot_admin(message.bot, chat_id):
        await message.answer("❌ Бот не админ!")
        return
    if not await is_chat_owner(message.bot, user_id, chat_id):
        await message.answer("❌ Только владелец!")
        return
    
    await init_ref_tables()
    ref_code = generate_ref_code()
    bot_username = await _get_bot_username()
    
    if not bot_username:
        await message.answer("❌ Не удалось получить username бота.")
        return
    
    ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
    
    try:
        await db._execute_with_retry(
            "INSERT OR REPLACE INTO ref_settings (chat_id,enabled,ref_link,bonus_amount,created_at) VALUES (?,1,?,100,?)",
            (chat_id, ref_link, datetime.now().isoformat())
        )
        
        rewards_text = "\n".join(
            f"├ {m} пригл. → +{r} NCoins" 
            for m, r in list(REWARDS.items())[:5]
        )
        
        await message.answer(
            f"✅ <b>Реферальная система ВКЛЮЧЕНА!</b>\n\n"
            f"🔗 <code>{ref_link}</code>\n\n"
            f"💰 За друга: +{REFERRAL_BONUS} NCoins\n\n"
            f"<b>🏆 БОНУСЫ:</b>\n{rewards_text}\n└ ... и больше!",
            parse_mode=ParseMode.HTML
        )
    except DatabaseError as e:
        logger.error(f"❌ Enable ref error: {e}", exc_info=True)
        await message.answer("❌ Ошибка БД.")


@router.message(Command("disable_ref"))
async def disable_referral(message: Message) -> None:
    """Отключение реферальной системы в чате."""
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id, user_id = message.chat.id, message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Только в группах!")
        return
    if not await is_chat_owner(message.bot, user_id, chat_id):
        await message.answer("❌ Только владелец!")
        return
    
    try:
        await db._execute_with_retry(
            "UPDATE ref_settings SET enabled=0 WHERE chat_id=?", (chat_id,)
        )
        await message.answer(
            "❌ <b>Реферальная система ВЫКЛЮЧЕНА!</b>", parse_mode=ParseMode.HTML
        )
    except DatabaseError as e:
        logger.error(f"❌ Disable ref error: {e}", exc_info=True)
        await message.answer("❌ Ошибка БД.")


@router.message(Command("ref_stats"))
async def ref_stats(message: Message) -> None:
    """Статистика реферальной системы (для владельца)."""
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id, user_id = message.chat.id, message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Только в группах!")
        return
    if not await is_chat_owner(message.bot, user_id, chat_id):
        await message.answer("❌ Только владелец!")
        return
    
    try:
        setting = await db._execute_with_retry(
            "SELECT enabled,bonus_amount FROM ref_settings WHERE chat_id=?",
            (chat_id,), fetch_one=True
        )
        top = await db._execute_with_retry(
            "SELECT user_id,invited_count,earned_coins FROM ref_links WHERE chat_id=? ORDER BY invited_count DESC LIMIT 10",
            (chat_id,), fetch_all=True
        )
        total = await db._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM ref_invites WHERE chat_id=?",
            (chat_id,), fetch_one=True
        )
        milestones = await db._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM ref_milestones WHERE chat_id=?",
            (chat_id,), fetch_one=True
        )
        
        text = (
            f"📊 <b>СТАТИСТИКА РЕФЕРАЛКИ</b>\n\n"
            f"📢 Статус: {'✅ ВКЛ' if setting and setting['enabled'] else '❌ ВЫКЛ'}\n"
            f"💰 Бонус: {setting['bonus_amount'] if setting else 100}\n"
            f"👥 Приглашений: {total['cnt'] if total else 0}\n"
            f"🏆 Наград: {milestones['cnt'] if milestones else 0}\n\n"
        )
        
        if top:
            text += "<b>🏆 ТОП-5:</b>\n"
            for i, row in enumerate(top[:5]):
                medal = _get_medal(i)
                user = await db.get_user(row['user_id'])
                name = _format_user_name(user, row['user_id'])
                text += f"{medal} {name} — {row['invited_count']} пригл. (+{row['earned_coins']})\n"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
    except DatabaseError as e:
        logger.error(f"❌ Ref stats error: {e}", exc_info=True)
        await message.answer("❌ Ошибка БД.")


# ==================== КОМАНДЫ УЧАСТНИКОВ ====================

@router.message(Command("my_ref"))
async def my_referral_link(message: Message) -> None:
    """
    Показать реферальную ссылку пользователя.
    
    Отображает ссылку, статистику и достижения.
    """
    if not message or not message.chat or not message.from_user:
        return
    
    user_id, chat_id = message.from_user.id, message.chat.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Только в группах!")
        return
    
    try:
        text, keyboard = await _build_my_ref_text(user_id, chat_id)
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        logger.info(f"✅ My ref viewed by user {user_id} in chat {chat_id}")
    except DatabaseError as e:
        logger.error(f"❌ My ref error: {e}", exc_info=True)
        await message.answer("❌ Ошибка БД.")


@router.callback_query(F.data == "ref_top")
async def ref_top_callback(callback: CallbackQuery) -> None:
    """Callback для отображения топа пригласителей."""
    if not callback or not callback.message:
        return
    
    chat_id = callback.message.chat.id
    
    try:
        text, keyboard = await _build_top_referrals_text(chat_id)
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await callback.answer()
    except DatabaseError as e:
        logger.error(f"❌ Ref top error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ОБРАБОТКА ПРИГЛАШЕНИЯ ====================

async def process_referral_start(message: Message, chat_id: int, ref_code: str) -> None:
    """
    Обработка перехода по реферальной ссылке.
    
    Вызывается из bot.py при получении deep linking параметра.
    
    Args:
        message: Сообщение пользователя
        chat_id: ID чата
        ref_code: Реферальный код
    """
    if not message or not message.from_user:
        return
    
    # ✅ Валидация кода
    if not validate_ref_code(ref_code):
        logger.warning(f"⚠️ Invalid ref_code format: {ref_code}")
        return
    
    try:
        inviter = await db._execute_with_retry(
            "SELECT user_id FROM ref_links WHERE ref_code=? AND chat_id=?",
            (ref_code, chat_id), fetch_one=True
        )
        if not inviter:
            return
        
        inviter_id, invited_id = inviter['user_id'], message.from_user.id
        
        if inviter_id == invited_id:
            await message.answer("❌ Нельзя пригласить себя!")
            return
        
        # Проверка на повторное приглашение
        existing = await db._execute_with_retry(
            "SELECT id FROM ref_invites WHERE inviter_id=? AND invited_id=? AND chat_id=?",
            (inviter_id, invited_id, chat_id), fetch_one=True
        )
        if existing:
            return
        
        setting = await db._execute_with_retry(
            "SELECT bonus_amount FROM ref_settings WHERE chat_id=?",
            (chat_id,), fetch_one=True
        )
        bonus = setting['bonus_amount'] if setting else REFERRAL_BONUS
        
        await db._execute_with_retry(
            "INSERT INTO ref_invites (inviter_id,invited_id,chat_id,invited_at) VALUES (?,?,?,?)",
            (inviter_id, invited_id, chat_id, datetime.now().isoformat())
        )
        await db._execute_with_retry(
            "UPDATE ref_links SET invited_count=invited_count+1, earned_coins=earned_coins+? WHERE user_id=? AND chat_id=?",
            (bonus, inviter_id, chat_id)
        )
        
        new_count_row = await db._execute_with_retry(
            "SELECT invited_count FROM ref_links WHERE user_id=? AND chat_id=?",
            (inviter_id, chat_id), fetch_one=True
        )
        new_count = new_count_row['invited_count'] if new_count_row else 1
        
        await db.update_balance(inviter_id, bonus, "Реферальный бонус")
        
        # Начисление XP
        try:
            from handlers.ranks import track_referral
            await track_referral(inviter_id)
        except ImportError:
            logger.debug("Ranks module not available")
        
        await check_milestone_reward(inviter_id, new_count, chat_id)
        
        # Уведомление пригласившему
        if _bot:
            try:
                await _bot.send_message(
                    inviter_id,
                    f"🎉 <b>НОВЫЙ УЧАСТНИК!</b>\n\n"
                    f"По вашей ссылке присоединился новый участник!\n"
                    f"💰 +{bonus} NCoins!\n📊 Всего: {new_count}",
                    parse_mode=ParseMode.HTML
                )
            except TelegramAPIError as e:
                logger.warning(f"⚠️ Could not notify inviter {inviter_id}: {e}")
                
    except DatabaseError as e:
        logger.error(f"❌ Process referral error: {e}", exc_info=True)


# ==================== МЕНЮ ====================

@router.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: CallbackQuery) -> None:
    """Меню реферальной системы."""
    if not callback or not callback.message:
        return
    
    rewards_text = "\n".join(
        f"├ {m} друзей: +{r} NCoins" 
        for m, r in list(REWARDS.items())[:5]
    )
    
    await callback.message.edit_text(
        f"📢 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b>\n\n"
        f"Приглашайте друзей и получайте NCoins!\n\n"
        f"💰 <b>БОНУСЫ:</b>\n├ За каждого: +{REFERRAL_BONUS} NCoins\n"
        f"{rewards_text}\n└ ... и больше!\n\n"
        f"✨ Чем больше друзей — тем выше награда!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 МОЯ ССЫЛКА", callback_data="my_ref")],
            [InlineKeyboardButton(text="📊 ТОП", callback_data="ref_top")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "my_ref")
async def my_ref_callback(callback: CallbackQuery) -> None:
    """Callback для отображения реферальной ссылки."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    try:
        text, keyboard = await _build_my_ref_text(user_id, chat_id)
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        logger.info(f"✅ My ref callback viewed by user {user_id}")
    except DatabaseError as e:
        logger.error(f"❌ My ref callback error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await callback.answer()
