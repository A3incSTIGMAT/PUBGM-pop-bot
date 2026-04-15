"""
Модуль личных игр (играем в боте, не спамим в чат)
"""

import random
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)


async def init_private_games():
    """Инициализация таблиц личных игр"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_game_stats (
            user_id INTEGER PRIMARY KEY,
            total_games INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_coins INTEGER DEFAULT 0,
            slot_played INTEGER DEFAULT 0,
            roulette_played INTEGER DEFAULT 0,
            rps_played INTEGER DEFAULT 0,
            duel_played INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


async def update_user_game_stats(user_id: int, game: str, win: bool, coins: int):
    """Обновить личную статистику игрока"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO user_game_stats (user_id, total_games, total_coins)
        VALUES (?, 1, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            total_games = total_games + 1,
            total_coins = total_coins + ?,
            updated_at = CURRENT_TIMESTAMP
    """, (user_id, coins, coins))
    
    if win:
        cursor.execute("UPDATE user_game_stats SET total_wins = total_wins + 1 WHERE user_id = ?", (user_id,))
    
    cursor.execute(f"UPDATE user_game_stats SET {game}_played = {game}_played + 1 WHERE user_id = ?", (user_id,))
    
    conn.commit()
    conn.close()


def private_games_menu() -> InlineKeyboardMarkup:
    """Клавиатура личных игр"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 СЛОТ", callback_data="private_slot"),
         InlineKeyboardButton(text="🎡 РУЛЕТКА", callback_data="private_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="private_rps"),
         InlineKeyboardButton(text="⚔️ ДУЭЛЬ", callback_data="private_duel")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="private_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


@router.message(Command("games_private"))
async def cmd_private_games(message: types.Message):
    """Личные игры (без спама в чат)"""
    await message.answer(
        "🎮 *ЛИЧНЫЕ ИГРЫ*\n\n"
        "Играйте в боте — результаты видны только вам!\n"
        "Никакого спама в чате.\n\n"
        "💰 Зарабатывайте NCoins и повышайте свой ранг!\n\n"
        "📊 Вся статистика сохраняется в вашем профиле.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=private_games_menu()
    )


@router.callback_query(F.data == "private_slot")
async def private_slot(callback: types.CallbackQuery):
    """Личный слот"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 50", callback_data="pslot_50"),
         InlineKeyboardButton(text="🎰 100", callback_data="pslot_100"),
         InlineKeyboardButton(text="🎰 200", callback_data="pslot_200")],
        [InlineKeyboardButton(text="🎰 500", callback_data="pslot_500"),
         InlineKeyboardButton(text="🎰 1000", callback_data="pslot_1000"),
         InlineKeyboardButton(text="🎰 МАКС", callback_data="pslot_max")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="private_games_back")]
    ])
    
    await callback.message.edit_text(
        f"🎰 *ЛИЧНЫЙ СЛОТ*\n\n"
        f"💰 Ваш баланс: {user['balance']} NCoins\n\n"
        f"Выберите ставку:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pslot_"))
async def play_private_slot(callback: types.CallbackQuery):
    """Игра в личный слот"""
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[1]
    
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    if bet_str == "max":
        bet = user["balance"]
        if bet > 10000:
            bet = 10000
    else:
        bet = int(bet_str)
    
    if bet < 50:
        await callback.answer("❌ Минимальная ставка: 50 NCoins", show_alert=True)
        return
    
    if user["balance"] < bet:
        await callback.answer(f"❌ Не хватает NCoins! Баланс: {user['balance']}", show_alert=True)
        return
    
    symbols = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎"]
    result = [random.choice(symbols) for _ in range(3)]
    
    if result[0] == result[1] == result[2]:
        if result[0] == "💎":
            win = bet * 10
            msg = "✨ ДЖЕКПОТ! x10! ✨"
        elif result[0] == "⭐":
            win = bet * 5
            msg = "✨ СУПЕР ВЫИГРЫШ! x5! ✨"
        else:
            win = bet * 3
            msg = "🎉 ВЫИГРЫШ! x3! 🎉"
        
        await db.update_balance(user_id, win, "Личный слот")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n{msg}\n💰 +{win} NCoins!"
        await update_user_game_stats(user_id, "slot", True, win)
        
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet // 2
        await db.update_balance(user_id, win, "Личный слот")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n🎉 Выигрыш! +{win} NCoins!"
        await update_user_game_stats(user_id, "slot", True, win)
    else:
        await db.update_balance(user_id, -bet, "Личный слот")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n😔 Проигрыш! -{bet} NCoins"
        await update_user_game_stats(user_id, "slot", False, -bet)
    
    user = await db.get_user(user_id)
    new_balance = user["balance"] if user else 0
    
    await callback.message.edit_text(
        f"{response}\n\n💰 Новый баланс: {new_balance} NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎰 ИГРАТЬ ЕЩЁ", callback_data="private_slot")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="private_games_back")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "private_stats")
async def private_stats(callback: types.CallbackQuery):
    """Личная статистика игрока"""
    user_id = callback.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_game_stats WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await callback.message.edit_text(
            "📊 *ВАША СТАТИСТИКА*\n\n"
            "Вы ещё не играли в личные игры!\n\n"
            "🎮 Начните играть через кнопки выше.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=private_games_menu()
        )
        await callback.answer()
        return
    
    text = f"""
📊 *ВАША СТАТИСТИКА ЛИЧНЫХ ИГР*

━━━━━━━━━━━━━━━━━━━━━

🎮 Всего игр: {row[1]}
🏆 Побед: {row[2]}
💰 Выиграно монет: {row[3]}

━━━━━━━━━━━━━━━━━━━━━

*По играм:*
🎰 Слот: {row[4]} игр
🎡 Рулетка: {row[5]} игр
✂️ КНБ: {row[6]} игр
⚔️ Дуэль: {row[7]} игр

━━━━━━━━━━━━━━━━━━━━━

💡 *Совет:* Играйте в личные игры, чтобы не спамить в чат!
"""
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=private_games_menu())
    await callback.answer()


@router.callback_query(F.data == "private_games_back")
async def private_games_back(callback: types.CallbackQuery):
    """Назад в меню личных игр"""
    await cmd_private_games(callback.message)
    await callback.answer()
