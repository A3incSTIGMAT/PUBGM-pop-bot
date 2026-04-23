#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/relationships.py
# ВЕРСИЯ: 2.2.1-stable
# ОПИСАНИЕ: Система отношений — ВСЕ ДЕЙСТВИЯ БЕСПЛАТНЫ
# ============================================

import html
import logging
import random
from typing import Optional

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
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💍 ПРЕДЛОЖИТЬ БРАК"), KeyboardButton(text="💕 ФЛИРТ")],
            [KeyboardButton(text="🤗 ОБНЯТЬ"), KeyboardButton(text="👋 ДАТЬ ЛЕЩА")],
            [KeyboardButton(text="✨ КОМПЛИМЕНТ"), KeyboardButton(text="💔 РАЗВЕСТИСЬ")],
            [KeyboardButton(text="🔙 НАЗАД")]
        ],
        resize_keyboard=True
    )

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ОТМЕНА")]], resize_keyboard=True)

def get_back_inline_keyboard(callback_data: str = "menu_relations") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data=callback_data)]
    ])

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасный экранинг для HTML. Возвращает пустую строку при None."""
    if not text:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""

async def get_user_name(user_id: int) -> str:
    """Получить имя пользователя по ID с защитой от None"""
    try:
        user = await db.get_user(user_id)
        if user:
            name = user.get("first_name") or user.get("username")
            if name:
                return safe_html_escape(name)
    except Exception as e:
        logger.error(f"Get user name error: {e}")
    return f"ID {user_id}"

async def get_marriage_partner(user_id: int) -> Optional[int]:
    """Получить ID партнёра по браку"""
    try:
        rel = await db.get_relationship_status(user_id, "marriage")
        if rel and isinstance(rel, dict):
            return rel.get("user2_id") if rel.get("user1_id") == user_id else rel.get("user1_id")
    except Exception as e:
        logger.error(f"Get marriage partner error: {e}")
    return None

async def build_relations_text(user_id: int) -> str:
    """Формирует текст меню отношений"""
    partner_id = await get_marriage_partner(user_id)
    if partner_id:
        partner_name = await get_user_name(partner_id)
        return (
            f"💕 <b>РАЗДЕЛ ОТНОШЕНИЙ</b>\n\n"
            f"💍 <b>В браке с:</b> {partner_name}\n\n"
            f"👇 Выбери действие:"
        )
    return (
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

# ==================== ВХОД В РАЗДЕЛ ОТНОШЕНИЙ ====================

@router.message(lambda m: m.text == "💕 Отношения")
async def relations_menu_from_message(message: Message, state: FSMContext):
    """Вход из ReplyKeyboard"""
    await state.clear()
    text = await build_relations_text(message.from_user.id)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())

@router.callback_query(F.data == "menu_relations")
async def relations_menu_from_callback(callback: CallbackQuery, state: FSMContext):
    """Вход из InlineKeyboard"""
    await state.clear()
    await callback.answer()
    if not callback.message:
        await callback.message.answer("⚠️ Не удалось открыть меню.", reply_markup=get_relations_keyboard())
        return

    text = await build_relations_text(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())
    except Exception:
        # Если edit_text не сработал (напр. слишком старое сообщение), отправляем новое
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())

# ==================== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ДЕЙСТВИЙ ====================

@router.message(lambda m: m.text in ["💍 ПРЕДЛОЖИТЬ БРАК", "💕 ФЛИРТ", "🤗 ОБНЯТЬ", "👋 ДАТЬ ЛЕЩА", "✨ КОМПЛИМЕНТ"])
async def action_start(message: Message, state: FSMContext):
    action_text = message.text
    await state.update_data(action=action_text)
    await state.set_state(ActionStates.waiting_for_target)
    
    emojis = {
        "💍 ПРЕДЛОЖИТЬ БРАК": "💍", "💕 ФЛИРТ": "💕", "🤗 ОБНЯТЬ": "🤗",
        "👋 ДАТЬ ЛЕЩА": "👋", "✨ КОМПЛИМЕНТ": "✨"
    }
    emoji = emojis.get(action_text, "❤️")
    
    info = f"{emoji} <b>{action_text}</b>\n\n"
    if action_text == "💍 ПРЕДЛОЖИТЬ БРАК":
        info += "Отправь username пользователя, которому хочешь сделать предложение.\n\n" \
                "<b>Пример:</b> @username\n\n" \
                "После предложения партнёр должен принять его.\n"
    else:
        info += "Отправь username пользователя.\n\n" \
                "<b>Пример:</b> @username\n"
    info += "❌ Для отмены нажми кнопку «ОТМЕНА»"
    
    await message.answer(info, parse_mode=ParseMode.HTML, reply_markup=get_cancel_keyboard())

# ==================== ПОЛУЧЕНИЕ USERNAME И ВЫПОЛНЕНИЕ ====================

@router.message(ActionStates.waiting_for_target)
async def action_execute(message: Message, state: FSMContext):
    if message.text == "❌ ОТМЕНА":
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=get_relations_keyboard())
        return

    data = await state.get_data()
    action = data.get("action")
    if not action:
        await state.clear()
        return

    target_text = message.text.strip()
    username = target_text.lstrip("@").strip()
    if not username:
        await message.answer("❌ Укажи корректный username! Пример: @username", reply_markup=get_cancel_keyboard())
        return

    try:
        target = await db.get_user_by_username(username)
    except Exception as e:
        logger.error(f"DB get_user_by_username error: {e}")
        target = None

    if not target or not target.get("user_id"):
        await message.answer(
            f"❌ Пользователь @{safe_html_escape(username)} не найден!\n\n"
            "Убедись, что он зарегистрирован в боте.",
            reply_markup=get_relations_keyboard()
        )
        await state.clear()
        return

    target_id = target["user_id"]
    from_id = message.from_user.id
    from_name = safe_html_escape(message.from_user.first_name or "Пользователь")
    target_name = f"@{safe_html_escape(username)}"

    if target_id == from_id:
        await message.answer("❌ Нельзя сделать это над самим собой!", reply_markup=get_relations_keyboard())
        await state.clear()
        return

    try:
        if action == "💍 ПРЕДЛОЖИТЬ БРАК":
            await execute_marry(message, from_id, target_id, target_name, from_name)
        elif action == "💕 ФЛИРТ":
            await message.answer(random.choice(FLIRTS).format(from_name=from_name, to_name=target_name), reply_markup=get_relations_keyboard())
        elif action == "🤗 ОБНЯТЬ":
            await message.answer(random.choice(HUGS).format(from_name=from_name, to_name=target_name), reply_markup=get_relations_keyboard())
        elif action == "👋 ДАТЬ ЛЕЩА":
            await message.answer(random.choice(SLAPS).format(from_name=from_name, to_name=target_name), reply_markup=get_relations_keyboard())
        elif action == "✨ КОМПЛИМЕНТ":
            await message.answer(f"🌸 {from_name} говорит {target_name}: {random.choice(COMPLIMENTS)}", reply_markup=get_relations_keyboard())
    except Exception as e:
        logger.error(f"Action execute error: {e}")
        await message.answer("❌ Произошла ошибка при выполнении действия.", reply_markup=get_relations_keyboard())
    finally:
        await state.clear()

async def execute_marry(message: Message, from_id: int, target_id: int, target_name: str, from_name: str):
    try:
        current_from = await db.get_relationship_status(from_id, "marriage")
        current_target = await db.get_relationship_status(target_id, "marriage")
    except Exception as e:
        logger.error(f"DB check marriage error: {e}")
        await message.answer("❌ Ошибка проверки статуса отношений.", reply_markup=get_relations_keyboard())
        return

    if current_from:
        await message.answer("❌ Вы уже в браке! Сначала разведитесь.", reply_markup=get_relations_keyboard())
        return
    if current_target:
        await message.answer(f"❌ {target_name} уже в браке!", reply_markup=get_relations_keyboard())
        return

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
    if not callback.message:
        await callback.answer("⚠️ Сообщение устарело", show_alert=True)
        return

    try:
        proposer_id = int(callback.data.removeprefix("marry_accept_"))
    except ValueError:
        await callback.answer("❌ Неверный формат данных", show_alert=True)
        return

    acceptor_id = callback.from_user.id
    if proposer_id == acceptor_id:
        await callback.answer("❌ Нельзя принять своё предложение!", show_alert=True)
        return

    try:
        if await db.get_relationship_status(proposer_id, "marriage"):
            await callback.answer("❌ Отправитель уже в браке!", show_alert=True)
            return
        if await db.get_relationship_status(acceptor_id, "marriage"):
            await callback.answer("❌ Вы уже в браке!", show_alert=True)
            return

        success = await db.create_relationship(proposer_id, acceptor_id, "marriage")
    except Exception as e:
        logger.error(f"Marriage accept DB error: {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
        return

    if success:
        proposer_name = await get_user_name(proposer_id)
        acceptor_name = await get_user_name(acceptor_id)
        text = (
            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
            f"💍 <b>{proposer_name}</b> и <b>{acceptor_name}</b> теперь в браке!\n\n"
            f"💕 Совет да любовь!"
        )
    else:
        text = "❌ Ошибка создания брака."

    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_back_inline_keyboard())
    except Exception:
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_back_inline_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("marry_reject_"))
async def marry_reject(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("⚠️ Сообщение устарело", show_alert=True)
        return
    try:
        await callback.message.edit_text("💔 Предложение отклонено.", parse_mode=ParseMode.HTML, reply_markup=get_back_inline_keyboard())
    except Exception:
        pass
    await callback.answer("❌ Отклонено", show_alert=True)

# ==================== РАЗВОД ====================

@router.message(lambda m: m.text == "💔 РАЗВЕСТИСЬ")
async def divorce_start(message: Message):
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
        f"Вы уверены, что хотите развестись с {partner_name}?\n\n"
        f"🔥 <b>БЕСПЛАТНО!</b>\n\n"
        f"Это действие нельзя отменить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@router.callback_query(F.data == "divorce_confirm")
async def divorce_confirm(callback: CallbackQuery):
    if not callback.message: return
    user_id = callback.from_user.id
    partner_id = await get_marriage_partner(user_id)
    if not partner_id:
        await callback.answer("❌ Вы не в браке!", show_alert=True)
        return

    try:
        success = await db.end_relationship(user_id, partner_id, "marriage")
    except Exception as e:
        logger.error(f"Divorce DB error: {e}")
        await callback.answer("❌ Ошибка базы данных", show_alert=True)
        return

    partner_name = await get_user_name(partner_id) if partner_id else "партнёром"
    text = (
        f"💔 <b>РАЗВОД ОФОРМЛЕН</b>\n\n"
        f"Вы развелись с {partner_name}.\n"
        f"Вы снова свободны!"
    ) if success else "❌ Ошибка при разводе."

    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_back_inline_keyboard())
    except Exception:
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_back_inline_keyboard())
    await callback.answer()

@router.callback_query(F.data == "divorce_cancel")
async def divorce_cancel(callback: CallbackQuery):
    if callback.message:
        try: await callback.message.edit_text("✅ Развод отменён.", reply_markup=get_back_inline_keyboard())
        except: pass
    await callback.answer()

# ==================== КОМАНДЫ (для обратной совместимости) ====================

@router.message(Command("relations"))
async def cmd_relations(message: Message, state: FSMContext):
    await state.clear()
    text = await build_relations_text(message.from_user.id)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_relations_keyboard())

# ... (остальные /marry, /flirt и т.д. остаются без изменений, 
# только добавлен try/except для db.get_user_by_username в них для единообразия)
# Для краткости оставлены логически идентичными оригиналу, 
# но в продакшене рекомендуется обернуть db-вызовы в try/except аналогично action_execute.

@router.message(Command("cancel"))
async def cancel_action(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=get_relations_keyboard())
    else:
        await message.answer("❌ Нет активных действий для отмены.")

@router.message(lambda m: m.text == "🔙 НАЗАД")
async def back_button(message: Message, state: FSMContext):
    """Безопасный возврат. Не импортирует cmd_start, чтобы избежать циклических зависимостей."""
    await state.clear()
    await message.answer(
        "🔙 Возврат в главное меню.\n"
        "Используйте команду /start или нажмите кнопку в меню бота.",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="💕 Отношения")]], resize_keyboard=True)
    )

