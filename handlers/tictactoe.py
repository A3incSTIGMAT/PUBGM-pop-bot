"""
Крестики-нолики для NEXUS Bot
Версия: 2.1 (Fixed ID Parsing & Callback Logic)
"""

import random
import asyncio
import time
import hashlib
import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE
from utils.keyboards import (
    xo_menu_keyboard, xo_difficulty_keyboard, xo_board_keyboard,
    xo_bet_keyboard, back_button
)

router = Router()
logger = logging.getLogger(__name__)

# Хранилище активных игр и временных состояний
active_games = {}
pending_challenges = {}

# Комбинации победы
WIN_COMBINATIONS = [
    [(0,0), (0,1), (0,2)], [(1,0), (1,1), (1,2)], [(2,0), (2,1), (2,2)],
    [(0,0), (1,0), (2,0)], [(0,1), (1,1), (2,1)], [(0,2), (1,2), (2,2)],
    [(0,0), (1,1), (2,2)], [(0,2), (1,1), (2,0)],
]

BOT_DIFFICULTY = {
    "easy": {"name": "😊 Лёгкий", "mistake_chance": 0.4},
    "medium": {"name": "🤔 Средний", "mistake_chance": 0.15},
    "hard": {"name": "🤖 Сложный", "mistake_chance": 0.0},
}

COMMISSION = 0.05
GAME_TIMEOUT_SECONDS = 600


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
    return user


def check_winner(board: list) -> str | None:
    for combo in WIN_COMBINATIONS:
        cells = [board[r][c] for r, c in combo]
        if cells[0] != " " and cells[0] == cells[1] == cells[2]:
            return cells[0]
    if all(board[r][c] != " " for r in range(3) for c in range(3)):
        return "draw"
    return None


def generate_game_id() -> str:
    """Генерирует ID игры БЕЗ символов '_', чтобы не ломать парсинг callback_data"""
    return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]


def copy_board(board: list) -> list:
    return [row[:] for row in board]


# ==================== ЛОГИКА БОТА ====================

def bot_move_easy(board: list) -> tuple:
    if random.random() < BOT_DIFFICULTY["easy"]["mistake_chance"]:
        empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
        return random.choice(empty) if empty else None
    return bot_move_medium(board)


def bot_move_medium(board: list) -> tuple:
    if random.random() < BOT_DIFFICULTY["medium"]["mistake_chance"]:
        empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
        return random.choice(empty) if empty else None
    return bot_move_hard(board)


def bot_move_hard(board: list) -> tuple:
    sim = copy_board(board)
    
    # 1. Победа
    for r, c in [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]:
        sim[r][c] = "O"
        if check_winner(sim) == "O":
            return (r, c)
        sim[r][c] = " "
    
    # 2. Блокировка
    for r, c in [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]:
        sim[r][c] = "X"
        if check_winner(sim) == "X":
            return (r, c)
        sim[r][c] = " "
    
    # 3. Центр
    if sim[1][1] == " ":
        return (1, 1)
    
    # 4. Углы
    corners = [(0,0), (0,2), (2,0), (2,2)]
    empty_corners = [c for c in corners if sim[c[0]][c[1]] == " "]
    if empty_corners:
        return random.choice(empty_corners)
    
    # 5. Любая
    empty = [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]
    return random.choice(empty) if empty else None


BOT_MOVES = {"easy": bot_move_easy, "medium": bot_move_medium, "hard": bot_move_hard}


# ==================== ОБРАБОТЧИКИ ====================

@router.message(Command("xo"))
async def cmd_xo(message: types.Message):
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n\n"
        "Выберите режим игры:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_menu_keyboard()
    )


@router.callback_query(F.data == "game_xo")
@router.callback_query(F.data == "games")
async def game_xo_callback(callback: types.CallbackQuery):
    await cmd_xo(callback.message)
    await callback.answer()


@router.callback_query(F.data == "xo_vs_bot")
async def xo_vs_bot_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤖 <b>ИГРА С БОТОМ</b>\n\n"
        "Выберите уровень сложности:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_difficulty_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xo_diff_"))
async def xo_start_vs_bot(callback: types.CallbackQuery):
    difficulty = callback.data.split("_")[2]
    if difficulty not in BOT_DIFFICULTY:
        await callback.answer("❌ Неверная сложность!", show_alert=True)
        return
        
    user_id = callback.from_user.id
    game_id = generate_game_id()
    board = [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
    
    active_games[game_id] = {
        "type": "pvb",
        "board": board,
        "player_x": user_id,
        "player_o": "bot",
        "current_turn": "X",
        "bet": 0,
        "difficulty": difficulty,
        "chat_id": callback.message.chat.id,
        "message_id": callback.message.message_id,
        "created_at": time.time(),
        "last_move": time.time(),
        "finished": False,
    }
    
    diff_name = BOT_DIFFICULTY[difficulty]["name"]
    
    await callback.message.edit_text(
        f"🎮 <b>ИГРА С БОТОМ</b>\n\n"
        f"Сложность: {diff_name}\n"
        f"Вы играете за ❌ <b>X</b>\n"
        f"Бот играет за ⭕ <b>O</b>\n\n"
        f"👇 Ваш ход:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(board, game_id, can_play=True)
    )
    await callback.answer()


@router.callback_query(F.data == "xo_vs_player")
async def xo_vs_player_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👤 <b>ИГРА С ИГРОКОМ</b>\n\n"
        "Выберите ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_bet_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xo_bet_"))
