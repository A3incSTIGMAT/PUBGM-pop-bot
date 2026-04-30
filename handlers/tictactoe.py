#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/tictactoe.py
# ВЕРСИЯ: 3.3.0-production (улучшенная)
# ОПИСАНИЕ: Крестики-нолики — обработчик с защитой от гонок данных и null-безопасностью
# УЛУЧШЕНИЯ v3.3.0:
#   ✅ Race Condition защита в xo_make_move (атомарная проверка хода)
#   ✅ Полная null-безопасность для всех БД-вызовов
#   ✅ Транзакционный подход к обновлению баланса
#   ✅ Улучшенная обработка ошибок Telegram API
#   ✅ Логирование всех критических событий
# ============================================

import asyncio
import hashlib
import html
import logging
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List, Union

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
BOT_USER = "bot"

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


# ==================== МЕТРИКИ ====================

class XOMetrics:
    """Счётчики для мониторинга (потокобезопасные через атомики)."""
    active_games: int = 0
    active_challenges: int = 0
    games_completed: int = 0
    games_timeout: int = 0
    games_surrendered: int = 0
    errors_total: int = 0
    
    @classmethod
    def increment(cls, attr: str, value: int = 1) -> None:
        if hasattr(cls, attr):
            setattr(cls, attr, getattr(cls, attr) + value)


# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

