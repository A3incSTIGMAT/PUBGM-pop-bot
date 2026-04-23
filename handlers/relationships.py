#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/relationships.py
# ВЕРСИЯ: 2.1.0-free
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

from database import db

logger = logging.getLogger(__name__)
router = Router()

# ==================== СОСТОЯНИЯ ДЛЯ FSM ====================

class ActionStates(StatesGroup):
    waiting_for_target = State()

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
    "💥 {from_name} шлёпает {to_name}!",
]

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
    """Получить имя пользователя по ID"""
    try:
        user = await db.get_user(user_id)
        if user:
            return user.get('first_name') or f"@{user.get('username')}" or f"ID {user_id}"
    except Exception as e:
        logger.error(f"Get user name error: {e}")
    return f"ID {user_id}"

async def get_marriage_partner(user_id: int) -> Optional[int]:
    """Получить ID партнёра по браку"""
    try:
        rel = await db.get_relationship_status(user_id, "marriage")
        if rel:
            return rel["user2_id"] if rel["user1_id"] == user_id else rel["user1_id"]
    except Exception as e:
        logger.error(f"Get marriage partner error: {e}")
    return None

# ==================== ВХОД В РАЗДЕЛ ОТНОШЕНИЙ ====================

@router.message(lambda message: message.text == "💕 Отношения")
async def relations_menu(message: Message, state: FSMContext):
    """Вход в раздел отношений"""
    await state.clear()
    
    # Проверяем, есть ли брак
    partner_id = await get_marriage_partner(message.from_user.id)
    
    if partner_id:
        partner_name = await get_user_name(partner_id)
        text = (
            f"💕 <b>РАЗДЕЛ ОТНОШЕНИЙ</b>\n\n"
            f"💍 <b>В браке с:</b> {safe_html_escape(partner_name)}\n\n"
            f"👇 Выбери действие:"
        )
    else:
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
    target = await db.get_user_by_username(username)
    if not target:
        await message.answer(f"❌ Пользователь @{safe_html_escape(username)} не найден!\n\nУбедись, что он зарегистрирован в боте.", reply_markup=get_relations_keyboard())
        await state.clear()
        return
    
    target_id = target["user_id"]
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
    current_from = await db.get_relationship_status(from_id, "marriage")
    if current_from:
        await message.answer("❌ Вы уже в браке! Сначала разведитесь.", reply_markup=get_relations_keyboard())
        return
    
    current_target = await db.get_relationship_status(target_id, "marriage")
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
    if await db.get_relationship_status(proposer_id, "marriage"):
        await callback.answer("❌ Отправитель уже в браке!", show_alert=True)
        return
    
    if await db.get_relationship_status(acceptor_id, "marriage"):
        await callback.answer("❌ Вы уже в браке!", show_alert=True)
        return
    
    success = await db.create_relationship(proposer_id, acceptor_id, "marriage")
    
    if success:
        proposer_name = await get_user_name(proposer_id)
        acceptor_name = await get_user_name(acceptor_id)
        await callback.message.edit_text(
            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
            f"💍 <b>{safe_html_escape(proposer_name)}</b> и <b>{safe_html_escape(acceptor_name)}</b> теперь в браке!\n\n"
            f"💕 Совет да любовь!",
            parse_mode=ParseMode.HTML
        )
        await callback.message.answer(
            "💍 Вы можете вернуться в раздел отношений через главное меню.",
            reply_markup=get_relations_keyboard()
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

# ==================== РАЗВОД ====================

@router.message(lambda message: message.text == "💔 РАЗВЕСТИСЬ" or message.data == "divorce")
async def divorce_start(message: Message, state: FSMContext):
    """Начало развода"""
    user_id = message.from_user.id
    
    partner_id = await get_marriage_partner(user_id)
    if not partner_id:
        await message.answer("❌ Вы не в браке!", reply_markup=get_relations_keyboard())
        return
    
    partner_name = await get_user_name(partner_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💔 ДА, РАЗВЕСТИСЬ", callback_data="divorce_confirm"),
         InlineKeyboardButton(text="❌ НЕТ, ОТМЕНА", callback_data="divorce_cancel")]
    ])
    
    await message.answer(
        f"💔 <b>РАЗВОД</b>\n\n"
        f"Вы уверены, что хотите развестись с {safe_html_escape(partner_name)}?\n\n"
        f"🔥 <b>БЕСПЛАТНО!</b>\n\n"
        f"Это действие нельзя отменить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@router.callback_query(F.data == "divorce_confirm")
async def divorce_confirm(callback: CallbackQuery):
    """Подтверждение развода"""
    user_id = callback.from_user.id
    
    partner_id = await get_marriage_partner(user_id)
    if not partner_id:
        await callback.answer("❌ Вы не в браке!", show_alert=True)
        await callback.message.edit_text("❌ Вы не в браке.")
        return
    
    success = await db.end_relationship(user_id, partner_id, "marriage")
    
    if success:
        partner_name = await get_user_name(partner_id)
        await callback.message.edit_text(
            f"💔 <b>РАЗВОД ОФОРМЛЕН</b>\n\n"
            f"Вы развелись с {safe_html_escape(partner_name)}.\n"
            f"Вы снова свободны!",
            parse_mode=ParseMode.HTML
        )
        await callback.message.answer(
            "💕 Вернуться в раздел отношений: /relations",
            reply_markup=get_relations_keyboard()
        )
    else:
        await callback.message.edit_text("❌ Ошибка при разводе.")
    
    await callback.answer()

@router.callback_query(F.data == "divorce_cancel")
async def divorce_cancel(callback: CallbackQuery):
    """Отмена развода"""
    await callback.message.edit_text("✅ Развод отменён.", reply_markup=get_relations_keyboard())
    await callback.answer()

# ==================== КОМАНДЫ (для обратной совместимости) ====================

@router.message(Command("relations"))
async def cmd_relations(message: Message, state: FSMContext):
    """Команда /relations — вход в раздел отношений"""
    await relations_menu(message, state)

@router.message(Command("marry"))
async def cmd_marry(message: Message, state: FSMContext):
    """/marry @username"""
    args = message.text.split() if message.text else []
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await db.get_user_by_username(username)
        if target:
            from_id = message.from_user.id
            from_name = safe_html_escape(message.from_user.first_name)
            target_name = f"@{safe_html_escape(username)}"
            await execute_marry(message, from_id, target["user_id"], target_name, from_name)
            return
    await message.answer("💍 Использование: <code>/marry @username</code>", parse_mode=ParseMode.HTML)

@router.message(Command("flirt"))
async def cmd_flirt(message: Message):
    args = message.text.split() if message.text else []
    if len(args) >= 2 and args[1].startswith('@'):
        username = args[1].lstrip('@')
        target = await db.get_user_by_username(username)
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
        target = await db.get_user_by_username(username)
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
        target = await db.get_user_by_username(username)
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
        target = await db.get_user_by_username(username)
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

# ==================== КНОПКА НАЗАД ====================

@router.message(lambda message: message.text == "🔙 НАЗАД")
async def back_button(message: Message, state: FSMContext):
    """Кнопка назад — возврат в главное меню"""
    await state.clear()
    from handlers.start import start_command
    await start_command(message, state)
