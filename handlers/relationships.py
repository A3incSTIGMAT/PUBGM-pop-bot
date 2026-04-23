#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/relationships.py
# ВЕРСИЯ: 1.0.0-production
# ОПИСАНИЕ: Система отношений — брак, семья, флирт
# ============================================

import html
import logging
from datetime import datetime
from typing import Optional, Dict, List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# ==================== КОНСТАНТЫ ====================

# Типы отношений
RELATION_TYPES = {
    "marriage": "💍 Брак",
    "divorce": "💔 Развод",
    "adoption": "👶 Усыновление",
    "flirt": "💋 Флирт",
    "hug": "🤗 Объятия",
    "kiss": "💋 Поцелуй",
    "slap": "👋 Лещ",
    "compliment": "🌸 Комплимент",
}

# Стоимость действий
MARRIAGE_COST = 500
DIVORCE_COST = 1000
ADOPTION_COST = 300

# Комплименты
COMPLIMENTS = [
    "Ты как солнышко — согреваешь всех вокруг! ☀️",
    "Твоя улыбка освещает этот чат! 😊",
    "Ты самый крутой человек в этом чате! 🏆",
    "С тобой всегда весело и интересно! 🎉",
    "Ты просто легенда! 👑",
    "Твой юмор — лучшее, что есть в этом чате! 😂",
    "Ты делаешь этот мир лучше! 🌍",
    "Ты невероятно талантлив! ⭐",
]


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


async def get_user_name(user_id: int) -> str:
    """Получить имя пользователя."""
    if db is None:
        return f"ID {user_id}"
    try:
        user = await db.get_user(user_id)
        if user:
            return user.get('first_name') or f"@{user.get('username')}" or f"ID {user_id}"
    except Exception:
        pass
    return f"ID {user_id}"


