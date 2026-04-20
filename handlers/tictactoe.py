# ============================================
# ФАЙЛ: handlers/tictactoe.py
# ОПИСАНИЕ: Крестики-нолики — ИСПРАВЛЕННАЯ СТАТИСТИКА
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# ============================================

import random
import asyncio
import time
import hashlib
import logging
import html
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE
from utils.keyboards import (
    xo_menu_keyboard, xo_difficulty_keyboard, xo_board_keyboard,
    xo_bet_keyboard, back_button, xo_side_choice_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

active_games = {}
pending_challenges = {}

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
    if user_id is None:
        return {}
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
    return user or {}


def check_winner(board: list) -> str | None:
    if board is None:
        return None
    for combo in WIN_COMBINATIONS:
        cells = [board[r][c] for r, c in combo]
        if cells[0] != " " and cells[0] == cells[1] == cells[2]:
            return cells[0]
    if all(board[r][c] != " " for r in range(3) for c in range(3)):
        return "draw"
    return None


def generate_game_id() -> str:
    return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]


def copy_board(board: list) -> list:
    if board is None:
        return [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
    return [row[:] for row in board]


# ==================== ЛОГИКА БОТА ====================

def bot_move_easy(board: list) -> tuple | None:
    if random.random() < BOT_DIFFICULTY["easy"]["mistake_chance"]:
        empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
        return random.choice(empty) if empty else None
    return bot_move_medium(board)


def bot_move_medium(board: list) -> tuple | None:
    if random.random() < BOT_DIFFICULTY["medium"]["mistake_chance"]:
        empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
        return random.choice(empty) if empty else None
    return bot_move_hard(board)


def bot_move_hard(board: list) -> tuple | None:
    sim = copy_board(board)
    
    for r, c in [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]:
        sim[r][c] = "O"
        if check_winner(sim) == "O":
            return (r, c)
        sim[r][c] = " "
    
    for r, c in [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]:
        sim[r][c] = "X"
        if check_winner(sim) == "X":
            return (r, c)
        sim[r][c] = " "
    
    if sim[1][1] == " ":
        return (1, 1)
    
    corners = [(0,0), (0,2), (2,0), (2,2)]
    empty_corners = [c for c in corners if sim[c[0]][c[1]] == " "]
    if empty_corners:
        return random.choice(empty_corners)
    
    empty = [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]
    return random.choice(empty) if empty else None


BOT_MOVES = {"easy": bot_move_easy, "medium": bot_move_medium, "hard": bot_move_hard}


# ==================== ЗАВЕРШЕНИЕ ИГРЫ ====================

async def end_game(callback: types.CallbackQuery, game_id: str, game: dict, result: str):
    """Завершение игры с сохранением статистики"""
    if game.get("finished", False):
        return
    game["finished"] = True
    
    bet = game.get("bet", 0)
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    result_text = ""
    
    if result == "timeout":
        result_text = "⏳ <b>ВРЕМЯ ВЫШЛО!</b>\nИгра завершена. Ставки возвращены."
        if bet > 0:
            if player_x != "bot" and player_x is not None:
                await db.update_balance(player_x, bet, "Возврат ставки (таймаут)")
            if player_o != "bot" and player_o is not None:
                await db.update_balance(player_o, bet, "Возврат ставки (таймаут)")
        await db.update_xo_stats(player_x, "draw", bet, 0)
        if player_o != "bot":
            await db.update_xo_stats(player_o, "draw", bet, 0)
            
    elif result == "X":
        px_user = await db.get_user(player_x) if player_x != "bot" and player_x is not None else None
        px_name = html.escape(px_user["first_name"]) if px_user else "Бот (X)"
        result_text = f"🎉 ПОБЕДИЛ {px_name} (X)!"
        win_amount = 0
        if bet > 0 and player_x != "bot" and player_x is not None:
            win_amount = int(bet * 2 * (1 - COMMISSION))
            await db.update_balance(player_x, win_amount, "Выигрыш в крестики-нолики")
            result_text += f"\n💰 Получено: <b>{win_amount} NCoin</b>"
        await db.update_xo_stats(player_x, "win", bet, win_amount)
        if player_o != "bot":
            await db.update_xo_stats(player_o, "loss", bet, 0)
        else:
            await db.update_xo_stats(player_x, "win_vs_bot", bet, win_amount)
            
    elif result == "O":
        if player_o == "bot" or player_o is None:
            result_text = "🤖 ПОБЕДИЛ БОТ!"
            await db.update_xo_stats(player_x, "loss_vs_bot", bet, 0)
        else:
            po_user = await db.get_user(player_o)
            po_name = html.escape(po_user["first_name"]) if po_user else "Игрок O"
            result_text = f"🎉 ПОБЕДИЛ {po_name} (O)!"
            win_amount = 0
            if bet > 0:
                win_amount = int(bet * 2 * (1 - COMMISSION))
                await db.update_balance(player_o, win_amount, "Выигрыш в крестики-нолики")
                result_text += f"\n💰 Получено: <b>{win_amount} NCoin</b>"
            await db.update_xo_stats(player_o, "win", bet, win_amount)
            await db.update_xo_stats(player_x, "loss", bet, 0)
    else:  # draw
        result_text = "🤝 НИЧЬЯ!"
        if bet > 0:
            if player_x != "bot" and player_x is not None:
                await db.update_balance(player_x, bet, "Возврат ставки (ничья)")
            if player_o != "bot" and player_o is not None:
                await db.update_balance(player_o, bet, "Возврат ставки (ничья)")
            result_text += f"\n💰 Ставка возвращена"
        await db.update_xo_stats(player_x, "draw", bet, 0)
        if player_o != "bot":
            await db.update_xo_stats(player_o, "draw", bet, 0)
    
    active_games.pop(game_id, None)
    
    try:
        await callback.message.edit_text(
            f"🎮 <b>ИГРА ОКОНЧЕНА!</b>\n\n{result_text}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
                [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
            ])
        )
    except Exception as e:
        logger.error(f"Error editing end game message: {e}")


