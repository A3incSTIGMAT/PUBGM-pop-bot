#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/relationships.py
# ВЕРСИЯ: 2.3.0-final
# ОПИСАНИЕ: Система отношений — ВСЕ ДЕЙСТВИЯ БЕСПЛАТНЫ + ВСЕ КОМАНДЫ
# ============================================

import html
import logging
import random
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError

logger = logging.getLogger(__name__)
router = Router()

# ==================== КОНСТАНТЫ ====================

COMPLIMENTS = [
    "Ты как солнышко — согреваешь всех вокруг! ☀️",
    "Твоя улыбка освещает этот чат! 😊",
    "Ты самый крутой человек в этом чате! 🏆",
    "С тобой всегда весело и интересно! 🎉",
    "Ты просто легенда! 👑",
    "Твой юмор — лучшее, что есть в этом чате! 😂",
    "Ты делаешь этот мир лучше! 🌍",
    "Ты невероятно талантлив! ⭐",
    "С тобой даже понедельник не такой ужасный! 📅",
    "Ты как кофе — без тебя никак! ☕",
]

FLIRTS = [
    "💋 {from_name} строит глазки {to_name}! Кажется, это любовь...",
    "😘 {from_name} отправляет воздушный поцелуй {to_name}!",
    "💕 {from_name} смотрит на {to_name} и улыбается.",
    "🌹 {from_name} дарит виртуальную розу {to_name}!",
    "🫶 {from_name} признаётся {to_name} в симпатии!",
]

SLAPS = [
    "👋 {from_name} даёт леща {to_name}! Прилетело знатно!",
    "🖐️ {from_name} отвешивает пощёчину {to_name}!",
    "💥 {from_name} шлёпает {to_name}! Это любя!",
]

HUGS = [
    "🤗 {from_name} крепко обнимает {to_name}! Тепло и уютно!",
    "🫂 {from_name} заключает {to_name} в дружеские объятия!",
    "💕 {from_name} обнимает {to_name} от всей души!",
]


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try: return html.escape(str(text))
    except: return ""


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


async def get_user_name(user_id: int) -> str:
    if db is None: return f"ID {user_id}"
    try:
        user = await db.get_user(user_id)
        if user:
            return safe_html_escape(user.get('first_name') or f"@{user.get('username')}" or f"ID {user_id}")
    except: pass
    return f"ID {user_id}"


async def get_marriage_partner(user_id: int) -> Optional[int]:
    if db is None: return None
    try:
        rel = await db.get_relationship_status(user_id, "marriage")
        if rel:
            return rel["user2_id"] if rel["user1_id"] == user_id else rel["user1_id"]
    except: pass
    return None


async def get_family_members(user_id: int) -> list:
    if db is None: return []
    try:
        rows = await db._execute_with_retry(
            """SELECT r.*, u.first_name, u.username 
               FROM relationships r
               LEFT JOIN users u ON (CASE WHEN r.user1_id = ? THEN r.user2_id ELSE r.user1_id END) = u.user_id
               WHERE (r.user1_id = ? OR r.user2_id = ?) AND r.status = 'active'
               ORDER BY r.created_at DESC""",
            (user_id, user_id, user_id), fetch_all=True
        )
        return [dict(r) for r in rows] if rows else []
    except: return []


# ==================== ГЛАВНОЕ МЕНЮ ОТНОШЕНИЙ ====================

