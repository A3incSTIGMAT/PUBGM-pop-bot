"""
Интерактивные игры NEXUS
"""

import random
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import get_balance, spend_balance, update_balance
from utils.logger import log_game

router = Router()

class GameStates(StatesGroup):
    slot_bet = State()
    duel_bet = State()
    duel_accept = State()

# ========== СЛОТ-МАШИНА ==========
@router.message(Command("slot"))
async def cmd_slot(message: Message, state: FSMContext):
    """Начать игру в слоты"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10 NCoin", callback_data="slot_10"),
         InlineKeyboardButton(text="50 NCoin", callback_data="slot_50")],
        [InlineKeyboardButton(text="100 NCoin", callback_data="slot_100"),
         InlineKeyboardButton(text="500 NCoin", callback_data="slot_500")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="slot_cancel")]
    ])
    
    await state.set_state(GameStates.slot_bet)
    await message.answer(
        f"🎰 **Слот-машина NEXUS**\n\n"
        f"💰 Ваш баланс: {balance} NCoin\n\n"
        f"Выберите ставку:",
        reply_markup=keyboard
    )

@router.callback_query(lambda c: c.data.startswith("slot_"))
async def process_slot(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.replace("slot_", ""))
    
    if bet == 0:
        await state.clear()
        await callback.message.edit_text("❌ Игра отменена.")
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    if balance < bet:
        await callback.message.edit_text(f"❌ Недостаточно средств! Ваш баланс: {balance} NCoin")
        await state.clear()
        await callback.answer()
        return
    
    # Слот-машина: 3 барабана
    slots = ["🍒", "🍋", "🍊", "🍉", "🔔", "💎", "7️⃣"]
    result = [random.choice(slots) for _ in range(3)]
    
    # Проверка выигрыша
    win = False
    win_mult = 1
    
    if result[0] == result[1] == result[2]:
        if result[0] == "7️⃣":
            win_mult = 10
        elif result[0] == "💎":
            win_mult = 7
        elif result[0] == "🔔":
            win_mult = 5
        else:
            win_mult = 3
        win = True
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win_mult = 2
        win = True
    
    if win:
        win_amount = bet * win_mult
        update_balance(user_id, chat_id, win_amount)
        text = f"🎰 {result[0]} {result[1]} {result[2]}\n\n🎉 **ВЫИГРЫШ!** +{win_amount} NCoin (x{win_mult})"
        log_game(callback.from_user.full_name, "slot", "win", win_amount)
    else:
        spend_balance(user_id, chat_id, bet)
        text = f"🎰 {result[0]} {result[1]} {result[2]}\n\n😔 **ПРОИГРЫШ!** -{bet} NCoin"
        log_game(callback.from_user.full_name, "slot", "loss", bet)
    
    new_balance = get_balance(user_id, chat_id)
    text += f"\n\n💰 Баланс: {new_balance} NCoin"
    
    await callback.message.edit_text(text)
    await state.clear()
    await callback.answer()

# ========== ДУЭЛЬ ==========
@router.message(Command("duel"))
async def cmd_duel(message: Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "⚔️ **Дуэль NEXUS**\n\n"
            "Использование: /duel @username [сумма]\n"
            "Пример: /duel @ivan 100\n\n"
            "💰 Победитель забирает банк!"
        )
        return
    
    target_username = args[1].replace("@", "")
    amount = int(args[2]) if len(args) > 2 else 50
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    
    if balance < amount:
        await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
        return
    
    # Находим пользователя
    target_id = None
    async for member in message.chat.get_members():
        if member.user.username and member.user.username.lower() == target_username.lower():
            target_id = member.user.id
            break
    
    if not target_id:
        await message.answer(f"❌ Пользователь @{target_username} не найден в чате.")
        return
    
    await state.update_data(
        challenger_id=user_id,
        target_id=target_id,
        amount=amount,
        challenger_name=message.from_user.full_name,
        target_name=target_username
    )
    await state.set_state(GameStates.duel_accept)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Принять дуэль", callback_data="duel_accept")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data="duel_decline")]
    ])
    
    await message.answer(
        f"⚔️ **ВЫЗОВ НА ДУЭЛЬ!**\n\n"
        f"{message.from_user.full_name} вызывает @{target_username}!\n"
        f"💰 Ставка: {amount} NCoin\n\n"
        f"У вас 60 секунд, чтобы принять вызов!",
        reply_markup=keyboard
    )

@router.callback_query(lambda c: c.data == "duel_accept", GameStates.duel_accept)
async def duel_accept(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("target_id")
    challenger_id = data.get("challenger_id")
    amount = data.get("amount")
    challenger_name = data.get("challenger_name")
    target_name = data.get("target_name")
    
    if callback.from_user.id != target_id:
        await callback.answer("❌ Это не ваш вызов!", show_alert=True)
        return
    
    # Проверка баланса у обоих
    balance_target = get_balance(target_id, callback.message.chat.id)
    balance_challenger = get_balance(challenger_id, callback.message.chat.id)
    
    if balance_target < amount:
        await callback.message.edit_text(f"❌ @{target_name} не может принять дуэль: недостаточно NCoin!")
        await state.clear()
        await callback.answer()
        return
    
    if balance_challenger < amount:
        await callback.message.edit_text(f"❌ Дуэль отменена: у {challenger_name} недостаточно NCoin!")
        await state.clear()
        await callback.answer()
        return
    
    # Списываем ставки
    spend_balance(challenger_id, callback.message.chat.id, amount)
    spend_balance(target_id, callback.message.chat.id, amount)
    
    # Результат дуэли
    winner = random.choice([challenger_id, target_id])
    winner_name = challenger_name if winner == challenger_id else target_name
    win_amount = amount * 2
    
    update_balance(winner, callback.message.chat.id, win_amount)
    
    await callback.message.edit_text(
        f"⚔️ **РЕЗУЛЬТАТ ДУЭЛИ!**\n\n"
        f"{challenger_name} ⚔️ {target_name}\n\n"
        f"🏆 **ПОБЕДИТЕЛЬ:** {winner_name}!\n"
        f"💰 Выигрыш: {win_amount} NCoin"
    )
    
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == "duel_decline", GameStates.duel_accept)
async def duel_decline(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    challenger_name = data.get("challenger_name")
    
    await callback.message.edit_text(
        f"❌ Дуэль отклонена!\n\n"
        f"{challenger_name}, ваш вызов не принят. Ставка возвращена."
    )
    
    # Возвращаем ставку
    amount = data.get("amount")
    challenger_id = data.get("challenger_id")
    update_balance(challenger_id, callback.message.chat.id, amount)
    
    await state.clear()
    await callback.answer()