async def bot_turn(callback: types.CallbackQuery, game_id: str, game: dict):
    """Ход бота"""
    difficulty = game.get("difficulty", "medium")
    if difficulty not in BOT_MOVES:
        difficulty = "medium"
    
    move_func = BOT_MOVES[difficulty]
    bot_side = game["current_turn"]
    
    move = move_func(game["board"])
    if not move:
        winner = check_winner(game["board"])
        if winner:
            await end_game(callback, game_id, game, winner)
        return
    
    r, c = move
    game["board"][r][c] = bot_side
    
    winner = check_winner(game["board"])
    if winner:
        await end_game(callback, game_id, game, winner)
        return
    
    game["current_turn"] = "O" if bot_side == "X" else "X"
    game["last_move"] = time.time()
    
    user_side = game.get("user_side", "X")
    user_id = game["player_x"] if user_side == "X" else game["player_o"]
    user_data = await db.get_user(user_id) if user_id != "bot" and user_id is not None else None
    user_name = html.escape(user_data["first_name"]) if user_data else "Игрок"
    
    diff_name = BOT_DIFFICULTY[difficulty]["name"]
    
    try:
        await callback.message.edit_text(
            f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
            f"❌ X vs ⭕ O\n"
            f"🤖 Сложность: {diff_name}\n\n"
            f"👇 <b>Ваш ход, {user_name} ({user_side})</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=xo_board_keyboard(game["board"], game_id, can_play=True)
        )
    except Exception as e:
        logger.error(f"Error updating bot turn message: {e}")


# ==================== ОБРАБОТЧИКИ ====================

@router.message(Command("xo"))
async def cmd_xo(message: types.Message):
    if message is None:
        return
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n\nВыберите режим игры:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_menu_keyboard()
    )