@router.callback_query(F.data == "menu_relations")
@router.callback_query(F.data == "relationships_menu")
async def relationships_menu(callback: CallbackQuery):
    """Главное меню отношений."""
    if not callback or not callback.message: return
    
    user_id = callback.from_user.id
    partner_id = await get_marriage_partner(user_id)
    
    if partner_id:
        partner_name = await get_user_name(partner_id)
        
        marriage = await db.get_relationship_status(user_id, "marriage") if db else None
        created_at = marriage.get('created_at', '')[:10] if marriage else ''
        
        text = (
            "💕 <b>ОТНОШЕНИЯ</b>\n\n"
            f"💍 <b>В браке с:</b> {partner_name}\n"
            f"📅 С: {created_at or 'Неизвестно'}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Доступные действия:</b>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤗 ОБНЯТЬ", callback_data=f"rel_hug_{partner_id}"),
             InlineKeyboardButton(text="💋 ПОЦЕЛОВАТЬ", callback_data=f"rel_kiss_{partner_id}")],
            [InlineKeyboardButton(text="🌸 КОМПЛИМЕНТ", callback_data=f"rel_compliment_{partner_id}"),
             InlineKeyboardButton(text="💋 ФЛИРТ", callback_data=f"rel_flirt_{partner_id}")],
            [InlineKeyboardButton(text="💔 РАЗВОД", callback_data="rel_divorce_confirm")],
            [InlineKeyboardButton(text="👨‍👩‍👧 МОЯ СЕМЬЯ", callback_data="rel_family")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")],
        ])
    else:
        text = (
            "💕 <b>ОТНОШЕНИЯ</b>\n\n"
            "Здесь вы можете найти пару, создать семью и многое другое!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🔥 ВСЕ ДЕЙСТВИЯ БЕСПЛАТНЫ!</b>\n\n"
            "<b>ДОСТУПНЫЕ КОМАНДЫ:</b>\n"
            "• 💍 <b>Брак</b> — /marry @username\n"
            "• 💋 <b>Флирт</b> — /flirt @username\n"
            "• 🤗 <b>Объятия</b> — /hug @username\n"
            "• 👋 <b>Лещ</b> — /slap @username\n"
            "• 🌸 <b>Комплимент</b> — /compliment @username\n\n"
            "💡 <b>Подсказка:</b> Для брака нужен согласный партнёр!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💍 ПРЕДЛОЖИТЬ БРАК", callback_data="rel_marry_info")],
            [InlineKeyboardButton(text="💋 ФЛИРТ", callback_data="rel_flirt_info")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")],
        ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


# ==================== КОМАНДА /marry ====================

@router.message(Command("marry"))
async def cmd_marry(message: Message):
    if not message or not message.from_user or not message.text: return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer(
            "💍 <b>ПРЕДЛОЖЕНИЕ БРАКА</b>\n\n"
            f"Использование: <code>/marry @username</code>\n"
            "🔥 <b>БЕСПЛАТНО!</b>\n\n"
            "После предложения партнёр должен принять его.",
            parse_mode=ParseMode.HTML
        )
        return
    
    username = args[1].lstrip('@')
    user_id = message.from_user.id
    
    # Проверка текущего брака
    if await get_marriage_partner(user_id):
        await message.answer("❌ Вы уже в браке! Сначала разведитесь.")
        return
    
    # Поиск партнёра
    try:
        partner = await db.get_user_by_username(username) if db else None
    except DatabaseError:
        await message.answer("❌ Ошибка базы данных.")
        return
    
    if not partner:
        await message.answer(f"❌ Пользователь @{safe_html_escape(username)} не найден!")
        return
    
    partner_id = partner['user_id']
    if partner_id == user_id:
        await message.answer("❌ Нельзя жениться на самом себе!")
        return
    
    if await get_marriage_partner(partner_id):
        await message.answer(f"❌ @{safe_html_escape(username)} уже в браке!")
        return
    
    # Предложение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💍 ПРИНЯТЬ", callback_data=f"marry_accept_{user_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"marry_reject_{user_id}")]
    ])
    
    await message.answer(
        f"💍 <b>ПРЕДЛОЖЕНИЕ БРАКА!</b>\n\n"
        f"👤 {safe_html_escape(message.from_user.first_name)} предлагает брак @{safe_html_escape(username)}!\n"
        f"🔥 <b>БЕСПЛАТНО!</b>\n\n"
        f"⚠️ ТОЛЬКО @{safe_html_escape(username)} может принять или отклонить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


# ==================== ПРИНЯТИЕ/ОТКЛОНЕНИЕ БРАКА ====================

@router.callback_query(F.data.startswith("marry_accept_"))
async def marry_accept(callback: CallbackQuery):
    if not callback or not callback.from_user: return
    
    try:
        proposer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    acceptor_id = callback.from_user.id
    if proposer_id == acceptor_id:
        await callback.answer("❌ Нельзя принять своё предложение!", show_alert=True)
        return
    
    try:
        if db:
            if await db.get_relationship_status(proposer_id, "marriage"):
                await callback.answer("❌ Отправитель уже в браке!", show_alert=True); return
            if await db.get_relationship_status(acceptor_id, "marriage"):
                await callback.answer("❌ Вы уже в браке!", show_alert=True); return
            
            success = await db.create_relationship(proposer_id, acceptor_id, "marriage")
        else:
            success = False
    except DatabaseError as e:
        logger.error(f"Marriage error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    if success:
        p_name = await get_user_name(proposer_id)
        a_name = await get_user_name(acceptor_id)
        await callback.message.edit_text(
            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
            f"💍 <b>{p_name}</b> и <b>{a_name}</b> теперь в браке!\n\n💕 Совет да любовь!",
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text("❌ Ошибка создания брака.")
    await callback.answer()


@router.callback_query(F.data.startswith("marry_reject_"))
async def marry_reject(callback: CallbackQuery):
    if not callback: return
    await callback.message.edit_text("💔 Предложение отклонено.", parse_mode=ParseMode.HTML)
    await callback.answer("❌ Отклонено")


# ==================== РАЗВОД ====================

@router.callback_query(F.data == "rel_divorce_confirm")
async def divorce_confirm(callback: CallbackQuery):
    if not callback or not callback.message: return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💔 ДА, РАЗВЕСТИСЬ", callback_data="rel_divorce_do"),
         InlineKeyboardButton(text="❌ НЕТ", callback_data="relationships_menu")]
    ])
    
    await callback.message.edit_text(
        "💔 <b>РАЗВОД</b>\n\n🔥 <b>БЕСПЛАТНО!</b>\n\nВы уверены? Это нельзя отменить!",
        parse_mode=ParseMode.HTML, reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "rel_divorce_do")
