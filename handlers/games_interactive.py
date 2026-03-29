"""
Интерактивные игры с кнопками
Слот-машина, дуэли, рулетка, камень-ножницы-бумага
С интеграцией AI (OpenRouter) и полной статистикой
"""

import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import json

from aiogram import F, Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, 
    InlineKeyboardButton, Chat, User
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from config import (
    BOT_TOKEN, MIN_BET, MAX_BET, DUEL_TIMEOUT, 
    RATE_LIMIT_GAMES, MAX_BET_CONFIRMATION, ADMIN_IDS,
    DATABASE_PATH, SECRET_KEY, LOG_LEVEL, LOG_FILE
)
from database import db
from utils.rate_limiter import rate_limit
from utils.logger import logger

# ========== Удалён импорт utils.security — не используется ==========
# from utils.security import verify_signature, generate_signature

# Prometheus metrics - ИСПРАВЛЕННАЯ ВЕРСИЯ
try:
    from prometheus_client import Counter, Histogram, Gauge
    
    # Game metrics
    GAMES_PLAYED = Counter(
        'nexus_games_played_total',
        'Total games played',
        ['game_type']
    )
    
    GAMES_WON = Counter(
        'nexus_games_won_total',
        'Total games won',
        ['game_type']
    )
    
    BETS_PLACED = Counter(
        'nexus_bets_placed_total',
        'Total bets placed',
        ['game_type']
    )
    
    BETS_WON = Counter(
        'nexus_bets_won_total',
        'Total bets won',
        ['game_type']
    )
    
    # API metrics
    API_REQUESTS = Counter(
        'nexus_api_requests_total',
        'Total API requests',
        ['endpoint', 'status']
    )
    
    API_ERRORS = Counter(
        'nexus_api_errors_total',
        'Total API errors',
        ['error_type']
    )
    
    # User metrics
    ACTIVE_USERS = Gauge(
        'nexus_active_users',
        'Currently active users'
    )
    
    TOTAL_USERS = Gauge(
        'nexus_total_users',
        'Total registered users'
    )
    
    # Performance metrics
    GAME_DURATION = Histogram(
        'nexus_game_duration_seconds',
        'Game duration in seconds',
        ['game_type']
    )
    
    # AI metrics
    AI_REQUESTS = Counter(
        'nexus_ai_requests_total',
        'Total AI requests',
        ['model', 'status']
    )
    
    AI_TOKENS = Counter(
        'nexus_ai_tokens_total',
        'Total AI tokens used',
        ['type']
    )
    
except ImportError:
    # Fallback if prometheus_client not installed
    class DummyMetric:
        def labels(self, *args, **kwargs):
            return self
        def inc(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass
    
    GAMES_PLAYED = DummyMetric()
    GAMES_WON = DummyMetric()
    BETS_PLACED = DummyMetric()
    BETS_WON = DummyMetric()
    API_REQUESTS = DummyMetric()
    API_ERRORS = DummyMetric()
    ACTIVE_USERS = DummyMetric()
    TOTAL_USERS = DummyMetric()
    GAME_DURATION = DummyMetric()
    AI_REQUESTS = DummyMetric()
    AI_TOKENS = DummyMetric()
    
    logger.warning("prometheus_client not installed, metrics disabled")

# AI Integration
try:
    import aiohttp
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    AI_ENABLED = bool(OPENROUTER_API_KEY)
except ImportError:
    AI_ENABLED = False
    logger.warning("aiohttp not installed, AI features disabled")

router = Router()


# ========== FSM States ==========

class DuelState(StatesGroup):
    waiting_confirmation = State()
    waiting_bet = State()


class RouletteState(StatesGroup):
    waiting_bet = State()
    waiting_color = State()


class SlotState(StatesGroup):
    waiting_bet = State()
    spinning = State()


class RPSState(StatesGroup):
    waiting_choice = State()
    waiting_bet = State()


# ========== Helper Functions ==========

async def update_user_balance(user_id: int, amount: int, operation: str, description: str = "") -> bool:
    """Update user balance and log transaction"""
    try:
        if operation == "add":
            await db.add_balance(user_id, amount, description)
        elif operation == "subtract":
            if not await db.subtract_balance(user_id, amount, description):
                return False
        return True
    except Exception as e:
        logger.error(f"Balance update error for user {user_id}: {e}")
        API_ERRORS.labels(error_type="balance_update").inc()
        return False


async def get_user_balance(user_id: int) -> int:
    """Get user balance"""
    try:
        return await db.get_balance(user_id)
    except Exception as e:
        logger.error(f"Get balance error for user {user_id}: {e}")
        API_ERRORS.labels(error_type="balance_get").inc()
        return 0


async def log_game_history(user_id: int, game_type: str, bet: int, result: str, win_amount: int = 0, details: dict = None):
    """Log game history to database"""
    try:
        await db.add_game_history(user_id, game_type, bet, result, win_amount, details)
    except Exception as e:
        logger.error(f"Game history error for user {user_id}: {e}")
        API_ERRORS.labels(error_type="history_log").inc()


async def get_user_stats(user_id: int) -> dict:
    """Get user statistics"""
    try:
        return await db.get_user_stats(user_id)
    except Exception as e:
        logger.error(f"Get stats error for user {user_id}: {e}")
        return {"total_games": 0, "total_wins": 0, "total_bets": 0, "total_won": 0}


async def get_active_games_count() -> int:
    """Get count of active games"""
    try:
        return await db.get_active_games_count()
    except Exception as e:
        return 0


# ========== AI Integration ==========

async def ai_generate_response(prompt: str, context: str = "") -> Optional[str]:
    """Generate AI response using OpenRouter API"""
    if not AI_ENABLED:
        return None
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": f"Ты игровой ассистент в Telegram боте. {context}"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.7
            }
            
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    AI_REQUESTS.labels(model="gpt-3.5-turbo", status="success").inc()
                    if "usage" in result:
                        AI_TOKENS.labels(type="prompt").inc(result["usage"].get("prompt_tokens", 0))
                        AI_TOKENS.labels(type="completion").inc(result["usage"].get("completion_tokens", 0))
                    return result["choices"][0]["message"]["content"]
                else:
                    AI_REQUESTS.labels(model="gpt-3.5-turbo", status="error").inc()
                    API_ERRORS.labels(error_type="ai_api").inc()
                    logger.error(f"AI API error: {response.status}")
                    return None
                    
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        API_ERRORS.labels(error_type="ai_exception").inc()
        return None


