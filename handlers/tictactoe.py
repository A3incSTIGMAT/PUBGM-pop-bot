#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/tictactoe.py
# ВЕРСИЯ: 3.1.0-production
# ОПИСАНИЕ: Крестики-нолики — игра в ЛС + СИНХРОНИЗАЦИЯ users.wins/losses
# ИСПРАВЛЕНИЯ V3.1.0: Синхронизация xo_stats с users при завершении игры
# ============================================

import asyncio
import hashlib
import html
import logging
import random
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramBadRequest

from database import db, DatabaseError
from config import START_BALANCE, GAME_COMMISSION, BOT_USERNAME
from utils.keyboards import (
    xo_menu_keyboard, xo_difficulty_keyboard, xo_board_keyboard,
    xo_bet_keyboard, back_button, xo_side_choice_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

_bot: Optional[Bot] = None

COMMISSION = GAME_COMMISSION if isinstance(GAME_COMMISSION, (int, float)) else 0.05

GAME_TIMEOUT = 600
CHALLENGE_TIMEOUT = 60
MOVE_TIMEOUT = 120
CLEANUP_INTERVAL = 300

MAX_ACTIVE_GAMES = 1000
MOVE_CLICK_COOLDOWN = 0.5

WIN_COMBINATIONS: List[List[Tuple[int, int]]] = [
    [(0,0), (0,1), (0,2)], [(1,0), (1,1), (1,2)], [(2,0), (2,1), (2,2)],
    [(0,0), (1,0), (2,0)], [(0,1), (1,1), (2,1)], [(0,2), (1,2), (2,2)],
    [(0,0), (1,1), (2,2)], [(0,2), (1,1), (2,0)],
]

BOT_DIFFICULTY = {
    "easy": {"name": "😊 Лёгкий", "mistake_chance": 0.4},
    "medium": {"name": "🤔 Средний", "mistake_chance": 0.15},
    "hard": {"name": "🤖 Сложный", "mistake_chance": 0.0},
}


# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

class GameManager:
    """Потокобезопасный менеджер активных игр с лимитами."""
    
    def __init__(self, max_games: int = MAX_ACTIVE_GAMES):
        self._lock = asyncio.Lock()
        self._active_games: Dict[str, Dict] = {}
        self._pending_challenges: Dict[int, Dict] = {}
        self._max_games = max_games
        self._move_clicks: Dict[str, float] = {}
    
    async def add_game(self, game_id: str, game_data: Dict) -> bool:
        async with self._lock:
            if len(self._active_games) >= self._max_games:
                oldest_id = min(
                    self._active_games.keys(),
                    key=lambda gid: self._active_games[gid].get("created_at", float('inf'))
                )
                logger.warning(f"🗑️ Game limit reached, removing oldest: {oldest_id}")
                self._active_games.pop(oldest_id, None)
            self._active_games[game_id] = game_data
            return True
    
    async def get_game(self, game_id: str) -> Optional[Dict]:
        async with self._lock:
            return self._active_games.get(game_id)
    
    async def remove_game(self, game_id: str) -> Optional[Dict]:
        async with self._lock:
            keys_to_remove = [k for k in self._move_clicks if k.startswith(f"{game_id}:")]
            for k in keys_to_remove:
                del self._move_clicks[k]
            return self._active_games.pop(game_id, None)
    
    async def get_all_games(self) -> List[Tuple[str, Dict]]:
        async with self._lock:
            return list(self._active_games.items())
    
    async def add_pending_challenge(self, user_id: int, bet: int, target_id: Optional[int] = None) -> bool:
        async with self._lock:
            if user_id in self._pending_challenges:
                return False
            self._pending_challenges[user_id] = {
                "bet": bet, "target_id": target_id, "timestamp": time.time()
            }
            return True
    
    async def pop_pending_challenge(self, user_id: int) -> Optional[Dict]:
        async with self._lock:
            return self._pending_challenges.pop(user_id, None)
    
    async def check_move_cooldown(self, game_id: str, user_id: int) -> bool:
        key = f"{game_id}:{user_id}"
        now = time.time()
        async with self._lock:
            last_click = self._move_clicks.get(key, 0)
            if now - last_click < MOVE_CLICK_COOLDOWN:
                return False
            self._move_clicks[key] = now
            return True
    
    async def cleanup_expired(self) -> int:
        now = time.time()
        expired_games = []
        expired_challenges = []
        
        async with self._lock:
            for game_id, game in list(self._active_games.items()):
                last_move = game.get("last_move", game.get("created_at", 0))
                if now - last_move > GAME_TIMEOUT:
                    expired_games.append(game_id)
            
            for game_id in expired_games:
                self._active_games.pop(game_id, None)
            
            for user_id, data in list(self._pending_challenges.items()):
                if now - data["timestamp"] > CHALLENGE_TIMEOUT:
                    expired_challenges.append(user_id)
            
            for user_id in expired_challenges:
                self._pending_challenges.pop(user_id, None)
        
        if expired_games:
            logger.info(f"🧹 Cleaned up {len(expired_games)} expired games")
        if expired_challenges:
            logger.info(f"🧹 Cleaned up {len(expired_challenges)} expired challenges")
        
        return len(expired_games) + len(expired_challenges)


_game_manager = GameManager()
_shutdown_event = asyncio.Event()
_cleanup_task: Optional[asyncio.Task] = None


# ==================== УПРАВЛЕНИЕ ФОНОВЫМИ ЗАДАЧАМИ ====================

def set_bot(bot_instance: Bot) -> None:
    global _bot
    _bot = bot_instance
    logger.info("✅ Bot instance set for tictactoe module")


async def start_background_tasks() -> None:
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info("🔄 Background cleanup task started")


async def stop_background_tasks() -> None:
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _shutdown_event.set()
        try:
            await asyncio.wait_for(_cleanup_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _cleanup_task.cancel()
            logger.warning("⚠️ Cleanup task force-stopped")
        finally:
            _cleanup_task = None
            _shutdown_event.clear()
            logger.info("🛑 Background tasks stopped")


async def _cleanup_loop() -> None:
    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            if _shutdown_event.is_set():
                break
            await _game_manager.cleanup_expired()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"❌ Error in cleanup loop: {e}", exc_info=True)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_number(num: Any) -> str:
    if num is None: return "0"
    try: return f"{int(num):,}".replace(",", " ")
    except: return "0"


def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try: return html.escape(str(text))
    except: return ""


def generate_game_id() -> str:
    return hashlib.md5(f"{time.time()}{random.random()}{id(asyncio.current_task())}".encode()).hexdigest()[:10]


def copy_board(board: Optional[List[List[str]]]) -> List[List[str]]:
    if board is None:
        return [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
    return [row[:] for row in board]


def check_winner(board: Optional[List[List[str]]]) -> Optional[str]:
    if board is None: return None
    for combo in WIN_COMBINATIONS:
        cells = [board[r][c] for r, c in combo]
        if cells[0] != " " and cells[0] == cells[1] == cells[2]:
            return cells[0]
    if all(board[r][c] != " " for r in range(3) for c in range(3)):
        return "draw"
    return None


async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict]:
    if user_id is None: return None
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            logger.info(f"🆕 Auto-registered user {user_id} in tictactoe")
        return user
    except DatabaseError as e:
        logger.error(f"❌ Database error in get_or_create_user: {e}")
        return None


async def safe_send_private(
    user_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> Optional[Message]:
    if _bot is None or user_id is None: return None
    try:
        return await _bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except TelegramForbiddenError:
        logger.warning(f"🚫 User {user_id} blocked the bot")
        return None
    except TelegramAPIError as e:
        logger.error(f"❌ Telegram API error sending to {user_id}: {e}")
        return None


async def safe_edit_private(
    user_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    if _bot is None or user_id is None or message_id is None: return False
    try:
        await _bot.edit_message_text(
            chat_id=user_id, message_id=message_id, text=text,
            parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower(): return True
        logger.debug(f"⚠️ Could not edit message {message_id} for {user_id}: {e}")
        return False
    except TelegramAPIError as e:
        logger.debug(f"⚠️ Could not edit message {message_id} for {user_id}: {e}")
        return False


async def safe_edit_callback(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    if not callback or not callback.message: return False
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            await callback.answer("ℹ️ Данные актуальны", show_alert=False)
            return True
        logger.warning(f"⚠️ Edit error: {e}")
        try:
            await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            return True
        except Exception:
            return False
    except Exception as e:
        logger.error(f"❌ Edit failed: {e}")
        return False


# ==================== ЛОГИКА БОТА ====================

def bot_move_easy(board: List[List[str]]) -> Optional[Tuple[int, int]]:
    if random.random() < BOT_DIFFICULTY["easy"]["mistake_chance"]:
        empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
        return random.choice(empty) if empty else None
    return bot_move_medium(board)


def bot_move_medium(board: List[List[str]]) -> Optional[Tuple[int, int]]:
    if random.random() < BOT_DIFFICULTY["medium"]["mistake_chance"]:
        empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
        return random.choice(empty) if empty else None
    return bot_move_hard(board)


def bot_move_hard(board: List[List[str]]) -> Optional[Tuple[int, int]]:
    sim = copy_board(board)
    
    for r, c in [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]:
        sim[r][c] = "O"
        if check_winner(sim) == "O": return (r, c)
        sim[r][c] = " "
    
    for r, c in [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]:
        sim[r][c] = "X"
        if check_winner(sim) == "X": return (r, c)
        sim[r][c] = " "
    
    if sim[1][1] == " ": return (1, 1)
    
    corners = [(0,0), (0,2), (2,0), (2,2)]
    empty_corners = [c for c in corners if sim[c[0]][c[1]] == " "]
    if empty_corners: return random.choice(empty_corners)
    
    empty = [(r, c) for r in range(3) for c in range(3) if sim[r][c] == " "]
    return random.choice(empty) if empty else None


BOT_MOVES = {"easy": bot_move_easy, "medium": bot_move_medium, "hard": bot_move_hard}


# ==================== СИНХРОНИЗАЦИЯ СТАТИСТИКИ ====================

async def _sync_users_wins_losses(player_id: int, result_type: str) -> None:
    """
    Синхронизирует users.wins/users.losses с xo_stats.
    Вызывается после каждого завершения игры.
    """
    if player_id is None or player_id == "bot":
        return
    
    try:
        if result_type == "win" or result_type == "win_vs_bot":
            await db._execute_with_retry(
                "UPDATE users SET wins = COALESCE(wins, 0) + 1 WHERE user_id = ?",
                (player_id,)
            )
        elif result_type == "loss" or result_type == "loss_vs_bot":
            await db._execute_with_retry(
                "UPDATE users SET losses = COALESCE(losses, 0) + 1 WHERE user_id = ?",
                (player_id,)
            )
    except DatabaseError as e:
        logger.error(f"❌ Failed to sync users.wins/losses for {player_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error syncing users.wins/losses: {e}")


# ==================== ЗАВЕРШЕНИЕ ИГРЫ ====================

async def end_game(
    game_id: str,
    game: Dict,
    result: str,
    callback: Optional[CallbackQuery] = None
) -> None:
    """Завершение игры с сохранением статистики и синхронизацией users."""
    if game.get("finished", False):
        return
    
    game["finished"] = True
    result_text = ""
    
    bet = game.get("bet", 0)
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    try:
        if result == "timeout":
            result_text = "⏳ <b>ВРЕМЯ ВЫШЛО!</b>\nИгра завершена. Ставки возвращены."
            if bet > 0:
                if isinstance(player_x, int) and player_x != "bot":
                    await db.update_balance(player_x, bet, "Возврат ставки (таймаут)")
                if isinstance(player_o, int) and player_o != "bot":
                    await db.update_balance(player_o, bet, "Возврат ставки (таймаут)")
            if isinstance(player_x, int):
                await db.update_xo_stats(player_x, "draw", bet, 0)
            if isinstance(player_o, int) and player_o != "bot":
                await db.update_xo_stats(player_o, "draw", bet, 0)
                
        elif result == "X":
            if isinstance(player_x, int):
                px_user = await db.get_user(player_x)
                px_name = safe_html_escape(px_user.get("first_name")) if px_user else "Игрок"
                result_text = f"🎉 ПОБЕДИЛ {px_name} (X)!"
                
                win_amount = 0
                if bet > 0:
                    win_amount = int(bet * 2 * (1 - COMMISSION))
                    await db.update_balance(player_x, win_amount, "Выигрыш в крестики-нолики")
                    result_text += f"\n💰 Получено: <b>{format_number(win_amount)} NCoin</b>"
                
                await db.update_xo_stats(player_x, "win", bet, win_amount)
                await _sync_users_wins_losses(player_x, "win")
                
                if isinstance(player_o, int):
                    await db.update_xo_stats(player_o, "loss", bet, 0)
                    await _sync_users_wins_losses(player_o, "loss")
                elif player_o == "bot":
                    await db.update_xo_stats(player_x, "win_vs_bot", bet, win_amount)
                    await _sync_users_wins_losses(player_x, "win_vs_bot")
            else:
                result_text = "🤖 ПОБЕДИЛ БОТ (X)!"
                if isinstance(player_o, int):
                    await db.update_xo_stats(player_o, "loss_vs_bot", bet, 0)
                    await _sync_users_wins_losses(player_o, "loss_vs_bot")
                
        elif result == "O":
            if isinstance(player_o, int):
                po_user = await db.get_user(player_o)
                po_name = safe_html_escape(po_user.get("first_name")) if po_user else "Игрок"
                result_text = f"🎉 ПОБЕДИЛ {po_name} (O)!"
                
                win_amount = 0
                if bet > 0:
                    win_amount = int(bet * 2 * (1 - COMMISSION))
                    await db.update_balance(player_o, win_amount, "Выигрыш в крестики-нолики")
                    result_text += f"\n💰 Получено: <b>{format_number(win_amount)} NCoin</b>"
                
                await db.update_xo_stats(player_o, "win", bet, win_amount)
                await _sync_users_wins_losses(player_o, "win")
                
                if isinstance(player_x, int):
                    await db.update_xo_stats(player_x, "loss", bet, 0)
                    await _sync_users_wins_losses(player_x, "loss")
            elif player_o == "bot":
                result_text = "🤖 ПОБЕДИЛ БОТ (O)!"
                if isinstance(player_x, int):
                    await db.update_xo_stats(player_x, "loss_vs_bot", bet, 0)
                    await _sync_users_wins_losses(player_x, "loss_vs_bot")
        else:  # draw
            result_text = "🤝 НИЧЬЯ!"
            if bet > 0:
                if isinstance(player_x, int):
                    await db.update_balance(player_x, bet, "Возврат ставки (ничья)")
                if isinstance(player_o, int) and player_o != "bot":
                    await db.update_balance(player_o, bet, "Возврат ставки (ничья)")
                result_text += f"\n💰 Ставка возвращена"
            if isinstance(player_x, int):
                await db.update_xo_stats(player_x, "draw", bet, 0)
            if isinstance(player_o, int) and player_o != "bot":
                await db.update_xo_stats(player_o, "draw", bet, 0)
    
    except DatabaseError as e:
        logger.error(f"❌ Database error in end_game: {e}", exc_info=True)
        result_text += "\n⚠️ Ошибка сохранения статистики"
    except Exception as e:
        logger.error(f"❌ Unexpected error in end_game: {e}", exc_info=True)
        result_text += "\n⚠️ Внутренняя ошибка"
    finally:
        await _game_manager.remove_game(game_id)
    
    if game.get("in_private", False):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
            [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
        ])
        
        if isinstance(player_x, int) and player_x != "bot":
            await safe_send_private(player_x, f"🎮 <b>ИГРА ОКОНЧЕНА!</b>\n\n{result_text}", keyboard)
        
        if isinstance(player_o, int) and player_o != "bot":
            await safe_send_private(player_o, f"🎮 <b>ИГРА ОКОНЧЕНА!</b>\n\n{result_text}", keyboard)
    
    if callback is not None and callback.message and not game.get("in_private", False):
        try:
            await callback.message.edit_text(
                f"🎮 <b>ИГРА ОКОНЧЕНА!</b>\n\n{result_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
                    [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
                ])
            )
        except TelegramAPIError as e:
            logger.debug(f"⚠️ Could not edit end game message: {e}")


async def bot_turn(game_id: str, game: Dict) -> None:
    difficulty = game.get("difficulty", "medium")
    if difficulty not in BOT_MOVES:
        difficulty = "medium"
    
    move_func = BOT_MOVES[difficulty]
    bot_side = game["current_turn"]
    
    move = move_func(game["board"])
    if not move:
        winner = check_winner(game["board"])
        if winner:
            await end_game(game_id, game, winner)
        return
    
    r, c = move
    game["board"][r][c] = bot_side
    
    winner = check_winner(game["board"])
    if winner:
        await end_game(game_id, game, winner)
        return
    
    game["current_turn"] = "O" if bot_side == "X" else "X"
    game["last_move"] = time.time()
    
    user_side = game.get("user_side", "X")
    user_id = game["player_x"] if user_side == "X" else game["player_o"]
    
    if isinstance(user_id, int) and user_id != "bot":
        diff_name = BOT_DIFFICULTY[difficulty]["name"]
        msg_id = game.get("private_msg_user")
        
        if msg_id:
            await safe_edit_private(
                user_id, msg_id,
                f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
                f"❌ X vs ⭕ O\n"
                f"🤖 Сложность: {diff_name}\n\n"
                f"👇 Ход бота завершён. Ваш черёд!",
                xo_board_keyboard(game["board"], game_id, can_play=True)
            )


# ==================== АВТООТМЕНА ВЫЗОВА ====================

async def auto_cancel_challenge(game_id: str, chat_id: int, message_id: int) -> None:
    await asyncio.sleep(CHALLENGE_TIMEOUT)
    game = await _game_manager.get_game(game_id)
    if game and game.get("pending", False):
        await _game_manager.remove_game(game_id)
        if _bot:
            try:
                await _bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text="⏰ <b>ВЫЗОВ ИСТЁК!</b>\n\nВремя ожидания вышло. Вызов автоматически отменён.",
                    parse_mode=ParseMode.HTML
                )
            except TelegramAPIError as e:
                logger.debug(f"⚠️ Could not edit expired challenge: {e}")


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("xo"))
async def cmd_xo(message: Message) -> None:
    if message is None or message.from_user is None: return
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n\nВыберите режим игры:",
        parse_mode=ParseMode.HTML, reply_markup=xo_menu_keyboard()
    )


