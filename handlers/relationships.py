#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/relationships.py
# ВЕРСИЯ: 2.0.0-free
# ОПИСАНИЕ: Система отношений — ВСЕ ДЕЙСТВИЯ БЕСПЛАТНЫ
# ============================================

import html
import logging
import random
from datetime import datetime
from typing import Optional, Dict, List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db, DatabaseError

logger = logging.getLogger(__name__)
router = Router()

# ==================== СОСТОЯНИЯ ДЛЯ FSM ====================

class ActionStates(StatesGroup):
    waiting_for_target = State()  # Ждём username цели

# ==================== КОНСТАНТЫ ====================

# Типы отношений
RELATION_TYPES = {
    "marriage": "💍 Брак",
    "divorce": "💔 Развод",
}

# 🔥 ВСЕ БЕСПЛАТНО!
MARRIAGE_COST = 0
DIVORCE_COST = 0

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
    "С тобой даже понедельник не такой ужасный! 📅",
    "Ты как кофе — без тебя никак! ☕",
]

# Флирт
FLIRTS = [
    "💋 {from_name} строит глазки {to_name}! Кажется, это любовь... или просто ветер.",
    "😘 {from_name} отправляет воздушный поцелуй {to_name}! Прямо в сердечко!",
    "💕 {from_name} смотрит на {to_name} и улыбается. Это мило или подозрительно?",
    "🌹 {from_name} дарит виртуальную розу {to_name}! Пахнет романтикой.",
    "🫶 {from_name} признаётся {to_name} в симпатии! Чат затаил дыхание.",
]

# Лещи
SLAPS = [
    "👋 {from_name} даёт леща {to_name}! Прилетело знатно!",
    "🖐️ {from_name} отвешивает пощёчину {to_name}! За дело!",
    "💥 {from_name} шлёпает {to_name}! Это любя!",
]

# Объятия
HUGS = [
    "🤗 {from_name} крепко обнимает {to_name}! Тепло и уютно!",
    "🫂 {from_name} заключает {to_name} в дружеские объятия!",
    "💕 {from_name} обнимает {to_name} от всей души!",
]

# ==================== КЛАВИАТУРЫ ====================

def get_relations_keyboard():
    """Клавиатура для раздела Отношения (основная)"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💍 ПРЕДЛОЖИТЬ БРАК"), KeyboardButton(text="💕 ФЛИРТ")],
            [KeyboardButton(text="🤗 ОБНЯТЬ"), KeyboardButton(text="👋 ДАТЬ ЛЕЩА")],
            [KeyboardButton(text="✨ КОМПЛИМЕНТ"), KeyboardButton(text="🔙 НАЗАД")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ ОТМЕНА")]],
        resize_keyboard=True
    )
    return keyboard

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try: return html.escape(str(text))
    except: return ""

async def get_user_name(user_id: int) -> str:
    if db is None: return f"ID {user_id}"
    try:
        user = await db.get_user(user_id)
        if user:
            return user.get('first_name') or f"@{user.get('username')}" or f"ID {user_id}"
    except: pass
    return f"ID {user_id}"

async def get_relationship_status(user_id: int) -> Optional[Dict]:
    if db is None: return None
    try:
        row = await db._execute_with_retry(
            """SELECT * FROM relationships 
               WHERE (user1_id = ? OR user2_id = ?) 
               AND type = 'marriage' AND status = 'active'
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, user_id), fetch_one=True
        )
        return dict(row) if row else None
    except: return None

async def create_relationship(user1_id: int, user2_id: int, rel_type: str) -> bool:
    if db is None: return False
    try:
        await db._execute_with_retry(
            """INSERT INTO relationships (user1_id, user2_id, type, status, created_at)
               VALUES (?, ?, ?, 'active', ?)""",
            (user1_id, user2_id, rel_type, datetime.now().isoformat())
        )
        return True
    except Exception as e:
        logger.error(f"Create relationship error: {e}")
        return False

async def end_relationship(user1_id: int, user2_id: int, rel_type: str) -> bool:
    if db is None: return False
    try:
        await db._execute_with_retry(
            """UPDATE relationships SET status = 'ended'
               WHERE type = ? AND status = 'active'
               AND ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))""",
            (rel_type, user1_id, user2_id, user2_id, user1_id)
        )
        return True
    except Exception as e:
        logger.error(f"End relationship error: {e}")
        return False

async def get_user_by_username(username: str):
    """Получить пользователя по username"""
    if db is None: return None
    try:
        return await db.get_user_by_username(username)
    except:
        return None

# ==================== ВХОД В РАЗДЕЛ ОТНОШЕНИЙ ====================

@router.message(lambda message: message.text == "💕 Отношения" or message.text == "🔙 НАЗАД")
async def relations_menu(message: Message, state: FSMContext):
    """Вход в раздел отношений"""
    await state.clear()
    
    text = (
        "💕 <b>РАЗДЕЛ ОТНОШЕНИЙ</b>\n\n"
        "Здесь ты можешь:\n"
        "• 💍 Предложить брак\n"
        "• 💕 Пофлиртовать\n"
        "• 🤗 Обнять\n"
        "• 👋 Дать леща\n"
        "• ✨ Сделать комплимент\n\n"
        "🔥 <b>ВСЕ ДЕЙСТВИЯ БЕСПЛАТНЫ!</b>\n\n"
        "👇 Выбери действие:"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())

