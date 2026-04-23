#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/referral.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Реферальная система NEXUS Bot
# ============================================

import asyncio
import html
import logging
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
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# Глобальный экземпляр бота
_bot: Optional[Bot] = None


def set_bot(bot_instance: Bot) -> None:
    """Установка экземпляра бота."""
    global _bot
    _bot = bot_instance


# ==================== КОНСТАНТЫ ====================

REFERRAL_BONUS = 100  # Бонус за одного приглашённого

REWARDS: Dict[int, int] = {
    1: 100,      # 1 приглашённый
    5: 500,      # 5 приглашённых
    10: 1000,    # 10 приглашённых
    25: 3000,    # 25 приглашённых
    50: 7000,    # 50 приглашённых
    100: 15000,  # 100 приглашённых
    250: 50000,  # 250 приглашённых
    500: 150000, # 500 приглашённых
    1000: 500000 # 1000 приглашённых
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


def generate_ref_code() -> str:
    """Генерирует уникальный реферальный код."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


async def is_chat_owner(bot: Bot, user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем чата."""
    if bot is None or user_id is None or chat_id is None:
        return False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status == 'creator'
    except TelegramAPIError:
        return False


async def is_bot_admin(bot: Bot, chat_id: int) -> bool:
    """Проверяет, является ли бот администратором чата."""
    if bot is None or chat_id is None:
        return False
    try:
        bot_id = (await bot.get_me()).id
        member = await bot.get_chat_member(chat_id, bot_id)
        return member.status in ['creator', 'administrator']
    except TelegramAPIError:
        return False


async def init_ref_tables() -> None:
    """Инициализация таблиц реферальной системы."""
    if db is None:
        return
    
    try:
        await db._execute_with_retry("""
            CREATE TABLE IF NOT EXISTS ref_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                ref_link TEXT,
                bonus_amount INTEGER DEFAULT 100,
                created_at TEXT
            )
        """)
        
        await db._execute_with_retry("""
            CREATE TABLE IF NOT EXISTS ref_links (
                user_id INTEGER,
                chat_id INTEGER,
                ref_code TEXT UNIQUE,
                invited_count INTEGER DEFAULT 0,
                earned_coins INTEGER DEFAULT 0,
                created_at TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        await db._execute_with_retry("""
            CREATE TABLE IF NOT EXISTS ref_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                chat_id INTEGER,
                invited_at TEXT
            )
        """)
        
        await db._execute_with_retry("""
            CREATE TABLE IF NOT EXISTS ref_milestones (
                user_id INTEGER,
                chat_id INTEGER,
                milestone INTEGER,
                awarded BOOLEAN DEFAULT 0,
                awarded_at TIMESTAMP,
                PRIMARY KEY (user_id, chat_id, milestone)
            )
        """)
        
        logger.info("✅ Referral tables initialized")
    except DatabaseError as e:
        logger.error(f"Failed to init referral tables: {e}")


async def check_milestone_reward(inviter_id: int, invited_count: int, chat_id: int) -> None:
    """Проверить и выдать награду за достижение."""
    if db is None:
        return
    
    try:
        for milestone, reward in REWARDS.items():
            if invited_count >= milestone:
                # Проверяем, не выдана ли уже награда
                row = await db._execute_with_retry(
                    "SELECT awarded FROM ref_milestones WHERE user_id = ? AND chat_id = ? AND milestone = ?",
                    (inviter_id, chat_id, milestone),
                    fetch_one=True
                )
                
                if not row or not row.get("awarded"):
                    await db._execute_with_retry(
                        """INSERT OR REPLACE INTO ref_milestones (user_id, chat_id, milestone, awarded, awarded_at)
                           VALUES (?, ?, ?, 1, ?)""",
                        (inviter_id, chat_id, milestone, datetime.now().isoformat()),
                        commit=True
                    )
                    
                    # Начисляем награду
                    await db.update_balance(inviter_id, reward, f"Реферальная награда за {milestone} приглашений")
                    
                    # Отслеживаем XP если модуль доступен
                    try:
                        from handlers.ranks import track_referral
                        await track_referral(inviter_id)
                    except ImportError:
                        pass
                    
                    # Уведомляем пользователя
                    if _bot:
                        try:
                            next_milestones = [m for m in REWARDS.keys() if m > milestone]
                            next_goal = next_milestones[0] if next_milestones else "МАКСИМУМ"
                            
                            await _bot.send_message(
                                inviter_id,
                                f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                                f"Вы пригласили {milestone} друзей!\n"
                                f"💰 Получена награда: +{reward} NCoins!\n\n"
                                f"📊 Следующая цель: {next_goal} приглашений",
                                parse_mode=ParseMode.HTML
                            )
                        except TelegramAPIError:
                            pass
                        
    except DatabaseError as e:
        logger.error(f"Error checking milestone reward: {e}")


# ==================== КОМАНДЫ ДЛЯ ВЛАДЕЛЬЦА ЧАТА ====================

@router.message(Command("enable_ref"))
async def enable_referral(message: Message) -> None:
    """Включить реферальную систему в чате."""
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if not await is_bot_admin(message.bot, chat_id):
        await message.answer(
            "❌ <b>Ошибка:</b> Бот не является администратором чата!\n\n"
            "Добавьте бота в чат и выдайте права администратора.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not await is_chat_owner(message.bot, user_id, chat_id):
        await message.answer("❌ Только владелец чата может включить реферальную систему!")
        return
    
    await init_ref_tables()
    
    ref_code = generate_ref_code()
    bot_username = (await message.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
    
    try:
        await db._execute_with_retry(
            """INSERT OR REPLACE INTO ref_settings (chat_id, enabled, ref_link, bonus_amount, created_at)
               VALUES (?, 1, ?, 100, ?)""",
            (chat_id, ref_link, datetime.now().isoformat()),
            commit=True
        )
        
        rewards_text = ""
        for milestone, reward in REWARDS.items():
            rewards_text += f"├ {milestone} приглашений → +{reward} NCoins\n"
        
        await message.answer(
            f"✅ <b>Реферальная система ВКЛЮЧЕНА!</b>\n\n"
            f"🔗 Ссылка чата: <code>{ref_link}</code>\n\n"
            f"📌 Участники используют /my_ref для получения своей ссылки.\n"
            f"💰 За каждого приглашённого: +{REFERRAL_BONUS} NCoins\n\n"
            f"<b>🏆 БОНУСЫ ЗА ДОСТИЖЕНИЯ:</b>\n{rewards_text}",
            parse_mode=ParseMode.HTML
        )
        
    except DatabaseError as e:
        logger.error(f"Error enabling referral: {e}")
        await message.answer("❌ Ошибка базы данных.")


@router.message(Command("disable_ref"))
async def disable_referral(message: Message) -> None:
    """Выключить реферальную систему."""
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if not await is_chat_owner(message.bot, user_id, chat_id):
        await message.answer("❌ Только владелец чата может выключить реферальную систему!")
        return
    
    try:
        await db._execute_with_retry(
            "UPDATE ref_settings SET enabled = 0 WHERE chat_id = ?",
            (chat_id,),
            commit=True
        )
        await message.answer("❌ <b>Реферальная система ВЫКЛЮЧЕНА!</b>", parse_mode=ParseMode.HTML)
    except DatabaseError as e:
        logger.error(f"Error disabling referral: {e}")
        await message.answer("❌ Ошибка базы данных.")


@router.message(Command("ref_stats"))
async def ref_stats(message: Message) -> None:
    """Статистика реферальной системы."""
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if not await is_chat_owner(message.bot, user_id, chat_id):
        await message.answer("❌ Только владелец чата может смотреть статистику!")
        return
    
    try:
        setting = await db._execute_with_retry(
            "SELECT enabled, bonus_amount FROM ref_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        
        top_inviters = await db._execute_with_retry(
            """SELECT user_id, invited_count, earned_coins 
               FROM ref_links 
               WHERE chat_id = ? 
               ORDER BY invited_count DESC 
               LIMIT 10""",
            (chat_id,),
            fetch_all=True
        )
        
        total = await db._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM ref_invites WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        
        milestones = await db._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM ref_milestones WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        
        text = (
            f"📊 <b>СТАТИСТИКА РЕФЕРАЛЬНОЙ СИСТЕМЫ</b>\n\n"
            f"📢 Статус: {'✅ ВКЛЮЧЕНА' if setting and setting['enabled'] else '❌ ВЫКЛЮЧЕНА'}\n"
            f"💰 Бонус: {setting['bonus_amount'] if setting else 100} NCoins\n"
            f"👥 Приглашений: {total['cnt'] if total else 0}\n"
            f"🏆 Наград выдано: {milestones['cnt'] if milestones else 0}\n\n"
        )
        
        if top_inviters:
            text += "<b>🏆 ТОП ПРИГЛАСИТЕЛЕЙ:</b>\n"
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, row in enumerate(top_inviters[:5]):
                medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
                user = await db.get_user(row['user_id'])
                name = f"@{user['username']}" if user and user.get('username') else f"ID {row['user_id']}"
                text += f"{medal} {safe_html_escape(name)} — {row['invited_count']} пригл. (+{row['earned_coins']} NCoins)\n"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except DatabaseError as e:
        logger.error(f"Error getting ref stats: {e}")
        await message.answer("❌ Ошибка загрузки статистики.")


# ==================== КОМАНДЫ ДЛЯ УЧАСТНИКОВ ====================

@router.message(Command("my_ref"))
async def my_referral_link(message: Message) -> None:
    """Получить свою реферальную ссылку."""
    if not message or not message.chat or not message.from_user:
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    await init_ref_tables()
    
    try:
        setting = await db._execute_with_retry(
            "SELECT enabled, bonus_amount FROM ref_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        
        if not setting or not setting['enabled']:
            await message.answer("❌ Реферальная система не включена владельцем чата!")
            return
        
        user_ref = await db._execute_with_retry(
            "SELECT ref_code, invited_count, earned_coins FROM ref_links WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
            fetch_one=True
        )
        
        if not user_ref:
            ref_code = generate_ref_code()
            await db._execute_with_retry(
                "INSERT INTO ref_links (user_id, chat_id, ref_code, created_at) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, ref_code, datetime.now().isoformat()),
                commit=True
            )
            user_ref = {"ref_code": ref_code, "invited_count": 0, "earned_coins": 0}
        else:
            ref_code = user_ref['ref_code']
        
        # Получаем полученные награды
        milestones_rows = await db._execute_with_retry(
            "SELECT milestone FROM ref_milestones WHERE user_id = ? AND chat_id = ? AND awarded = 1 ORDER BY milestone",
            (user_id, chat_id),
            fetch_all=True
        )
        awarded_milestones = {row['milestone'] for row in milestones_rows} if milestones_rows else set()
        
        bot_username = (await message.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
        
        rewards_text = ""
        for milestone, reward in REWARDS.items():
            if milestone in awarded_milestones:
                rewards_text += f"✅ {milestone} пригл. — +{reward} NCoins (получено)\n"
            elif user_ref['invited_count'] >= milestone:
                rewards_text += f"🎉 {milestone} пригл. — +{reward} NCoins (доступно!)\n"
            else:
                remaining = milestone - user_ref['invited_count']
                rewards_text += f"🔜 {milestone} пригл. — +{reward} NCoins (ещё {remaining})\n"
        
        text = (
            f"🔗 <b>ВАША РЕФЕРАЛЬНАЯ ССЫЛКА</b>\n\n"
            f"<code>{ref_link}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 <b>СТАТИСТИКА:</b>\n"
            f"├ 👥 Приглашено: {user_ref['invited_count']}\n"
            f"└ 💰 Заработано: {user_ref['earned_coins']} NCoins\n\n"
            f"💰 <b>БОНУС:</b> +{setting['bonus_amount']} NCoins за друга\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>🏆 ДОСТИЖЕНИЯ:</b>\n{rewards_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 Чем больше друзей — тем выше награда!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ", url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся!")],
            [InlineKeyboardButton(text="📊 ТОП ПРИГЛАСИТЕЛЕЙ", callback_data="ref_top")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
    except DatabaseError as e:
        logger.error(f"Error in my_ref: {e}")
        await message.answer("❌ Ошибка загрузки данных.")


@router.callback_query(F.data == "ref_top")
async def ref_top_callback(callback: CallbackQuery) -> None:
    """Топ пригласителей чата."""
    if not callback or not callback.message:
        return
    
    chat_id = callback.message.chat.id
    
    try:
        top_inviters = await db._execute_with_retry(
            """SELECT user_id, invited_count, earned_coins 
               FROM ref_links 
               WHERE chat_id = ? 
               ORDER BY invited_count DESC 
               LIMIT 10""",
            (chat_id,),
            fetch_all=True
        )
        
        if not top_inviters:
            await callback.answer("Пока нет приглашений!", show_alert=True)
            return
        
        text = "🏆 <b>ТОП ПРИГЛАСИТЕЛЕЙ ЧАТА</b>\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for i, row in enumerate(top_inviters):
            medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
            user = await db.get_user(row['user_id'])
            name = f"@{user['username']}" if user and user.get('username') else f"ID {row['user_id']}"
            text += f"{medal} {safe_html_escape(name)} — {row['invited_count']} пригл. (+{row['earned_coins']} NCoins)\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="ref_menu")]
        ])
        
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await callback.answer()
        
    except DatabaseError as e:
        logger.error(f"Error in ref_top: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)


# ==================== ОБРАБОТЧИК ПРИГЛАШЕНИЙ ====================

async def process_referral_start(message: Message, chat_id: int, ref_code: str) -> None:
    """Обработка перехода по реферальной ссылке."""
    if not message or not message.from_user:
        return
    
    try:
        inviter_row = await db._execute_with_retry(
            "SELECT user_id FROM ref_links WHERE ref_code = ? AND chat_id = ?",
            (ref_code, chat_id),
            fetch_one=True
        )
        
        if not inviter_row:
            return
        
        inviter_id = inviter_row['user_id']
        invited_id = message.from_user.id
        
        if inviter_id == invited_id:
            await message.answer("❌ Нельзя пригласить самого себя!")
            return
        
        # Проверяем, не было ли уже приглашения
        existing = await db._execute_with_retry(
            "SELECT id FROM ref_invites WHERE inviter_id = ? AND invited_id = ? AND chat_id = ?",
            (inviter_id, invited_id, chat_id),
            fetch_one=True
        )
        
        if existing:
            return  # Уже приглашён, молча пропускаем
        
        setting = await db._execute_with_retry(
            "SELECT bonus_amount FROM ref_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        bonus_amount = setting['bonus_amount'] if setting else REFERRAL_BONUS
        
        # Добавляем запись о приглашении
        await db._execute_with_retry(
            "INSERT INTO ref_invites (inviter_id, invited_id, chat_id, invited_at) VALUES (?, ?, ?, ?)",
            (inviter_id, invited_id, chat_id, datetime.now().isoformat()),
            commit=True
        )
        
        # Обновляем счётчик
        await db._execute_with_retry(
            """UPDATE ref_links 
               SET invited_count = invited_count + 1, earned_coins = earned_coins + ?
               WHERE user_id = ? AND chat_id = ?""",
            (bonus_amount, inviter_id, chat_id),
            commit=True
        )
        
        # Получаем новое количество
        new_count_row = await db._execute_with_retry(
            "SELECT invited_count FROM ref_links WHERE user_id = ? AND chat_id = ?",
            (inviter_id, chat_id),
            fetch_one=True
        )
        new_count = new_count_row['invited_count'] if new_count_row else 1
        
        # Начисляем бонус
        await db.update_balance(inviter_id, bonus_amount, "Реферальный бонус")
        
        # Отслеживаем XP
        try:
            from handlers.ranks import track_referral
            await track_referral(inviter_id)
        except ImportError:
            pass
        
        # Проверяем награды
        await check_milestone_reward(inviter_id, new_count, chat_id)
        
        # Уведомляем пригласившего
        if _bot:
            try:
                await _bot.send_message(
                    inviter_id,
                    f"🎉 <b>НОВЫЙ УЧАСТНИК!</b>\n\n"
                    f"По вашей ссылке присоединился новый участник!\n"
                    f"💰 Вам начислено +{bonus_amount} NCoins!\n"
                    f"📊 Всего приглашений: {new_count}",
                    parse_mode=ParseMode.HTML
                )
            except TelegramAPIError:
                pass
        
    except DatabaseError as e:
        logger.error(f"Error processing referral: {e}")


# ==================== МЕНЮ ====================

@router.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: CallbackQuery) -> None:
    """Меню реферальной системы."""
    if not callback or not callback.message:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 МОЯ ССЫЛКА", callback_data="my_ref")],
        [InlineKeyboardButton(text="📊 ТОП ПРИГЛАСИТЕЛЕЙ", callback_data="ref_top")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    rewards_text = ""
    for milestone, reward in list(REWARDS.items())[:5]:
        rewards_text += f"├ {milestone} друзей: +{reward} NCoins\n"
    
    await callback.message.edit_text(
        f"📢 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b>\n\n"
        f"Приглашайте друзей и получайте NCoins!\n\n"
        f"💰 <b>БОНУСЫ:</b>\n"
        f"├ За каждого: +{REFERRAL_BONUS} NCoins\n"
        f"{rewards_text}"
        f"└ ... и больше!\n\n"
        f"✨ Чем больше друзей — тем выше награда!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "my_ref")
async def my_ref_callback(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Моя ссылка'."""
    if not callback or not callback.message:
        return
    await my_referral_link(callback.message)
    await callback.answer()
