"""
Модуль игр NEXUS Bot с инлайн-кнопками
Слот, рулетка, камень-ножницы-бумага, дуэль
"""

import random
import asyncio
import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

router = Router()
logger = logging.getLogger(__name__)

# Константы игр (с резервными значениями)
try:
    from config import SLOT_COST, ROULETTE_MIN, DUEL_MIN
except ImportError:
    SLOT_COST = 50
    ROULETTE_MIN = 50
    DUEL_MIN = 100

# Хранилище запросов дуэлей (с таймаутом)
duel_requests = {}
DUEL_TIMEOUT = 300  # 5 минут


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Получить пользователя или создать если не существует"""
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Auto-registered user {user_id} in games module")
    return user


async def update_game_stats(user_id: int, is_win: bool):
    """Обновить статистику игр (асинхронно)"""
    def _sync_update():
        conn = db._get_connection()
        cursor = conn.cursor()
        if is_win:
            cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        
        # Обновляем детальную статистику
        cursor.execute("""
            INSERT OR IGNORE INTO user_game_stats (user_id) VALUES (?)
        """, (user_id,))
        cursor.execute("""
            UPDATE user_game_stats 
            SET total_games = total_games + 1,
                total_wins = total_wins + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (1 if is_win else 0, user_id))
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_update)


async def update_specific_game_stat(user_id: int, game_type: str):
    """Обновить статистику конкретной игры"""
    def _sync_update():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO user_game_stats (user_id) VALUES (?)
        """, (user_id,))
        
        if game_type == "slot":
            cursor.execute("UPDATE user_game_stats SET slot_played = slot_played + 1 WHERE user_id = ?", (user_id,))
        elif game_type == "roulette":
            cursor.execute("UPDATE user_game_stats SET roulette_played = roulette_played + 1 WHERE user_id = ?", (user_id,))
        elif game_type == "rps":
            cursor.execute("UPDATE user_game_stats SET rps_played = rps_played + 1 WHERE user_id = ?", (user_id,))
        elif game_type == "duel":
            cursor.execute("UPDATE user_game_stats SET duel_played = duel_played + 1 WHERE user_id = ?", (user_id,))
        
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_update)


# ==================== КЛАВИАТУРЫ ИГР ====================

def games_keyboard() -> InlineKeyboardMarkup:
    """Главное меню игр"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 СЛОТ", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 РУЛЕТКА", callback_data="game_roulette")],
        [InlineKeyboardButton(text="✂️ КАМЕНЬ-НОЖНИЦЫ-БУМАГА", callback_data="game_rps"),
         InlineKeyboardButton(text="⚔️ ДУЭЛЬ", callback_data="game_duel")],
        [InlineKeyboardButton(text="◀️ НАЗАД В МЕНЮ", callback_data="back_to_menu")]
    ])


def slot_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для слота (ставки)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 50", callback_data="slot_50"),
         InlineKeyboardButton(text="🎰 100", callback_data="slot_100"),
         InlineKeyboardButton(text="🎰 200", callback_data="slot_200")],
        [InlineKeyboardButton(text="🎰 500", callback_data="slot_500"),
         InlineKeyboardButton(text="🎰 1000", callback_data="slot_1000"),
         InlineKeyboardButton(text="🎰 МАКС", callback_data="slot_max")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
    ])


def roulette_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для рулетки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 50", callback_data="roulette_red_50"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 50", callback_data="roulette_black_50")],
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 100", callback_data="roulette_red_100"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 100", callback_data="roulette_black_100")],
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 200", callback_data="roulette_red_200"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 200", callback_data="roulette_black_200")],
        [InlineKeyboardButton(text="🔴 КРАСНОЕ 500", callback_data="roulette_red_500"),
         InlineKeyboardButton(text="⚫ ЧЁРНОЕ 500", callback_data="roulette_black_500")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
    ])


def rps_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для КНБ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗿 КАМЕНЬ", callback_data="rps_rock"),
         InlineKeyboardButton(text="✂️ НОЖНИЦЫ", callback_data="rps_scissors"),
         InlineKeyboardButton(text="📄 БУМАГА", callback_data="rps_paper")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
    ])


