"""
Крестики-нолики для NEXUS Bot
Игра против бота и против других игроков
ПОЛНОСТЬЮ ИСПРАВЛЕННАЯ ВЕРСИЯ
"""

import random
import asyncio
import time
import html
import hashlib
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

# Импорт клавиатур
from utils.keyboards import (
    xo_menu_keyboard, xo_difficulty_keyboard, xo_board_keyboard,
    xo_bet_keyboard, back_button
)

router = Router()
logger = __import__('logging').getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

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
    return f"xo_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"


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
    
    # 1. Победный ход
    for r, c in [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]:
        sim[r][c] = "O"
        if check_winner(sim) == "O":
            return (r, c)
        sim[r][c] = " "
    
    # 2. Блокировка игрока
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
    
    # 5. Любая свободная
    empty = [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]
    return random.choice(empty) if empty else None


BOT_MOVES = {"easy": bot_move_easy, "medium": bot_move_medium, "hard": bot_move_hard}


# ==================== СТАТИСТИКА ====================

async def update_xo_stats(user_id: int, result_type: str):
    def _sync_update():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS xo_stats (
                user_id INTEGER PRIMARY KEY,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                wins_vs_bot INTEGER DEFAULT 0,
                losses_vs_bot INTEGER DEFAULT 0
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO xo_stats (user_id) VALUES (?)", (user_id,))
        cursor.execute("UPDATE xo_stats SET games_played = games_played + 1 WHERE user_id = ?", (user_id,))
        
        if result_type == "win":
            cursor.execute("UPDATE xo_stats SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        elif result_type == "loss":
            cursor.execute("UPDATE xo_stats SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        elif result_type == "draw":
            cursor.execute("UPDATE xo_stats SET draws = draws + 1 WHERE user_id = ?", (user_id,))
        elif result_type == "loss_vs_bot":
            cursor.execute("UPDATE xo_stats SET losses_vs_bot = losses_vs_bot + 1 WHERE user_id = ?", (user_id,))
        
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_update)


async def end_game(callback: types.CallbackQuery, game_id: str, game: dict, result: str):
    if game.get("finished", False):
        return
    game["finished"] = True
    
    bet = game["bet"]
    player_x = game["player_x"]
    player_o = game["player_o"]
    
    result_text = ""
    
    if result == "timeout":
        result_text = "⏳ <b>ВРЕМЯ ВЫШЛО!</b>\nИгра завершена. Ставки возвращены."
        if bet > 0:
            await db.update_balance(player_x, bet, "Возврат ставки (таймаут)")
            if player_o != "bot":
                await db.update_balance(player_o, bet, "Возврат ставки (таймаут)")
        await update_xo_stats(player_x, "draw")
        if player_o != "bot":
            await update_xo_stats(player_o, "draw")
            
    elif result == "X":
        px_name = html.escape((await db.get_user(player_x))["first_name"])
        result_text = f"🎉 ПОБЕДИЛ {px_name} (X)!"
        if bet > 0:
            win_amount = int(bet * 2 * (1 - COMMISSION))
            await db.update_balance(player_x, win_amount, "Выигрыш в крестики-нолики")
            result_text += f"\n💰 Получено: <b>{win_amount} NCoin</b>"
        await update_xo_stats(player_x, "win")
        if player_o != "bot":
            await update_xo_stats(player_o, "loss")
            
    elif result == "O":
        if player_o == "bot":
            result_text = "🤖 ПОБЕДИЛ БОТ!"
            await update_xo_stats(player_x, "loss_vs_bot")
        else:
            po_name = html.escape((await db.get_user(player_o))["first_name"])
            result_text = f"🎉 ПОБЕДИЛ {po_name} (O)!"
            if bet > 0:
                win_amount = int(bet * 2 * (1 - COMMISSION))
                await db.update_balance(player_o, win_amount, "Выигрыш в крестики-нолики")
                result_text += f"\n💰 Получено: <b>{win_amount} NCoin</b>"
            await update_xo_stats(player_o, "win")
            await update_xo_stats(player_x, "loss")
    else:  # draw
        result_text = "🤝 НИЧЬЯ!"
        if bet > 0:
            await db.update_balance(player_x, bet, "Возврат ставки (ничья)")
            if player_o != "bot":
                await db.update_balance(player_o, bet, "Возврат ставки (ничья)")
            result_text += f"\n💰 Ставка возвращена"
        await update_xo_stats(player_x, "draw")
        if player_o != "bot":
            await update_xo_stats(player_o, "draw")
    
    active_games.pop(game_id, None)
    
    await callback.message.edit_text(
        f"🎮 <b>ИГРА ОКОНЧЕНА!</b>\n\n{result_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
            [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
        ])
    )


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
    
    player_x = html.escape((await db.get_user(game["player_x"]))["first_name"])
    
    await callback.message.edit_text(
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
        f"❌ {player_x} vs 🤖 Бот\n"
        f"Сложность: {BOT_DIFFICULTY[difficulty]['name']}\n\n"
        f"👇 Ваш ход, <b>{player_x} (X)</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=True)
    )


# ==================== ОБРАБОТЧИКИ ====================

@router.message(Command("xo"))
async def cmd_xo(message: types.Message):
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n\n"
        "Выберите режим игры:\n\n"
        "🤖 <b>С ботом</b> — три уровня сложности\n"
        "👤 <b>С игроком</b> — вызовите друга на дуэль\n"
        "💰 <b>Ставки</b> — играйте на NCoin!\n\n"
        "👇 Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_menu_keyboard()
    )


