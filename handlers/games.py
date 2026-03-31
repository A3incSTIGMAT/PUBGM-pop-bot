"""
games.py — Игры: слоты, дуэль, рулетка, КНБ
"""

import random
import uuid
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from utils.keyboards import back_button, game_buttons, duel_buttons, roulette_buttons, rps_buttons
from utils.helpers import extract_amount, extract_color, extract_rps_choice, extract_username
from utils.smart_parser import smart_parser

router = Router()

# ==================== FSM STATES ====================

class SlotState(StatesGroup):
    waiting_bet = State()

class DuelState(StatesGroup):
    waiting_bet = State()
    waiting_confirm = State()

class RouletteState(StatesGroup):
    waiting_bet = State()
    waiting_color = State()

class RPSState(StatesGroup):
    waiting_bet = State()
    waiting_choice = State()


# ==================== СЛОТ-МАШИНА ====================

@router.message(Command("slot"))
async def cmd_slot(message: Message, state: FSMContext):
    await message.answer("🎰 *Слот-машина*\n\n💰 Введите сумму ставки (от 10 до 10000):", parse_mode="Markdown")
    await state.set_state(SlotState.waiting_bet)


async def cmd_slot_smart(message: Message, state: FSMContext, amount: int = None):
    """Смарт-версия команды слота"""
    if amount is None:
        amount = extract_amount(message.text)

    if amount and 10 <= amount <= 10000:
        await process_slot_bet(message, state, amount)
    else:
        await cmd_slot(message, state)


@router.message(SlotState.waiting_bet)
async def slot_bet(message: Message, state: FSMContext):
    try:
        bet = int(message.text)
        if bet < 10 or bet > 10000:
            raise ValueError
    except ValueError:
        await message.answer("❌ Ставка должна быть числом от 10 до 10000")
        return

    await process_slot_bet(message, state, bet)


async def process_slot_bet(message: Message, state: FSMContext, bet: int):
    user_id = message.from_user.id
    balance = await db.get_balance(user_id)

    if balance < bet:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {balance} NCoin")
        await state.clear()
        return

    await db.subtract_balance(user_id, bet, f"Ставка в слотах: {bet}")

    symbols = ["🍒", "🍋", "🍊", "🍉", "🔔", "💎", "7️⃣"]
    reels = [random.choice(symbols) for _ in range(3)]

    win = False
    multiplier = 0
    if reels[0] == reels[1] == reels[2]:
        win = True
        multiplier = 10 if reels[0] == "7️⃣" else 5 if reels[0] == "💎" else 3

    if win:
        win_amount = bet * multiplier
        await db.add_balance(user_id, win_amount, f"Выигрыш в слотах: {win_amount}")
        result_text = f"🎉 *ПОБЕДА!* +{win_amount} NCoin\n✨ Множитель: x{multiplier}"
    else:
        win_amount = 0
        result_text = f"😢 *ПРОИГРЫШ*\n💸 Потеряно: {bet} NCoin"

    await db.add_game_history(user_id, "slot", bet, "win" if win else "loss", win_amount, {"reels": reels})

    new_balance = await db.get_balance(user_id)

    await message.answer(
        f"🎰 *Слот-машина*\n\n"
        f"{' | '.join(reels)}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {new_balance} NCoin",
        parse_mode="Markdown"
    )
    await state.clear()


# ==================== ДУЭЛЬ ====================