def duel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для дуэли"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ 100", callback_data="duel_100"),
         InlineKeyboardButton(text="⚔️ 200", callback_data="duel_200"),
         InlineKeyboardButton(text="⚔️ 500", callback_data="duel_500")],
        [InlineKeyboardButton(text="⚔️ 1000", callback_data="duel_1000"),
         InlineKeyboardButton(text="⚔️ 5000", callback_data="duel_5000"),
         InlineKeyboardButton(text="⚔️ МАКС", callback_data="duel_max")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games_back")]
    ])


# ==================== МЕНЮ ИГР ====================

@router.message(Command("games"))
async def cmd_games(message: types.Message):
    """Меню игр"""
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    await message.answer(
        "🎮 *ДОБРО ПОЖАЛОВАТЬ В ИГРЫ NEXUS!* 🎮\n\n"
        "Выберите игру на кнопках ниже:\n\n"
        f"🎰 *Слот* — минимальная ставка {SLOT_COST} NCoins\n"
        f"🎡 *Рулетка* — минимальная ставка {ROULETTE_MIN} NCoins\n"
        f"✂️ *КНБ* — ставка 50 NCoins\n"
        f"⚔️ *Дуэль* — минимальная ставка {DUEL_MIN} NCoins\n\n"
        f"💰 Ваш баланс: *{user['balance']}* NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_keyboard()
    )


@router.callback_query(lambda c: c.data == "games")
@router.callback_query(lambda c: c.data == "games_category")
async def games_callback(callback: types.CallbackQuery):
    """Обработчик кнопки ИГРЫ из меню"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    await callback.message.edit_text(
        "🎮 *ДОБРО ПОЖАЛОВАТЬ В ИГРЫ NEXUS!* 🎮\n\n"
        "Выберите игру на кнопках ниже:\n\n"
        f"🎰 *Слот* — минимальная ставка {SLOT_COST} NCoins\n"
        f"🎡 *Рулетка* — минимальная ставка {ROULETTE_MIN} NCoins\n"
        f"✂️ *КНБ* — ставка 50 NCoins\n"
        f"⚔️ *Дуэль* — минимальная ставка {DUEL_MIN} NCoins\n\n"
        f"💰 Ваш баланс: *{user['balance']}* NCoins\n"
        f"🏆 Побед: {user.get('wins', 0)} | Поражений: {user.get('losses', 0)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "games_back")
async def games_back(callback: types.CallbackQuery):
    """Вернуться в меню игр"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    await callback.message.edit_text(
        "🎮 *ДОБРО ПОЖАЛОВАТЬ В ИГРЫ NEXUS!* 🎮\n\n"
        "Выберите игру на кнопках ниже:\n\n"
        f"🎰 *Слот* — минимальная ставка {SLOT_COST} NCoins\n"
        f"🎡 *Рулетка* — минимальная ставка {ROULETTE_MIN} NCoins\n"
        f"✂️ *КНБ* — ставка 50 NCoins\n"
        f"⚔️ *Дуэль* — минимальная ставка {DUEL_MIN} NCoins\n\n"
        f"💰 Ваш баланс: *{user['balance']}* NCoins\n"
        f"🏆 Побед: {user.get('wins', 0)} | Поражений: {user.get('losses', 0)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_keyboard()
    )
    await callback.answer()


# ==================== СЛОТ ====================

