import random
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import get_balance, update_balance, add_user, spend_balance
from utils.logger import log_game
from utils.helpers import delete_after_response

router = Router()

# Состояния для игр
class GameStates(StatesGroup):
    roulette_bet = State()
    roulette_color = State()
    rps_choice = State()

# Камень-ножницы-бумага
@router.message(Command("rps"))
async def cmd_rps_start(message: Message, state: FSMContext):
    """Начинаем игру в камень-ножницы-бумага"""
    await state.set_state(GameStates.rps_choice)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🪨 Камень", callback_data="rps_rock"),
            InlineKeyboardButton(text="✂️ Ножницы", callback_data="rps_scissors"),
            InlineKeyboardButton(text="📄 Бумага", callback_data="rps_paper")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="rps_cancel")
        ]
    ])
    
    response = await message.answer(
        "🎮 **Камень-ножницы-бумага**\n\n"
        "Выберите свой ход:",
        reply_markup=keyboard
    )
    await delete_after_response(response, message, delay=30)

@router.callback_query(lambda c: c.data.startswith("rps_"))
async def process_rps(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора в игре"""
    choice = callback.data.replace("rps_", "")
    
    if choice == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Игра отменена.")
        await callback.answer()
        return
    
    choices = {
        "rock": {"name": "Камень", "emoji": "🪨"},
        "scissors": {"name": "Ножницы", "emoji": "✂️"},
        "paper": {"name": "Бумага", "emoji": "📄"}
    }
    
    user_choice_name = choices[choice]["name"]
    user_emoji = choices[choice]["emoji"]
    
    bot_choice_key = random.choice(list(choices.keys()))
    bot_choice_name = choices[bot_choice_key]["name"]
    bot_emoji = choices[bot_choice_key]["emoji"]
    
    if choice == bot_choice_key:
        result = "🤝 Ничья!"
    elif (choice == "rock" and bot_choice_key == "scissors") or \
         (choice == "scissors" and bot_choice_key == "paper") or \
         (choice == "paper" and bot_choice_key == "rock"):
        result = "🎉 Вы выиграли!"
    else:
        result = "😔 Вы проиграли!"
    
    await callback.message.edit_text(
        f"{user_emoji} **Вы:** {user_choice_name}\n"
        f"{bot_emoji} **Бот:** {bot_choice_name}\n\n"
        f"{result}"
    )
    await state.clear()
    await callback.answer()
    log_game(callback.from_user.full_name, "rps", result)

# Рулетка
@router.message(Command("roulette"))
async def cmd_roulette_start(message: Message, state: FSMContext):
    """Начинаем игру в рулетку"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10", callback_data="roulette_bet_10"),
            InlineKeyboardButton(text="50", callback_data="roulette_bet_50"),
            InlineKeyboardButton(text="100", callback_data="roulette_bet_100")
        ],
        [
            InlineKeyboardButton(text="250", callback_data="roulette_bet_250"),
            InlineKeyboardButton(text="500", callback_data="roulette_bet_500"),
            InlineKeyboardButton(text="1000", callback_data="roulette_bet_1000")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="roulette_cancel")
        ]
    ])
    
    response = await message.answer(
        f"🎲 **Рулетка NEXUS**\n\n"
        f"💰 Ваш баланс: {balance} NCoin\n\n"
        f"Выберите сумму ставки:",
        reply_markup=keyboard
    )
    await delete_after_response(response, message, delay=30)

@router.callback_query(lambda c: c.data.startswith("roulette_bet_"))
async def process_roulette_bet(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора суммы ставки"""
    bet = int(callback.data.replace("roulette_bet_", ""))
    
    if bet == 0:
        await state.clear()
        await callback.message.edit_text("❌ Игра отменена.")
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    if balance < bet:
        await callback.message.edit_text(
            f"❌ **Недостаточно средств!**\n\n"
            f"💰 Ваш баланс: {balance} NCoin\n"
            f"🎲 Ставка: {bet} NCoin\n\n"
            f"Получите ежедневный бонус: /daily"
        )
        await state.clear()
        await callback.answer()
        return
    
    await state.update_data(bet=bet)
    await state.set_state(GameStates.roulette_color)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 Красное (x2)", callback_data="roulette_color_red"),
            InlineKeyboardButton(text="⚫ Черное (x2)", callback_data="roulette_color_black")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="roulette_cancel")
        ]
    ])
    
    await callback.message.edit_text(
        f"🎲 **Рулетка NEXUS**\n\n"
        f"💰 Ставка: {bet} NCoin\n\n"
        f"Выберите цвет:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("roulette_color_"))
async def process_roulette_color(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора цвета"""
    color = callback.data.replace("roulette_color_", "")
    
    if color == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Игра отменена.")
        await callback.answer()
        return
    
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet == 0:
        await state.clear()
        await callback.message.edit_text("❌ Ошибка. Попробуйте снова /roulette")
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    balance = get_balance(user_id, chat_id)
    if balance < bet:
        await callback.message.edit_text(
            f"❌ **Недостаточно средств!**\n\n"
            f"💰 Ваш баланс: {balance} NCoin"
        )
        await state.clear()
        await callback.answer()
        return
    
    result_color = random.choice(["red", "black"])
    win = (color == result_color)
    
    if win:
        win_amount = bet * 2
        update_balance(user_id, chat_id, win_amount)
        new_balance = get_balance(user_id, chat_id)
        result_text = (
            f"🎲 Колесо остановилось на **{result_color.upper()}**!\n\n"
            f"🎉 **ПОБЕДА!** Вы выиграли {win_amount} NCoin!\n"
            f"💰 Ваш баланс: {new_balance} NCoin"
        )
        log_game(callback.from_user.full_name, "roulette", "win", win_amount)
    else:
        spend_balance(user_id, chat_id, bet)
        new_balance = get_balance(user_id, chat_id)
        result_text = (
            f"🎲 Колесо остановилось на **{result_color.upper()}**!\n\n"
            f"😔 **ПРОИГРЫШ!** Вы проиграли {bet} NCoin.\n"
            f"💰 Ваш баланс: {new_balance} NCoin"
        )
        log_game(callback.from_user.full_name, "roulette", "loss", bet)
    
    await callback.message.edit_text(result_text)
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == "roulette_cancel")
async def roulette_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена игры"""
    await state.clear()
    await callback.message.edit_text("❌ Игра отменена.")
    await callback.answer()
