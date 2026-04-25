#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/referral.py
# ВЕРСИЯ: 2.1.0-production
# ОПИСАНИЕ: Реферальная система — ИСПРАВЛЕН commit=True
# ============================================

import html
import logging
import secrets
import string
from datetime import datetime
from typing import Optional, Dict, List

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError

logger = logging.getLogger(__name__)
router = Router()

_bot: Optional[Bot] = None


def set_bot(bot_instance: Bot) -> None:
    global _bot
    _bot = bot_instance


# ==================== КОНСТАНТЫ ====================

REFERRAL_BONUS = 100

REWARDS: Dict[int, int] = {
    1: 100, 5: 500, 10: 1000, 25: 3000, 50: 7000,
    100: 15000, 250: 50000, 500: 150000, 1000: 500000
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try: return html.escape(str(text))
    except: return ""


def generate_ref_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


async def is_chat_owner(bot: Bot, user_id: int, chat_id: int) -> bool:
    if bot is None or user_id is None or chat_id is None: return False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status == 'creator'
    except TelegramAPIError: return False


async def is_bot_admin(bot: Bot, chat_id: int) -> bool:
    if bot is None or chat_id is None: return False
    try:
        bot_id = (await bot.get_me()).id
        member = await bot.get_chat_member(chat_id, bot_id)
        return member.status in ['creator', 'administrator']
    except TelegramAPIError: return False


async def init_ref_tables() -> None:
    if db is None: return
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
        logger.info("✅ Referral tables initialized")
    except DatabaseError as e: logger.error(f"Init ref tables error: {e}")


async def check_milestone_reward(inviter_id: int, invited_count: int, chat_id: int) -> None:
    if db is None: return
    try:
        for milestone, reward in REWARDS.items():
            if invited_count >= milestone:
                row = await db._execute_with_retry(
                    "SELECT awarded FROM ref_milestones WHERE user_id=? AND chat_id=? AND milestone=?",
                    (inviter_id, chat_id, milestone), fetch_one=True)
                if not row or not row.get("awarded"):
                    await db._execute_with_retry(
                        "INSERT OR REPLACE INTO ref_milestones (user_id,chat_id,milestone,awarded,awarded_at) VALUES (?,?,?,1,?)",
                        (inviter_id, chat_id, milestone, datetime.now().isoformat()))
                    await db.update_balance(inviter_id, reward, f"Реферальная награда за {milestone} приглашений")
                    try:
                        from handlers.ranks import track_referral
                        await track_referral(inviter_id)
                    except ImportError: pass
                    if _bot:
                        try:
                            next_goal = next((m for m in REWARDS if m > milestone), "МАКСИМУМ")
                            await _bot.send_message(inviter_id,
                                f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\nВы пригласили {milestone} друзей!\n"
                                f"💰 Награда: +{reward} NCoins!\n📊 Следующая цель: {next_goal} приглашений",
                                parse_mode=ParseMode.HTML)
                        except TelegramAPIError: pass
    except DatabaseError as e: logger.error(f"Milestone error: {e}")


# ==================== КОМАНДЫ ВЛАДЕЛЬЦА ====================

@router.message(Command("enable_ref"))
async def enable_referral(message: Message) -> None:
    if not message or not message.chat or not message.from_user: return
    chat_id, user_id = message.chat.id, message.from_user.id
    if message.chat.type not in ['group','supergroup']: await message.answer("❌ Только в группах!"); return
    if not await is_bot_admin(message.bot, chat_id): await message.answer("❌ Бот не админ!"); return
    if not await is_chat_owner(message.bot, user_id, chat_id): await message.answer("❌ Только владелец!"); return
    
    await init_ref_tables()
    ref_code = generate_ref_code()
    bot_username = (await message.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
    
    try:
        await db._execute_with_retry(
            "INSERT OR REPLACE INTO ref_settings (chat_id,enabled,ref_link,bonus_amount,created_at) VALUES (?,1,?,100,?)",
            (chat_id, ref_link, datetime.now().isoformat()))
        rewards_text = "\n".join(f"├ {m} пригл. → +{r} NCoins" for m, r in list(REWARDS.items())[:5])
        await message.answer(
            f"✅ <b>Реферальная система ВКЛЮЧЕНА!</b>\n\n🔗 <code>{ref_link}</code>\n\n"
            f"💰 За друга: +{REFERRAL_BONUS} NCoins\n\n<b>🏆 БОНУСЫ:</b>\n{rewards_text}\n└ ... и больше!",
            parse_mode=ParseMode.HTML)
    except DatabaseError as e: logger.error(f"Enable ref error: {e}"); await message.answer("❌ Ошибка БД.")


@router.message(Command("disable_ref"))
async def disable_referral(message: Message) -> None:
    if not message or not message.chat or not message.from_user: return
    chat_id, user_id = message.chat.id, message.from_user.id
    if message.chat.type not in ['group','supergroup']: await message.answer("❌ Только в группах!"); return
    if not await is_chat_owner(message.bot, user_id, chat_id): await message.answer("❌ Только владелец!"); return
    try:
        await db._execute_with_retry("UPDATE ref_settings SET enabled=0 WHERE chat_id=?", (chat_id,))
        await message.answer("❌ <b>Реферальная система ВЫКЛЮЧЕНА!</b>", parse_mode=ParseMode.HTML)
    except DatabaseError as e: logger.error(f"Disable ref error: {e}"); await message.answer("❌ Ошибка БД.")


@router.message(Command("ref_stats"))
async def ref_stats(message: Message) -> None:
    if not message or not message.chat or not message.from_user: return
    chat_id, user_id = message.chat.id, message.from_user.id
    if message.chat.type not in ['group','supergroup']: await message.answer("❌ Только в группах!"); return
    if not await is_chat_owner(message.bot, user_id, chat_id): await message.answer("❌ Только владелец!"); return
    
    try:
        setting = await db._execute_with_retry("SELECT enabled,bonus_amount FROM ref_settings WHERE chat_id=?", (chat_id,), fetch_one=True)
        top = await db._execute_with_retry("SELECT user_id,invited_count,earned_coins FROM ref_links WHERE chat_id=? ORDER BY invited_count DESC LIMIT 10", (chat_id,), fetch_all=True)
        total = await db._execute_with_retry("SELECT COUNT(*) as cnt FROM ref_invites WHERE chat_id=?", (chat_id,), fetch_one=True)
        milestones = await db._execute_with_retry("SELECT COUNT(*) as cnt FROM ref_milestones WHERE chat_id=?", (chat_id,), fetch_one=True)
        
        text = (f"📊 <b>СТАТИСТИКА РЕФЕРАЛКИ</b>\n\n📢 Статус: {'✅ ВКЛ' if setting and setting['enabled'] else '❌ ВЫКЛ'}\n"
                f"💰 Бонус: {setting['bonus_amount'] if setting else 100}\n"
                f"👥 Приглашений: {total['cnt'] if total else 0}\n🏆 Наград: {milestones['cnt'] if milestones else 0}\n\n")
        if top:
            text += "<b>🏆 ТОП-5:</b>\n"
            medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
            for i, row in enumerate(top[:5]):
                medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
                user = await db.get_user(row['user_id'])
                name = f"@{user['username']}" if user and user.get('username') else f"ID {row['user_id']}"
                text += f"{medal} {safe_html_escape(name)} — {row['invited_count']} пригл. (+{row['earned_coins']})\n"
        await message.answer(text, parse_mode=ParseMode.HTML)
    except DatabaseError as e: logger.error(f"Ref stats error: {e}"); await message.answer("❌ Ошибка БД.")


# ==================== КОМАНДЫ УЧАСТНИКОВ ====================

@router.message(Command("my_ref"))
async def my_referral_link(message: Message) -> None:
    if not message or not message.chat or not message.from_user: return
    user_id, chat_id = message.from_user.id, message.chat.id
    if message.chat.type not in ['group','supergroup']: await message.answer("❌ Только в группах!"); return
    
    await init_ref_tables()
    try:
        setting = await db._execute_with_retry("SELECT enabled,bonus_amount FROM ref_settings WHERE chat_id=?", (chat_id,), fetch_one=True)
        if not setting or not setting['enabled']: await message.answer("❌ Рефералка не включена!"); return
        
        user_ref = await db._execute_with_retry("SELECT ref_code,invited_count,earned_coins FROM ref_links WHERE user_id=? AND chat_id=?", (user_id, chat_id), fetch_one=True)
        if not user_ref:
            ref_code = generate_ref_code()
            await db._execute_with_retry("INSERT INTO ref_links (user_id,chat_id,ref_code,created_at) VALUES (?,?,?,?)", (user_id, chat_id, ref_code, datetime.now().isoformat()))
            user_ref = {"ref_code": ref_code, "invited_count": 0, "earned_coins": 0}
        else: ref_code = user_ref['ref_code']
        
        milestones_rows = await db._execute_with_retry("SELECT milestone FROM ref_milestones WHERE user_id=? AND chat_id=? AND awarded=1 ORDER BY milestone", (user_id, chat_id), fetch_all=True)
        awarded = {r['milestone'] for r in (milestones_rows or [])}
        
        rewards_text = ""
        for m, r in REWARDS.items():
            if m in awarded: rewards_text += f"✅ {m} пригл. — +{r} NCoins\n"
            elif user_ref['invited_count'] >= m: rewards_text += f"🎉 {m} пригл. — +{r} NCoins (доступно!)\n"
            else: rewards_text += f"🔜 {m} пригл. — +{r} NCoins (ещё {m - user_ref['invited_count']})\n"
        
        bot_username = (await message.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
        
        text = (f"🔗 <b>ВАША ССЫЛКА</b>\n\n<code>{ref_link}</code>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 <b>СТАТИСТИКА:</b>\n├ 👥 Приглашено: {user_ref['invited_count']}\n└ 💰 Заработано: {user_ref['earned_coins']}\n\n"
                f"💰 <b>БОНУС:</b> +{setting['bonus_amount']} NCoins\n\n━━━━━━━━━━━━━━━━━━━━━\n\n<b>🏆 ДОСТИЖЕНИЯ:</b>\n{rewards_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n💡 Чем больше друзей — тем выше награда!")
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ", url=f"https://t.me/share/url?url={ref_link}")],
            [InlineKeyboardButton(text="📊 ТОП", callback_data="ref_top")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]])
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except DatabaseError as e: logger.error(f"My ref error: {e}"); await message.answer("❌ Ошибка БД.")


@router.callback_query(F.data == "ref_top")
async def ref_top_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message: return
    chat_id = callback.message.chat.id
    try:
        top = await db._execute_with_retry("SELECT user_id,invited_count,earned_coins FROM ref_links WHERE chat_id=? ORDER BY invited_count DESC LIMIT 10", (chat_id,), fetch_all=True)
        if not top: await callback.answer("Пока нет приглашений!", show_alert=True); return
        
        text = "🏆 <b>ТОП ПРИГЛАСИТЕЛЕЙ</b>\n\n"
        medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        for i, row in enumerate(top):
            medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
            user = await db.get_user(row['user_id'])
            name = f"@{user['username']}" if user and user.get('username') else f"ID {row['user_id']}"
            text += f"{medal} {safe_html_escape(name)} — {row['invited_count']} пригл. (+{row['earned_coins']})\n"
        
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ НАЗАД", callback_data="ref_menu")]]))
        await callback.answer()
    except DatabaseError as e: logger.error(f"Ref top error: {e}"); await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ОБРАБОТКА ПРИГЛАШЕНИЯ ====================

async def process_referral_start(message: Message, chat_id: int, ref_code: str) -> None:
    if not message or not message.from_user: return
    try:
        inviter = await db._execute_with_retry("SELECT user_id FROM ref_links WHERE ref_code=? AND chat_id=?", (ref_code, chat_id), fetch_one=True)
        if not inviter: return
        
        inviter_id, invited_id = inviter['user_id'], message.from_user.id
        if inviter_id == invited_id: await message.answer("❌ Нельзя пригласить себя!"); return
        
        existing = await db._execute_with_retry("SELECT id FROM ref_invites WHERE inviter_id=? AND invited_id=? AND chat_id=?", (inviter_id, invited_id, chat_id), fetch_one=True)
        if existing: return
        
        setting = await db._execute_with_retry("SELECT bonus_amount FROM ref_settings WHERE chat_id=?", (chat_id,), fetch_one=True)
        bonus = setting['bonus_amount'] if setting else REFERRAL_BONUS
        
        await db._execute_with_retry("INSERT INTO ref_invites (inviter_id,invited_id,chat_id,invited_at) VALUES (?,?,?,?)", (inviter_id, invited_id, chat_id, datetime.now().isoformat()))
        await db._execute_with_retry("UPDATE ref_links SET invited_count=invited_count+1, earned_coins=earned_coins+? WHERE user_id=? AND chat_id=?", (bonus, inviter_id, chat_id))
        
        new_count_row = await db._execute_with_retry("SELECT invited_count FROM ref_links WHERE user_id=? AND chat_id=?", (inviter_id, chat_id), fetch_one=True)
        new_count = new_count_row['invited_count'] if new_count_row else 1
        
        await db.update_balance(inviter_id, bonus, "Реферальный бонус")
        try:
            from handlers.ranks import track_referral
            await track_referral(inviter_id)
        except ImportError: pass
        
        await check_milestone_reward(inviter_id, new_count, chat_id)
        
        if _bot:
            try:
                await _bot.send_message(inviter_id,
                    f"🎉 <b>НОВЫЙ УЧАСТНИК!</b>\n\nПо вашей ссылке присоединился новый участник!\n💰 +{bonus} NCoins!\n📊 Всего: {new_count}",
                    parse_mode=ParseMode.HTML)
            except TelegramAPIError: pass
    except DatabaseError as e: logger.error(f"Process referral error: {e}")


# ==================== МЕНЮ ====================

@router.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message: return
    rewards_text = "\n".join(f"├ {m} друзей: +{r} NCoins" for m, r in list(REWARDS.items())[:5])
    await callback.message.edit_text(
        f"📢 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b>\n\nПриглашайте друзей и получайте NCoins!\n\n"
        f"💰 <b>БОНУСЫ:</b>\n├ За каждого: +{REFERRAL_BONUS} NCoins\n{rewards_text}\n"
        f"└ ... и больше!\n\n✨ Чем больше друзей — тем выше награда!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 МОЯ ССЫЛКА", callback_data="my_ref")],
            [InlineKeyboardButton(text="📊 ТОП", callback_data="ref_top")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]]))
    await callback.answer()


@router.callback_query(F.data == "my_ref")
async def my_ref_callback(callback: CallbackQuery) -> None:
    if not callback or not callback.message: return
    await my_referral_link(callback.message); await callback.answer()