async def xo_bet_selected(callback: types.CallbackQuery):
    try:
        bet = int(callback.data.split("_")[2])
    except ValueError:
        await callback.answer("❌ Неверная ставка!", show_alert=True)
        return
        
    pending_challenges[callback.from_user.id] = bet
    
    await callback.message.edit_text(
        f"👤 <b>ВЫЗОВ ИГРОКА</b>\n\n"
        f"💰 Ставка: <b>{bet} NCoin</b>\n\n"
        f"📝 Напишите @username противника:",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("xo_vs_player")
    )
    await callback.answer()


@router.message(lambda m: m.text and m.text.startswith('@') and m.from_user.id in pending_challenges)
async def xo_challenge_player(message: types.Message):
    user_id = message.from_user.id
    username = message.text.replace('@', '').strip()
    bet = pending_challenges.pop(user_id, 0)
    
    target = await db.get_user_by_username(username)
    if not target:
        await message.answer(f"❌ Пользователь @{username} не найден!")
        return
    
    target_id = target["user_id"]
    if target_id == user_id:
        await message.answer("❌ Нельзя вызвать самого себя!")
        return
    
    if bet > 0:
        balance = await db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ У вас недостаточно средств! Баланс: {balance} NCoin")
            return
    
    game_id = generate_game_id()
    active_games[game_id] = {
        "type": "pvp",
        "board": [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]],
        "player_x": user_id,
        "player_o": target_id,
        "current_turn": "X",
        "bet": bet,
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "created_at": time.time(),
        "last_move": time.time(),
        "pending": True,
        "finished": False,
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]
    ])
    
    await message.answer(
        f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
        f"👤 {message.from_user.first_name} вызывает @{username}!\n"
        f"💰 Ставка: <b>{bet} NCoin</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("xo_accept_"))
async def xo_accept_challenge(callback: types.CallbackQuery):
    game_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена!", show_alert=True)
        return
    
    game = active_games[game_id]
    if user_id != game["player_o"]:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    if not game.get("pending", False):
        await callback.answer("❌ Вызов уже принят!", show_alert=True)
        return
    
    bet = game["bet"]
    if bet > 0:
        balance_o = await db.get_balance(game["player_o"])
        balance_x = await db.get_balance(game["player_x"])
        if balance_o < bet or balance_x < bet:
            await callback.answer("❌ У кого-то не хватает средств!", show_alert=True)
            return
        await db.update_balance(game["player_x"], -bet, "Ставка в крестики-нолики")
        await db.update_balance(game["player_o"], -bet, "Ставка в крестики-нолики")
    
    game["pending"] = False
    game["last_move"] = time.time()
    
    await callback.message.edit_text(
        f"🎮 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"❌ X: {game['player_x']}\n⭕ O: {game['player_o']}\n"
        f"💰 Ставка: <b>{bet} NCoin</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=True)
    )
    await callback.answer("✅ Игра началась!")


@router.callback_query(F.data.startswith("xo_reject_"))
async def xo_reject_challenge(callback: types.CallbackQuery):
    game_id = callback.data.split("_")[2]
    if game_id in active_games:
        active_games.pop(game_id)
    await callback.message.edit_text("❌ Вызов отклонён!")
    await callback.answer()


@router.callback_query(F.data.startswith("xo_move_"))
async def xo_make_move(callback: types.CallbackQuery):
    # Формат: xo_move_{game_id}_{r}_{c}
    # Пример: xo_move_abc123_0_1
    # Split: ['xo', 'move', 'abc123', '0', '1']
    parts = callback.data.split("_")
    
    if len(parts) < 5:
        await callback.answer("❌ Неверный формат хода!", show_alert=True)
        return

    try:
        game_id = parts[2]
        r, c = int(parts[3]), int(parts[4])
    except (ValueError, IndexError):
        await callback.answer("❌ Неверные координаты!", show_alert=True)
        return

    user_id = callback.from_user.id
    
    if game_id not in active_games:
        await callback.answer("❌ Игра завершена или не найдена!", show_alert=True)
        return
    
    game = active_games[game_id]
    if game.get("finished", False):
        await callback.answer("❌ Игра уже окончена!", show_alert=True)
        return
        
    # Таймаут
    if time.time() - game["last_move"] > GAME_TIMEOUT_SECONDS:
        await end_game(callback, game_id, game, "timeout")
        return
    
    # Проверка очереди
    current_turn = game["current_turn"]
    if (current_turn == "X" and user_id != game["player_x"]) or \
       (current_turn == "O" and user_id != game["player_o"]):
        await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return
    
    # Проверка клетки
    if game["board"][r][c] != " ":
        await callback.answer("❌ Клетка занята!", show_alert=True)
        return
    
    # Ход
    game["board"][r][c] = current_turn
    game["last_move"] = time.time()
    
    winner = check_winner(game["board"])
    if winner:
        await end_game(callback, game_id, game, winner)
        return
    
    # Смена хода
    game["current_turn"] = "O" if current_turn == "X" else "X"
    
    # Обновление UI
    player_x_name = (await db.get_user(game["player_x"]))["first_name"]
    player_o_name = "Бот" if game["player_o"] == "bot" else (await db.get_user(game["player_o"]))["first_name"]
    next_player = player_x_name if game["current_turn"] == "X" else player_o_name
    
    can_play = True
    if game["type"] == "pvp":
        can_play = (game["current_turn"] == "X" and user_id == game["player_x"]) or \
                   (game["current_turn"] == "O" and user_id == game["player_o"])
    
    await callback.message.edit_text(
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
        f"❌ {player_x_name} vs ⭕ {player_o_name}\n"
        f"💰 Ставка: <b>{game['bet']} NCoin</b>\n\n"
        f"👇 Ход <b>{next_player} ({game['current_turn']})</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=can_play)
    )
    
    # Ход бота
    if game["type"] == "pvb" and game["current_turn"] == "O":
        await asyncio.sleep(0.6)
        await bot_turn(callback, game_id, game)
    
    await callback.answer()


async def bot_turn(callback: types.CallbackQuery, game_id: str, game: dict):
    difficulty = game.get("difficulty", "medium")
    move_func = BOT_MOVES.get(difficulty, bot_move_medium)
    
    move = move_func(game["board"])
    if not move:
        winner = check_winner(game["board"])
        if winner:
            await end_game(callback, game_id, game, winner)
        return
    
    r, c = move
    game["board"][r][c] = "O"
    
    winner = check_winner(game["board"])
    if winner:
        await end_game(callback, game_id, game, winner)
        return
    
    game["current_turn"] = "X"
    game["last_move"] = time.time()
    
    player_x_name = (await db.get_user(game["player_x"]))["first_name"]
    
    await callback.message.edit_text(
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
        f"❌ {player_x_name} vs 🤖 Бот\n"
        f"👇 Ваш ход, <b>{player_x_name} (X)</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=True)
    )


async def end_game(callback: types.CallbackQuery, game_id: str, game: dict, result: str):
    if game.get("finished", False):
        return
    game["finished"] = True
    
    bet = game["bet"]
    player_x = game["player_x"]
    player_o = game["player_o"]
    
    result_text = ""
    
    if result == "timeout":
        result_text = "⏳ <b>ВРЕМЯ ВЫШЛО!</b> Ставки возвращены."
        if bet > 0:
            await db.update_balance(player_x, bet, "Возврат ставки (таймаут)")
            if player_o != "bot":
                await db.update_balance(player_o, bet, "Возврат ставки (таймаут)")
            
    elif result == "X":
        result_text = f"🎉 ПОБЕДИЛ X! (Игрок)"
        if bet > 0:
            win_amount = int(bet * 2 * (1 - COMMISSION))
            await db.update_balance(player_x, win_amount, "Выигрыш в крестики-нолики")
            result_text += f"\n💰 +{win_amount} NCoin"
            
    elif result == "O":
        if player_o == "bot":
            result_text = "🤖 ПОБЕДИЛ БОТ!"
        else:
            result_text = f"🎉 ПОБЕДИЛ O! (Игрок)"
            if bet > 0:
                win_amount = int(bet * 2 * (1 - COMMISSION))
                await db.update_balance(player_o, win_amount, "Выигрыш в крестики-нолики")
                result_text += f"\n💰 +{win_amount} NCoin"
    else:  # draw
        result_text = "🤝 НИЧЬЯ!"
        if bet > 0:
            await db.update_balance(player_x, bet, "Возврат ставки (ничья)")
            if player_o != "bot":
                await db.update_balance(player_o, bet, "Возврат ставки (ничья)")
    
    active_games.pop(game_id, None)
    
    await callback.message.edit_text(
        f"🎮 <b>ИГРА ОКОНЧЕНА!</b>\n\n{result_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
            [InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="back_to_menu")]
        ])
    )


@router.callback_query(F.data.startswith("xo_surrender_"))
async def xo_surrender(callback: types.CallbackQuery):
    game_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    if game_id in active_games:
        game = active_games[game_id]
        winner = "O" if user_id == game["player_x"] else "X"
        await end_game(callback, game_id, game, winner)
        await callback.answer("🏳️ Вы сдались!")


@router.callback_query(F.data == "xo_stats")
async def xo_stats_callback(callback: types.CallbackQuery):
    await callback.answer("📊 Статистика в разработке!", show_alert=True)

@router.callback_query(F.data == "xo_help")
async def xo_help_callback(callback: types.CallbackQuery):
    await callback.answer("📜 Правила: соберите 3 в ряд!", show_alert=True)

@router.callback_query(F.data == "xo_noop")
async def xo_noop(callback: types.CallbackQuery):
    await callback.answer("❌ Занято или не ваш ход!", show_alert=True)