# ==================== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ДЕЙСТВИЙ ====================

@router.message(lambda message: message.text in ["💍 ПРЕДЛОЖИТЬ БРАК", "💕 ФЛИРТ", "🤗 ОБНЯТЬ", "👋 ДАТЬ ЛЕЩА", "✨ КОМПЛИМЕНТ"])
async def action_start(message: Message, state: FSMContext):
    """Начало действия — запрашиваем username"""
    action_text = message.text
    
    # Сохраняем действие
    await state.update_data(action=action_text)
    await state.set_state(ActionStates.waiting_for_target)
    
    # Эмодзи для каждого действия
    emojis = {
        "💍 ПРЕДЛОЖИТЬ БРАК": "💍",
        "💕 ФЛИРТ": "💕",
        "🤗 ОБНЯТЬ": "🤗",
        "👋 ДАТЬ ЛЕЩА": "👋",
        "✨ КОМПЛИМЕНТ": "✨"
    }
    emoji = emojis.get(action_text, "❤️")
    
    # Специальный текст для брака
    if action_text == "💍 ПРЕДЛОЖИТЬ БРАК":
        info = (
            f"{emoji} <b>{action_text}</b>\n\n"
            f"Отправь username пользователя, которому хочешь сделать предложение.\n\n"
            f"<b>Пример:</b> @username\n\n"
            f"После предложения партнёр должен принять его.\n\n"
            f"❌ Для отмены нажми кнопку «ОТМЕНА»"
        )
    else:
        info = (
            f"{emoji} <b>{action_text}</b>\n\n"
            f"Отправь username пользователя.\n\n"
            f"<b>Пример:</b> @username\n\n"
            f"❌ Для отмены нажми кнопку «ОТМЕНА»"
        )
    
    await message.answer(info, parse_mode=ParseMode.HTML, reply_markup=get_cancel_keyboard())

# ==================== ПОЛУЧЕНИЕ USERNAME И ВЫПОЛНЕНИЕ ====================

@router.message(ActionStates.waiting_for_target)
async def action_execute(message: Message, state: FSMContext):
    """Получаем username и выполняем действие"""
    data = await state.get_data()
    action = data.get("action")
    
    # Проверка на отмену
    if message.text == "❌ ОТМЕНА":
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=get_relations_keyboard())
        return
    
    # Извлекаем username
    target_text = message.text.strip()
    username = target_text.lstrip('@').strip()
    
    if not username:
        await message.answer("❌ Укажи username! Пример: @username")
        return
    
    # Ищем пользователя
    target = await get_user_by_username(username)
    if not target:
        await message.answer(f"❌ Пользователь @{safe_html_escape(username)} не найден!\n\nУбедись, что он зарегистрирован в боте.", reply_markup=get_relations_keyboard())
        await state.clear()
        return
    
    target_id = target['user_id']
    from_id = message.from_user.id
    from_name = safe_html_escape(message.from_user.first_name)
    target_name = f"@{safe_html_escape(username)}"
    
    # Нельзя действовать над собой
    if target_id == from_id:
        await message.answer("❌ Нельзя сделать это над самим собой!", reply_markup=get_relations_keyboard())
        await state.clear()
        return
    
    # Выполняем действие
    if action == "💍 ПРЕДЛОЖИТЬ БРАК":
        await execute_marry(message, from_id, target_id, target_name, from_name)
    
    elif action == "💕 ФЛИРТ":
        flirt = random.choice(FLIRTS).format(from_name=from_name, to_name=target_name)
        await message.answer(flirt, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())
    
    elif action == "🤗 ОБНЯТЬ":
        hug = random.choice(HUGS).format(from_name=from_name, to_name=target_name)
        await message.answer(hug, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())
    
    elif action == "👋 ДАТЬ ЛЕЩА":
        slap = random.choice(SLAPS).format(from_name=from_name, to_name=target_name)
        await message.answer(slap, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())
    
    elif action == "✨ КОМПЛИМЕНТ":
        compliment = random.choice(COMPLIMENTS)
        await message.answer(f"🌸 {from_name} говорит {target_name}: {compliment}", parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())
    
    await state.clear()