@router.callback_query(lambda c: c.data == "game_slot")
async def slot_menu(callback: types.CallbackQuery):
    """Меню слота с выбором ставки"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    await callback.message.edit_text(
        "🎰 *СЛОТ-МАШИНА* 🎰\n\n"
        "Выберите ставку:\n\n"
        "✨ *Выигрыши:*\n"
        "├ 💎💎💎 → x10\n"
        "├ ⭐⭐⭐ → x5\n"
        "├ 🍒🍒🍒 → x3\n"
        "└ 🍒🍒🍊 → x0.5\n\n"
        f"💰 Ваш баланс: *{user['balance']}* NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=slot_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("slot_"))
async def play_slot(callback: types.CallbackQuery):
    """Игра в слот"""
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[1]
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    # Определяем ставку
    if bet_str == "max":
        bet = min(user["balance"], 10000)
    else:
        bet = int(bet_str)
    
    # Проверки
    if bet < SLOT_COST:
        await callback.answer(f"❌ Минимальная ставка: {SLOT_COST} NCoins", show_alert=True)
        return
    
    if user["balance"] < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {user['balance']}", show_alert=True)
        return
    
    # Игра
    symbols = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎"]
    result = [random.choice(symbols) for _ in range(3)]
    
    is_win = False
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
        is_win = True
        await db.update_balance(user_id, win, "Выигрыш в слоте")
        result_text = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n{msg}\n💰 +{win} NCoins!"
        
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet // 2
        is_win = True
        await db.update_balance(user_id, win, "Выигрыш в слоте")
        result_text = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n🎉 Выигрыш! +{win} NCoins!"
    else:
        await db.update_balance(user_id, -bet, "Проигрыш в слоте")
        result_text = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n😔 Проигрыш! -{bet} NCoins"
    
    # Обновляем статистику
    await update_game_stats(user_id, is_win)
    await update_specific_game_stat(user_id, "slot")
    
    # Получаем новый баланс
    user = await db.get_user(user_id)
    new_balance = user["balance"] if user else 0
    
    await callback.message.edit_text(
        f"{result_text}\n\n💰 Новый баланс: {new_balance} NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=slot_keyboard()
    )
    await callback.answer()


# ==================== РУЛЕТКА ====================

@router.callback_query(lambda c: c.data == "game_roulette")
async def roulette_menu(callback: types.CallbackQuery):
    """Меню рулетки"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    await callback.message.edit_text(
        "🎡 *РУЛЕТКА* 🎡\n\n"
        "Выберите цвет и ставку:\n\n"
        "🔴 КРАСНОЕ — выигрыш x2\n"
        "⚫ ЧЁРНОЕ — выигрыш x2\n\n"
        f"💰 Ваш баланс: *{user['balance']}* NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=roulette_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("roulette_"))
async def play_roulette(callback: types.CallbackQuery):
    """Игра в рулетку"""
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    color = parts[1]  # red или black
    bet = int(parts[2])
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    # Проверки
    if bet < ROULETTE_MIN:
        await callback.answer(f"❌ Минимальная ставка: {ROULETTE_MIN} NCoins", show_alert=True)
        return
    
    if user["balance"] < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {user['balance']}", show_alert=True)
        return
    
    # Игра
    result_color = random.choice(["red", "black"])
    color_names = {"red": "🔴 КРАСНОЕ", "black": "⚫ ЧЁРНОЕ"}
    
    if color == result_color:
        win = bet * 2
        await db.update_balance(user_id, win, "Выигрыш в рулетке")
        result_text = f"🎡 *РУЛЕТКА*\n\nВыпало: {color_names[result_color]}\n\n🎉 ВЫ ВЫИГРАЛИ! +{win} NCoins!"
        is_win = True
    else:
        await db.update_balance(user_id, -bet, "Проигрыш в рулетке")
        result_text = f"🎡 *РУЛЕТКА*\n\nВыпало: {color_names[result_color]}\n\n😔 Вы проиграли {bet} NCoins"
        is_win = False
    
    # Обновляем статистику
    await update_game_stats(user_id, is_win)
    await update_specific_game_stat(user_id, "roulette")
    
    user = await db.get_user(user_id)
    new_balance = user["balance"] if user else 0
    
    await callback.message.edit_text(
        f"{result_text}\n\n💰 Новый баланс: {new_balance} NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=roulette_keyboard()
    )
    await callback.answer()


# ==================== КАМЕНЬ-НОЖНИЦЫ-БУМАГА ====================