@router.callback_query(F.data == "game_xo")
@router.callback_query(F.data == "games")
async def game_xo_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    await cmd_xo(callback.message)
    await callback.answer()


@router.callback_query(F.data == "xo_vs_bot")
async def xo_vs_bot_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "🤖 <b>ИГРА С БОТОМ</b>\n\n"
        "Выберите уровень сложности:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_difficulty_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xo_diff_"))
async def xo_choose_side(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
    difficulty = callback.data.split("_")[2]
    if difficulty not in BOT_DIFFICULTY:
        difficulty = "medium"
    await callback.message.edit_text(
        "🤖 <b>ИГРА С БОТОМ</b>\n\n"
        "За кого будете играть?",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_side_choice_keyboard(difficulty)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xo_side_"))
async def xo_start_vs_bot(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
        
    player_side = parts[2]
    difficulty = parts[3]
    
    if player_side not in ["X", "O"]:
        player_side = "X"
    if difficulty not in BOT_DIFFICULTY:
        difficulty = "medium"
    
    user_id = callback.from_user.id
    game_id = generate_game_id()
    board = [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
    
    if player_side == "X":
        player_x = user_id
        player_o = "bot"
        current_turn = "X"
    else:
        player_x = "bot"
        player_o = user_id
        current_turn = "X"
    
    active_games[game_id] = {
        "type": "pvb",
        "board": board,
        "player_x": player_x,
        "player_o": player_o,
        "user_side": player_side,
        "current_turn": current_turn,
        "bet": 0,
        "difficulty": difficulty,
        "chat_id": callback.message.chat.id,
        "message_id": callback.message.message_id,
        "created_at": time.time(),
        "last_move": time.time(),
        "finished": False,
    }
    
    diff_name = BOT_DIFFICULTY[difficulty]["name"]
    user_symbol = "❌" if player_side == "X" else "⭕"
    bot_symbol = "⭕" if player_side == "X" else "❌"
    
    is_user_turn = (current_turn == player_side)
    
    await callback.message.edit_text(
        f"🎮 <b>ИГРА С БОТОМ</b>\n\n"
        f"Сложность: {diff_name}\n"
        f"Вы играете за {user_symbol} <b>{player_side}</b>\n"
        f"Бот играет за {bot_symbol} <b>{'O' if player_side == 'X' else 'X'}</b>\n\n"
        f"👇 {'Ваш ход' if is_user_turn else 'Ход бота'}...",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(board, game_id, can_play=is_user_turn)
    )
    
    if not is_user_turn:
        await asyncio.sleep(0.8)
        await bot_turn(callback, game_id, active_games[game_id])
    
    await callback.answer()


@router.callback_query(F.data == "xo_vs_player")
async def xo_vs_player_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "👤 <b>ИГРА С ИГРОКОМ</b>\n\nВыберите ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_bet_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xo_bet_"))
async def xo_bet_selected(callback: types.CallbackQuery):
    if callback is None:
        return
    try:
        bet = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
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
    if message is None:
        return
        
    user_id = message.from_user.id
    username = message.text.replace('@', '').strip()
    bet = pending_challenges.pop(user_id, 0)
    
    target = await db.get_user_by_username(username)
    if not target:
        await message.answer(f"❌ Пользователь @{username} не найден!")
        return
    
    target_id = target.get("user_id")
    if target_id is None:
        await message.answer(f"❌ Пользователь не активировал бота!")
        return
        
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
        f"👤 {html.escape(message.from_user.first_name or 'Игрок')} вызывает @{html.escape(username)}!\n"
        f"💰 Ставка: <b>{bet} NCoin</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("xo_accept_"))
async def xo_accept_challenge(callback: types.CallbackQuery):
    if callback is None:
        return
        
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
        
    game_id = parts[2]
    user_id = callback.from_user.id
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена!", show_alert=True)
        return
    
    game = active_games[game_id]
    if user_id != game.get("player_o"):
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    if not game.get("pending", False):
        await callback.answer("❌ Вызов уже принят!", show_alert=True)
        return
    
    bet = game.get("bet", 0)
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    if bet > 0:
        balance_o = await db.get_balance(player_o) if player_o is not None else 0
        balance_x = await db.get_balance(player_x) if player_x is not None else 0
        if balance_o < bet or balance_x < bet:
            await callback.answer("❌ У кого-то не хватает средств!", show_alert=True)
            return
        await db.update_balance(player_x, -bet, "Ставка в крестики-нолики")
        await db.update_balance(player_o, -bet, "Ставка в крестики-нолики")
    
    game["pending"] = False
    game["last_move"] = time.time()
    
    px_user = await db.get_user(player_x) if player_x is not None else None
    po_user = await db.get_user(player_o) if player_o is not None else None
    player_x_name = html.escape(px_user["first_name"]) if px_user else "Игрок X"
    player_o_name = html.escape(po_user["first_name"]) if po_user else "Игрок O"
    
    await callback.message.edit_text(
        f"🎮 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"❌ X: {player_x_name}\n⭕ O: {player_o_name}\n"
        f"💰 Ставка: <b>{bet} NCoin</b>\n\n"
        f"👇 Ходит {player_x_name} (X)",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=(user_id == player_x))
    )
    await callback.answer("✅ Игра началась!")


@router.callback_query(F.data.startswith("xo_reject_"))
async def xo_reject_challenge(callback: types.CallbackQuery):
    if callback is None:
        return
    parts = callback.data.split("_")
    if len(parts) >= 3:
        game_id = parts[2]
        if game_id in active_games:
            active_games.pop(game_id)
    await callback.message.edit_text("❌ Вызов отклонён!")
    await callback.answer()


@router.callback_query(F.data.startswith("xo_move_"))
async def xo_make_move(callback: types.CallbackQuery):
    if callback is None:
        return
        
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
        
    if time.time() - game.get("last_move", 0) > GAME_TIMEOUT_SECONDS:
        await end_game(callback, game_id, game, "timeout")
        return
    
    current_turn = game.get("current_turn", "X")
    
    if game.get("type") == "pvb":
        user_side = game.get("user_side", "X")
        if current_turn != user_side:
            await callback.answer("❌ Сейчас ход бота! Подождите...", show_alert=True)
            return
    else:
        if (current_turn == "X" and user_id != game.get("player_x")) or \
           (current_turn == "O" and user_id != game.get("player_o")):
            await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
            return
    
    if r < 0 or r > 2 or c < 0 or c > 2:
        await callback.answer("❌ Неверные координаты!", show_alert=True)
        return
        
    if game["board"][r][c] != " ":
        await callback.answer("❌ Клетка занята!", show_alert=True)
        return
    
    game["board"][r][c] = current_turn
    game["last_move"] = time.time()
    
    winner = check_winner(game["board"])
    if winner:
        await end_game(callback, game_id, game, winner)
        return
    
    game["current_turn"] = "O" if current_turn == "X" else "X"
    
    if game.get("type") == "pvb":
        user_side = game.get("user_side", "X")
        user_id_actual = game["player_x"] if user_side == "X" else game["player_o"]
        user_data = await db.get_user(user_id_actual) if user_id_actual != "bot" else None
        user_name = html.escape(user_data["first_name"]) if user_data else "Игрок"
        next_is_user = (game["current_turn"] == user_side)
        
        diff_name = BOT_DIFFICULTY[game.get("difficulty", "medium")]["name"]
        
        await callback.message.edit_text(
            f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
            f"❌ X vs ⭕ O\n"
            f"🤖 Сложность: {diff_name}\n\n"
            f"👇 {'Ваш ход' if next_is_user else 'Ход бота'}...",
            parse_mode=ParseMode.HTML,
            reply_markup=xo_board_keyboard(game["board"], game_id, can_play=next_is_user)
        )
        
        if not next_is_user:
            await asyncio.sleep(0.6)
            await bot_turn(callback, game_id, game)
    else:
        px_user = await db.get_user(game["player_x"]) if game["player_x"] is not None else None
        po_user = await db.get_user(game["player_o"]) if game["player_o"] is not None else None
        player_x_name = html.escape(px_user["first_name"]) if px_user else "Игрок X"
        player_o_name = html.escape(po_user["first_name"]) if po_user else "Игрок O"
        next_player = player_x_name if game["current_turn"] == "X" else player_o_name
        
        can_play = (game["current_turn"] == "X" and user_id == game["player_x"]) or \
                   (game["current_turn"] == "O" and user_id == game["player_o"])
        
        await callback.message.edit_text(
            f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
            f"❌ {player_x_name} vs ⭕ {player_o_name}\n"
            f"💰 Ставка: <b>{game.get('bet', 0)} NCoin</b>\n\n"
            f"👇 Ход <b>{next_player} ({game['current_turn']})</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=xo_board_keyboard(game["board"], game_id, can_play=can_play)
        )
    
    await callback.answer(f"✅ Ход на ({r+1}, {c+1})")


@router.callback_query(F.data.startswith("xo_surrender_"))
async def xo_surrender(callback: types.CallbackQuery):
    if callback is None:
        return
        
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
        
    game_id = parts[2]
    user_id = callback.from_user.id
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена!", show_alert=True)
        return
    
    game = active_games[game_id]
    if game.get("finished", False):
        await callback.answer("❌ Игра уже окончена!", show_alert=True)
        return
    
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    if user_id == player_x:
        winner = "O"
    elif user_id == player_o:
        winner = "X"
    else:
        await callback.answer("❌ Вы не участвуете в этой игре!", show_alert=True)
        return
    
    await end_game(callback, game_id, game, winner)
    await callback.answer("🏳️ Вы сдались!")


@router.callback_query(F.data == "xo_stats")
async def xo_stats_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    user_id = callback.from_user.id
    
    stats = await db.get_user_stats(user_id)
    
    if not stats:
        await callback.message.edit_text(
            "📊 <b>СТАТИСТИКА</b>\n\nУ вас пока нет сыгранных игр!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_button("game_xo")
        )
        return
    
    games = stats.get('games_played', 0) or 0
    wins = stats.get('wins', 0) or 0
    losses = stats.get('losses', 0) or 0
    draws = stats.get('draws', 0) or 0
    losses_vs_bot = stats.get('losses_vs_bot', 0) or 0
    winrate = (wins / games * 100) if games > 0 else 0
    
    if games == 0:
        await callback.message.edit_text(
            "📊 <b>СТАТИСТИКА</b>\n\nУ вас пока нет сыгранных игр!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_button("game_xo")
        )
        return
    
    text = (
        f"📊 <b>ВАША СТАТИСТИКА</b>\n\n"
        f"🎮 Игр: <b>{games}</b>\n"
        f"🏆 Побед: <b>{wins}</b>\n"
        f"💔 Поражений: <b>{losses}</b>\n"
        f"🤝 Ничьих: <b>{draws}</b>\n"
        f"🤖 Поражений от бота: <b>{losses_vs_bot}</b>\n"
        f"📈 Винрейт: <b>{winrate:.1f}%</b>"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="game_xo")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "xo_help")
async def xo_help_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "❓ <b>ПРАВИЛА КРЕСТИКОВ-НОЛИКОВ</b>\n\n"
        "🎯 <b>Цель:</b> Собрать 3 своих символа в ряд\n\n"
        "🤖 <b>С ботом:</b> Выберите сторону (X/O) и сложность\n"
        "👤 <b>С игроком:</b> Вызовите друга и играйте на NCoin\n\n"
        "💰 <b>Ставки:</b> Победитель получает ×2 (комиссия 5%)",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("game_xo")
    )
    await callback.answer()


@router.callback_query(F.data == "xo_noop")
async def xo_noop(callback: types.CallbackQuery):
    await callback.answer("❌ Эта клетка занята или игра не активна!", show_alert=True)