async def execute_marry(message: Message, from_id: int, target_id: int, target_name: str, from_name: str):
    """Выполнить предложение брака"""
    # Проверяем, не в браке ли уже
    current_from = await get_relationship_status(from_id)
    if current_from:
        await message.answer("❌ Вы уже в браке! Сначала разведитесь.", reply_markup=get_relations_keyboard())
        return
    
    current_target = await get_relationship_status(target_id)
    if current_target:
        await message.answer(f"❌ {target_name} уже в браке!", reply_markup=get_relations_keyboard())
        return
    
    # Создаём клавиатуру для принятия
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💍 ПРИНЯТЬ", callback_data=f"marry_accept_{from_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"marry_reject_{from_id}")]
    ])
    
    await message.answer(
        f"💍 <b>ПРЕДЛОЖЕНИЕ БРАКА!</b>\n\n"
        f"👤 {from_name} предлагает брак {target_name}!\n"
        f"🔥 <b>БЕСПЛАТНО!</b>\n\n"
        f"⚠️ ТОЛЬКО {target_name} может принять или отклонить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    
    await message.answer("✅ Предложение отправлено! Ожидаем ответа...", reply_markup=get_relations_keyboard())

# ==================== ПРИНЯТИЕ/ОТКЛОНЕНИЕ БРАКА ====================

@router.callback_query(F.data.startswith("marry_accept_"))
async def marry_accept(callback: CallbackQuery):
    """Принять предложение брака"""
    if not callback or not callback.from_user:
        return
    
    parts = callback.data.split("_")
    proposer_id = int(parts[2])
    acceptor_id = callback.from_user.id
    
    if proposer_id == acceptor_id:
        await callback.answer("❌ Нельзя принять своё предложение!", show_alert=True)
        return
    
    # Проверяем, что оба ещё не в браке
    if await get_relationship_status(proposer_id):
        await callback.answer("❌ Отправитель уже в браке!", show_alert=True)
        return
    
    if await get_relationship_status(acceptor_id):
        await callback.answer("❌ Вы уже в браке!", show_alert=True)
        return
    
    success = await create_relationship(proposer_id, acceptor_id, "marriage")
    
    if success:
        proposer_name = await get_user_name(proposer_id)
        acceptor_name = await get_user_name(acceptor_id)
        await callback.message.edit_text(
            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
            f"💍 <b>{safe_html_escape(proposer_name)}</b> и <b>{safe_html_escape(acceptor_name)}</b> теперь в браке!\n\n"
            f"💕 Совет да любовь!",
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text("❌ Ошибка создания брака.")
    
    await callback.answer()

@router.callback_query(F.data.startswith("marry_reject_"))
async def marry_reject(callback: CallbackQuery):
    """Отклонить предложение брака"""
    if not callback:
        return
    await callback.message.edit_text("💔 Предложение отклонено.", parse_mode=ParseMode.HTML)
    await callback.answer("❌ Отклонено")

# ==================== КОМАНДЫ (для обратной совместимости) ====================

@router.message(Command("marry"))
async def cmd_marry(message: Message, state: FSMContext):
    """/marry @username"""
    args = message.text.split() if message.text else []
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await get_user_by_username(username)
        if target:
            from_id = message.from_user.id
            from_name = safe_html_escape(message.from_user.first_name)
            target_name = f"@{safe_html_escape(username)}"
            await execute_marry(message, from_id, target['user_id'], target_name, from_name)
            return
    await message.answer("💍 Использование: <code>/marry @username</code>", parse_mode=ParseMode.HTML)

@router.message(Command("flirt"))
async def cmd_flirt(message: Message):
    args = message.text.split() if message.text else []
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await get_user_by_username(username)
        if target:
            flirt = random.choice(FLIRTS).format(
                from_name=safe_html_escape(message.from_user.first_name),
                to_name=f"@{safe_html_escape(username)}"
            )
            await message.answer(flirt, parse_mode=ParseMode.HTML)
            return
    await message.answer("💋 Использование: <code>/flirt @username</code>", parse_mode=ParseMode.HTML)

@router.message(Command("hug"))
async def cmd_hug(message: Message):
    args = message.text.split() if message.text else []
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await get_user_by_username(username)
        if target:
            hug = random.choice(HUGS).format(
                from_name=safe_html_escape(message.from_user.first_name),
                to_name=f"@{safe_html_escape(username)}"
            )
            await message.answer(hug, parse_mode=ParseMode.HTML)
            return
    await message.answer("🤗 Использование: <code>/hug @username</code>", parse_mode=ParseMode.HTML)

@router.message(Command("slap"))
async def cmd_slap(message: Message):
    args = message.text.split() if message.text else []
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await get_user_by_username(username)
        if target:
            slap = random.choice(SLAPS).format(
                from_name=safe_html_escape(message.from_user.first_name),
                to_name=f"@{safe_html_escape(username)}"
            )
            await message.answer(slap, parse_mode=ParseMode.HTML)
            return
    await message.answer("👋 Использование: <code>/slap @username</code>", parse_mode=ParseMode.HTML)

@router.message(Command("compliment"))
async def cmd_compliment(message: Message):
    args = message.text.split() if message.text else []
    compliment = random.choice(COMPLIMENTS)
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await get_user_by_username(username)
        if target:
            await message.answer(
                f"🌸 {safe_html_escape(message.from_user.first_name)} говорит @{safe_html_escape(username)}: {compliment}",
                parse_mode=ParseMode.HTML
            )
            return
    await message.answer(f"🌸 {compliment}", parse_mode=ParseMode.HTML)

# ==================== ОБРАБОТКА ОТМЕНЫ ====================

@router.message(Command("cancel"))
async def cancel_action(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=get_relations_keyboard())
    else:
        await message.answer("❌ Нет активных действий для отмены.")