async def get_ai_game_comment(game_type: str, result: str, amount: int) -> Optional[str]:
    """Get AI comment for game result"""
    if not AI_ENABLED:
        return None
    
    prompts = {
        "slot": f"Игрок сыграл в слот-машину и {result} {amount} рублей. Напиши короткое эмоциональное сообщение (1-2 предложения)",
        "duel": f"Игрок участвовал в дуэли и {result} {amount} рублей. Напиши короткое эпичное сообщение о дуэли",
        "roulette": f"Игрок играл в рулетку и {result} {amount} рублей. Напиши короткое сообщение о рулетке",
        "rps": f"Игрок играл в камень-ножницы-бумага и {result} {amount} рублей. Напиши короткое забавное сообщение"
    }
    
    return await ai_generate_response(prompts.get(game_type, ""), "Будь эмоциональным и поддерживающим")


# ========== Slot Machine ==========

@router.message(Command("slot"))
@rate_limit(limit=RATE_LIMIT_GAMES, key="slot")
async def cmd_slot(message: Message, state: FSMContext):
    """Slot machine game"""
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    stats = await get_user_stats(user_id)
    
    # Update active users metric
    ACTIVE_USERS.inc()
    
    # Available bet options
    bet_options = [MIN_BET, MIN_BET * 5, MIN_BET * 10, MIN_BET * 25, MIN_BET * 50]
    bet_options = [b for b in bet_options if b <= min(MAX_BET, balance) and b >= MIN_BET]
    
    if not bet_options:
        await message.answer(
            f"🎰 *Слот-машина*\n\n"
            f"❌ Недостаточно средств для минимальной ставки!\n"
            f"💰 Ваш баланс: {balance} ₽\n"
            f"🎲 Минимальная ставка: {MIN_BET} ₽",
            parse_mode="Markdown"
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for bet in bet_options:
        builder.add(InlineKeyboardButton(
            text=f"🎲 {bet} ₽",
            callback_data=f"slot_bet_{bet}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🎲 Случайная ставка",
        callback_data="slot_random"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 Статистика",
        callback_data="slot_stats"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="slot_cancel"
    ))
    builder.adjust(2)
    
    await message.answer(
        f"🎰 *Слот-машина*\n\n"
        f"💰 Ваш баланс: {balance} ₽\n"
        f"📊 Игр сыграно: {stats.get('total_games', 0)}\n"
        f"🏆 Побед: {stats.get('total_wins', 0)}\n\n"
        f"Выберите размер ставки:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SlotState.waiting_bet)


@router.callback_query(SlotState.waiting_bet, F.data.startswith("slot_bet_"))
async def slot_play(callback: CallbackQuery, state: FSMContext):
    """Play slot machine"""
    start_time = datetime.now()
    bet = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if bet > MAX_BET:
        await callback.answer(f"❌ Максимальная ставка: {MAX_BET} ₽", show_alert=True)
        return
    
    balance = await get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        await state.clear()
        return
    
    # Deduct bet
    if not await update_user_balance(user_id, bet, "subtract", f"Ставка в слотах: {bet} ₽"):
        await callback.answer("❌ Ошибка списания средств", show_alert=True)
        await state.clear()
        return
    
    # Slot machine logic with weighted probabilities
    symbols = ["🍒", "🍋", "🍊", "🍉", "🔔", "💎", "7️⃣", "🎰", "⭐", "💎"]
    weights = [0.2, 0.2, 0.15, 0.1, 0.1, 0.08, 0.05, 0.05, 0.04, 0.03]
    
    reels = [random.choices(symbols, weights=weights)[0] for _ in range(3)]
    
    # Win combinations with multipliers
    win_multiplier = 0
    special_message = ""
    
    if reels[0] == reels[1] == reels[2]:
        # Three of a kind
        multipliers = {
            "7️⃣": 15, "🎰": 12, "💎": 8, "⭐": 6, "🔔": 5,
            "🍉": 4, "🍊": 3, "🍋": 2, "🍒": 2
        }
        win_multiplier = multipliers.get(reels[0], 3)
        special_message = f"🎉 *ТРИ {reels[0]}!* 🎉\n"
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        # Two of a kind
        win_multiplier = 1
        special_message = "👍 *Пара!* 👍\n"
    elif "💎" in reels and "7️⃣" in reels:
        # Special combo
        win_multiplier = 3
        special_message = "💎✨ *Джекпот комбо!* ✨💎\n"
    
    win_amount = bet * win_multiplier if win_multiplier > 0 else 0
    
    # Animate reels effect
    await callback.answer("🎰 Крутим барабаны...")
    
    result_text = f"🎰 *Слот-машина*\n\n"
    result_text += f"{' │ '.join(reels)}\n\n"
    result_text += special_message
    
    if win_amount > 0:
        await update_user_balance(user_id, win_amount, "add", f"Выигрыш в слотах: {win_amount} ₽")
        result_text += f"🎉 *ПОБЕДА!* 🎉\n"
        result_text += f"💰 Выигрыш: {win_amount} ₽\n"
        result_text += f"✨ Множитель: x{win_multiplier}\n"
        GAMES_WON.labels(game_type="slot").inc()
        BETS_WON.labels(game_type="slot").inc()
    else:
        result_text += f"😢 *ПРОИГРЫШ*\n"
        result_text += f"💸 Потеряно: {bet} ₽\n"
    
    result_text += f"\n💰 Новый баланс: {await get_user_balance(user_id)} ₽"
    
    # Get AI comment
    ai_comment = await get_ai_game_comment("slot", "выиграл" if win_amount > 0 else "проиграл", win_amount or bet)
    if ai_comment:
        result_text += f"\n\n🤖 *AI совет:* {ai_comment}"
    
    # Log history
    result_status = "win" if win_amount > 0 else "loss"
    details = {"reels": reels, "multiplier": win_multiplier}
    await log_game_history(user_id, "slot", bet, result_status, win_amount, details)
    
    # Update metrics
    GAMES_PLAYED.labels(game_type="slot").inc()
    BETS_PLACED.labels(game_type="slot").inc()
    duration = (datetime.now() - start_time).total_seconds()
    GAME_DURATION.labels(game_type="slot").observe(duration)
    
    await callback.message.edit_text(result_text, parse_mode="Markdown")
    await callback.answer()
    await state.clear()


@router.callback_query(SlotState.waiting_bet, F.data == "slot_random")
async def slot_random_bet(callback: CallbackQuery, state: FSMContext):
    """Play slot with random bet"""
    user_id = callback.from_user.id
    balance = await get_user_balance(user_id)
    
    if balance < MIN_BET:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return
    
    max_possible_bet = min(MAX_BET, balance)
    bet = random.randint(MIN_BET, max_possible_bet)
    
    # Process the bet
    await slot_play(callback, state)
    # Need to override the bet value
    callback.data = f"slot_bet_{bet}"


@router.callback_query(SlotState.waiting_bet, F.data == "slot_stats")
async def slot_stats(callback: CallbackQuery, state: FSMContext):
    """Show slot statistics"""
    user_id = callback.from_user.id
    stats = await get_user_stats(user_id)
    
    text = f"📊 *Ваша статистика в слотах*\n\n"
    text += f"🎮 Всего игр: {stats.get('total_games', 0)}\n"
    text += f"🏆 Побед: {stats.get('total_wins', 0)}\n"
    text += f"💰 Всего поставлено: {stats.get('total_bets', 0)} ₽\n"
    text += f"💸 Всего выиграно: {stats.get('total_won', 0)} ₽\n"
    
    if stats.get('total_bets', 0) > 0:
        win_rate = (stats.get('total_wins', 0) / stats.get('total_games', 0)) * 100
        profit = stats.get('total_won', 0) - stats.get('total_bets', 0)
        text += f"\n📈 Процент побед: {win_rate:.1f}%\n"
        text += f"💰 Чистая прибыль: {profit:+} ₽"
    
    await callback.answer()
    await callback.message.answer(text, parse_mode="Markdown")


@router.callback_query(SlotState.waiting_bet, F.data == "slot_cancel")
async def slot_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel slot game"""
    await callback.message.edit_text("🎰 Игра отменена")
    await callback.answer()
    await state.clear()


# ========== Duel ==========

@router.message(Command("duel"))
@rate_limit(limit=RATE_LIMIT_GAMES, key="duel")
async def cmd_duel(message: Message, state: FSMContext):
    """Start a duel with another user"""
    if not message.reply_to_message:
        await message.answer(
            "⚔️ *Дуэль*\n\n"
            "Чтобы вызвать на дуэль, ответьте на сообщение соперника:\n"
            "`/duel [сумма]`\n\n"
            "Пример: `/duel 1000`\n\n"
            "⚔️ *Правила:*\n"
            "• Оба игрока ставят одинаковую сумму\n"
            "• Победитель забирает весь банк\n"
            "• При ничьей ставки возвращаются",
            parse_mode="Markdown"
        )
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Укажите сумму ставки!\n"
            "Пример: `/duel 1000`",
            parse_mode="Markdown"
        )
        return
    
    try:
        bet = int(args[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    if bet < MIN_BET:
        await message.answer(f"❌ Минимальная ставка: {MIN_BET} ₽")
        return
    
    if bet > MAX_BET:
        await message.answer(f"❌ Максимальная ставка: {MAX_BET} ₽")
        return
    
    challenger_id = message.from_user.id
    opponent_id = message.reply_to_message.from_user.id
    
    if challenger_id == opponent_id:
        await message.answer("❌ Нельзя вызвать самого себя на дуэль!")
        return
    
    # Check if opponent is bot
    if message.reply_to_message.from_user.is_bot:
        await message.answer("❌ Нельзя вызвать бота на дуэль!")
        return
    
    challenger_balance = await get_user_balance(challenger_id)
    if challenger_balance < bet:
        await message.answer(f"❌ У вас недостаточно средств! Нужно: {bet} ₽")
        return
    
    opponent_balance = await get_user_balance(opponent_id)
    if opponent_balance < bet:
        await message.answer(f"❌ У {message.reply_to_message.from_user.full_name} недостаточно средств!")
        return
    
    # Store duel data
    duel_id = str(uuid.uuid4())
    duel_data = {
        "challenger": challenger_id,
        "opponent": opponent_id,
        "bet": bet,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "challenger_name": message.from_user.full_name,
        "opponent_name": message.reply_to_message.from_user.full_name
    }
    
    await state.update_data(duel_id=duel_id, duel_data=duel_data)
    await state.set_state(DuelState.waiting_confirmation)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅ Принять дуэль",
        callback_data=f"duel_accept_{duel_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Отклонить",
        callback_data=f"duel_decline_{duel_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="💰 Увеличить ставку",
        callback_data=f"duel_increase_{duel_id}"
    ))
    
    await message.answer(
        f"⚔️ *ВЫЗОВ НА ДУЭЛЬ!* ⚔️\n\n"
        f"👤 {message.from_user.full_name} вызывает {message.reply_to_message.from_user.full_name}\n"
        f"💰 Ставка: {bet} ₽\n\n"
        f"⏰ У вас есть {DUEL_TIMEOUT} секунд, чтобы ответить!\n\n"
        f"*Правила:* Победитель определяется случайным броском кубика.",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    # Auto-cancel after timeout
    await asyncio.sleep(DUEL_TIMEOUT)
    current_state = await state.get_state()
    if current_state == DuelState.waiting_confirmation:
        await state.clear()
        await message.answer("⏰ Время на принятие дуэли истекло!")


@router.callback_query(DuelState.waiting_confirmation, F.data.startswith("duel_accept_"))
async def duel_accept(callback: CallbackQuery, state: FSMContext):
    """Accept duel"""
    start_time = datetime.now()
    duel_id = callback.data.split("_")[2]
    data = await state.get_data()
    
    if data.get("duel_id") != duel_id:
        await callback.answer("❌ Дуэль не найдена или истекло время", show_alert=True)
        return
    
    duel_data = data.get("duel_data")
    if callback.from_user.id != duel_data["opponent"]:
        await callback.answer("❌ Это не ваша дуэль!", show_alert=True)
        return
    
    # Deduct bets from both players
    bet = duel_data["bet"]
    challenger_id = duel_data["challenger"]
    opponent_id = duel_data["opponent"]
    challenger_name = duel_data["challenger_name"]
    opponent_name = duel_data["opponent_name"]
    
    # Check balances again
    if not await update_user_balance(challenger_id, bet, "subtract", f"Дуэль с {opponent_name}: ставка {bet} ₽"):
        await callback.answer("❌ У соперника недостаточно средств!", show_alert=True)
        await state.clear()
        return
    
    if not await update_user_balance(opponent_id, bet, "subtract", f"Дуэль с {challenger_name}: ставка {bet} ₽"):
        # Refund challenger
        await update_user_balance(challenger_id, bet, "add", "Возврат ставки по дуэли")
        await callback.answer("❌ У вас недостаточно средств!", show_alert=True)
        await state.clear()
        return
    
    # Determine winner with animated roll
    await callback.answer("🎲 Бросаем кубики...")
    
    challenger_roll = random.randint(1, 100)
    opponent_roll = random.randint(1, 100)
    
    # Add some randomness with skill factor (previous game wins)
    challenger_stats = await get_user_stats(challenger_id)
    opponent_stats = await get_user_stats(opponent_id)
    
    # Small bonus for experienced players (max 5%)
    challenger_bonus = min(5, challenger_stats.get('total_games', 0) // 100)
    opponent_bonus = min(5, opponent_stats.get('total_games', 0) // 100)
    
    challenger_final = challenger_roll + challenger_bonus
    opponent_final = opponent_roll + opponent_bonus
    
    # Determine winner
    if challenger_final > opponent_final:
        winner_id = challenger_id
        winner_name = challenger_name
        win_amount = bet * 2
        await update_user_balance(winner_id, win_amount, "add", f"Выигрыш в дуэли: {win_amount} ₽")
        result_text = f"⚔️ *РЕЗУЛЬТАТ ДУЭЛИ* ⚔️\n\n"
        result_text += f"🏆 *ПОБЕДИТЕЛЬ: {winner_name}!* 🏆\n\n"
        loser_id = opponent_id
    elif opponent_final > challenger_final:
        winner_id = opponent_id
        winner_name = opponent_name
        win_amount = bet * 2
        await update_user_balance(winner_id, win_amount, "add", f"Выигрыш в дуэли: {win_amount} ₽")
        result_text = f"⚔️ *РЕЗУЛЬТАТ ДУЭЛИ* ⚔️\n\n"
        result_text += f"🏆 *ПОБЕДИТЕЛЬ: {winner_name}!* 🏆\n\n"
        loser_id = challenger_id
    else:
        # Draw - refund both
        await update_user_balance(challenger_id, bet, "add", "Возврат ставки (ничья)")
        await update_user_balance(opponent_id, bet, "add", "Возврат ставки (ничья)")
        winner_id = None
        win_amount = 0
        result_text = f"⚔️ *РЕЗУЛЬТАТ ДУЭЛИ* ⚔️\n\n"
        result_text += f"🤝 *НИЧЬЯ!* 🤝\n"
        result_text += f"💰 Ставки возвращены\n"
        loser_id = None
    
    result_text += f"🎲 Результаты:\n"
    result_text += f"👤 {challenger_name}: {challenger_roll}"
    if challenger_bonus > 0:
        result_text += f" +{challenger_bonus} (опыт)"
    result_text += f" = {challenger_final}\n"
    
    result_text += f"👤 {opponent_name}: {opponent_roll}"
    if opponent_bonus > 0:
        result_text += f" +{opponent_bonus} (опыт)"
    result_text += f" = {opponent_final}\n\n"
    
    if win_amount > 0:
        result_text += f"💰 Приз: {win_amount} ₽"
    
    # Get AI comment
    if winner_id:
        ai_comment = await get_ai_game_comment("duel", "выиграл", win_amount)
        if ai_comment:
            result_text += f"\n\n🤖 *AI комментатор:* {ai_comment}"
    
    # Log history
    if winner_id:
        await log_game_history(winner_id, "duel", bet, "win", win_amount, {"opponent": loser_id, "roll": challenger_final if winner_id == challenger_id else opponent_final})
        if loser_id:
            await log_game_history(loser_id, "duel", bet, "loss", 0, {"opponent": winner_id})
    else:
        await log_game_history(challenger_id, "duel", bet, "draw", 0, {"opponent": opponent_id})
        await log_game_history(opponent_id, "duel", bet, "draw", 0, {"opponent": challenger_id})
    
    # Update metrics
    GAMES_PLAYED.labels(game_type="duel").inc()
    BETS_PLACED.labels(game_type="duel").inc()
    if win_amount > 0:
        BETS_WON.labels(game_type="duel").inc()
        GAMES_WON.labels(game_type="duel").inc()
    
    duration = (datetime.now() - start_time).total_seconds()
    GAME_DURATION.labels(game_type="duel").observe(duration)
    
    await callback.message.edit_text(result_text, parse_mode="Markdown")
    await callback.answer()
    await state.clear()


@router.callback_query(DuelState.waiting_confirmation, F.data.startswith("duel_decline_"))
async def duel_decline(callback: CallbackQuery, state: FSMContext):
    """Decline duel"""
    duel_id = callback.data.split("_")[2]
    data = await state.get_data()
    
    if data.get("duel_id") != duel_id:
        await callback.answer("❌ Дуэль не найдена", show_alert=True)
        return
    
    await callback.message.edit_text("⚔️ Дуэль отклонена")
    await callback.answer()
    await state.clear()


@router.callback_query(DuelState.waiting_confirmation, F.data.startswith("duel_increase_"))
async def duel_increase(callback: CallbackQuery, state: FSMContext):
    """Increase duel bet"""
    duel_id = callback.data.split("_")[2]
    data = await state.get_data()
    
    if data.get("duel_id") != duel_id:
        await callback.answer("❌ Дуэль не найдена", show_alert=True)
        return
    
    duel_data = data.get("duel_data")
    current_bet = duel_data["bet"]
    new_bet = min(current_bet * 2, MAX_BET)
    
    if new_bet == current_bet:
        await callback.answer("❌ Нельзя увеличить ставку (максимум)", show_alert=True)
        return
    
    duel_data["bet"] = new_bet
    await state.update_data(duel_data=duel_data)
    
    await callback.answer(f"💰 Ставка увеличена до {new_bet} ₽", show_alert=True)
    
    # Update message
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅ Принять дуэль",
        callback_data=f"duel_accept_{duel_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Отклонить",
        callback_data=f"duel_decline_{duel_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="💰 Увеличить ставку",
        callback_data=f"duel_increase_{duel_id}"
    ))
    
    await callback.message.edit_text(
        f"⚔️ *ВЫЗОВ НА ДУЭЛЬ!* ⚔️\n\n"
        f"👤 {duel_data['challenger_name']} вызывает {duel_data['opponent_name']}\n"
        f"💰 Новая ставка: {new_bet} ₽\n\n"
        f"⏰ У вас есть {DUEL_TIMEOUT} секунд, чтобы ответить!",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )


# ========== Roulette ==========

@router.message(Command("roulette"))
@rate_limit(limit=RATE_LIMIT_GAMES, key="roulette")
async def cmd_roulette(message: Message, state: FSMContext):
    """Roulette game with color/bet selection"""
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    
    if balance < MIN_BET:
        await message.answer(
            f"🎲 *Рулетка*\n\n"
            f"❌ Недостаточно средств!\n"
            f"💰 Ваш баланс: {balance} ₽\n"
            f"🎲 Минимальная ставка: {MIN_BET} ₽",
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(balance=balance)
    await state.set_state(RouletteState.waiting_bet)
    
    builder = InlineKeyboardBuilder()
    bet_options = [MIN_BET, MIN_BET * 5, MIN_BET * 10, MIN_BET * 25, MIN_BET * 50]
    bet_options = [b for b in bet_options if b <= min(MAX_BET, balance)]
    
    for bet in bet_options:
        builder.add(InlineKeyboardButton(
            text=f"{bet} ₽",
            callback_data=f"roulette_bet_{bet}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🎲 Своя сумма",
        callback_data="roulette_custom_bet"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="roulette_cancel"
    ))
    builder.adjust(3)
    
    await message.answer(
        f"🎲 *Рулетка*\n\n"
        f"💰 Ваш баланс: {balance} ₽\n\n"
        f"*Шаг 1:* Выберите размер ставки",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )


@router.callback_query(RouletteState.waiting_bet, F.data.startswith("roulette_bet_"))
async def roulette_choose_color(callback: CallbackQuery, state: FSMContext):
    """Choose color after setting bet"""
    bet = int(callback.data.split("_")[2])
    await state.update_data(bet=bet)
    await state.set_state(RouletteState.waiting_color)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🔴 RED (x2)",
        callback_data="roulette_color_red"
    ))
    builder.add(InlineKeyboardButton(
        text="⚫ BLACK (x2)",
        callback_data="roulette_color_black"
    ))
    builder.add(InlineKeyboardButton(
        text="🟢 GREEN (x36)",
        callback_data="roulette_color_green"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"🎲 *Рулетка*\n\n"
        f"💰 Ставка: {bet} ₽\n\n"
        f"*Шаг 2:* Выберите цвет",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(RouletteState.waiting_color, F.data.startswith("roulette_color_"))
async def roulette_play(callback: CallbackQuery, state: FSMContext):
    """Play roulette"""
    start_time = datetime.now()
    color = callback.data.split("_")[2]
    data = await state.get_data()
    bet = data.get("bet")
    user_id = callback.from_user.id
    
    color_map = {"red": "🔴 RED", "black": "⚫ BLACK", "green": "🟢 GREEN"}
    color_display = color_map.get(color, color)
    
    # Deduct bet
    if not await update_user_balance(user_id, bet, "subtract", f"Ставка в рулетке: {bet} ₽ ({color})"):
        await callback.answer("❌ Ошибка списания средств", show_alert=True)
        await state.clear()
        return
    
    # Roulette logic
    roulette_numbers = {
        "red": [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36],
        "black": [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35],
        "green": [0]
    }
    
    result_number = random.randint(0, 36)
    result_color = "green" if result_number == 0 else "red" if result_number in roulette_numbers["red"] else "black"
    
    win_multiplier = 36 if color == "green" else 2
    is_win = result_color == color
    
    await callback.answer("🎲 Крутим рулетку...")
    
    if is_win:
        win_amount = bet * win_multiplier
        await update_user_balance(user_id, win_amount, "add", f"Выигрыш в рулетке: {win_amount} ₽")
        result_text = f"🎲 *РУЛЕТКА* 🎲\n\n"
        result_text += f"🎯 Выпало: *{result_number}* ({'🔴' if result_color == 'red' else '⚫' if result_color == 'black' else '🟢'} {result_color.upper()})\n\n"
        result_text += f"🎉 *ПОБЕДА!* 🎉\n"
        result_text += f"💰 Выигрыш: {win_amount} ₽\n"
        result_text += f"✨ Множитель: x{win_multiplier}\n"
        GAMES_WON.labels(game_type="roulette").inc()
        BETS_WON.labels(game_type="roulette").inc()
    else:
        win_amount = 0
        result_text = f"🎲 *РУЛЕТКА* 🎲\n\n"
        result_text += f"🎯 Выпало: *{result_number}* ({'🔴' if result_color == 'red' else '⚫' if result_color == 'black' else '🟢'} {result_color.upper()})\n\n"
        result_text += f"😢 *ПРОИГРЫШ*\n"
        result_text += f"💸 Потеряно: {bet} ₽\n"
    
    result_text += f"\n💰 Новый баланс: {await get_user_balance(user_id)} ₽"
    
    # Get AI comment
    ai_comment = await get_ai_game_comment("roulette", "выиграл" if is_win else "проиграл", win_amount or bet)
    if ai_comment:
        result_text += f"\n\n🤖 *AI совет:* {ai_comment}"
    
    # Log history
    result_status = "win" if is_win else "loss"
    details = {"number": result_number, "color": result_color, "bet_color": color}
    await log_game_history(user_id, "roulette", bet, result_status, win_amount, details)
    
    # Update metrics
    GAMES_PLAYED.labels(game_type="roulette").inc()
    BETS_PLACED.labels(game_type="roulette").inc()
    duration = (datetime.now() - start_time).total_seconds()
    GAME_DURATION.labels(game_type="roulette").observe(duration)
    
    await callback.message.edit_text(result_text, parse_mode="Markdown")
    await callback.answer()
    await state.clear()


@router.callback_query(RouletteState.waiting_bet, F.data == "roulette_cancel")
async def roulette_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel roulette"""
    await callback.message.edit_text("🎲 Игра отменена")
    await callback.answer()
    await state.clear()


# ========== Rock Paper Scissors ==========

@router.message(Command("rps"))
@rate_limit(limit=RATE_LIMIT_GAMES, key="rps")
async def cmd_rps(message: Message, state: FSMContext):
    """Rock Paper Scissors game"""
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    
    if balance < MIN_BET:
        await message.answer(
            f"✊ *Камень-ножницы-бумага*\n\n"
            f"❌ Недостаточно средств!\n"
            f"💰 Ваш баланс: {balance} ₽\n"
            f"🎲 Минимальная ставка: {MIN_BET} ₽",
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(balance=balance)
    await state.set_state(RPSState.waiting_bet)
    
    builder = InlineKeyboardBuilder()
    bet_options = [MIN_BET, MIN_BET * 5, MIN_BET * 10, MIN_BET * 25]
    bet_options = [b for b in bet_options if b <= min(MAX_BET, balance)]
    
    for bet in bet_options:
        builder.add(InlineKeyboardButton(
            text=f"{bet} ₽",
            callback_data=f"rps_bet_{bet}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="rps_cancel"
    ))
    builder.adjust(2)
    
    await message.answer(
        f"✊ *Камень-ножницы-бумага*\n\n"
        f"💰 Ваш баланс: {balance} ₽\n\n"
        f"Выберите размер ставки:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )


@router.callback_query(RPSState.waiting_bet, F.data.startswith("rps_bet_"))
async def rps_choose_hand(callback: CallbackQuery, state: FSMContext):
    """Choose hand after setting bet"""
    bet = int(callback.data.split("_")[2])
    await state.update_data(bet=bet)
    await state.set_state(RPSState.waiting_choice)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✊ Камень",
        callback_data="rps_choice_rock"
    ))
    builder.add(InlineKeyboardButton(
        text="✌️ Ножницы",
        callback_data="rps_choice_scissors"
    ))
    builder.add(InlineKeyboardButton(
        text="✋ Бумага",
        callback_data="rps_choice_paper"
    ))
    builder.adjust(3)
    
    await callback.message.edit_text(
        f"✊ *Камень-ножницы-бумага*\n\n"
        f"💰 Ставка: {bet} ₽\n\n"
        f"Выберите свой ход:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(RPSState.waiting_choice, F.data.startswith("rps_choice_"))
async def rps_play(callback: CallbackQuery, state: FSMContext):
    """Play Rock Paper Scissors"""
    start_time = datetime.now()
    choice_map = {
        "rock": {"name": "✊ Камень", "emoji": "✊"},
        "scissors": {"name": "✌️ Ножницы", "emoji": "✌️"},
        "paper": {"name": "✋ Бумага", "emoji": "✋"}
    }
    
    player_choice_key = callback.data.split("_")[2]
    player_choice = choice_map.get(player_choice_key, {"name": "Unknown", "emoji": "❓"})
    
    data = await state.get_data()
    bet = data.get("bet")
    user_id = callback.from_user.id
    
    # Deduct bet
    if not await update_user_balance(user_id, bet, "subtract", f"Ставка в RPS: {bet} ₽"):
        await callback.answer("❌ Ошибка списания средств", show_alert=True)
        await state.clear()
        return
    
    # Bot choice
    bot_choices = ["rock", "scissors", "paper"]
    bot_choice_key = random.choice(bot_choices)
    bot_choice = choice_map[bot_choice_key]
    
    # Determine winner
    win_rules = {
        ("rock", "scissors"): "win",
        ("scissors", "paper"): "win",
        ("paper", "rock"): "win",
        ("rock", "paper"): "loss",
        ("scissors", "rock"): "loss",
        ("paper", "scissors"): "loss"
    }
    
    result = win_rules.get((player_choice_key, bot_choice_key), "draw")
    
    await callback.answer(f"🤖 Бот выбрал {bot_choice['name']}")
    
    if result == "win":
        win_amount = bet * 2
        await update_user_balance(user_id, win_amount, "add", f"Выигрыш в RPS: {win_amount} ₽")
        result_text = f"✊ *КАМЕНЬ-НОЖНИЦЫ-БУМАГА* ✋\n\n"
        result_text += f"👤 Вы: {player_choice['emoji']}\n"
        result_text += f"🤖 Бот: {bot_choice['emoji']}\n\n"
        result_text += f"🎉 *ПОБЕДА!* 🎉\n"
        result_text += f"💰 Выигрыш: {win_amount} ₽\n"
        GAMES_WON.labels(game_type="rps").inc()
        BETS_WON.labels(game_type="rps").inc()
    elif result == "loss":
        win_amount = 0
        result_text = f"✊ *КАМЕНЬ-НОЖНИЦЫ-БУМАГА* ✋\n\n"
        result_text += f"👤 Вы: {player_choice['emoji']}\n"
        result_text += f"🤖 Бот: {bot_choice['emoji']}\n\n"
        result_text += f"😢 *ПРОИГРЫШ*\n"
        result_text += f"💸 Потеряно: {bet} ₽\n"
    else:
        win_amount = bet
        await update_user_balance(user_id, win_amount, "add", "Возврат ставки (ничья)")
        result_text = f"✊ *КАМЕНЬ-НОЖНИЦЫ-БУМАГА* ✋\n\n"
        result_text += f"👤 Вы: {player_choice['emoji']}\n"
        result_text += f"🤖 Бот: {bot_choice['emoji']}\n\n"
        result_text += f"🤝 *НИЧЬЯ!*\n"
        result_text += f"💰 Возврат ставки: {bet} ₽\n"
    
    result_text += f"\n💰 Новый баланс: {await get_user_balance(user_id)} ₽"
    
    # Get AI comment
    ai_comment = await get_ai_game_comment("rps", "выиграл" if result == "win" else "проиграл" if result == "loss" else "сыграл вничью", win_amount if result == "win" else bet)
    if ai_comment:
        result_text += f"\n\n🤖 *AI совет:* {ai_comment}"
    
    # Log history
    result_status = "win" if result == "win" else "loss" if result == "loss" else "draw"
    details = {"player_choice": player_choice_key, "bot_choice": bot_choice_key}
    await log_game_history(user_id, "rps", bet, result_status, win_amount if result == "win" else 0, details)
    
    # Update metrics
    GAMES_PLAYED.labels(game_type="rps").inc()
    BETS_PLACED.labels(game_type="rps").inc()
    duration = (datetime.now() - start_time).total_seconds()
    GAME_DURATION.labels(game_type="rps").observe(duration)
    
    await callback.message.edit_text(result_text, parse_mode="Markdown")
    await callback.answer()
    await state.clear()


@router.callback_query(RPSState.waiting_bet, F.data == "rps_cancel")
async def rps_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel RPS game"""
    await callback.message.edit_text("✊ Игра отменена")
    await callback.answer()
    await state.clear()


# ========== Game History ==========

@router.message(Command("games_history"))
@rate_limit(limit=10, key="history")
async def cmd_games_history(message: Message):
    """Show user's game history with pagination"""
    user_id = message.from_user.id
    page = 0
    
    try:
        history = await db.get_game_history(user_id, limit=20, offset=page * 20)
        
        if not history:
            await message.answer("📜 *История игр*\n\nУ вас пока нет истории игр.\n\nСыграйте в любую игру: /slot, /duel, /roulette, /rps", parse_mode="Markdown")
            return
        
        stats = await get_user_stats(user_id)
        
        text = "📜 *ИСТОРИЯ ИГР*\n\n"
        text += f"📊 *Общая статистика:*\n"
        text += f"🎮 Всего игр: {stats.get('total_games', 0)}\n"
        text += f"🏆 Побед: {stats.get('total_wins', 0)}\n"
        text += f"💰 Поставлено: {stats.get('total_bets', 0)} ₽\n"
        text += f"💸 Выиграно: {stats.get('total_won', 0)} ₽\n\n"
        
        if stats.get('total_bets', 0) > 0:
            win_rate = (stats.get('total_wins', 0) / stats.get('total_games', 0)) * 100 if stats.get('total_games', 0) > 0 else 0
            profit = stats.get('total_won', 0) - stats.get('total_bets', 0)
            text += f"📈 Процент побед: {win_rate:.1f}%\n"
            text += f"💰 Чистая прибыль: {profit:+} ₽\n\n"
        
        text += "*Последние игры:*\n"
        
        for game in history:
            game_type = game.get("game_type", "unknown")
            bet = game.get("bet", 0)
            result = game.get("result", "unknown")
            win_amount = game.get("win_amount", 0)
            created_at = game.get("created_at", datetime.now())
            
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            
            time_str = created_at.strftime("%d.%m %H:%M")
            
            game_emoji = {
                "slot": "🎰", "duel": "⚔️", "roulette": "🎲", "rps": "✊"
            }.get(game_type, "🎮")
            
            if result == "win":
                result_emoji = "✅"
                result_text = f"+{win_amount} ₽"
            elif result == "loss":
                result_emoji = "❌"
                result_text = f"-{bet} ₽"
            else:
                result_emoji = "🔄"
                result_text = "0 ₽"
            
            text += f"{result_emoji} {time_str} {game_emoji} {game_type}: {result_text}\n"
        
        # Add pagination if more games
        total_games = stats.get('total_games', 0)
        if total_games > 20:
            text += f"\n📄 Страница {page + 1}/{(total_games + 19) // 20}"
            
            builder = InlineKeyboardBuilder()
            builder.add(InlineKeyboardButton(
                text="▶️ Следующая",
                callback_data=f"history_next_{page + 1}"
            ))
            await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())
        else:
            await message.answer(text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Games history error: {e}")
        await message.answer("❌ Ошибка загрузки истории игр")


@router.callback_query(F.data.startswith("history_next_"))
async def history_next(callback: CallbackQuery):
    """Show next page of history"""
    page = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    try:
        history = await db.get_game_history(user_id, limit=20, offset=page * 20)
        
        if not history:
            await callback.answer("Больше нет записей", show_alert=True)
            return
        
        text = "📜 *ИСТОРИЯ ИГР*\n\n"
        
        for game in history:
            game_type = game.get("game_type", "unknown")
            bet = game.get("bet", 0)
            result = game.get("result", "unknown")
            win_amount = game.get("win_amount", 0)
            created_at = game.get("created_at", datetime.now())
            
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            
            time_str = created_at.strftime("%d.%m %H:%M")
            
            game_emoji = {
                "slot": "🎰", "duel": "⚔️", "roulette": "🎲", "rps": "✊"
            }.get(game_type, "🎮")
            
            if result == "win":
                result_emoji = "✅"
                result_text = f"+{win_amount} ₽"
            elif result == "loss":
                result_emoji = "❌"
                result_text = f"-{bet} ₽"
            else:
                result_emoji = "🔄"
                result_text = "0 ₽"
            
            text += f"{result_emoji} {time_str} {game_emoji} {game_type}: {result_text}\n"
        
        stats = await get_user_stats(user_id)
        total_games = stats.get('total_games', 0)
        text += f"\n📄 Страница {page + 1}/{(total_games + 19) // 20}"
        
        builder = InlineKeyboardBuilder()
        if page > 0:
            builder.add(InlineKeyboardButton(
                text="◀️ Предыдущая",
                callback_data=f"history_prev_{page - 1}"
            ))
        if (page + 1) * 20 < total_games:
            builder.add(InlineKeyboardButton(
                text="▶️ Следующая",
                callback_data=f"history_next_{page + 1}"
            ))
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup() if builder.buttons else None)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"History pagination error: {e}")
        await callback.answer("Ошибка загрузки", show_alert=True)


@router.callback_query(F.data.startswith("history_prev_"))
async def history_prev(callback: CallbackQuery):
    """Show previous page of history"""
    page = int(callback.data.split("_")[2])
    await history_next(callback)  # Reuse logic with prev button


# ========== Metrics ==========

@router.message(Command("metrics"))
async def cmd_metrics(message: Message):
    """Show bot metrics (admin only)"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("🔒 *Доступ запрещен*\n\nТолько для администраторов.", parse_mode="Markdown")
        return
    
    try:
        total_users = await db.get_total_users()
        active_today = await db.get_active_users_today()
        total_games = await db.get_total_games()
        total_bets = await db.get_total_bets()
        total_wins = await db.get_total_wins()
        active_games = await get_active_games_count()
        
        text = "📊 *СТАТИСТИКА БОТА* 📊\n\n"
        text += "👥 *Пользователи:*\n"
        text += f"• Всего: {total_users}\n"
        text += f"• Активных сегодня: {active_today}\n"
        text += f"• Активных игр: {active_games}\n\n"
        
        text += "🎮 *Игры:*\n"
        text += f"• Всего игр: {total_games}\n"
        text += f"• Всего ставок: {total_bets:,} ₽\n"
        text += f"• Всего выигрышей: {total_wins:,} ₽\n\n"
        
        if total_bets > 0:
            house_edge = ((total_bets - total_wins) / total_bets) * 100
            profit = total_bets - total_wins
            text += "💰 *Финансы:*\n"
            text += f"• Прибыль бота: {profit:,} ₽\n"
            text += f"• Преимущество казино: {house_edge:.2f}%\n\n"
        
        # AI stats if enabled
        if AI_ENABLED:
            text += "🤖 *AI (OpenRouter):*\n"
            text += f"• Статус: ✅ Активен\n"
            text += f"• Модель: GPT-3.5 Turbo\n"
        else:
            text += "🤖 *AI:* ❌ Отключен\n"
        
        text += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await message.answer(text, parse_mode="Markdown")
        
        # Update metrics
        TOTAL_USERS.set(total_users)
        
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        await message.answer("❌ Ошибка загрузки статистики")