@router.callback_query(F.data == "game_xo")
async def game_xo_callback(callback: types.CallbackQuery):
    await cmd_xo(callback.message)
    await callback.answer()


@router.callback_query(F.data == "xo_vs_bot")
async def xo_vs_bot_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤖 <b>ИГРА С БОТОМ</b>\n\n"
        "Выберите уровень сложности:\n\n"
        "😊 <b>Лёгкий</b> — бот часто ошибается\n"
        "🤔 <b>Средний</b> — бот играет хорошо\n"
        "🤖 <b>Сложный</b> — бот играет идеально\n\n"
        "🎯 <i>Вы играете за X и ходите первым!</i>",
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
        "Выберите ставку:\n\n"
        "💰 <b>Без ставки</b> — просто игра\n"
        "💰 <b>Со ставкой</b> — победитель получает ставку ×2 (комиссия 5%)\n\n"
        "👇 Выберите сумму:",
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
        f"📝 Напишите @username противника:\n\n"
        f"<i>Пример: @player</i>\n\n"
        f"❌ Для отмены: /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("xo_vs_player")
    )
    await callback.answer()


@router.message(lambda m: m.text and m.text.startswith('@') and m.from_user.id in pending_challenges)
async def xo_challenge_player(message: types.Message):
    user_id = message.from_user.id
    username = message.text.replace('@', '').strip()
    bet = pending_challenges.pop(user_id, 0)
    
    user = await db.get_user(user_id)
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
        f"👤 {html.escape(message.from_user.first_name)} вызывает @{html.escape(username)}!\n"
        f"💰 Ставка: <b>{bet} NCoin</b>\n\n"
        f"@{html.escape(username)}, примите вызов!",
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
        
        if balance_o < bet:
            await callback.answer(f"❌ У вас недостаточно средств! Нужно {bet}", show_alert=True)
            return
        if balance_x < bet:
            await callback.answer(f"❌ У противника недостаточно средств!", show_alert=True)
            return
        
        await db.update_balance(game["player_x"], -bet, "Ставка в крестики-нолики")
        await db.update_balance(game["player_o"], -bet, "Ставка в крестики-нолики")
    
    game["pending"] = False
    game["last_move"] = time.time()
    
    player_x_name = html.escape((await db.get_user(game["player_x"]))["first_name"])
    player_o_name = html.escape(callback.from_user.first_name)
    
    await callback.message.edit_text(
        f"🎮 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"❌ <b>X:</b> {player_x_name}\n"
        f"⭕ <b>O:</b> {player_o_name}\n"
        f"💰 Ставка: <b>{bet} NCoin</b>\n\n"
        f"👇 Ходит <b>{player_x_name} (X)</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=False)
    )
    
    msg = await callback.bot.send_message(
        game["chat_id"],
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
        f"❌ {player_x_name} vs ⭕ {player_o_name}\n\n"
        f"👇 Ход {player_x_name}:",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=True)
    )
    game["message_id"] = msg.message_id
    
    await callback.answer("✅ Игра началась!")


@router.callback_query(F.data.startswith("xo_reject_"))
async def xo_reject_challenge(callback: types.CallbackQuery):
    game_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена!", show_alert=True)
        return
    
    game = active_games.pop(game_id)
    if user_id != game["player_o"]:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"❌ {html.escape(callback.from_user.first_name)} отклонил вызов!",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xo_move_"))