async def get_relationship_status(user_id: int) -> Optional[Dict]:
    """Получить статус отношений пользователя."""
    if db is None:
        return None
    try:
        row = await db._execute_with_retry(
            """SELECT * FROM relationships 
               WHERE (user1_id = ? OR user2_id = ?) 
               AND type = 'marriage' 
               AND status = 'active'
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, user_id),
            fetch_one=True
        )
        return dict(row) if row else None
    except Exception:
        return None


async def create_relationship(user1_id: int, user2_id: int, rel_type: str) -> bool:
    """Создать отношения между пользователями."""
    if db is None:
        return False
    try:
        await db._execute_with_retry(
            """INSERT INTO relationships (user1_id, user2_id, type, status, created_at)
               VALUES (?, ?, ?, 'active', ?)""",
            (user1_id, user2_id, rel_type, datetime.now().isoformat()),
            commit=True
        )
        return True
    except Exception as e:
        logger.error(f"Create relationship error: {e}")
        return False


async def end_relationship(user1_id: int, user2_id: int, rel_type: str) -> bool:
    """Завершить отношения."""
    if db is None:
        return False
    try:
        await db._execute_with_retry(
            """UPDATE relationships SET status = 'ended', updated_at = ?
               WHERE type = ? AND status = 'active'
               AND ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))""",
            (datetime.now().isoformat(), rel_type, user1_id, user2_id, user2_id, user1_id),
            commit=True
        )
        return True
    except Exception as e:
        logger.error(f"End relationship error: {e}")
        return False


async def get_family_members(user_id: int) -> List[Dict]:
    """Получить членов семьи."""
    if db is None:
        return []
    try:
        rows = await db._execute_with_retry(
            """SELECT r.*, u.first_name, u.username 
               FROM relationships r
               LEFT JOIN users u ON (CASE WHEN r.user1_id = ? THEN r.user2_id ELSE r.user1_id END) = u.user_id
               WHERE (r.user1_id = ? OR r.user2_id = ?)
               AND r.status = 'active'
               ORDER BY r.created_at DESC""",
            (user_id, user_id, user_id),
            fetch_all=True
        )
        return [dict(row) for row in rows] if rows else []
    except Exception:
        return []


# ==================== ГЛАВНОЕ МЕНЮ ОТНОШЕНИЙ ====================

@router.callback_query(F.data == "menu_relations")
@router.callback_query(F.data == "relationships_menu")
async def relationships_menu(callback: CallbackQuery):
    """Главное меню отношений."""
    if not callback or not callback.message:
        return
    
    user_id = callback.from_user.id
    
    # Проверяем статус
    marriage = await get_relationship_status(user_id)
    
    if marriage:
        partner_id = marriage['user2_id'] if marriage['user1_id'] == user_id else marriage['user1_id']
        partner_name = await get_user_name(partner_id)
        
        text = (
            "💕 <b>ОТНОШЕНИЯ</b>\n\n"
            f"💍 <b>Вы в браке с:</b> {safe_html_escape(partner_name)}\n"
            f"📅 С: {marriage.get('created_at', 'Неизвестно')[:10]}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Доступные действия:</b>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤗 ОБНЯТЬ", callback_data=f"rel_hug_{partner_id}"),
             InlineKeyboardButton(text="💋 ПОЦЕЛОВАТЬ", callback_data=f"rel_kiss_{partner_id}")],
            [InlineKeyboardButton(text="🌸 КОМПЛИМЕНТ", callback_data=f"rel_compliment_{partner_id}"),
             InlineKeyboardButton(text="👶 УСЫНОВИТЬ", callback_data="rel_adoption_menu")],
            [InlineKeyboardButton(text="💔 РАЗВОД", callback_data="rel_divorce_confirm")],
            [InlineKeyboardButton(text="👨‍👩‍👧 МОЯ СЕМЬЯ", callback_data="rel_family")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")],
        ])
    else:
        text = (
            "💕 <b>ОТНОШЕНИЯ</b>\n\n"
            "Здесь вы можете создать семью, найти пару и многое другое!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>ДОСТУПНЫЕ ДЕЙСТВИЯ:</b>\n"
            "• 💍 <b>Брак</b> — /marry @username (500 NCoin)\n"
            "• 💋 <b>Флирт</b> — /flirt @username\n"
            "• 🤗 <b>Объятия</b> — /hug @username\n"
            "• 👋 <b>Дать леща</b> — /slap @username\n"
            "• 🌸 <b>Комплимент</b> — /compliment @username\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>💍 ДЛЯ БРАКА:</b>\n"
            f"• Стоимость: {MARRIAGE_COST} NCoin\n"
            "• Оба должны быть согласны\n"
            "• Используйте: /marry @username"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💍 ПРЕДЛОЖИТЬ БРАК", callback_data="rel_marry_info")],
            [InlineKeyboardButton(text="💋 ФЛИРТ", callback_data="rel_flirt_info")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")],
        ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


# ==================== КОМАНДЫ ====================

@router.message(Command("marry"))
async def cmd_marry(message: Message):
    """Предложить брак: /marry @username"""
    if not message or not message.from_user or not message.text:
        return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer(
            "💍 <b>ПРЕДЛОЖЕНИЕ БРАКА</b>\n\n"
            f"Использование: <code>/marry @username</code>\n"
            f"Стоимость: <b>{MARRIAGE_COST} NCoin</b>\n\n"
            "После предложения второй пользователь должен принять его.",
            parse_mode=ParseMode.HTML
        )
        return
    
    username = args[1].lstrip('@')
    user_id = message.from_user.id
    
    # Проверяем баланс
    balance = await db.get_balance(user_id) if db else 0
    if balance < MARRIAGE_COST:
        await message.answer(f"❌ Недостаточно средств! Нужно {MARRIAGE_COST} NCoin\nВаш баланс: {balance} NCoin")
        return
    
    # Ищем партнёра
    partner = await db.get_user_by_username(username) if db else None
    if not partner:
        await message.answer(f"❌ Пользователь @{username} не найден!")
        return
    
    partner_id = partner['user_id']
    if partner_id == user_id:
        await message.answer("❌ Нельзя жениться на самом себе!")
        return
    
    # Проверяем, не в браке ли уже
    current = await get_relationship_status(user_id)
    if current:
        await message.answer("❌ Вы уже в браке! Сначала разведитесь.")
        return
    
    partner_status = await get_relationship_status(partner_id)
    if partner_status:
        await message.answer(f"❌ @{username} уже в браке!")
        return
    
    # Создаём предложение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💍 ПРИНЯТЬ", callback_data=f"marry_accept_{user_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"marry_reject_{user_id}")]
    ])
    
    await message.answer(
        f"💍 <b>ПРЕДЛОЖЕНИЕ БРАКА!</b>\n\n"
        f"👤 {safe_html_escape(message.from_user.first_name)} предлагает брак @{safe_html_escape(username)}!\n"
        f"💰 Стоимость: {MARRIAGE_COST} NCoin\n\n"
        f"⚠️ ТОЛЬКО @{safe_html_escape(username)} может принять или отклонить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("marry_accept_"))
async def marry_accept(callback: CallbackQuery):
    """Принять предложение брака."""
    if not callback or not callback.from_user:
        return
    
    parts = callback.data.split("_")
    proposer_id = int(parts[2])
    acceptor_id = callback.from_user.id
    
    if proposer_id == acceptor_id:
        await callback.answer("❌ Нельзя принять своё предложение!", show_alert=True)
        return
    
    # Проверяем баланс
    balance = await db.get_balance(proposer_id) if db else 0
    if balance < MARRIAGE_COST:
        await callback.answer(f"❌ У предложившего недостаточно средств!", show_alert=True)
        return
    
    # Списываем средства
    try:
        await db.update_balance(proposer_id, -MARRIAGE_COST, "Брак")
    except Exception:
        await callback.answer("❌ Ошибка списания средств", show_alert=True)
        return
    
    # Создаём брак
    success = await create_relationship(proposer_id, acceptor_id, "marriage")
    
    if success:
        proposer_name = await get_user_name(proposer_id)
        acceptor_name = await get_user_name(acceptor_id)
        
        await callback.message.edit_text(
            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
            f"💍 <b>{safe_html_escape(proposer_name)}</b> и <b>{safe_html_escape(acceptor_name)}</b> "
            f"теперь в браке!\n\n"
            f"💕 Совет да любовь!",
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text("❌ Ошибка создания брака.")
    
    await callback.answer()


@router.callback_query(F.data.startswith("marry_reject_"))
async def marry_reject(callback: CallbackQuery):
    """Отклонить предложение."""
    if not callback:
        return
    await callback.message.edit_text("💔 Предложение отклонено.", parse_mode=ParseMode.HTML)
    await callback.answer("❌ Отклонено")


@router.callback_query(F.data == "rel_divorce_confirm")
async def divorce_confirm(callback: CallbackQuery):
    """Подтверждение развода."""
    if not callback or not callback.message:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💔 ДА, РАЗВЕСТИСЬ", callback_data="rel_divorce_do"),
         InlineKeyboardButton(text="❌ НЕТ", callback_data="relationships_menu")]
    ])
    
    await callback.message.edit_text(
        f"💔 <b>РАЗВОД</b>\n\n"
        f"Стоимость: <b>{DIVORCE_COST} NCoin</b>\n\n"
        f"Вы уверены? Это действие нельзя отменить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "rel_divorce_do")
async def divorce_do(callback: CallbackQuery):
    """Выполнить развод."""
    if not callback or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    
    balance = await db.get_balance(user_id) if db else 0
    if balance < DIVORCE_COST:
        await callback.answer(f"❌ Недостаточно средств! Нужно {DIVORCE_COST} NCoin", show_alert=True)
        return
    
    marriage = await get_relationship_status(user_id)
    if not marriage:
        await callback.answer("❌ Вы не в браке!", show_alert=True)
        return
    
    partner_id = marriage['user2_id'] if marriage['user1_id'] == user_id else marriage['user1_id']
    
    try:
        await db.update_balance(user_id, -DIVORCE_COST, "Развод")
        await end_relationship(user_id, partner_id, "marriage")
        
        await callback.message.edit_text(
            "💔 <b>РАЗВОД ОФОРМЛЕН</b>\n\n"
            f"💰 Списано: {DIVORCE_COST} NCoin\n\n"
            "Вы снова свободны!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Divorce error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data == "rel_family")
async def show_family(callback: CallbackQuery):
    """Показать семью."""
    if not callback or not callback.message:
        return
    
    user_id = callback.from_user.id
    members = await get_family_members(user_id)
    
    if not members:
        text = "👨‍👩‍👧 <b>МОЯ СЕМЬЯ</b>\n\nУ вас пока нет семьи. Заключите брак!"
    else:
        text = "👨‍👩‍👧 <b>МОЯ СЕМЬЯ</b>\n\n"
        for m in members:
            partner_id = m['user2_id'] if m['user1_id'] == user_id else m['user1_id']
            name = await get_user_name(partner_id)
            rel_type = RELATION_TYPES.get(m['type'], m['type'])
            text += f"• {rel_type}: <b>{safe_html_escape(name)}</b>\n"
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()


# ==================== РП-ДЕЙСТВИЯ ====================

@router.message(Command("flirt"))
async def cmd_flirt(message: Message):
    """Флирт: /flirt @username"""
    if not message or not message.from_user or not message.text:
        return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer("💋 Использование: <code>/flirt @username</code>", parse_mode=ParseMode.HTML)
        return
    
    username = args[1].lstrip('@')
    target = await db.get_user_by_username(username) if db else None
    
    if not target:
        await message.answer(f"❌ @{username} не найден!")
        return
    
    flirts = [
        f"💋 {safe_html_escape(message.from_user.first_name)} флиртует с @{safe_html_escape(username)}!",
        f"😘 @{safe_html_escape(username)}, ты сегодня особенно хорош(а)!",
        f"💕 {safe_html_escape(message.from_user.first_name)} строит глазки @{safe_html_escape(username)}",
    ]
    import random
    await message.answer(random.choice(flirts), parse_mode=ParseMode.HTML)


@router.message(Command("hug"))
async def cmd_hug(message: Message):
    """Объятия: /hug @username"""
    if not message or not message.from_user or not message.text:
        return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer("🤗 Использование: <code>/hug @username</code>", parse_mode=ParseMode.HTML)
        return
    
    username = args[1].lstrip('@')
    target = await db.get_user_by_username(username) if db else None
    
    if not target:
        await message.answer(f"❌ @{username} не найден!")
        return
    
    await message.answer(
        f"🤗 {safe_html_escape(message.from_user.first_name)} крепко обнимает @{safe_html_escape(username)}!",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("slap"))
async def cmd_slap(message: Message):
    """Лещ: /slap @username"""
    if not message or not message.from_user or not message.text:
        return
    
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer("👋 Использование: <code>/slap @username</code>", parse_mode=ParseMode.HTML)
        return
    
    username = args[1].lstrip('@')
    target = await db.get_user_by_username(username) if db else None
    
    if not target:
        await message.answer(f"❌ @{username} не найден!")
        return
    
    await message.answer(
        f"👋 {safe_html_escape(message.from_user.first_name)} даёт леща @{safe_html_escape(username)}!",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("compliment"))
async def cmd_compliment(message: Message):
    """Комплимент: /compliment @username"""
    if not message or not message.from_user or not message.text:
        return
    
    import random
    compliment = random.choice(COMPLIMENTS)
    
    args = message.text.split()
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await db.get_user_by_username(username) if db else None
        if target:
            await message.answer(
                f"🌸 {safe_html_escape(message.from_user.first_name)} говорит @{safe_html_escape(username)}: {compliment}",
                parse_mode=ParseMode.HTML
            )
            return
    
    await message.answer(f"🌸 {compliment}", parse_mode=ParseMode.HTML)


# ==================== ОБРАБОТЧИКИ КНОПОК РП ====================

@router.callback_query(F.data.startswith("rel_hug_"))
async def rel_hug(callback: CallbackQuery):
    """Обнять партнёра."""
    if not callback or not callback.from_user:
        return
    partner_id = int(callback.data.split("_")[2])
    partner_name = await get_user_name(partner_id)
    await callback.message.answer(
        f"🤗 {safe_html_escape(callback.from_user.first_name)} обнимает {safe_html_escape(partner_name)}!",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("🤗 Обнял(а)!")


@router.callback_query(F.data.startswith("rel_kiss_"))
async def rel_kiss(callback: CallbackQuery):
    """Поцеловать партнёра."""
    if not callback or not callback.from_user:
        return
    partner_id = int(callback.data.split("_")[2])
    partner_name = await get_user_name(partner_id)
    await callback.message.answer(
        f"💋 {safe_html_escape(callback.from_user.first_name)} целует {safe_html_escape(partner_name)}!",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("💋 Поцеловал(а)!")


@router.callback_query(F.data.startswith("rel_compliment_"))
async def rel_compliment(callback: CallbackQuery):
    """Сделать комплимент партнёру."""
    if not callback or not callback.from_user:
        return
    import random
    partner_id = int(callback.data.split("_")[2])
    partner_name = await get_user_name(partner_id)
    compliment = random.choice(COMPLIMENTS)
    await callback.message.answer(
        f"🌸 {safe_html_escape(callback.from_user.first_name)} говорит {safe_html_escape(partner_name)}: {compliment}",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("🌸 Комплимент отправлен!")