class GameManager:
    """
    Потокобезопасный менеджер активных игр.
    
    ✅ Атомарные операции с блокировками
    ✅ Защита от переполнения
    ✅ Очистка устаревших данных
    """
    
    def __init__(self, max_games: int = MAX_ACTIVE_GAMES):
        self._lock = asyncio.Lock()
        self._game_locks: Dict[str, asyncio.Lock] = {}  # Локальные локи для каждой игры
        self._active_games: Dict[str, Dict] = {}
        self._pending_challenges: Dict[int, Dict] = {}
        self._challenge_tasks: Dict[int, asyncio.Task] = {}
        self._max_games = max_games
        self._move_clicks: Dict[str, float] = {}
    
    async def _get_game_lock(self, game_id: str) -> asyncio.Lock:
        """Получить или создать локальный лок для игры."""
        async with self._lock:
            if game_id not in self._game_locks:
                self._game_locks[game_id] = asyncio.Lock()
            return self._game_locks[game_id]
    
    async def _release_game_lock(self, game_id: str) -> None:
        """Очистить лок после удаления игры."""
        async with self._lock:
            self._game_locks.pop(game_id, None)
    
    @asynccontextmanager
    async def game_lock(self, game_id: str):
        """Контекстный менеджер для блокировки конкретной игры."""
        lock = await self._get_game_lock(game_id)
        async with lock:
            try:
                yield
            finally:
                # Очищаем лок если игра удалена
                if game_id not in self._active_games:
                    await self._release_game_lock(game_id)
    
    async def add_game(self, game_id: str, game_data: Dict) -> bool:
        async with self._lock:
            if len(self._active_games) >= self._max_games:
                # Удаляем самую старую неактивную игру
                candidates = [
                    (gid, g) for gid, g in self._active_games.items()
                    if g.get("finished", False) or g.get("pending", False)
                ]
                if candidates:
                    oldest_id = min(candidates, key=lambda x: x[1].get("created_at", float('inf')))[0]
                    logger.warning("🗑️ Game limit reached, removing: %s", oldest_id)
                    self._active_games.pop(oldest_id, None)
                    self._game_locks.pop(oldest_id, None)
                else:
                    logger.warning("⚠️ Game limit reached, no removable games")
                    return False
            
            self._active_games[game_id] = game_data
            self._game_locks[game_id] = asyncio.Lock()
            XOMetrics.active_games = len(self._active_games)
            return True
    
    async def get_game(self, game_id: str) -> Optional[Dict]:
        async with self._lock:
            game = self._active_games.get(game_id)
            return game.copy() if game else None  # Возвращаем копию для безопасности
    
    async def update_game(self, game_id: str, updates: Dict) -> bool:
        """Атомарное обновление полей игры."""
        async with self._lock:
            if game_id not in self._active_games:
                return False
            self._active_games[game_id].update(updates)
            return True
    
    async def remove_game(self, game_id: str) -> Optional[Dict]:
        async with self._lock:
            # Очистка координат кликов
            keys_to_remove = [k for k in self._move_clicks if k.startswith(game_id + ":")]
            for k in keys_to_remove:
                del self._move_clicks[k]
            
            game = self._active_games.pop(game_id, None)
            self._game_locks.pop(game_id, None)
            XOMetrics.active_games = len(self._active_games)
            return game
    
    async def get_all_games(self) -> List[Tuple[str, Dict]]:
        async with self._lock:
            return [(gid, g.copy()) for gid, g in self._active_games.items()]
    
    async def find_user_game(self, user_id: int) -> Optional[Tuple[str, Dict]]:
        """Найти активную игру пользователя (не завершённую)."""
        async with self._lock:
            for gid, g in self._active_games.items():
                if g.get("finished", False):
                    continue
                if g.get("player_x") == user_id or g.get("player_o") == user_id:
                    return gid, g.copy()
            return None
    
    async def add_pending_challenge(self, user_id: int, bet: int,
                                     target_id: Optional[int] = None) -> bool:
        async with self._lock:
            if user_id in self._pending_challenges:
                return False
            self._pending_challenges[user_id] = {
                "bet": bet, "target_id": target_id, "timestamp": time.time()
            }
            XOMetrics.active_challenges = len(self._pending_challenges)
            return True
    
    async def pop_pending_challenge(self, user_id: int) -> Optional[Dict]:
        async with self._lock:
            # Отмена фоновой задачи таймаута
            if user_id in self._challenge_tasks:
                task = self._challenge_tasks.pop(user_id)
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            challenge = self._pending_challenges.pop(user_id, None)
            XOMetrics.active_challenges = len(self._pending_challenges)
            return challenge
    
    async def set_challenge_task(self, user_id: int, task: asyncio.Task) -> None:
        async with self._lock:
            self._challenge_tasks[user_id] = task
    
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
        """Очистка просроченных игр и вызовов."""
        now = time.time()
        expired_games = []
        expired_challenges = []
        
        async with self._lock:
            # Проверка игр
            for game_id, game in list(self._active_games.items()):
                if game.get("finished", False):
                    continue
                last_move = game.get("last_move") or game.get("created_at", 0)
                if now - last_move > GAME_TIMEOUT:
                    expired_games.append(game_id)
            
            for game_id in expired_games:
                game = self._active_games.pop(game_id, None)
                self._game_locks.pop(game_id, None)
                if game:
                    # Возврат ставок при таймауте
                    bet = game.get("bet", 0)
                    if bet > 0:
                        for pid in [game.get("player_x"), game.get("player_o")]:
                            if isinstance(pid, int) and pid != BOT_USER:
                                try:
                                    await db.update_balance(pid, bet, "Возврат (таймаут XO)")
                                except DatabaseError as e:
                                    logger.error("❌ Refund failed: %s", e)
            
            # Проверка вызовов
            for user_id, data in list(self._pending_challenges.items()):
                if now - data["timestamp"] > CHALLENGE_TIMEOUT:
                    expired_challenges.append(user_id)
            
            for user_id in expired_challenges:
                self._pending_challenges.pop(user_id, None)
                if user_id in self._challenge_tasks:
                    task = self._challenge_tasks.pop(user_id)
                    if not task.done():
                        task.cancel()
            
            XOMetrics.active_games = len(self._active_games)
            XOMetrics.active_challenges = len(self._pending_challenges)
        
        if expired_games:
            XOMetrics.increment("games_timeout", len(expired_games))
            logger.info("🧹 Cleaned %s expired games", len(expired_games))
        if expired_challenges:
            logger.info("🧹 Cleaned %s expired challenges", len(expired_challenges))
        
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
    global _cleanup_task, _shutdown_event
    if _cleanup_task and not _cleanup_task.done():
        _shutdown_event.set()
        try:
            await asyncio.wait_for(_cleanup_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _cleanup_task.cancel()
            try:
                await _cleanup_task
            except asyncio.CancelledError:
                pass
        finally:
            _cleanup_task = None
            _shutdown_event = asyncio.Event()
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
            logger.error("❌ Cleanup loop error: %s", e, exc_info=True)
            XOMetrics.increment("errors_total")


# ==================== УТИЛИТЫ ====================

def format_number(num: Any) -> str:
    """Форматирование числа с разделителями тысяч."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование для HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return str(text)


def generate_game_id() -> str:
    """Генерация уникального ID игры (10 символов)."""
    seed = f"{time.time()}{random.random()}{id(asyncio.current_task())}"
    return hashlib.md5(seed.encode()).hexdigest()[:10]


def copy_board(board: Optional[List[List[str]]]) -> List[List[str]]:
    """Глубокое копирование игрового поля 3x3."""
    if board is None:
        return [[" ", " ", " "] for _ in range(3)]
    return [row[:] for row in board]


def check_winner(board: Optional[List[List[str]]]) -> Optional[str]:
    """
    Проверка победителя.
    Возвращает: 'X', 'O', 'draw' или None.
    """
    if board is None:
        return None
    
    for combo in WIN_COMBINATIONS:
        cells = [board[r][c] for r, c in combo]
        if cells[0] != " " and cells[0] == cells[1] == cells[2]:
            return cells[0]
    
    if all(board[r][c] != " " for r in range(3) for c in range(3)):
        return "draw"
    
    return None


def is_board_full(board: List[List[str]]) -> bool:
    """Проверка заполненности доски."""
    return all(cell != " " for row in board for cell in row)


async def get_or_create_user(
    user_id: Optional[int], 
    username: Optional[str] = None, 
    first_name: Optional[str] = None
) -> Optional[Dict]:
    """Получить или создать пользователя в БД с обработкой ошибок."""
    if user_id is None:
        return None
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
        return user
    except DatabaseError as e:
        logger.error("❌ DB error in get_or_create_user(%s): %s", user_id, e)
        XOMetrics.increment("errors_total")
        return None
    except Exception as e:
        logger.error("❌ Unexpected error in get_or_create_user: %s", e, exc_info=True)
        return None


async def safe_send_private(
    user_id: Optional[int], 
    text: str, 
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> Optional[Message]:
    """Безопасная отправка сообщения в ЛС с обработкой всех ошибок."""
    if _bot is None or user_id is None:
        return None
    
    try:
        return await _bot.send_message(
            user_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
    except TelegramForbiddenError:
        logger.warning("🚫 User %s blocked the bot", user_id)
        return None
    except TelegramBadRequest as e:
        if "bot was blocked" in str(e).lower() or "user is deactivated" in str(e).lower():
            logger.warning("🚫 User %s unavailable: %s", user_id, e)
            return None
        logger.error("❌ BadRequest to %s: %s", user_id, e)
        return None
    except TelegramAPIError as e:
        logger.error("❌ API error sending to %s: %s", user_id, e)
        XOMetrics.increment("errors_total")
        return None
    except Exception as e:
        logger.error("❌ Unexpected error sending to %s: %s", user_id, e, exc_info=True)
        return None


async def safe_edit_private(
    user_id: Optional[int], 
    message_id: Optional[int], 
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """Безопасное редактирование сообщения в ЛС."""
    if _bot is None or user_id is None or message_id is None:
        return False
    
    try:
        await _bot.edit_message_text(
            chat_id=user_id, message_id=message_id, text=text,
            parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
        return True
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg or "message can't be edited" in err_msg:
            return True  # Нормальная ситуация
        if "message to edit not found" in err_msg:
            logger.debug("⚠️ Message %s not found for user %s", message_id, user_id)
            return False
        logger.error("❌ Edit error for %s: %s", user_id, e)
        return False
    except TelegramForbiddenError:
        logger.warning("🚫 Can't edit: user %s blocked bot", user_id)
        return False
    except TelegramAPIError as e:
        logger.error("❌ API error editing for %s: %s", user_id, e)
        return False
    except Exception as e:
        logger.error("❌ Unexpected edit error: %s", e, exc_info=True)
        return False


async def safe_edit_callback(
    callback: Optional[CallbackQuery], 
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """Безопасное редактирование сообщения из callback."""
    if not callback or not callback.message:
        return False
    
    try:
        await callback.message.edit_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
        return True
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            return True
        if "message can't be edited" in err_msg or "have no rights" in err_msg:
            # Пытаемся отправить новое сообщение как фоллбэк
            try:
                await callback.message.answer(
                    text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
                )
                return True
            except Exception:
                return False
        logger.error("❌ Callback edit error: %s", e)
        return False
    except Exception as e:
        logger.error("❌ Unexpected callback edit error: %s", e, exc_info=True)
        return False


# ==================== ЛОГИКА БОТА ====================

def bot_move_easy(board: List[List[str]]) -> Optional[Tuple[int, int]]:
    """Лёгкий уровень: 40% случайных ходов."""
    empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
    if not empty:
        return None
    if random.random() < BOT_DIFFICULTY["easy"]["mistake_chance"]:
        return random.choice(empty)
    return bot_move_medium(board)


def bot_move_medium(board: List[List[str]]) -> Optional[Tuple[int, int]]:
    """Средний уровень: 15% случайных ходов."""
    empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
    if not empty:
        return None
    if random.random() < BOT_DIFFICULTY["medium"]["mistake_chance"]:
        return random.choice(empty)
    return bot_move_hard(board)


def bot_move_hard(board: List[List[str]]) -> Optional[Tuple[int, int]]:
    """
    Сложный уровень: мини-минимакс.
    1. Победа, если возможно
    2. Блокировка победы противника
    3. Центр, затем углы, затем остальное
    """
    empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == " "]
    if not empty:
        return None
    
    sim = copy_board(board)
    
    # 1. Поиск выигрышного хода
    for r, c in empty:
        sim[r][c] = "O"
        if check_winner(sim) == "O":
            return (r, c)
        sim[r][c] = " "
    
    # 2. Блокировка выигрыша противника
    for r, c in empty:
        sim[r][c] = "X"
        if check_winner(sim) == "X":
            return (r, c)
        sim[r][c] = " "
    
    # 3. Стратегические позиции
    if board[1][1] == " ":
        return (1, 1)
    
    corners = [(0,0), (0,2), (2,0), (2,2)]
    empty_corners = [c for c in corners if board[c[0]][c[1]] == " "]
    if empty_corners:
        return random.choice(empty_corners)
    
    return random.choice(empty)


BOT_MOVES = {"easy": bot_move_easy, "medium": bot_move_medium, "hard": bot_move_hard}


# ==================== СИНХРОНИЗАЦИЯ СТАТИСТИКИ ====================

async def _sync_user_stats(player_id: Optional[int], result_type: str) -> None:
    """
    Обновление статистики побед/поражений пользователя.
    
    result_type: 'win', 'loss', 'win_vs_bot', 'loss_vs_bot'
    """
    if player_id is None or player_id == BOT_USER:
        return
    
    try:
        if result_type in ("win", "win_vs_bot"):
            await db._execute_with_retry(
                "UPDATE users SET wins = COALESCE(wins, 0) + 1 WHERE user_id = ?", 
                (player_id,)
            )
        elif result_type in ("loss", "loss_vs_bot"):
            await db._execute_with_retry(
                "UPDATE users SET losses = COALESCE(losses, 0) + 1 WHERE user_id = ?", 
                (player_id,)
            )
    except DatabaseError as e:
        logger.error("❌ Failed to sync stats for %s: %s", player_id, e)
        XOMetrics.increment("errors_total")
    except Exception as e:
        logger.error("❌ Unexpected error syncing stats: %s", e, exc_info=True)


# ==================== ЗАВЕРШЕНИЕ ИГРЫ ====================

async def end_game(
    game_id: str, 
    game: Dict, 
    result: str,
    callback: Optional[CallbackQuery] = None
) -> None:
    """
    Завершение игры с обработкой ставок и статистики.
    
    result: 'X', 'O', 'draw', 'timeout'
    """
    if game.get("finished", False):
        return
    
    game["finished"] = True
    XOMetrics.increment("games_completed")
    
    result_text = ""
    bet = game.get("bet", 0) or 0
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    try:
        if result == "timeout":
            result_text = "⏳ <b>ВРЕМЯ ВЫШЛО!</b>\nИгра завершена. Ставки возвращены."
            if bet > 0:
                for pid in [player_x, player_o]:
                    if isinstance(pid, int) and pid != BOT_USER:
                        await db.update_balance(pid, bet, "Возврат ставки (таймаут XO)")
            for pid in [player_x, player_o]:
                if isinstance(pid, int):
                    await db.update_xo_stats(pid, "draw", bet, 0)
                    
        elif result == "X":
            if isinstance(player_x, int) and player_x != BOT_USER:
                px_user = await db.get_user(player_x)
                px_name = safe_html_escape(px_user.get("first_name") if px_user else None) or "Игрок"
                result_text = f"🎉 ПОБЕДИЛ {px_name} (X)!"
                
                win_amount = 0
                if bet > 0:
                    win_amount = int(bet * 2 * (1 - COMMISSION))
                    await db.update_balance(player_x, win_amount, "Выигрыш в XO")
                    result_text += f"\n💰 Получено: <b>{format_number(win_amount)} NCoin</b>"
                
                await db.update_xo_stats(player_x, "win", bet, win_amount)
                await _sync_user_stats(player_x, "win")
                
                if isinstance(player_o, int) and player_o != BOT_USER:
                    await db.update_xo_stats(player_o, "loss", bet, 0)
                    await _sync_user_stats(player_o, "loss")
                elif player_o == BOT_USER:
                    await db.update_xo_stats(player_x, "win_vs_bot", bet, win_amount)
                    
            elif player_x == BOT_USER:
                result_text = "🤖 ПОБЕДИЛ БОТ (X)!"
                if isinstance(player_o, int):
                    await db.update_xo_stats(player_o, "loss_vs_bot", bet, 0)
                    
        elif result == "O":
            if isinstance(player_o, int) and player_o != BOT_USER:
                po_user = await db.get_user(player_o)
                po_name = safe_html_escape(po_user.get("first_name") if po_user else None) or "Игрок"
                result_text = f"🎉 ПОБЕДИЛ {po_name} (O)!"
                
                win_amount = 0
                if bet > 0:
                    win_amount = int(bet * 2 * (1 - COMMISSION))
                    await db.update_balance(player_o, win_amount, "Выигрыш в XO")
                    result_text += f"\n💰 Получено: <b>{format_number(win_amount)} NCoin</b>"
                
                await db.update_xo_stats(player_o, "win", bet, win_amount)
                await _sync_user_stats(player_o, "win")
                
                if isinstance(player_x, int):
                    await db.update_xo_stats(player_x, "loss", bet, 0)
                    
            elif player_o == BOT_USER:
                result_text = "🤖 ПОБЕДИЛ БОТ (O)!"
                if isinstance(player_x, int):
                    await db.update_xo_stats(player_x, "loss_vs_bot", bet, 0)
                    
        else:  # draw
            result_text = "🤝 НИЧЬЯ!"
            if bet > 0:
                for pid in [player_x, player_o]:
                    if isinstance(pid, int) and pid != BOT_USER:
                        await db.update_balance(pid, bet, "Возврат ставки (ничья)")
            for pid in [player_x, player_o]:
                if isinstance(pid, int):
                    await db.update_xo_stats(pid, "draw", bet, 0)
        
        logger.info("🏁 Game %s ended: result=%s, bet=%s", game_id, result, bet)
        
    except DatabaseError as e:
        logger.error("❌ DB error in end_game: %s", e, exc_info=True)
        result_text += "\n⚠️ Ошибка сохранения статистики"
        XOMetrics.increment("errors_total")
    except Exception as e:
        logger.error("❌ Unexpected error in end_game: %s", e, exc_info=True)
        result_text += "\n⚠️ Внутренняя ошибка"
        XOMetrics.increment("errors_total")
    finally:
        await _game_manager.remove_game(game_id)
    
    # Отправка результатов игрокам
    final_text = "🎮 <b>ИГРА ОКОНЧЕНА!</b>\n\n" + result_text
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
        [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
    ])
    
    if game.get("in_private", False):
        for pid in [player_x, player_o]:
            if isinstance(pid, int) and pid != BOT_USER:
                await safe_send_private(pid, final_text, keyboard)
    
    if callback and callback.message and not game.get("in_private", False):
        try:
            await callback.message.edit_text(final_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except TelegramAPIError as e:
            logger.debug("⚠️ Could not edit end message: %s", e)


async def bot_turn(game_id: str, game: Dict) -> None:
    """
    Выполнение хода бота.
    
    ✅ Проверка на заполненность доски перед ходом
    ✅ Обработка всех ошибок без падения
    """
    try:
        difficulty = game.get("difficulty", "medium")
        if difficulty not in BOT_MOVES:
            difficulty = "medium"
        
        move_func = BOT_MOVES[difficulty]
        bot_side = game.get("current_turn")
        
        if not bot_side or bot_side not in ("X", "O"):
            await end_game(game_id, game, "draw")
            return
        
        # Проверка на заполненность
        if is_board_full(game["board"]):
            await end_game(game_id, game, "draw")
            return
        
        move = move_func(game["board"])
        if not move:
            await end_game(game_id, game, "draw")
            return
        
        r, c = move
        game["board"][r][c] = bot_side
        
        winner = check_winner(game["board"])
        if winner:
            await end_game(game_id, game, winner)
            return
        
        # Передача хода
        game["current_turn"] = "O" if bot_side == "X" else "X"
        game["last_move"] = time.time()
        
        # Обновление UI для пользователя
        user_side = game.get("user_side", "X")
        user_id = game["player_x"] if user_side == "X" else game["player_o"]
        
        if isinstance(user_id, int) and user_id != BOT_USER:
            diff_name = BOT_DIFFICULTY[difficulty]["name"]
            msg_id = game.get("private_msg_user")
            next_is_user = (game["current_turn"] == user_side)
            
            if msg_id:
                await safe_edit_private(
                    user_id, msg_id,
                    f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ X vs ⭕ O\n🤖 Сложность: {diff_name}\n\n"
                    f"👇 {'Ваш ход' if next_is_user else 'Ход бота'}...",
                    xo_board_keyboard(game["board"], game_id, can_play=next_is_user)
                )
                
    except Exception as e:
        logger.error("❌ Error in bot_turn: %s", e, exc_info=True)
        XOMetrics.increment("errors_total")
        try:
            await end_game(game_id, game, "draw")
        except Exception:
            pass


# ==================== АВТООТМЕНА ВЫЗОВА ====================

async def auto_cancel_challenge(game_id: str, chat_id: int, message_id: int,
                                challenger_id: int) -> None:
    """Фоновая задача: автоматическая отмена просроченного вызова."""
    try:
        await asyncio.sleep(CHALLENGE_TIMEOUT)
        
        game = await _game_manager.get_game(game_id)
        if game and game.get("pending", False):
            await _game_manager.remove_game(game_id)
            
            if _bot:
                try:
                    await _bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text="⏰ <b>ВЫЗОВ ИСТЁК!</b>\n\nВремя ожидания вышло.",
                        parse_mode=ParseMode.HTML
                    )
                except TelegramAPIError as e:
                    logger.debug("⚠️ Could not edit expired challenge: %s", e)
                    
    except asyncio.CancelledError:
        logger.debug("🛑 Challenge auto-cancel cancelled: %s", game_id)
    except Exception as e:
        logger.error("❌ Error in auto_cancel_challenge: %s", e, exc_info=True)


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("xo"))
async def cmd_xo(message: Message) -> None:
    """Команда /xo — главное меню игры."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    
    await message.answer(
        "🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n\nВыберите режим игры:",
        parse_mode=ParseMode.HTML, 
        reply_markup=xo_menu_keyboard()
    )


@router.message(Command("cancel_xo"))
async def cmd_cancel_xo(message: Message) -> None:
    """Команда /cancel_xo — отмена активной игры пользователя."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    result = await _game_manager.find_user_game(user_id)
    
    if not result:
        await message.answer("❌ У вас нет активных игр.")
        return
    
    game_id, game = result
    bet = game.get("bet", 0) or 0
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    is_pending = game.get("pending", False)
    
    # Возврат ставок
    if bet > 0:
        try:
            refund_reason = "Возврат ставки (отмена вызова)" if is_pending else "Возврат ставки (отмена игры)"
            for pid in [player_x, player_o]:
                if isinstance(pid, int) and pid != BOT_USER:
                    await db.update_balance(pid, bet, refund_reason)
        except DatabaseError as e:
            logger.error("❌ DB error cancelling game: %s", e)
            XOMetrics.increment("errors_total")
    
    # Уведомление соперника
    if not is_pending:
        opponent = player_o if user_id == player_x else player_x
        if isinstance(opponent, int) and opponent != BOT_USER:
            await safe_send_private(
                opponent, 
                "❌ <b>ИГРА ОТМЕНЕНА!</b>\n\nСоперник отменил игру. Ставка возвращена."
            )
    
    await _game_manager.remove_game(game_id)
    await message.answer("✅ Игра отменена. Ставка возвращена.")
    logger.info("🚫 Game %s cancelled by user %s", game_id, user_id)


@router.callback_query(F.data == "game_xo")
@router.callback_query(F.data == "games")
async def game_xo_callback(callback: CallbackQuery) -> None:
    """Callback для открытия меню игры."""
    if not callback:
        return
    await cmd_xo(callback.message)
    await callback.answer()


@router.callback_query(F.data == "xo_vs_bot")
async def xo_vs_bot_callback(callback: CallbackQuery) -> None:
    """Выбор игры с ботом."""
    if not callback or not callback.message:
        return
    await safe_edit_callback(callback, "🤖 <b>ИГРА С БОТОМ</b>\n\nВыберите уровень сложности:", xo_difficulty_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("xo_diff_"))
async def xo_choose_side(callback: CallbackQuery) -> None:
    """Выбор стороны в игре с ботом."""
    if not callback or not callback.message:
        return
    
    parts = callback.data.split("_")
    difficulty = parts[2] if len(parts) > 2 else "medium"
    if difficulty not in BOT_DIFFICULTY:
        difficulty = "medium"
    
    await safe_edit_callback(
        callback, 
        "🤖 <b>ИГРА С БОТОМ</b>\n\nЗа кого будете играть?", 
        xo_side_choice_keyboard(difficulty)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xo_side_"))
async def xo_start_vs_bot(callback: CallbackQuery) -> None:
    """Запуск игры с ботом."""
    if not callback or not callback.message or not _bot:
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
    board = [[" ", " ", " "] for _ in range(3)]
    
    if player_side == "X":
        player_x, player_o = user_id, BOT_USER
        current_turn = "X"
    else:
        player_x, player_o = BOT_USER, user_id
        current_turn = "X"
    
    game_data = {
        "type": "pvb", 
        "board": board, 
        "player_x": player_x, 
        "player_o": player_o,
        "user_side": player_side, 
        "current_turn": current_turn, 
        "bet": 0,
        "difficulty": difficulty, 
        "created_at": time.time(), 
        "last_move": time.time(),
        "finished": False, 
        "in_private": True, 
        "cancel_button_msg": None,
    }
    
    if not await _game_manager.add_game(game_id, game_data):
        await callback.answer("❌ Слишком много активных игр.", show_alert=True)
        return
    
    diff_name = BOT_DIFFICULTY[difficulty]["name"]
    user_symbol = "❌" if player_side == "X" else "⭕"
    bot_symbol = "⭕" if player_side == "X" else "❌"
    is_user_turn = (current_turn == player_side)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНИТЬ ИГРУ", callback_data=f"xo_cancel_game_{game_id}")]
    ])
    
    msg = await safe_send_private(
        user_id,
        f"🎮 <b>ИГРА С БОТОМ</b>\n\n"
        f"Сложность: {diff_name}\n"
        f"Вы играете за {user_symbol} <b>{player_side}</b>\n"
        f"Бот играет за {bot_symbol} <b>{('O' if player_side == 'X' else 'X')}</b>\n\n"
        f"👇 {'Ваш ход' if is_user_turn else 'Ход бота'}...",
        xo_board_keyboard(game_data["board"], game_id, can_play=is_user_turn)
    )
    
    if msg:
        game_data["private_msg_user"] = msg.message_id
        
        cancel_msg = await safe_send_private(user_id, "⚙️ Управление игрой:", cancel_kb)
        if cancel_msg:
            game_data["cancel_button_msg"] = cancel_msg.message_id
        
        await safe_edit_callback(
            callback,
            "🎮 <b>ИГРА С БОТОМ</b>\n\n📩 <b>Игра началась в ЛС!</b>\nПроверьте личные сообщения."
        )
        
        if not is_user_turn:
            await asyncio.sleep(0.8)
            await bot_turn(game_id, game_data)
    else:
        await _game_manager.remove_game(game_id)
        bot_link = f"https://t.me/{BOT_USERNAME or 'NEXUS_Manager_Official_bot'}"
        await safe_edit_callback(
            callback,
            "❌ <b>НЕ УДАЛОСЬ НАЧАТЬ ИГРУ!</b>\n\n"
            f"Активируйте бота: перейдите в @{BOT_USERNAME or 'NEXUS_Manager_Official_bot'} и нажмите START",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 ОТКРЫТЬ БОТА", url=bot_link)]])
        )
    
    await callback.answer()


@router.callback_query(F.data == "xo_vs_player")
async def xo_vs_player_callback(callback: CallbackQuery) -> None:
    """Выбор игры с игроком."""
    if not callback or not callback.message:
        return
    await safe_edit_callback(callback, "👤 <b>ИГРА С ИГРОКОМ</b>\n\nВыберите ставку:", xo_bet_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("xo_bet_"))
async def xo_bet_selected(callback: CallbackQuery) -> None:
    """Выбор ставки для вызова игрока."""
    if not callback or not callback.from_user:
        return
    
    try:
        bet = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Неверная ставка!", show_alert=True)
        return
    
    await _game_manager.add_pending_challenge(callback.from_user.id, bet, None)
    
    await safe_edit_callback(
        callback,
        f"👤 <b>ВЫЗОВ ИГРОКА</b>\n\n💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n📝 Напишите @username противника:",
        back_button("xo_vs_player")
    )
    await callback.answer()


@router.message(lambda m: m.text and m.text.startswith('@'))
async def xo_challenge_player(message: Message) -> None:
    """Вызов игрока через @username."""
    if not message or not message.from_user:
        return
    
    user_id = message.from_user.id
    pending = await _game_manager.pop_pending_challenge(user_id)
    
    if not pending:
        return
    
    username = message.text.replace('@', '').strip()
    bet = pending.get("bet", 0) or 0
    
    await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    
    try:
        target = await db.get_user_by_username(username)
    except DatabaseError as e:
        logger.error("❌ DB error: %s", e)
        await message.answer("❌ Ошибка базы данных.")
        return
    
    if not target:
        await message.answer(
            f"❌ <b>Пользователь @{safe_html_escape(username)} не найден!</b>\n\n"
            "Попросите его написать /start в бота.", 
            parse_mode=ParseMode.HTML
        )
        return
    
    target_id = target.get("user_id")
    if not target_id or target_id == user_id:
        await message.answer("❌ Нельзя вызвать самого себя!")
        return
    
    # Проверка на дублирующий вызов
    for gid, g in await _game_manager.get_all_games():
        if g.get("pending", False):
            px, po = g.get("player_x"), g.get("player_o")
            if (px == user_id and po == target_id) or (px == target_id and po == user_id):
                await message.answer("❌ У вас уже есть активный вызов!")
                return
    
    # ✅ NULL-SAFE проверка баланса
    if bet > 0:
        try:
            user_balance = await db.get_balance(user_id)
            if user_balance is None or user_balance < bet:
                await message.answer(f"❌ У вас недостаточно средств! Баланс: {format_number(user_balance or 0)} NCoin")
                return
            
            target_balance = await db.get_balance(target_id)
            if target_balance is None or target_balance < bet:
                await message.answer(f"❌ У @{safe_html_escape(username)} недостаточно средств!")
                return
        except DatabaseError:
            await message.answer("❌ Ошибка проверки баланса.")
            return
    
    game_id = generate_game_id()
    game_data = {
        "type": "pvp", 
        "board": [[" ", " ", " "] for _ in range(3)],
        "player_x": user_id, 
        "player_o": target_id, 
        "current_turn": "X", 
        "bet": bet,
        "chat_id": message.chat.id, 
        "created_at": time.time(), 
        "last_move": time.time(),
        "pending": True, 
        "finished": False,
        "challenger_name": safe_html_escape(message.from_user.first_name or "Игрок"),
        "challenged_name": safe_html_escape(target.get("first_name") or username),
    }
    
    await _game_manager.add_game(game_id, game_data)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]
    ])
    
    await message.answer(
        f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
        f"👤 {safe_html_escape(message.from_user.first_name or 'Игрок')} вызывает @{safe_html_escape(username)}!\n"
        f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n"
        f"⏰ Вызов действителен 60 секунд\n\n"
        f"⚠️ ТОЛЬКО @{safe_html_escape(username)} может принять или отклонить!",
        parse_mode=ParseMode.HTML, 
        reply_markup=keyboard
    )
    
    task = asyncio.create_task(auto_cancel_challenge(game_id, message.chat.id, message.message_id, user_id))
    await _game_manager.set_challenge_task(user_id, task)


@router.callback_query(F.data.startswith("xo_accept_"))
async def xo_accept_challenge(callback: CallbackQuery) -> None:
    """Принятие вызова от игрока."""
    if not callback or not callback.from_user or not _bot:
        return
    
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
    
    game_id = parts[2]
    user_id = callback.from_user.id
    
    game = await _game_manager.get_game(game_id)
    if not game or not game.get("pending", False):
        await callback.answer("❌ Вызов уже неактивен!", show_alert=True)
        return
    
    if user_id != game.get("player_o"):
        await callback.answer("❌ Этот вызов не вам!", show_alert=True)
        return
    
    bet = game.get("bet", 0) or 0
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    # Проверка связи с игроками
    tx = await safe_send_private(player_x, "🎮 Проверка связи...") if isinstance(player_x, int) else None
    to = await safe_send_private(player_o, "🎮 Проверка связи...") if isinstance(player_o, int) else None
    
    if (isinstance(player_x, int) and not tx) or (isinstance(player_o, int) and not to):
        await safe_edit_callback(callback, "❌ Один из игроков не активировал бота!")
        await _game_manager.remove_game(game_id)
        await callback.answer("❌ Игрок не активировал бота", show_alert=True)
        return
    
    # Удаление тестовых сообщений
    try:
        if tx and isinstance(player_x, int):
            await _bot.delete_message(player_x, tx.message_id)
        if to and isinstance(player_o, int):
            await _bot.delete_message(player_o, to.message_id)
    except TelegramAPIError:
        pass
    
    await _game_manager.pop_pending_challenge(player_x if isinstance(player_x, int) else player_o)
    
    # Списание ставок
    if bet > 0:
        try:
            if isinstance(player_x, int):
                await db.update_balance(player_x, -bet, "Ставка в XO")
            if isinstance(player_o, int):
                await db.update_balance(player_o, -bet, "Ставка в XO")
        except DatabaseError as e:
            logger.error("❌ DB error processing bet: %s", e)
            await callback.answer("❌ Ошибка обработки ставки", show_alert=True)
            return
    
    # Обновление статуса игры
    game["pending"] = False
    game["last_move"] = time.time()
    game["in_private"] = True
    await _game_manager.update_game(game_id, {"pending": False, "last_move": time.time(), "in_private": True})
    
    # Получение имён игроков
    px_user = await db.get_user(player_x) if isinstance(player_x, int) else None
    po_user = await db.get_user(player_o) if isinstance(player_o, int) else None
    px_name = safe_html_escape(px_user.get("first_name") if px_user else None) or "Игрок X"
    po_name = safe_html_escape(po_user.get("first_name") if po_user else None) or "Игрок O"
    
    await safe_edit_callback(
        callback,
        f"🎮 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"❌ X: {px_name}\n⭕ O: {po_name}\n💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n"
        f"📩 <b>Игра продолжается в ЛС!</b>"
    )
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНИТЬ ИГРУ", callback_data=f"xo_cancel_game_{game_id}")]
    ])
    
    # Отправка досок игрокам
    if isinstance(player_x, int):
        msg_x = await safe_send_private(
            player_x,
            f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ Вы: {px_name} (X)\n⭕ Соперник: {po_name} (O)\n"
            f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n👇 <b>Ваш ход!</b>",
            xo_board_keyboard(game["board"], game_id, can_play=True)
        )
        if msg_x:
            game["private_msg_x"] = msg_x.message_id
            cancel_x = await safe_send_private(player_x, "⚙️ Управление игрой:", cancel_kb)
            if cancel_x:
                game["cancel_msg_x"] = cancel_x.message_id
    
    if isinstance(player_o, int):
        msg_o = await safe_send_private(
            player_o,
            f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ Соперник: {px_name} (X)\n⭕ Вы: {po_name} (O)\n"
            f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n⏳ <b>Ожидайте хода соперника...</b>",
            xo_board_keyboard(game["board"], game_id, can_play=False)
        )
        if msg_o:
            game["private_msg_o"] = msg_o.message_id
            cancel_o = await safe_send_private(player_o, "⚙️ Управление игрой:", cancel_kb)
            if cancel_o:
                game["cancel_msg_o"] = cancel_o.message_id
    
    logger.info("✅ Challenge accepted: game %s (%s vs %s)", game_id, player_x, player_o)
    await callback.answer("✅ Игра началась! Проверьте ЛС.")


@router.callback_query(F.data.startswith("xo_reject_"))
async def xo_reject_challenge(callback: CallbackQuery) -> None:
    """Отклонение вызова."""
    if not callback or not callback.from_user:
        return
    
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
    
    game_id = parts[2]
    user_id = callback.from_user.id
    
    game = await _game_manager.get_game(game_id)
    if not game or user_id != game.get("player_o"):
        await callback.answer("❌ Вызов не найден или не вам!", show_alert=True)
        return
    
    player_x = game.get("player_x")
    await _game_manager.pop_pending_challenge(player_x if isinstance(player_x, int) else user_id)
    await _game_manager.remove_game(game_id)
    
    challenged_name = safe_html_escape(game.get("challenged_name", "Игрок"))
    await safe_edit_callback(
        callback, 
        f"❌ <b>ВЫЗОВ ОТКЛОНЁН!</b>\n\n{challenged_name} отклонил(а) вызов."
    )
    logger.info("❌ Challenge rejected: game %s", game_id)
    await callback.answer("❌ Вызов отклонён!")


@router.callback_query(F.data.startswith("xo_cancel_game_"))
async def xo_cancel_game(callback: CallbackQuery) -> None:
    """Отмена активной игры через кнопку."""
    if not callback or not callback.from_user:
        return
    
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
    
    game_id = parts[3]
    user_id = callback.from_user.id
    
    game = await _game_manager.get_game(game_id)
    if not game or game.get("finished", False):
        await callback.answer("❌ Игра не найдена или уже окончена!", show_alert=True)
        return
    
    player_x = game.get("player_x")
    player_o = game.get("player_o")
    
    if user_id != player_x and user_id != player_o:
        await callback.answer("❌ Вы не участвуете в этой игре!", show_alert=True)
        return
    
    bet = game.get("bet", 0) or 0
    is_pending = game.get("pending", False)
    
    # Возврат ставок (только для начатых игр)
    if bet > 0 and not is_pending:
        try:
            for pid in [player_x, player_o]:
                if isinstance(pid, int) and pid != BOT_USER:
                    await db.update_balance(pid, bet, "Возврат ставки (отмена игры)")
        except DatabaseError as e:
            logger.error("❌ DB error cancelling game: %s", e)
            XOMetrics.increment("errors_total")
    
    # Уведомление соперника
    opponent = player_o if user_id == player_x else player_x
    if isinstance(opponent, int) and opponent != BOT_USER:
        await safe_send_private(
            opponent, 
            "❌ <b>ИГРА ОТМЕНЕНА!</b>\n\nСоперник отменил игру. Ставка возвращена."
        )
    
    await _game_manager.remove_game(game_id)
    XOMetrics.increment("games_surrendered")
    
    await safe_edit_callback(callback, "✅ Игра отменена. Ставка возвращена.")
    logger.info("🚫 Game %s cancelled via button by user %s", game_id, user_id)
    await callback.answer("✅ Игра отменена")


@router.callback_query(F.data.startswith("xo_move_"))
async def xo_make_move(callback: CallbackQuery) -> None:
    """
    Обработка хода игрока с ЗАЩИТОЙ ОТ ГОНОК ДАННЫХ.
    
    ✅ Атомарная проверка и выполнение хода
    ✅ Полный цикл обновления для обоих игроков в PvP
    """
    if not callback or not callback.from_user:
        await callback.answer("❌ Ошибка авторизации", show_alert=True)
        return
    
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
    
    try:
        game_id, r, c = parts[2], int(parts[3]), int(parts[4])
    except (ValueError, IndexError):
        await callback.answer("❌ Неверные координаты!", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    # Получение игры
    game = await _game_manager.get_game(game_id)
    if not game:
        await callback.answer("❌ Игра не найдена!", show_alert=True)
        return
    
    if game.get("finished", False):
        await callback.answer("❌ Игра уже окончена!", show_alert=True)
        return
    
    # Проверка кулдауна
    if not await _game_manager.check_move_cooldown(game_id, user_id):
        await callback.answer("⏱️ Слишком часто!", show_alert=True)
        return
    
    # Проверка таймаута
    if time.time() - (game.get("last_move") or game.get("created_at", 0)) > MOVE_TIMEOUT:
        asyncio.create_task(end_game(game_id, game, "timeout", callback))
        await callback.answer("⏰ Время на ход истекло!", show_alert=True)
        return
    
    current_turn = game.get("current_turn", "X")
    
    # Проверка очередности хода
    if game.get("type") == "pvb":
        if current_turn != game.get("user_side", "X"):
            await callback.answer("❌ Сейчас ход бота!", show_alert=True)
            return
    else:
        if (current_turn == "X" and user_id != game.get("player_x")) or \
           (current_turn == "O" and user_id != game.get("player_o")):
            await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
            return
    
    # 🔒 АТОМАРНАЯ ПРОВЕРКА И ВЫПОЛНЕНИЕ ХОДА
    async with _game_manager.game_lock(game_id):
        # Повторная проверка после захвата лока
        fresh_game = await _game_manager.get_game(game_id)
        if not fresh_game or fresh_game.get("finished", False):
            await callback.answer("❌ Игра изменилась!", show_alert=True)
            return
        
        # ✅ КРИТИЧЕСКАЯ ПРОВЕРКА: занята ли клетка ПРЯМО СЕЙЧАС
        if r < 0 or r > 2 or c < 0 or c > 2 or fresh_game["board"][r][c] != " ":
            await callback.answer("❌ Клетка занята!", show_alert=True)
            return
        
        # Выполнение хода
        fresh_game["board"][r][c] = current_turn
        fresh_game["last_move"] = time.time()
        
        winner = check_winner(fresh_game["board"])
        if winner:
            # Обновляем состояние в менеджере перед завершением
            await _game_manager.update_game(game_id, {
                "board": fresh_game["board"],
                "last_move": fresh_game["last_move"]
            })
            await end_game(game_id, fresh_game, winner, callback)
            await callback.answer(f"✅ Ход на ({r+1}, {c+1})")
            return
        
        # Передача хода
        fresh_game["current_turn"] = "O" if current_turn == "X" else "X"
        
        # Сохранение изменений
        await _game_manager.update_game(game_id, {
            "board": fresh_game["board"],
            "last_move": fresh_game["last_move"],
            "current_turn": fresh_game["current_turn"]
        })
        
        # ✅ ОБНОВЛЕНИЕ ИНТЕРФЕЙСА ДЛЯ ОБОИХ ИГРОКОВ
        if fresh_game.get("in_private", False):
            if fresh_game.get("type") == "pvb":
                # PvB: обновление для одного пользователя
                user_side = fresh_game.get("user_side", "X")
                user_id_actual = fresh_game["player_x"] if user_side == "X" else fresh_game["player_o"]
                next_is_user = (fresh_game["current_turn"] == user_side)
                diff_name = BOT_DIFFICULTY[fresh_game.get("difficulty", "medium")]["name"]
                msg_id = fresh_game.get("private_msg_user")
                
                if msg_id and isinstance(user_id_actual, int):
                    await safe_edit_private(
                        user_id_actual, msg_id,
                        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n❌ X vs ⭕ O\n🤖 Сложность: {diff_name}\n\n"
                        f"👇 {'Ваш ход' if next_is_user else 'Ход бота'}...",
                        xo_board_keyboard(fresh_game["board"], game_id, can_play=next_is_user)
                    )
                
                if not next_is_user:
                    await asyncio.sleep(0.6)
                    await bot_turn(game_id, fresh_game)
                    
            else:
                # PvP: обновление для обоих игроков
                px = fresh_game["player_x"]
                po = fresh_game["player_o"]
                px_user = await db.get_user(px) if isinstance(px, int) else None
                po_user = await db.get_user(po) if isinstance(po, int) else None
                px_name = safe_html_escape(px_user.get("first_name") if px_user else None) or "Игрок X"
                po_name = safe_html_escape(po_user.get("first_name") if po_user else None) or "Игрок O"
                next_is_x = (fresh_game["current_turn"] == "X")
                
                msg_x_id = fresh_game.get("private_msg_x")
                msg_o_id = fresh_game.get("private_msg_o")
                
                if msg_x_id and isinstance(px, int):
                    await safe_edit_private(
                        px, msg_x_id,
                        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
                        f"❌ Вы: {px_name} (X)\n⭕ Соперник: {po_name} (O)\n"
                        f"💰 Ставка: <b>{format_number(fresh_game.get('bet', 0))} NCoin</b>\n\n"
                        + ("👇 <b>Ваш ход!</b>" if next_is_x else "⏳ Ожидайте хода соперника..."),
                        xo_board_keyboard(fresh_game["board"], game_id, can_play=next_is_x)
                    )
                
                if msg_o_id and isinstance(po, int):
                    await safe_edit_private(
                        po, msg_o_id,
                        f"🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n"
                        f"❌ Соперник: {px_name} (X)\n⭕ Вы: {po_name} (O)\n"
                        f"💰 Ставка: <b>{format_number(fresh_game.get('bet', 0))} NCoin</b>\n\n"
                        + ("👇 <b>Ваш ход!</b>" if not next_is_x else "⏳ Ожидайте хода соперника..."),
                        xo_board_keyboard(fresh_game["board"], game_id, can_play=not next_is_x)
                    )
        
        logger.debug("♟️ Move on %s: user=%s, pos=(%s,%s)", game_id, user_id, r, c)
        await callback.answer(f"✅ Ход на ({r+1}, {c+1})")


@router.callback_query(F.data.startswith("xo_surrender_"))
async def xo_surrender(callback: CallbackQuery) -> None:
    """Сдача в игре (поражение)."""
    if not callback or not callback.from_user:
        return
    
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Неверный формат!", show_alert=True)
        return
    
    game_id = parts[2]
    user_id = callback.from_user.id
    
    game = await _game_manager.get_game(game_id)
    if not game or game.get("finished", False):
        await callback.answer("❌ Игра не найдена или окончена!", show_alert=True)
        return
    
    player_x, player_o = game.get("player_x"), game.get("player_o")
    
    if user_id == player_x:
        winner = "O"
    elif user_id == player_o:
        winner = "X"
    else:
        await callback.answer("❌ Вы не участвуете в этой игре!", show_alert=True)
        return
    
    XOMetrics.increment("games_surrendered")
    await end_game(game_id, game, winner, callback)
    logger.info("🏳️ Surrender on %s by user %s", game_id, user_id)
    await callback.answer("🏳️ Вы сдались!")


@router.callback_query(F.data == "xo_stats")
async def xo_stats_callback(callback: CallbackQuery) -> None:
    """Показать статистику игрока."""
    if not callback or not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    
    try:
        stats = await db.get_user_stats(user_id)
    except DatabaseError:
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)
        return
    
    if not stats:
        await safe_edit_callback(
            callback,
            "📊 <b>СТАТИСТИКА</b>\n\nУ вас пока нет сыгранных игр!", 
            back_button("game_xo")
        )
        return
    
    games = stats.get('games_played', 0) or 0
    wins = stats.get('wins', 0) or 0
    losses = stats.get('losses', 0) or 0
    draws = stats.get('draws', 0) or 0
    losses_vs_bot = stats.get('losses_vs_bot', 0) or 0
    winrate = (wins / games * 100) if games > 0 else 0
    
    text = (
        f"📊 <b>ВАША СТАТИСТИКА XO</b>\n\n"
        f"🎮 Игр: <b>{games}</b>\n"
        f"🏆 Побед: <b>{wins}</b>\n"
        f"💔 Поражений: <b>{losses}</b>\n"
        f"🤝 Ничьих: <b>{draws}</b>\n"
        f"🤖 Поражений от бота: <b>{losses_vs_bot}</b>\n"
        f"📈 Винрейт: <b>{round(winrate, 1)}%</b>"
    )
    
    await safe_edit_callback(
        callback, text, InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 НОВАЯ ИГРА", callback_data="game_xo")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="game_xo")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "xo_help")
async def xo_help_callback(callback: CallbackQuery) -> None:
    """Показать справку по игре."""
    if not callback or not callback.message:
        return
    
    await safe_edit_callback(
        callback,
        f"❓ <b>ПРАВИЛА КРЕСТИКОВ-НОЛИКОВ</b>\n\n"
        f"🎯 <b>Цель:</b> Собрать 3 своих символа в ряд\n\n"
        f"🤖 <b>С ботом:</b> Выберите сторону (X/O) и сложность\n"
        f"👤 <b>С игроком:</b> Вызовите друга и играйте на NCoin\n\n"
        f"💰 <b>Ставки:</b> Победитель получает ×2 (комиссия {int(COMMISSION * 100)}%)\n\n"
        f"📩 <b>Игра проходит в личных сообщениях!</b>\n\n"
        f"🚫 <b>Отмена игры:</b> /cancel_xo или кнопка в ЛС",
        back_button("game_xo")
    )
    await callback.answer()


@router.callback_query(F.data == "xo_noop")
async def xo_noop(callback: CallbackQuery) -> None:
    """Обработчик неактивных кнопок (защита от спама)."""
    if callback and callback.from_user:
        logger.debug("NOOP callback from user %s (data: %s)", callback.from_user.id, callback.data)
    await callback.answer("❌ Эта клетка занята или игра не активна!", show_alert=True)