async def xo_make_move(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    game_id = parts[2]
    try:
        r, c = int(parts[3]), int(parts[4])
    except (ValueError, IndexError):
        await callback.answer("❌ Неверный ход!", show_alert=True)
        return
        
    user_id = callback.from_user.id
    
    if game_id not in active_games:
        await callback.answer("❌ Игра завершена или не найдена!", show_alert=True)
        return
    
    game = active_games[game_id]
    if game.get("finished", False):
        await callback.answer("❌ Игра уже окончена!", show_alert=True)
        return
        
    if time.time() - game["last_move"] > GAME_TIMEOUT_SECONDS:
        await end_game(callback, game_id, game, "timeout")
        await callback.answer("⏳ Игра завершена по таймауту.", show_alert=True)
        return
    
    current_turn = game["current_turn"]
    if (current_turn == "X" and user_id != game["player_x"]) or \
       (current_turn == "O" and user_id != game["player_o"]):
        await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
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
    
    player_x = html.escape((await db.get_user(game["player_x"]))["first_name"])
    player_o = html.escape((await db.get_user(game["player_o"]))["first_name"]) if game["player_o"] != "bot" else "Бот"
    next_player = player_x if game["current_turn"] == "X" else player_o
    
    can_play = True
    if game["type"] == "pvp":
        can_play = (game["current_turn"] == "X" and user_id == game["player_x"]) or \
                   (game["current_turn"] == "O" and user_id == game["player_o"])
    
    await callback.message.edit_text(
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
        f"❌ {player_x} vs ⭕ {player_o}\n"
        f"💰 Ставка: <b>{game['bet']} NCoin</b>\n\n"
        f"👇 Ход <b>{next_player} ({game['current_turn']})</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=xo_board_keyboard(game["board"], game_id, can_play=can_play)
    )
    
    if game["type"] == "pvb" and game["current_turn"] == "O":
        await asyncio.sleep(0.6)
        await bot_turn(callback, game_id, game)
    
    await callback.answer(f"✅ Ход на ({r+1}, {c+1})")


@router.callback_query(F.data.startswith("xo_surrender_"))
async def xo_surrender(callback: types.CallbackQuery):
    game_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена!", show_alert=True)
        return
    
    game = active_games[game_id]
    if game.get("finished", False):
        await callback.answer("❌ Игра уже окончена!", show_alert=True)
        return
        
    if user_id == game["player_x"]:
        winner = "O"
    elif user_id == game["player_o"]:
        winner = "X"
    else:
        await callback.answer("❌ Вы не участвуете в этой игре!", show_alert=True)
        return
    
    await end_game(callback, game_id, game, winner)
    await callback.answer("🏳️ Вы сдались!")


@router.callback_query(F.data == "xo_stats")
async def xo_stats_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    def _sync_get():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT games_played, wins, losses, draws, losses_vs_bot FROM xo_stats WHERE user_id = ?", (user_id,))
        return cursor.fetchone()
    
    row = await asyncio.to_thread(_sync_get)
    
    if not row or row[0] == 0:
        await callback.message.edit_text(
            "📊 <b>СТАТИСТИКА КРЕСТИКОВ-НОЛИКОВ</b>\n\n"
            "У вас пока нет сыгранных игр!\n\n"
            "🎮 Начните играть прямо сейчас!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_button("game_xo")
        )
        return
    
    games, wins, losses, draws, losses_vs_bot = row
    winrate = (wins / games * 100) if games > 0 else 0
    
    text = (
        f"📊 <b>ВАША СТАТИСТИКА</b>\n\n"
        f"🎮 Игр всего: <b>{games}</b>\n"
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
    await callback.message.edit_text(
        "❓ <b>ПРАВИЛА КРЕСТИКОВ-НОЛИКОВ</b>\n\n"
        "🎯 <b>Цель:</b> Собрать 3 своих символа в ряд\n\n"
        "📋 <b>Как играть:</b>\n"
        "• Игроки ходят по очереди\n"
        "• X всегда ходит первым\n"
        "• Нажмите на пустую клетку чтобы сделать ход\n\n"
        "🤖 <b>Игра с ботом:</b>\n"
        "• Три уровня сложности\n"
        "• Вы всегда играете за X\n\n"
        "👤 <b>Игра с игроком:</b>\n"
        "• Вызовите друга через @username\n"
        "• Можно играть на NCoin\n\n"
        "💰 <b>Ставки:</b>\n"
        "• Победитель получает ставку ×2\n"
        "• Комиссия бота: 5%\n"
        "• При ничьей или таймауте ставка возвращается",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("game_xo")
    )
    await callback.answer()


@router.callback_query(F.data == "xo_noop")
async def xo_noop(callback: types.CallbackQuery):
    await callback.answer("❌ Эта клетка занята или игра не активна!", show_alert=True)