@router.message(Command("duel"))
async def cmd_duel(message: Message, state: FSMContext):
    if not message.reply_to_message:
        await message.answer(
            "⚔️ *Дуэль*\n\n"
            "Чтобы вызвать на дуэль, ответьте на сообщение соперника и укажите сумму:\n"
            "`/duel 100`",
            parse_mode="Markdown"
        )
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажите сумму: `/duel 100`")
        return

    try:
        bet = int(args[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return

    await process_duel(message, state, bet)


async def cmd_duel_smart(message: Message, state: FSMContext, amount: int = None, target: str = None):
    """Смарт-версия команды дуэли"""
    if amount is None:
        amount = extract_amount(message.text)
    if target is None:
        target = extract_username(message.text)

    if not amount:
        await message.answer("⚔️ *Дуэль*\n\nУкажите сумму ставки.\nНапример: `дуэль @username 100`")
        return

    # Если есть реплай — используем его
    if message.reply_to_message:
        await process_duel(message, state, amount)
    else:
        await message.answer("⚔️ Ответьте на сообщение пользователя, которого вызываете на дуэль")


async def process_duel(message: Message, state: FSMContext, bet: int):
    if bet < 10 or bet > 10000:
        await message.answer("❌ Ставка должна быть от 10 до 10000")
        return

    opponent = message.reply_to_message.from_user
    if opponent.id == message.from_user.id:
        await message.answer("❌ Нельзя вызвать самого себя")
        return

    challenger_balance = await db.get_balance(message.from_user.id)
    if challenger_balance < bet:
        await message.answer(f"❌ У вас недостаточно средств! Баланс: {challenger_balance} NCoin")
        return

    opponent_balance = await db.get_balance(opponent.id)
    if opponent_balance < bet:
        await message.answer(f"❌ У {opponent.full_name} недостаточно средств!")
        return

    duel_id = str(uuid.uuid4())
    await state.update_data(
        duel_id=duel_id,
        challenger=message.from_user.id,
        opponent=opponent.id,
        bet=bet,
        challenger_name=message.from_user.full_name,
        opponent_name=opponent.full_name
    )
    await state.set_state(DuelState.waiting_confirm)

    await message.answer(
        f"⚔️ *ВЫЗОВ НА ДУЭЛЬ!*\n\n"
        f"👤 {message.from_user.full_name} вызывает {opponent.full_name}\n"
        f"💰 Ставка: {bet} NCoin\n\n"
        f"Подтвердите командой `/accept`",
        parse_mode="Markdown"
    )


@router.message(Command("accept"))
async def duel_accept(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data or message.from_user.id != data.get('opponent'):
        return

    bet = data['bet']
    challenger_id = data['challenger']
    opponent_id = data['opponent']
    challenger_name = data['challenger_name']
    opponent_name = data['opponent_name']

    # Списываем ставки
    await db.subtract_balance(challenger_id, bet, f"Дуэль с {opponent_name}: ставка")
    await db.subtract_balance(opponent_id, bet, f"Дуэль с {challenger_name}: ставка")

    # Бросаем кубики
    challenger_roll = random.randint(1, 100)
    opponent_roll = random.randint(1, 100)

    if challenger_roll > opponent_roll:
        winner_id = challenger_id
        winner_name = challenger_name
        win_amount = bet * 2
        loser_id = opponent_id
    elif opponent_roll > challenger_roll:
        winner_id = opponent_id
        winner_name = opponent_name
        win_amount = bet * 2
        loser_id = challenger_id
    else:
        # Ничья — возврат ставок
        await db.add_balance(challenger_id, bet, "Дуэль: возврат (ничья)")
        await db.add_balance(opponent_id, bet, "Дуэль: возврат (ничья)")
        await message.answer("🤝 *НИЧЬЯ!* Ставки возвращены", parse_mode="Markdown")
        await state.clear()
        return

    await db.add_balance(winner_id, win_amount, f"Выигрыш в дуэли: {win_amount}")

    await db.add_game_history(winner_id, "duel", bet, "win", win_amount, {"opponent": loser_id})
    await db.add_game_history(loser_id, "duel", bet, "loss", 0, {"opponent": winner_id})

    await message.answer(
        f"⚔️ *РЕЗУЛЬТАТ ДУЭЛИ*\n\n"
        f"🎲 {challenger_name}: {challenger_roll}\n"
        f"🎲 {opponent_name}: {opponent_roll}\n\n"
        f"🏆 *ПОБЕДИТЕЛЬ: {winner_name}!*\n"
        f"💰 Приз: {win_amount} NCoin",
        parse_mode="Markdown"
    )
    await state.clear()


# ==================== РУЛЕТКА ====================

@router.message(Command("roulette"))
async def cmd_roulette(message: Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "🎲 *Рулетка*\n\n"
            "Использование: `/roulette [сумма] [цвет]`\n"
            "Цвета: `red`, `black`, `green`\n\n"
            "Пример: `/roulette 100 red`",
            parse_mode="Markdown"
        )
        return

    try:
        bet = int(args[1])
        color = args[2].lower()
    except ValueError:
        await message.answer("❌ Неверный формат")
        return

    await process_roulette(message, state, bet, color)


async def cmd_roulette_smart(message: Message, state: FSMContext, amount: int = None, color: str = None):
    """Смарт-версия команды рулетки"""
    if amount is None:
        amount = extract_amount(message.text)
    if color is None:
        color = extract_color(message.text)

    if not amount or not color:
        await message.answer(
            "🎲 *Рулетка*\n\n"
            "Напишите: `рулетка 100 красный` или `roulette 100 red`\n\n"
            "Цвета: красный, черный, зеленый",
            parse_mode="Markdown"
        )
        return

    await process_roulette(message, state, amount, color)


async def process_roulette(message: Message, state: FSMContext, bet: int, color: str):
    if bet < 10 or bet > 10000:
        await message.answer("❌ Ставка должна быть от 10 до 10000")
        return

    color_map = {
        'red': {'ru': 'красный', 'mult': 2},
        'black': {'ru': 'черный', 'mult': 2},
        'green': {'ru': 'зеленый', 'mult': 36}
    }

    if color not in color_map:
        await message.answer("❌ Неверный цвет. Доступны: red, black, green")
        return

    balance = await db.get_balance(message.from_user.id)
    if balance < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {balance} NCoin")
        return

    await db.subtract_balance(message.from_user.id, bet, f"Ставка в рулетке: {bet} на {color}")

    # Спин рулетки
    numbers = list(range(37))
    result_number = random.choice(numbers)

    if result_number == 0:
        result_color = 'green'
    elif result_number % 2 == 0:
        result_color = 'black'
    else:
        result_color = 'red'

    win = result_color == color
    multiplier = color_map[color]['mult']

    if win:
        win_amount = bet * multiplier
        await db.add_balance(message.from_user.id, win_amount, f"Выигрыш в рулетке: {win_amount}")
        result_text = f"🎉 *ПОБЕДА!* +{win_amount} NCoin\n✨ Множитель: x{multiplier}"
    else:
        win_amount = 0
        result_text = f"😢 *ПРОИГРЫШ*\n💸 Потеряно: {bet} NCoin"

    await db.add_game_history(
        message.from_user.id, "roulette", bet, "win" if win else "loss",
        win_amount, {"number": result_number, "color": result_color}
    )

    new_balance = await db.get_balance(message.from_user.id)

    await message.answer(
        f"🎲 *РУЛЕТКА*\n\n"
        f"🎯 Выпало: *{result_number}* ({'🔴' if result_color == 'red' else '⚫' if result_color == 'black' else '🟢'} {color_map[result_color]['ru']})\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {new_balance} NCoin",
        parse_mode="Markdown"
    )


# ==================== КАМЕНЬ-НОЖНИЦЫ-БУМАГА ====================

@router.message(Command("rps"))
async def cmd_rps(message: Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "✊ *Камень-ножницы-бумага*\n\n"
            "Использование: `/rps [выбор]`\n"
            "Выбор: камень, ножницы, бумага",
            parse_mode="Markdown"
        )
        return

    choice = args[1].lower()
    await process_rps(message, state, choice)


async def cmd_rps_smart(message: Message, state: FSMContext, choice: str = None):
    """Смарт-версия команды КНБ"""
    if choice is None:
        choice = extract_rps_choice(message.text)

    if not choice:
        await message.answer(
            "✊ *Камень-ножницы-бумага*\n\n"
            "Напишите: `камень`, `ножницы` или `бумага`",
            parse_mode="Markdown"
        )
        return

    await process_rps(message, state, choice)


async def process_rps(message: Message, state: FSMContext, choice: str):
    choice_map = {
        'rock': {'ru': '✊ камень', 'emoji': '✊'},
        'scissors': {'ru': '✌️ ножницы', 'emoji': '✌️'},
        'paper': {'ru': '✋ бумага', 'emoji': '✋'}
    }

    if choice not in choice_map:
        await message.answer("❌ Неверный выбор. Доступны: камень, ножницы, бумага")
        return

    bet = 10  # Минимальная ставка для КНБ

    balance = await db.get_balance(message.from_user.id)
    if balance < bet:
        await message.answer(f"❌ Недостаточно средств! Минимальная ставка: 10 NCoin")
        return

    await db.subtract_balance(message.from_user.id, bet, f"Ставка в КНБ: {bet}")

    bot_choice = random.choice(['rock', 'scissors', 'paper'])

    # Определяем победителя
    if choice == bot_choice:
        result = 'draw'
        win_amount = bet
        await db.add_balance(message.from_user.id, win_amount, "Возврат ставки (ничья)")
        result_text = "🤝 *НИЧЬЯ!*"
    elif (choice == 'rock' and bot_choice == 'scissors') or \
         (choice == 'scissors' and bot_choice == 'paper') or \
         (choice == 'paper' and bot_choice == 'rock'):
        result = 'win'
        win_amount = bet * 2
        await db.add_balance(message.from_user.id, win_amount, f"Выигрыш в КНБ: {win_amount}")
        result_text = f"🎉 *ПОБЕДА!* +{win_amount} NCoin"
    else:
        result = 'loss'
        win_amount = 0
        result_text = f"😢 *ПРОИГРЫШ*\n💸 Потеряно: {bet} NCoin"

    await db.add_game_history(
        message.from_user.id, "rps", bet, result, win_amount,
        {"player": choice, "bot": bot_choice}
    )

    new_balance = await db.get_balance(message.from_user.id)

    await message.answer(
        f"✊ *КАМЕНЬ-НОЖНИЦЫ-БУМАГА*\n\n"
        f"👤 Вы: {choice_map[choice]['ru']}\n"
        f"🤖 Бот: {choice_map[bot_choice]['ru']}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {new_balance} NCoin",
        parse_mode="Markdown"
    )


# ==================== МЕНЮ ИГР ====================

@router.callback_query(F.data == "games")
async def games_menu(callback: CallbackQuery):
    """Меню игр"""
    text = (
        "🎮 *Игры NEXUS*\n\n"
        "🎰 `/slot` — слот-машина\n"
        "⚔️ `/duel [сумма]` — дуэль (ответом на сообщение)\n"
        "🎲 `/roulette [сумма] [цвет]` — рулетка\n"
        "✊ `/rps [выбор]` — камень-ножницы-бумага\n\n"
        "📜 `/history` — история игр\n\n"
        "💡 *Подсказка:* можно писать команды простым текстом!\n"
        "Например: `сыграй в слот`, `рулетка 100 красный`"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=game_buttons())
    await callback.answer()


@router.callback_query(F.data == "game_slot")
async def game_slot_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cmd_slot(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "game_duel")
async def game_duel_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "⚔️ *Дуэль*\n\n"
        "Ответьте на сообщение пользователя и напишите сумму:\n"
        "`/duel 100`\n\n"
        "Или просто: `дуэль @username 100`",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "game_roulette")
async def game_roulette_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎲 *Рулетка*\n\n"
        "Напишите: `/roulette 100 red`\n"
        "Или просто: `рулетка 100 красный`\n\n"
        "Цвета: красный, черный, зеленый",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "game_rps")
async def game_rps_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "✊ *Камень-ножницы-бумага*\n\n"
        "Напишите: `/rps камень`\n"
        "Или просто: `камень`, `ножницы`, `бумага`",
        parse_mode="Markdown"
    )
    await callback.answer()


# ==================== ИСТОРИЯ ИГР ====================

@router.message(Command("history"))
async def cmd_history(message: Message):
    """История игр пользователя"""
    user_id = message.from_user.id
    history = await db.get_game_history(user_id, limit=10)

    if not history:
        await message.answer("📜 *История игр*\n\nУ вас пока нет истории игр.", parse_mode="Markdown")
        return

    text = "📜 *ИСТОРИЯ ИГР*\n\n"
    for game in history:
        game_type = game.get('game_type', 'unknown')
        bet = game.get('bet', 0)
        result = game.get('result', 'unknown')
        win_amount = game.get('win_amount', 0)
        created_at = game.get('created_at', '')[:16]

        game_emoji = {
            'slot': '🎰', 'duel': '⚔️', 'roulette': '🎲', 'rps': '✊'
        }.get(game_type, '🎮')

        if result == 'win':
            result_text = f"✅ +{win_amount}"
        elif result == 'loss':
            result_text = f"❌ -{bet}"
        else:
            result_text = f"🔄 0"

        text += f"{game_emoji} {created_at} | {game_type} | {result_text}\n"

    await message.answer(text, parse_mode="Markdown")