@router.callback_query(lambda c: c.data == "game_rps")
async def rps_menu(callback: types.CallbackQuery):
    """Меню КНБ"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    await callback.message.edit_text(
        "✂️ *КАМЕНЬ-НОЖНИЦЫ-БУМАГА* ✂️\n\n"
        "Выберите свой ход:\n\n"
        "🗿 КАМЕНЬ → побеждает ножницы\n"
        "✂️ НОЖНИЦЫ → побеждают бумагу\n"
        "📄 БУМАГА → побеждает камень\n\n"
        f"💰 Ставка: 50 NCoins\n"
        f"💰 Ваш баланс: *{user['balance']}* NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=rps_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("rps_"))
async def play_rps(callback: types.CallbackQuery):
    """Игра в КНБ"""
    user_id = callback.from_user.id
    choice = callback.data.split("_")[1]  # rock, scissors, paper
    bet = 50
    
    choice_names = {"rock": "🗿 КАМЕНЬ", "scissors": "✂️ НОЖНИЦЫ", "paper": "📄 БУМАГА"}
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    if user["balance"] < bet:
        await callback.answer(f"❌ Недостаточно средств! Нужно {bet}", show_alert=True)
        return
    
    bot_choice = random.choice(["rock", "scissors", "paper"])
    
    # Определяем победителя
    if choice == bot_choice:
        result = 0
        msg = "🤝 НИЧЬЯ!"
        is_win = None
    elif (choice == "rock" and bot_choice == "scissors") or \
         (choice == "scissors" and bot_choice == "paper") or \
         (choice == "paper" and bot_choice == "rock"):
        result = bet
        msg = f"✅ ПОБЕДА! +{bet} NCoins!"
        is_win = True
    else:
        result = -bet
        msg = f"❌ ПОРАЖЕНИЕ! -{bet} NCoins"
        is_win = False
    
    await db.update_balance(user_id, result, "Игра КНБ")
    
    if is_win is not None:
        await update_game_stats(user_id, is_win)
    await update_specific_game_stat(user_id, "rps")
    
    user = await db.get_user(user_id)
    new_balance = user["balance"] if user else 0
    
    await callback.message.edit_text(
        f"✂️ *КАМЕНЬ-НОЖНИЦЫ-БУМАГА*\n\n"
        f"Вы: {choice_names[choice]}\n"
        f"Бот: {choice_names[bot_choice]}\n\n"
        f"{msg}\n\n"
        f"💰 Новый баланс: {new_balance} NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=rps_keyboard()
    )
    await callback.answer()


# ==================== ДУЭЛЬ ====================

@router.callback_query(lambda c: c.data == "game_duel")
async def duel_menu(callback: types.CallbackQuery):
    """Меню дуэли"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    await callback.message.edit_text(
        "⚔️ *ДУЭЛЬ* ⚔️\n\n"
        "Выберите ставку:\n\n"
        "После выбора ставки, бот попросит указать @username противника\n\n"
        f"💰 Ваш баланс: *{user['balance']}* NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=duel_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("duel_"))
async def duel_choose_bet(callback: types.CallbackQuery):
    """Выбор ставки для дуэли"""
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[1]
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    if bet_str == "max":
        bet = min(user["balance"], 10000)
    else:
        bet = int(bet_str)
    
    if bet < DUEL_MIN:
        await callback.answer(f"❌ Минимальная ставка: {DUEL_MIN} NCoins", show_alert=True)
        return
    
    if user["balance"] < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {user['balance']}", show_alert=True)
        return
    
    # Сохраняем ставку в состоянии с таймаутом
    duel_requests[user_id] = {
        "bet": bet,
        "chat_id": callback.message.chat.id,
        "message_id": callback.message.message_id
    }
    
    # Устанавливаем таймаут
    asyncio.create_task(clear_duel_request(user_id, DUEL_TIMEOUT))
    
    await callback.message.edit_text(
        f"⚔️ *ДУЭЛЬ* ⚔️\n\n"
        f"💰 Ставка: *{bet}* NCoins\n\n"
        f"📝 Напишите @username противника в ответном сообщении.\n\n"
        f"❌ Для отмены отправьте /cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


async def clear_duel_request(user_id: int, delay: int):
    """Очистить запрос дуэли по таймауту"""
    await asyncio.sleep(delay)
    if user_id in duel_requests:
        del duel_requests[user_id]
        logger.info(f"Duel request for {user_id} timed out")


@router.message(Command("cancel"))
async def cancel_duel(message: types.Message):
    """Отмена дуэли"""
    user_id = message.from_user.id
    if user_id in duel_requests:
        del duel_requests[user_id]
        await message.answer("❌ Вызов на дуэль отменён.")
    else:
        await message.answer("ℹ️ Нет активного вызова на дуэль.")


@router.message(Command("duel"))
async def cmd_duel_start(message: types.Message):
    """Запуск дуэли по команде"""
    await cmd_games(message)


@router.message(lambda message: message.from_user.id in duel_requests and message.text and message.text.startswith('@'))
async def duel_process(message: types.Message):
    """Обработка вызова на дуэль"""
    user_id = message.from_user.id
    username = message.text.replace('@', '').strip()
    
    if user_id not in duel_requests:
        return
    
    bet = duel_requests[user_id]["bet"]
    del duel_requests[user_id]  # Удаляем состояние
    
    # Находим противника
    target_user = await db.get_user_by_username(username)
    
    if not target_user:
        await message.answer(f"❌ Пользователь @{username} не найден в базе!\n"
                           f"Попросите его активировать бота командой /start")
        return
    
    target_id = target_user["user_id"]
    target_name = target_user.get("first_name", username)
    
    if target_id == user_id:
        await message.answer("❌ Нельзя вызвать на дуэль самого себя!")
        return
    
    user = await db.get_user(user_id)
    target = await db.get_user(target_id)
    
    if target["balance"] < bet:
        await message.answer(f"❌ У @{username} недостаточно NCoins для дуэли!")
        return
    
    # Сохраняем запрос для противника
    duel_requests[target_id] = {
        "from_id": user_id,
        "from_name": message.from_user.first_name,
        "bet": bet,
        "chat_id": message.chat.id
    }
    
    # Таймаут для противника
    asyncio.create_task(clear_duel_request(target_id, DUEL_TIMEOUT))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ ДУЭЛЬ", callback_data=f"accept_duel_{target_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"reject_duel_{target_id}")]
    ])
    
    await message.answer(
        f"⚔️ *ВЫЗОВ НА ДУЭЛЬ!*\n\n"
        f"@{username}, вас вызвал на дуэль {message.from_user.first_name}\n"
        f"💰 Ставка: *{bet}* NCoins\n\n"
        f"Нажмите кнопку, чтобы принять вызов!\n"
        f"⏰ Вызов действителен 5 минут",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data and c.data.startswith("accept_duel_"))
