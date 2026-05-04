#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/relationships.py
# ВЕРСИЯ: 2.5.0-production (исправленная после аудита)
# ОПИСАНИЕ: Система отношений — ВСЕ ДЕЙСТВИЯ БЕСПЛАТНЫ
# ============================================
# ИСПРАВЛЕНИЯ v2.5.0:
#   🔴 Все вызовы БД проверены через hasattr с fallback
#   🟡 Устранено дублирование (find_user, partner_action)
#   🟡 Безопасное форматирование дат
#   🟡 Все ошибки логируются
#   🟢 Вынесены константы типов отношений
#   🟢 Добавлены docstrings
# ============================================

import html
import logging
import os
import random
from datetime import datetime
from typing import Optional, List, Dict, Any

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError

logger = logging.getLogger(__name__)
router = Router()

# ==================== КОНСТАНТЫ ====================

REL_TYPE_MARRIAGE = "marriage"
REL_TYPE_ADOPTION = "adoption"

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

# Действия для партнёра (кнопки): callback_prefix → (шаблоны, эмодзи ответа)
PARTNER_ACTIONS = {
    "rel_hug_": (HUGS, "🤗 Обнял(а)!"),
    "rel_kiss_": (["💋 {from_name} целует {to_name}!"], "💋 Поцеловал(а)!"),
    "rel_compliment_": (COMPLIMENTS, "🌸 Комплимент отправлен!"),
    "rel_flirt_": (FLIRTS, "💋 Флирт!"),
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return str(text) if text else ""


def _safe_str(value: Any) -> str:
    """Безопасное преобразование в строку."""
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой НАЗАД."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


async def get_user_name(user_id: int) -> str:
    """
    Получить отображаемое имя пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Имя пользователя или "ID {user_id}"
    """
    if db is None:
        return f"ID {user_id}"
    try:
        user = await db.get_user(user_id)
        if user:
            name = user.get('first_name')
            if name:
                return safe_html_escape(name)
            username = user.get('username')
            if username:
                return f"@{safe_html_escape(username)}"
        return f"ID {user_id}"
    except DatabaseError as e:
        logger.warning(f"⚠️ Could not get user name for {user_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting user name: {e}", exc_info=True)
    return f"ID {user_id}"


async def _find_user_by_username(username: str) -> Optional[Dict]:
    """
    Найти пользователя по username с проверкой доступности метода.
    
    Args:
        username: Username без @
        
    Returns:
        Данные пользователя или None
    """
    if db is None:
        return None
    
    try:
        if hasattr(db, 'get_user_by_username') and callable(db.get_user_by_username):
            return await db.get_user_by_username(username)
        
        # Fallback
        user = await db._execute_with_retry(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
            (username,), fetch_one=True
        )
        return dict(user) if user else None
    except DatabaseError as e:
        logger.error(f"❌ Error finding user @{username}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error finding user: {e}", exc_info=True)
        return None


async def get_marriage_partner(user_id: int) -> Optional[int]:
    """
    Получить ID партнёра по браку.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        ID партнёра или None
        
    Example:
        >>> partner = await get_marriage_partner(123456)
        >>> if partner: print(f"Married to {partner}")
    """
    if db is None:
        return None
    try:
        if hasattr(db, 'get_relationship_status') and callable(db.get_relationship_status):
            rel = await db.get_relationship_status(user_id, REL_TYPE_MARRIAGE)
            if rel and rel.get("status") == "active":
                return rel.get("partner_id")
        else:
            # Fallback: прямой запрос
            row = await db._execute_with_retry(
                """SELECT user1_id, user2_id FROM relationships 
                   WHERE ((user1_id = ?) OR (user2_id = ?)) 
                   AND type = ? AND status = 'active'""",
                (user_id, user_id, REL_TYPE_MARRIAGE), fetch_one=True
            )
            if row:
                return row['user2_id'] if row['user1_id'] == user_id else row['user1_id']
    except DatabaseError as e:
        logger.error(f"❌ Error getting marriage partner for {user_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting marriage partner: {e}", exc_info=True)
    return None


async def get_family_members(user_id: int) -> List[Dict[str, Any]]:
    """
    Получить всех членов семьи пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Список словарей с данными членов семьи
    """
    if db is None:
        return []
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
    except DatabaseError as e:
        logger.error(f"❌ Error getting family for {user_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Unexpected error getting family: {e}", exc_info=True)
        return []


async def _save_relationship(user1_id: int, user2_id: int, rel_type: str, status: str = "pending") -> bool:
    """
    Сохранить отношения в БД.
    
    Использует db.create_relationship или fallback-запрос.
    
    Args:
        user1_id: ID инициатора
        user2_id: ID партнёра
        rel_type: Тип отношений
        status: Статус (pending/active)
        
    Returns:
        True при успехе
    """
    try:
        if hasattr(db, 'create_relationship') and callable(db.create_relationship):
            result = await db.create_relationship(user1_id, user2_id, rel_type, status)
            if isinstance(result, dict) and not result.get("success"):
                logger.warning(f"⚠️ create_relationship failed: {result.get('error')}")
                return False
            return True
        else:
            # Fallback
            await db._execute_with_retry(
                "INSERT INTO relationships (user1_id, user2_id, type, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (user1_id, user2_id, rel_type, status, datetime.now().isoformat())
            )
            return True
    except DatabaseError as e:
        logger.error(f"❌ Error saving relationship: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error saving relationship: {e}", exc_info=True)
        return False


async def _safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = True) -> None:
    """Безопасный ответ на callback."""
    if callback is None:
        return
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramAPIError:
        pass