async def divorce_do(callback: CallbackQuery):
    if not callback or not callback.from_user: return
    
    user_id = callback.from_user.id
    partner_id = await get_marriage_partner(user_id)
    
    if not partner_id:
        await callback.answer("❌ Вы не в браке!", show_alert=True); return
    
    try:
        if db:
            await db.end_relationship(user_id, partner_id, "marriage")
        partner_name = await get_user_name(partner_id)
        await callback.message.edit_text(
            f"💔 <b>РАЗВОД ОФОРМЛЕН</b>\n\nВы развелись с {partner_name}.\nВы снова свободны!",
            parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Divorce error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    await callback.answer()


# ==================== СЕМЬЯ ====================

@router.callback_query(F.data == "rel_family")
async def show_family(callback: CallbackQuery):
    if not callback or not callback.message: return
    
    user_id = callback.from_user.id
    members = await get_family_members(user_id)
    
    if not members:
        text = "👨‍👩‍👧 <b>МОЯ СЕМЬЯ</b>\n\nУ вас пока нет семьи. Заключите брак!"
    else:
        text = "👨‍👩‍👧 <b>МОЯ СЕМЬЯ</b>\n\n"
        rel_names = {"marriage": "💍 Брак", "adoption": "👶 Усыновление"}
        for m in members:
            partner_id = m['user2_id'] if m['user1_id'] == user_id else m['user1_id']
            name = await get_user_name(partner_id)
            rel_type = rel_names.get(m['type'], m['type'])
            text += f"• {rel_type}: <b>{name}</b>\n"
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()


# ==================== КОМАНДЫ РП ====================

@router.message(Command("flirt"))
async def cmd_flirt(message: Message):
    if not message or not message.from_user or not message.text: return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer("💋 Использование: <code>/flirt @username</code>", parse_mode=ParseMode.HTML)
        return
    
    username = args[1].lstrip('@')
    try:
        target = await db.get_user_by_username(username) if db else None
    except DatabaseError:
        await message.answer("❌ Ошибка базы данных.")
        return
    
    if not target:
        await message.answer(f"❌ @{safe_html_escape(username)} не найден!")
        return
    
    flirt = random.choice(FLIRTS).format(
        from_name=safe_html_escape(message.from_user.first_name),
        to_name=f"@{safe_html_escape(username)}"
    )
    await message.answer(flirt, parse_mode=ParseMode.HTML)


@router.message(Command("hug"))
async def cmd_hug(message: Message):
    if not message or not message.from_user or not message.text: return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer("🤗 Использование: <code>/hug @username</code>", parse_mode=ParseMode.HTML)
        return
    
    username = args[1].lstrip('@')
    try:
        target = await db.get_user_by_username(username) if db else None
    except DatabaseError:
        await message.answer("❌ Ошибка базы данных.")
        return
    
    if not target:
        await message.answer(f"❌ @{safe_html_escape(username)} не найден!")
        return
    
    hug = random.choice(HUGS).format(
        from_name=safe_html_escape(message.from_user.first_name),
        to_name=f"@{safe_html_escape(username)}"
    )
    await message.answer(hug, parse_mode=ParseMode.HTML)


@router.message(Command("slap"))
async def cmd_slap(message: Message):
    if not message or not message.from_user or not message.text: return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer("👋 Использование: <code>/slap @username</code>", parse_mode=ParseMode.HTML)
        return
    
    username = args[1].lstrip('@')
    try:
        target = await db.get_user_by_username(username) if db else None
    except DatabaseError:
        await message.answer("❌ Ошибка базы данных.")
        return
    
    if not target:
        await message.answer(f"❌ @{safe_html_escape(username)} не найден!")
        return
    
    slap = random.choice(SLAPS).format(
        from_name=safe_html_escape(message.from_user.first_name),
        to_name=f"@{safe_html_escape(username)}"
    )
    await message.answer(slap, parse_mode=ParseMode.HTML)


@router.message(Command("compliment"))
async def cmd_compliment(message: Message):
    if not message or not message.from_user: return
    
    compliment = random.choice(COMPLIMENTS)
    args = message.text.split() if message.text else []
    
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        try:
            target = await db.get_user_by_username(username) if db else None
        except DatabaseError:
            target = None
        
        if target:
            await message.answer(
                f"🌸 {safe_html_escape(message.from_user.first_name)} говорит @{safe_html_escape(username)}: {compliment}",
                parse_mode=ParseMode.HTML
            )
            return
    
    await message.answer(f"🌸 {compliment}", parse_mode=ParseMode.HTML)


# ==================== КНОПКИ РП ДЛЯ ПАРТНЁРА ====================

@router.callback_query(F.data.startswith("rel_hug_"))
async def rel_hug(callback: CallbackQuery):
    if not callback or not callback.from_user: return
    try:
        partner_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    partner_name = await get_user_name(partner_id)
    await callback.message.answer(
        f"🤗 {safe_html_escape(callback.from_user.first_name)} обнимает {partner_name}!",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("🤗 Обнял(а)!")


@router.callback_query(F.data.startswith("rel_kiss_"))
async def rel_kiss(callback: CallbackQuery):
    if not callback or not callback.from_user: return
    try:
        partner_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    partner_name = await get_user_name(partner_id)
    await callback.message.answer(
        f"💋 {safe_html_escape(callback.from_user.first_name)} целует {partner_name}!",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("💋 Поцеловал(а)!")


@router.callback_query(F.data.startswith("rel_compliment_"))
async def rel_compliment(callback: CallbackQuery):
    if not callback or not callback.from_user: return
    try:
        partner_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    partner_name = await get_user_name(partner_id)
    compliment = random.choice(COMPLIMENTS)
    await callback.message.answer(
        f"🌸 {safe_html_escape(callback.from_user.first_name)} говорит {partner_name}: {compliment}",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("🌸 Комплимент отправлен!")


@router.callback_query(F.data.startswith("rel_flirt_"))
async def rel_flirt(callback: CallbackQuery):
    if not callback or not callback.from_user: return
    try:
        partner_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    partner_name = await get_user_name(partner_id)
    flirt = random.choice(FLIRTS).format(
        from_name=safe_html_escape(callback.from_user.first_name),
        to_name=partner_name
    )
    await callback.message.answer(flirt, parse_mode=ParseMode.HTML)
    await callback.answer("💋 Флирт!")