async def accept_duel(callback: types.CallbackQuery):
    """Принять дуэль"""
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if target_id not in duel_requests:
        await callback.answer("❌ Вызов устарел!", show_alert=True)
        return
    
    request = duel_requests[target_id]
    from_id = request["from_id"]
    from_name = request["from_name"]
    bet = request["bet"]
    
    del duel_requests[target_id]  # Удаляем состояние
    
    user = await db.get_user(user_id)
    from_user = await db.get_user(from_id)
    
    if not user or not from_user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    
    if user["balance"] < bet:
        await callback.answer(f"❌ У вас недостаточно средств! Нужно {bet}", show_alert=True)
        return
    
    if from_user["balance"] < bet:
        await callback.answer(f"❌ У {from_name} недостаточно средств!", show_alert=True)
        return
    
    # Списываем ставки
    await db.update_balance(user_id, -bet, f"Дуэль с {from_name}")
    await db.update_balance(from_id, -bet, f"Дуэль с {callback.from_user.first_name}")
    
    # Случайный победитель
    winner_id = random.choice([user_id, from_id])
    
    if winner_id == user_id:
        win_amount = bet * 2
        await db.update_balance(user_id, win_amount, f"Выигрыш в дуэли")
        result_text = f"🎉 ПОБЕДИЛ {callback.from_user.first_name}! +{win_amount} NCoins!"
        
        await update_game_stats(user_id, True)
        await update_game_stats(from_id, False)
    else:
        win_amount = bet * 2
        await db.update_balance(from_id, win_amount, f"Выигрыш в дуэли")
        result_text = f"🎉 ПОБЕДИЛ {from_name}! +{win_amount} NCoins!"
        
        await update_game_stats(from_id, True)
        await update_game_stats(user_id, False)
    
    await update_specific_game_stat(user_id, "duel")
    await update_specific_game_stat(from_id, "duel")
    
    await callback.message.edit_text(
        f"⚔️ *РЕЗУЛЬТАТ ДУЭЛИ* ⚔️\n\n{result_text}",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("reject_duel_"))
async def reject_duel(callback: types.CallbackQuery):
    """Отклонить дуэль"""
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if target_id in duel_requests:
        request = duel_requests[target_id]
        del duel_requests[target_id]
        
        await callback.message.edit_text(f"❌ {callback.from_user.first_name} отклонил вызов на дуэль!")
        
        try:
            await callback.bot.send_message(
                request["from_id"],
                f"❌ {callback.from_user.first_name} отклонил ваш вызов на дуэль!"
            )
        except:
            pass
    
    await callback.answer()