@router.callback_query(F.data == "game_xo")
@router.callback_query(F.data == "games")
async def game_xo_callback(callback: CallbackQuery) -> None:
    if callback is None: return
    await cmd_xo(callback.message)
    await callback.answer()


@router.callback_query(F.data == "xo_vs_bot")
async def xo_vs_bot_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None: return
    await safe_edit_callback(callback, "🤖 <b>ИГРА С БОТОМ</b>\n\nВыберите уровень сложности:", xo_difficulty_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("xo_diff_"))
async def xo_choose_side(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None: return
    parts = callback.data.split("_")
    difficulty = parts[2] if len(parts) > 2 else "medium"
    if difficulty not in BOT_DIFFICULTY: difficulty = "medium"
    await safe_edit_callback(callback, "🤖 <b>ИГРА С БОТОМ</b>\n\nЗа кого будете играть?", xo_side_choice_keyboard(difficulty))
    await callback.answer()


@router.callback_query(F.data.startswith("xo_side_"))
async def xo_start_vs_bot(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None or _bot is None: return
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Неверный формат!", show_alert=True); return
    
    player_side = parts[2]
    difficulty = parts[3]
    if player_side not in ["X", "O"]: player_side = "X"
    if difficulty not in BOT_DIFFICULTY: difficulty = "medium"
    
    user_id = callback.from_user.id
    game_id = generate_game_id()
    board = [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
    
    if player_side == "X":
        player_x, player_o = user_id, "bot"
        current_turn = "X"
    else:
        player_x, player_o = "bot", user_id
        current_turn = "X"
    
    game_data = {
        "type": "pvb", "board": board, "player_x": player_x, "player_o": player_o,
        "user_side": player_side, "current_turn": current_turn, "bet": 0,
        "difficulty": difficulty, "created_at": time.time(), "last_move": time.time(),
        "finished": False, "in_private": True,
    }
    
    if not await _game_manager.add_game(game_id, game_data):
        await callback.answer("❌ Слишком много активных игр. Попробуйте позже.", show_alert=True); return
    
    diff_name = BOT_DIFFICULTY[difficulty]["name"]
    user_symbol = "❌" if player_side == "X" else "⭕"
    bot_symbol = "⭕" if player_side == "X" else "❌"
    is_user_turn = (current_turn == player_side)
    
    msg = await safe_send_private(
        user_id,
        f"🎮 <b>ИГРА С БОТОМ</b>\n\n"
        f"Сложность: {diff_name}\n"
        f"Вы играете за {user_symbol} <b>{player_side}</b>\n"
        f"Бот играет за {bot_symbol} <b>{'O' if player_side == 'X' else 'X'}</b>\n\n"
        f"👇 {'Ваш ход' if is_user_turn else 'Ход бота'}...",
        xo_board_keyboard(board, game_id, can_play=is_user_turn)
    )
    
    if msg:
        game_data["private_msg_user"] = msg.message_id
        await safe_edit_callback(
            callback,
            f"🎮 <b>ИГРА С БОТОМ</b>\n\n"
            f"📩 <b>Игра началась в личных сообщениях!</b>\n"
            f"Проверьте ЛС от бота.",
        )
        if not is_user_turn:
            await asyncio.sleep(0.8)
            await bot_turn(game_id, game_data)
    else:
        await _game_manager.remove_game(game_id)
        bot_link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "https://t.me/NEXUS_Manager_Official_bot"
        await safe_edit_callback(
            callback,
            f"❌ <b>НЕ УДАЛОСЬ НАЧАТЬ ИГРУ!</b>\n\n"
            f"Вы должны активировать бота:\n\n"
            f"1️⃣ Перейти в @{BOT_USERNAME or 'NEXUS_Manager_Official_bot'}\n"
            f"2️⃣ Нажать <b>START</b> (или написать /start)\n"
            f"3️⃣ Убедиться, что бот не заблокирован\n\n"
            f"💡 <i>После этого игра заработает!</i>",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 ОТКРЫТЬ БОТА", url=bot_link)]
            ])
        )
    await callback.answer()


@router.callback_query(F.data == "xo_vs_player")
async def xo_vs_player_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None: return
    await safe_edit_callback(callback, "👤 <b>ИГРА С ИГРОКОМ</b>\n\nВыберите ставку:", xo_bet_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("xo_bet_"))
async def xo_bet_selected(callback: CallbackQuery) -> None:
    if callback is None or callback.from_user is None: return
    try: bet = int(callback.data.split("_")[2])
    except (ValueError, IndexError): await callback.answer("❌ Неверная ставка!", show_alert=True); return
    await _game_manager.add_pending_challenge(callback.from_user.id, bet, None)
    await safe_edit_callback(
        callback,
        f"👤 <b>ВЫЗОВ ИГРОКА</b>\n\n💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n📝 Напишите @username противника:",
        back_button("xo_vs_player")
    )
    await callback.answer()


@router.message(lambda m: m.text and m.text.startswith('@'))
async def xo_challenge_player(message: Message) -> None:
    if message is None or message.from_user is None: return
    user_id = message.from_user.id
    pending = await _game_manager.pop_pending_challenge(user_id)
    if not pending: return
    
    username = message.text.replace('@', '').strip()
    bet = pending.get("bet", 0)
    
    await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    
    try: target = await db.get_user_by_username(username)
    except DatabaseError as e:
        logger.error(f"❌ Database error getting user: {e}")
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.", parse_mode=ParseMode.HTML); return
    
    if not target:
        await message.answer(
            f"❌ <b>Пользователь @{safe_html_escape(username)} не найден!</b>\n\n"
            f"Возможные причины:\n• Пользователь никогда не запускал бота\n• Неправильно указан username\n\n"
            f"💡 Попросите пользователя написать /start в бота.",
            parse_mode=ParseMode.HTML
        ); return
    
    target_id = target.get("user_id")
    if target_id is None:
        await message.answer(
            f"❌ <b>Пользователь @{safe_html_escape(username)} не активировал бота!</b>\n\n"
            f"Попросите его написать /start.", parse_mode=ParseMode.HTML
        ); return
    
    if target_id == user_id:
        await message.answer("❌ Нельзя вызвать самого себя!", parse_mode=ParseMode.HTML); return
    
    for game_id, game in await _game_manager.get_all_games():
        if game.get("pending", False):
            px, po = game.get("player_x"), game.get("player_o")
            if (px == user_id and po == target_id) or (px == target_id and po == user_id):
                await message.answer("❌ У вас уже есть активный вызов! Дождитесь ответа или отмены.", parse_mode=ParseMode.HTML); return
    
    if bet > 0:
        try:
            balance = await db.get_balance(user_id)
            if balance < bet:
                await message.answer(f"❌ У вас недостаточно средств! Баланс: {format_number(balance)} NCoin", parse_mode=ParseMode.HTML); return
        except DatabaseError:
            await message.answer("❌ Ошибка проверки баланса.", parse_mode=ParseMode.HTML); return
    
    game_id = generate_game_id()
    game_data = {
        "type": "pvp", "board": [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]],
        "player_x": user_id, "player_o": target_id, "current_turn": "X", "bet": bet,
        "chat_id": message.chat.id, "created_at": time.time(), "last_move": time.time(),
        "pending": True, "finished": False,
        "challenger_name": safe_html_escape(message.from_user.first_name or "Игрок"),
        "challenged_name": safe_html_escape(target.get("first_name") or username),
    }
    
    await _game_manager.add_game(game_id, game_data)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]
    ])
    
    msg = await message.answer(
        f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
        f"👤 {safe_html_escape(message.from_user.first_name or 'Игрок')} вызывает @{safe_html_escape(username)}!\n"
        f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n"
        f"⏰ Вызов действителен 60 секунд\n\n"
        f"⚠️ ТОЛЬКО @{safe_html_escape(username)} может принять или отклонить вызов!",
        parse_mode=ParseMode.HTML, reply_markup=keyboard
    )
    
    asyncio.create_task(auto_cancel_challenge(game_id, msg.chat.id, msg.message_id))