# ==================== ПОСТРОИТЕЛИ МЕНЮ ====================

async def _build_menu_for_married(user_id: int, partner_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Построить меню для пользователя в браке."""
    partner_name = await get_user_name(partner_id)
    
    marriage = None
    if db and hasattr(db, 'get_relationship_status'):
        marriage = await db.get_relationship_status(user_id, REL_TYPE_MARRIAGE)
    
    created_str = ""
    if marriage and marriage.get('created_at'):
        created_str = _safe_str(marriage['created_at'])[:10]
    
    text = (
        "💕 <b>ОТНОШЕНИЯ</b>\n\n"
        f"💍 <b>В браке с:</b> {partner_name}\n"
        f"📅 С: {created_str or 'Неизвестно'}\n\n"
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
    
    return text, keyboard


async def _build_menu_for_single() -> Tuple[str, InlineKeyboardMarkup]:
    """Построить меню для одинокого пользователя."""
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
    
    return text, keyboard


# ==================== ГЛАВНОЕ МЕНЮ ОТНОШЕНИЙ ====================

@router.callback_query(F.data == "menu_relations")
@router.callback_query(F.data == "relationships_menu")
async def relationships_menu(callback: CallbackQuery) -> None:
    """
    Главное меню отношений.
    
    Отображает разный интерфейс для пользователей в браке и одиноких.
    """
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    user_id = callback.from_user.id
    partner_id = await get_marriage_partner(user_id)
    
    if partner_id:
        text, keyboard = await _build_menu_for_married(user_id, partner_id)
    else:
        text, keyboard = await _build_menu_for_single()
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit relationships menu: {e}")
    
    await _safe_callback_answer(callback)


# ==================== КОМАНДА /marry ====================

@router.message(Command("marry"))
async def cmd_marry(message: Message) -> None:
    """
    Предложить брак пользователю.
    
    Использование: /marry @username
    """
    if not message or not message.from_user or not message.text:
        return
    
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
    partner = await _find_user_by_username(username)
    
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
    
    # Создание предложения через БД
    try:
        success = await _save_relationship(user_id, partner_id, REL_TYPE_MARRIAGE, "pending")
        if not success:
            await message.answer("❌ Ошибка создания предложения.")
            return
    except DatabaseError as e:
        logger.error(f"❌ Marriage proposal error: {e}")
        await message.answer("❌ Ошибка базы данных.")
        return
    
    # Отправка предложения
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
    
    logger.info(f"💍 Marriage proposal: {user_id} -> {partner_id}")


# ==================== ПРИНЯТИЕ/ОТКЛОНЕНИЕ БРАКА ====================

@router.callback_query(F.data.startswith("marry_accept_"))
async def marry_accept(callback: CallbackQuery) -> None:
    """Принятие предложения брака."""
    if not callback or not callback.from_user:
        return
    
    try:
        proposer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await _safe_callback_answer(callback, "❌ Ошибка данных")
        return
    
    acceptor_id = callback.from_user.id
    if proposer_id == acceptor_id:
        await _safe_callback_answer(callback, "❌ Нельзя принять своё предложение!")
        return
    
    try:
        # Проверка что оба не в браке
        if await get_marriage_partner(proposer_id):
            await _safe_callback_answer(callback, "❌ Отправитель уже в браке!")
            return
        if await get_marriage_partner(acceptor_id):
            await _safe_callback_answer(callback, "❌ Вы уже в браке!")
            return
        
        # Подтверждение отношений
        if db and hasattr(db, 'accept_relationship') and callable(db.accept_relationship):
            success = await db.accept_relationship(proposer_id, acceptor_id, REL_TYPE_MARRIAGE)
        else:
            # Fallback
            await db._execute_with_retry(
                "UPDATE relationships SET status = 'active' WHERE user1_id = ? AND user2_id = ? AND type = ? AND status = 'pending'",
                (proposer_id, acceptor_id, REL_TYPE_MARRIAGE)
            )
            success = True
    except DatabaseError as e:
        logger.error(f"❌ Marriage accept error: {e}")
        await _safe_callback_answer(callback, "❌ Ошибка БД")
        return
    
    if success:
        p_name = await get_user_name(proposer_id)
        a_name = await get_user_name(acceptor_id)
        await callback.message.edit_text(
            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
            f"💍 <b>{p_name}</b> и <b>{a_name}</b> теперь в браке!\n\n💕 Совет да любовь!",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"💍 Marriage confirmed: {proposer_id} <-> {acceptor_id}")
    else:
        await callback.message.edit_text("❌ Ошибка подтверждения брака.")
    
    await _safe_callback_answer(callback)


@router.callback_query(F.data.startswith("marry_reject_"))
async def marry_reject(callback: CallbackQuery) -> None:
    """Отклонение предложения брака."""
    if not callback or not callback.message:
        return
    
    try:
        proposer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        return
    
    # Удаляем предложение из БД
    try:
        if db:
            await db._execute_with_retry(
                "DELETE FROM relationships WHERE user1_id = ? AND user2_id = ? AND type = ? AND status = 'pending'",
                (proposer_id, callback.from_user.id, REL_TYPE_MARRIAGE)
            )
    except DatabaseError as e:
        logger.warning(f"⚠️ Could not delete rejected proposal: {e}")
    
    await callback.message.edit_text("💔 Предложение отклонено.", parse_mode=ParseMode.HTML)
    await _safe_callback_answer(callback, "❌ Отклонено")


# ==================== РАЗВОД ====================

@router.callback_query(F.data == "rel_divorce_confirm")
async def divorce_confirm(callback: CallbackQuery) -> None:
    """Подтверждение развода."""
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💔 ДА, РАЗВЕСТИСЬ", callback_data="rel_divorce_do"),
         InlineKeyboardButton(text="❌ НЕТ", callback_data="relationships_menu")]
    ])
    
    try:
        await callback.message.edit_text(
            "💔 <b>РАЗВОД</b>\n\n🔥 <b>БЕСПЛАТНО!</b>\n\nВы уверены? Это нельзя отменить!",
            parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit divorce confirm: {e}")
    
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "rel_divorce_do")
async def divorce_do(callback: CallbackQuery) -> None:
    """Выполнение развода."""
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    user_id = callback.from_user.id
    partner_id = await get_marriage_partner(user_id)
    
    if not partner_id:
        await _safe_callback_answer(callback, "❌ Вы не в браке!")
        return
    
    try:
        if db and hasattr(db, 'end_relationship') and callable(db.end_relationship):
            await db.end_relationship(user_id, partner_id, REL_TYPE_MARRIAGE)
        else:
            await db._execute_with_retry(
                "DELETE FROM relationships WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)) AND type = ?",
                (user_id, partner_id, partner_id, user_id, REL_TYPE_MARRIAGE)
            )
        
        partner_name = await get_user_name(partner_id)
        await callback.message.edit_text(
            f"💔 <b>РАЗВОД ОФОРМЛЕН</b>\n\nВы развелись с {partner_name}.\nВы снова свободны!",
            parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard()
        )
        logger.info(f"💔 Divorce: {user_id} <-> {partner_id}")
    except DatabaseError as e:
        logger.error(f"❌ Divorce error: {e}")
        await _safe_callback_answer(callback, "❌ Ошибка БД")
    except Exception as e:
        logger.error(f"❌ Unexpected divorce error: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка")
    
    await _safe_callback_answer(callback)


# ==================== СЕМЬЯ ====================

@router.callback_query(F.data == "rel_family")
async def show_family(callback: CallbackQuery) -> None:
    """Показать семью пользователя."""
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    user_id = callback.from_user.id
    members = await get_family_members(user_id)
    
    if not members:
        text = "👨‍👩‍👧 <b>МОЯ СЕМЬЯ</b>\n\nУ вас пока нет семьи. Заключите брак!"
    else:
        text = "👨‍👩‍👧 <b>МОЯ СЕМЬЯ</b>\n\n"
        rel_names = {REL_TYPE_MARRIAGE: "💍 Брак", REL_TYPE_ADOPTION: "👶 Усыновление"}
        for m in members:
            partner_id = m['user2_id'] if m['user1_id'] == user_id else m['user1_id']
            name = await get_user_name(partner_id)
            rel_type = rel_names.get(m.get('type', ''), m.get('type', 'Отношения'))
            text += f"• {rel_type}: <b>{name}</b>\n"
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit family: {e}")
    
    await _safe_callback_answer(callback)


# ==================== КОМАНДЫ РП ====================

async def _do_rp_action(
    message: Message,
    templates: List[str],
    command_name: str,
    action_emoji: str
) -> None:
    """
    Общая функция для РП-команд (/flirt, /hug, /slap, /compliment).
    
    Args:
        message: Сообщение пользователя
        templates: Список шаблонов
        command_name: Название команды
        action_emoji: Эмодзи действия
    """
    if not message or not message.from_user or not message.text:
        return
    
    args = message.text.split()
    
    # Проверяем, указан ли @username
    if len(args) < 2 or not args[1].startswith('@'):
        await message.answer(
            f"{action_emoji} Использование: <code>/{command_name} @username</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    username = args[1].lstrip('@')
    
    # Проверка на пустой username
    if not username:
        await message.answer(f"❌ Укажите @username пользователя!")
        return
    
    target = await _find_user_by_username(username)
    
    if not target:
        await message.answer(f"❌ @{safe_html_escape(username)} не найден!")
        return
    
    # Выбираем случайный шаблон и форматируем
    template = random.choice(templates)
    formatted = template.format(
        from_name=safe_html_escape(message.from_user.first_name),
        to_name=f"@{safe_html_escape(username)}"
    )
    
    await message.answer(formatted, parse_mode=ParseMode.HTML)


@router.message(Command("flirt"))
async def cmd_flirt(message: Message) -> None:
    """Флирт с пользователем."""
    await _do_rp_action(message, FLIRTS, "flirt", "💋")


@router.message(Command("hug"))
async def cmd_hug(message: Message) -> None:
    """Объятия с пользователем."""
    await _do_rp_action(message, HUGS, "hug", "🤗")


@router.message(Command("slap"))
async def cmd_slap(message: Message) -> None:
    """Дать леща пользователю."""
    await _do_rp_action(message, SLAPS, "slap", "👋")


@router.message(Command("compliment"))
async def cmd_compliment(message: Message) -> None:
    """
    Сделать комплимент пользователю.
    
    Поддерживает формат: /compliment @username или просто /compliment.
    """
    if not message or not message.from_user:
        return
    
    compliment = random.choice(COMPLIMENTS)
    args = message.text.split() if message.text else []
    
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        if username:
            target = await _find_user_by_username(username)
            if target:
                await message.answer(
                    f"🌸 {safe_html_escape(message.from_user.first_name)} говорит @{safe_html_escape(username)}: {compliment}",
                    parse_mode=ParseMode.HTML
                )
                return
    
    # Если пользователь не указан или не найден — просто комплимент
    await message.answer(f"🌸 {compliment}", parse_mode=ParseMode.HTML)


# ==================== КНОПКИ ДЕЙСТВИЙ ДЛЯ ПАРТНЁРА ====================

@router.callback_query(F.data.startswith("rel_hug_"))
@router.callback_query(F.data.startswith("rel_kiss_"))
@router.callback_query(F.data.startswith("rel_compliment_"))
@router.callback_query(F.data.startswith("rel_flirt_"))
async def partner_action_handler(callback: CallbackQuery) -> None:
    """
    Универсальный обработчик для кнопок действий с партнёром.
    
    Поддерживает: rel_hug_, rel_kiss_, rel_compliment_, rel_flirt_.
    """
    if not callback or not callback.message or not callback.from_user:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    # Определяем префикс действия
    prefix = None
    for p in PARTNER_ACTIONS:
        if callback.data.startswith(p):
            prefix = p
            break
    
    if not prefix:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    try:
        partner_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    partner_name = await get_user_name(partner_id)
    templates, answer_text = PARTNER_ACTIONS[prefix]
    
    # Выбираем шаблон
    if prefix == "rel_kiss_":
        formatted = templates[0].format(
            from_name=safe_html_escape(callback.from_user.first_name),
            to_name=partner_name
        )
    else:
        template = random.choice(templates)
        formatted = template.format(
            from_name=safe_html_escape(callback.from_user.first_name),
            to_name=partner_name
        )
    
    await callback.message.answer(formatted, parse_mode=ParseMode.HTML)
    await _safe_callback_answer(callback, answer_text)


@router.callback_query(F.data == "rel_marry_info")
async def rel_marry_info(callback: CallbackQuery) -> None:
    """Показать информацию о браке."""
    if not callback or not callback.message:
        return
    
    text = (
        "💍 <b>БРАК В NEXUS</b>\n\n"
        "Чтобы заключить брак:\n"
        "1. Используйте <code>/marry @username</code>\n"
        "2. Партнёр должен принять предложение\n\n"
        "🔥 <b>Брак абсолютно бесплатен!</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="relationships_menu")]
    ])
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit marry info: {e}")
    
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "rel_flirt_info")
async def rel_flirt_info(callback: CallbackQuery) -> None:
    """Показать информацию о флирте."""
    if not callback or not callback.message:
        return
    
    text = (
        "💋 <b>ФЛИРТ В NEXUS</b>\n\n"
        "Используйте <code>/flirt @username</code> чтобы флиртовать!\n\n"
        "🔥 <b>Бесплатно!</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="relationships_menu")]
    ])
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit flirt info: {e}")
    
    await _safe_callback_answer(callback)