@router.callback_query(F.data.startswith("xo_accept_"))
async def xo_accept_challenge(callback: CallbackQuery) -> None:
    if callback is None or callback.from_user is None or _bot is None:
        await callback.answer("❌ Ошибка обработки", show_alert=True); return
    
    parts = callback.data.split("_")
    if len(parts) < 3: await callback.answer("❌ Неверный формат!", show_alert=True); return
    
    game_id = parts[2]
    user_id = callback.from_user.id
    
    game = await _game_manager.get_game(game_id)
    if not game:
        await callback.answer("❌ Вызов уже неактивен (истёк или отменён)!", show_alert=True)
        try: await callback.message.delete()
        except TelegramAPIError: pass
        return
    
    if user_id != game.get("player_o"):
        await callback.answer("❌ Этот вызов не вам! Только вызванный игрок может принять.", show_alert=True); return
    
    if not game.get("pending", False):
        await callback.answer("❌ Вызов уже неактивен!", show_alert=True)
        try: await callback.message.delete()
        except TelegramAPIError: pass
        return
    
    bet = game.get("bet", 0)
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    test_msg_x = await safe_send_private(player_x, "🎮 Проверка связи...") if isinstance(player_x, int) else None
    test_msg_o = await safe_send_private(player_o, "🎮 Проверка связи...") if isinstance(player_o, int) else None
    
    bot_link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "https://t.me/NEXUS_Manager_Official_bot"
    
    if isinstance(player_x, int) and not test_msg_x:
        await safe_edit_callback(callback,
            f"❌ <b>НЕ УДАЛОСЬ НАЧАТЬ ИГРУ!</b>\n\nИгрок <b>{safe_html_escape(game.get('challenger_name', 'X'))}</b> должен активировать бота:\n\n"
            f"1️⃣ Перейти в @{BOT_USERNAME or 'NEXUS_Manager_Official_bot'}\n2️⃣ Нажать <b>START</b>\n3️⃣ Убедиться, что бот не заблокирован",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 ОТКРЫТЬ БОТА", url=bot_link)]]))
        await _game_manager.remove_game(game_id)
        await callback.answer("❌ Игрок X не активировал бота", show_alert=True); return
    
    if isinstance(player_o, int) and not test_msg_o:
        await safe_edit_callback(callback,
            f"❌ <b>НЕ УДАЛОСЬ НАЧАТЬ ИГРУ!</b>\n\nИгрок <b>{safe_html_escape(game.get('challenged_name', 'O'))}</b> должен активировать бота:\n\n"
            f"1️⃣ Перейти в @{BOT_USERNAME or 'NEXUS_Manager_Official_bot'}\n2️⃣ Нажать <b>START</b>\n3️⃣ Убедиться, что бот не заблокирован",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 ОТКРЫТЬ БОТА", url=bot_link)]]))
        await _game_manager.remove_game(game_id)
        await callback.answer("❌ Игрок O не активировал бота", show_alert=True); return
    
    try:
        if test_msg_x: await _bot.delete_message(player_x, test_msg_x.message_id)
        if test_msg_o: await _bot.delete_message(player_o, test_msg_o.message_id)
    except TelegramAPIError: pass
    
    if bet > 0:
        try:
            balance_o = await db.get_balance(player_o) if isinstance(player_o, int) else 0
            balance_x = await db.get_balance(player_x) if isinstance(player_x, int) else 0
            if isinstance(player_o, int) and balance_o < bet:
                await callback.answer(f"❌ У вас недостаточно средств! Нужно {bet} NCoin", show_alert=True); return
            if isinstance(player_x, int) and balance_x < bet:
                await callback.answer(f"❌ У вызывающего недостаточно средств! Вызов отменён.", show_alert=True)
                await _game_manager.remove_game(game_id)
                await safe_edit_callback(callback, "❌ Вызов отменён: у вызывающего недостаточно средств."); return
            if isinstance(player_x, int): await db.update_balance(player_x, -bet, "Ставка в крестики-нолики")
            if isinstance(player_o, int): await db.update_balance(player_o, -bet, "Ставка в крестики-нолики")
        except DatabaseError as e:
            logger.error(f"❌ Database error processing bet: {e}")
            await callback.answer("❌ Ошибка обработки ставки", show_alert=True); return
    
    game["pending"] = False
    game["last_move"] = time.time()
    game["in_private"] = True
    
    px_user = await db.get_user(player_x) if isinstance(player_x, int) else None
    po_user = await db.get_user(player_o) if isinstance(player_o, int) else None
    player_x_name = safe_html_escape(px_user.get("first_name")) if px_user else "Игрок X"
    player_o_name = safe_html_escape(po_user.get("first_name")) if po_user else "Игрок O"
    
    await safe_edit_callback(callback,
        f"🎮 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"❌ X: {player_x_name}\n⭕ O: {player_o_name}\n💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n"
        f"📩 <b>Игра продолжается в личных сообщениях!</b>\nПроверьте ЛС от бота.",
    )
    
    msg_x = await safe_send_private(
        player_x,
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ Вы: {player_x_name} (X)\n⭕ Соперник: {player_o_name} (O)\n"
        f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n👇 <b>Ваш ход!</b>",
        xo_board_keyboard(game["board"], game_id, can_play=True)
    ) if isinstance(player_x, int) else None
    
    msg_o = await safe_send_private(
        player_o,
        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ Соперник: {player_x_name} (X)\n⭕ Вы: {player_o_name} (O)\n"
        f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n⏳ <b>Ожидайте хода соперника...</b>",
        xo_board_keyboard(game["board"], game_id, can_play=False)
    ) if isinstance(player_o, int) else None
    
    if msg_x and isinstance(player_x, int): game["private_msg_x"] = msg_x.message_id
    if msg_o and isinstance(player_o, int): game["private_msg_o"] = msg_o.message_id
    
    await callback.answer("✅ Игра началась! Проверьте ЛС.")


@router.callback_query(F.data.startswith("xo_reject_"))
async def xo_reject_challenge(callback: CallbackQuery) -> None:
    if callback is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    parts = callback.data.split("_")
    if len(parts) < 3: await callback.answer("❌ Неверный формат!", show_alert=True); return
    
    game_id = parts[2]
    user_id = callback.from_user.id
    
    game = await _game_manager.get_game(game_id)
    if not game:
        await callback.answer("❌ Вызов уже неактивен!", show_alert=True)
        try: await callback.message.delete()
        except TelegramAPIError: pass
        return
    
    if user_id != game.get("player_o"):
        await callback.answer("❌ Этот вызов не вам!", show_alert=True); return
    
    await _game_manager.remove_game(game_id)
    challenged_name = safe_html_escape(game.get("challenged_name", "Игрок"))
    await safe_edit_callback(callback, f"❌ <b>ВЫЗОВ ОТКЛОНЁН!</b>\n\n{challenged_name} отклонил(а) вызов.")
    await callback.answer("❌ Вызов отклонён!")


@router.callback_query(F.data.startswith("xo_move_"))
async def xo_make_move(callback: CallbackQuery) -> None:
    if callback is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    parts = callback.data.split("_")
    if len(parts) < 5: await callback.answer("❌ Неверный формат хода!", show_alert=True); return
    
    try: game_id, r, c = parts[2], int(parts[3]), int(parts[4])
    except (ValueError, IndexError): await callback.answer("❌ Неверные координаты!", show_alert=True); return
    
    user_id = callback.from_user.id
    
    if not await _game_manager.check_move_cooldown(game_id, user_id):
        await callback.answer("⏱️ Слишком часто! Подождите немного.", show_alert=True); return
    
    game = await _game_manager.get_game(game_id)
    if not game: await callback.answer("❌ Игра завершена или не найдена!", show_alert=True); return
    if game.get("finished", False): await callback.answer("❌ Игра уже окончена!", show_alert=True); return
    
    if time.time() - game.get("last_move", 0) > MOVE_TIMEOUT:
        await end_game(game_id, game, "timeout", callback)
        await callback.answer("⏰ Время на ход истекло!", show_alert=True); return
    
    current_turn = game.get("current_turn", "X")
    
    if game.get("type") == "pvb":
        if current_turn != game.get("user_side", "X"):
            await callback.answer("❌ Сейчас ход бота! Подождите...", show_alert=True); return
    else:
        if (current_turn == "X" and user_id != game.get("player_x")) or \
           (current_turn == "O" and user_id != game.get("player_o")):
            await callback.answer("❌ Сейчас не ваш ход! Ожидайте соперника.", show_alert=True); return
    
    if r < 0 or r > 2 or c < 0 or c > 2 or game["board"][r][c] != " ":
        await callback.answer("❌ Клетка занята или неверные координаты!", show_alert=True); return
    
    game["board"][r][c] = current_turn
    game["last_move"] = time.time()
    
    winner = check_winner(game["board"])
    if winner:
        await end_game(game_id, game, winner, callback)
        await callback.answer(f"✅ Ход на ({r+1}, {c+1})"); return
    
    game["current_turn"] = "O" if current_turn == "X" else "X"
    
    if game.get("in_private", False):
        if game.get("type") == "pvb":
            user_side = game.get("user_side", "X")
            user_id_actual = game["player_x"] if user_side == "X" else game["player_o"]
            next_is_user = (game["current_turn"] == user_side)
            diff_name = BOT_DIFFICULTY[game.get("difficulty", "medium")]["name"]
            msg_id = game.get("private_msg_user")
            
            if msg_id and isinstance(user_id_actual, int):
                await safe_edit_private(
                    user_id_actual, msg_id,
                    f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ X vs ⭕ O\n🤖 Сложность: {diff_name}\n\n"
                    f"👇 {'Ваш ход' if next_is_user else 'Ход бота'}...",
                    xo_board_keyboard(game["board"], game_id, can_play=next_is_user)
                )
            
            if not next_is_user:
                await asyncio.sleep(0.6)
                await bot_turn(game_id, game)
        else:
            player_x, player_o = game["player_x"], game["player_o"]
            px_user = await db.get_user(player_x) if isinstance(player_x, int) else None
            po_user = await db.get_user(player_o) if isinstance(player_o, int) else None
            player_x_name = safe_html_escape(px_user.get("first_name")) if px_user else "Игрок X"
            player_o_name = safe_html_escape(po_user.get("first_name")) if po_user else "Игрок O"
            next_is_x = (game["current_turn"] == "X")
            
            msg_x_id = game.get("private_msg_x")
            if msg_x_id and isinstance(player_x, int):
                await safe_edit_private(
                    player_x, msg_x_id,
                    f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ Вы: {player_x_name} (X)\n⭕ Соперник: {player_o_name} (O)\n"
                    f"💰 Ставка: <b>{format_number(game.get('bet', 0))} NCoin</b>\n\n"
                    f"👇 {'<b>Ваш ход!</b>' if next_is_x else '⏳ Ожидайте хода соперника...'}",
                    xo_board_keyboard(game["board"], game_id, can_play=next_is_x)
                )
            
            msg_o_id = game.get("private_msg_o")
            if msg_o_id and isinstance(player_o, int):
                await safe_edit_private(
                    player_o, msg_o_id,
                    f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ Соперник: {player_x_name} (X)\n⭕ Вы: {player_o_name} (O)\n"
                    f"💰 Ставка: <b>{format_number(game.get('bet', 0))} NCoin</b>\n\n"
                    f"👇 {'<b>Ваш ход!</b>' if not next_is_x else '⏳ Ожидайте хода соперника...'}",
                    xo_board_keyboard(game["board"], game_id, can_play=not next_is_x)
                )
    
    await callback.answer(f"✅ Ход на ({r+1}, {c+1})")


@router.callback_query(F.data.startswith("xo_surrender_"))
async def xo_surrender(callback: CallbackQuery) -> None:
    if callback is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    parts = callback.data.split("_")
    if len(parts) < 3: await callback.answer("❌ Неверный формат!", show_alert=True); return
    
    game_id = parts[2]
    user_id = callback.from_user.id
    
    game = await _game_manager.get_game(game_id)
    if not game or game.get("finished", False):
        await callback.answer("❌ Игра не найдена или уже окончена!", show_alert=True); return
    
    player_x, player_o = game.get("player_x"), game.get("player_o")
    
    if user_id == player_x: winner = "O"
    elif user_id == player_o: winner = "X"
    else: await callback.answer("❌ Вы не участвуете в этой игре!", show_alert=True); return
    
    await end_game(game_id, game, winner, callback)
    await callback.answer("🏳️ Вы сдались!")


@router.callback_query(F.data == "xo_stats")
async def xo_stats_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None or callback.from_user is None:
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    user_id = callback.from_user.id
    
    try:
        stats = await db.get_user_stats(user_id)
    except DatabaseError:
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True); return
    
    if not stats:
        await safe_edit_callback(callback, "📊 <b>СТАТИСТИКА</b>\n\nУ вас пока нет сыгранных игр!", back_button("game_xo")); return
    
    games = stats.get('games_played', 0) or 0
    wins = stats.get('wins', 0) or 0
    losses = stats.get('losses', 0) or 0
    draws = stats.get('draws', 0) or 0
    losses_vs_bot = stats.get('losses_vs_bot', 0) or 0
    winrate = (wins / games * 100) if games > 0 else 0
    
    text = (
        f"📊 <b>ВАША СТАТИСТИКА</b>\n\n"
        f"🎮 Игр: <b>{games}</b>\n🏆 Побед: <b>{wins}</b>\n💔 Поражений: <b>{losses}</b>\n"
        f"🤝 Ничьих: <b>{draws}</b>\n🤖 Поражений от бота: <b>{losses_vs_bot}</b>\n"
        f"📈 Винрейт: <b>{winrate:.1f}%</b>"
    )
    
    await safe_edit_callback(callback, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="game_xo")]
    ]))
    await callback.answer()


@router.callback_query(F.data == "xo_help")
async def xo_help_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
        await callback.answer("❌ Ошибка", show_alert=True); return
    
    await safe_edit_callback(
        callback,
        "❓ <b>ПРАВИЛА КРЕСТИКОВ-НОЛИКОВ</b>\n\n"
        "🎯 <b>Цель:</b> Собрать 3 своих символа в ряд\n\n"
        "🤖 <b>С ботом:</b> Выберите сторону (X/O) и сложность\n"
        "👤 <b>С игроком:</b> Вызовите друга и играйте на NCoin\n\n"
        f"💰 <b>Ставки:</b> Победитель получает ×2 (комиссия {int(COMMISSION * 100)}%)\n\n"
        "📩 <b>Игра проходит в личных сообщениях!</b>",
        back_button("game_xo")
    )
    await callback.answer()


@router.callback_query(F.data == "xo_noop")
async def xo_noop(callback: CallbackQuery) -> None:
    await callback.answer("❌ Эта клетка занята или игра не активна!", show_alert=True)
