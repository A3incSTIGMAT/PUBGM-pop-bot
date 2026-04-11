"""
Модуль игр NEXUS Bot
Слот-машина, рулетка, дуэль, камень-ножницы-бумага
"""

import random
import re
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import SLOT_COST, ROULETTE_MIN, DUEL_MIN

router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def parse_amount(text: str) -> int:
    """Извлечь число из текста"""
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 0


def parse_color(text: str) -> str:
    """Извлечь цвет (красный/черный)"""
    text = text.lower()
    if 'красн' in text or 'red' in text:
        return 'red'
    if 'черн' in text or 'black' in text:
        return 'black'
    return None


def parse_rps_choice(text: str) -> str:
    """Извлечь выбор для КНБ"""
    text = text.lower()
    if any(word in text for word in ['камень', 'rock', '🗿']):
        return 'rock'
    if any(word in text for word in ['ножницы', 'scissors', '✂️']):
        return 'scissors'
    if any(word in text for word in ['бумага', 'paper', '📄']):
        return 'paper'
    return None


def choice_to_emoji(choice: str) -> str:
    """Преобразовать выбор в эмодзи"""
    emojis = {"rock": "🗿", "scissors": "✂️", "paper": "📄"}
    return emojis.get(choice, "?")


def get_games_keyboard():
    """Клавиатура игр"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Слот", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel"),
         InlineKeyboardButton(text="✂️ КНБ", callback_data="game_rps")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    return keyboard


# ==================== ОБНОВЛЕНИЕ VIP ПРИ ПОБЕДАХ ====================

async def update_vip_by_wins(user_id: int) -> bool:
    """Обновляет VIP статус пользователя на основе побед"""
    user = await db.get_user(user_id)
    if not user:
        return False
    
    wins = user.get("wins", 0)
    current_vip = user.get("vip_level", 0)
    
    # Определяем новый уровень VIP
    new_vip = 0
    if wins >= 100:
        new_vip = 3
    elif wins >= 50:
        new_vip = 2
    elif wins >= 10:
        new_vip = 1
    
    # Обновляем если изменилось
    if new_vip > current_vip:
        from datetime import datetime, timedelta
        new_until = (datetime.now() + timedelta(days=30)).isoformat()
        
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET vip_level = ?, vip_until = ? WHERE user_id = ?", 
                       (new_vip, new_until, user_id))
        conn.commit()
        conn.close()
        return True
    return False


# ==================== СЛОТ-МАШИНА ====================

async def play_slot(user_id: int, bet: int):
    """Слот-машина"""
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
        
        await db.update_balance(user_id, win, f"Выигрыш в слоте")
        return win, f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n{msg}\n💰 +{win} монет!"
    
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet // 2
        await db.update_balance(user_id, win, f"Выигрыш в слоте")
        return win, f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n🎉 Выигрыш! +{win} монет!"
    
    else:
        await db.update_balance(user_id, -bet, f"Проигрыш в слоте")
        return -bet, f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n😔 Проигрыш! -{bet} монет."


@router.message(Command("slot"))
async def cmd_slot(message: types.Message):
    """Слот-машина"""
    user_id = message.from_user.id
    bet = parse_amount(message.text)
    
    if bet == 0:
        await message.answer(
            "🎰 *Слот-машина*\n\n"
            "Использование: `/slot 100`\n"
            f"Минимальная ставка: {SLOT_COST} монет\n\n"
            "✨ *Выигрыши:*\n"
            "├ 💎💎💎 → x10\n"
            "├ ⭐⭐⭐ → x5\n"
            "└ 🍒🍒🍒 → x3",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if bet < SLOT_COST:
        await message.answer(f"❌ Минимальная ставка: {SLOT_COST} монет")
        return
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} монет")
        return
    
    win, response = await play_slot(user_id, bet)
    
    # Обновляем статистику и VIP
    if win > 0:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        upgraded = await update_vip_by_wins(user_id)
        if upgraded:
            response += "\n\n🎉 *ПОЗДРАВЛЯЮ!* Вы получили новый VIP уровень! 🎉"
    elif win < 0:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    await message.answer(response, parse_mode=ParseMode.MARKDOWN)


# ==================== РУЛЕТКА ====================

@router.message(Command("roulette"))
async def cmd_roulette(message: types.Message):
    """Рулетка"""
    user_id = message.from_user.id
    
    bet = parse_amount(message.text)
    color = parse_color(message.text)
    
    if bet == 0 or not color:
        await message.answer(
            "🎡 *Рулетка*\n\n"
            "Использование: `/roulette 100 красный`\n"
            f"Минимальная ставка: {ROULETTE_MIN} монет\n\n"
            "Цвета: красный, черный\n"
            "💰 Выигрыш: x2 от ставки",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if bet < ROULETTE_MIN:
        await message.answer(f"❌ Минимальная ставка: {ROULETTE_MIN} монет")
        return
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} монет")
        return
    
    result_color = random.choice(["red", "black"])
    color_names = {"red": "🔴 КРАСНОЕ", "black": "⚫ ЧЁРНОЕ"}
    
    if color == result_color:
        win = bet * 2
        await db.update_balance(user_id, win, f"Выигрыш в рулетке")
        
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        upgraded = await update_vip_by_wins(user_id)
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n🎉 ВЫ ВЫИГРАЛИ! +{win} монет!"
        if upgraded:
            response += "\n\n🎉 *ПОЗДРАВЛЯЮ!* Вы получили новый VIP уровень! 🎉"
    else:
        await db.update_balance(user_id, -bet, f"Проигрыш в рулетке")
        
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n😔 Вы проиграли {bet} монет"
    
    await message.answer(response, parse_mode=ParseMode.MARKDOWN)


# ==================== КАМЕНЬ-НОЖНИЦЫ-БУМАГА ====================

async def play_rps(user_choice: str, bot_choice: str, bet: int):
    """Игра в КНБ"""
    rules = {
        ("rock", "scissors"): ("win", "🗿 камень разбивает ✂️ ножницы!"),
        ("scissors", "paper"): ("win", "✂️ ножницы режут 📄 бумагу!"),
        ("paper", "rock"): ("win", "📄 бумага оборачивает 🗿 камень!"),
        ("scissors", "rock"): ("lose", "🗿 камень разбивает ✂️ ножницы!"),
        ("paper", "scissors"): ("lose", "✂️ ножницы режут 📄 бумагу!"),
        ("rock", "paper"): ("lose", "📄 бумага оборачивает 🗿 камень!"),
    }
    
    if user_choice == bot_choice:
        return 0, f"🤝 Ничья! Оба выбрали {choice_to_emoji(user_choice)}"
    
    result, msg = rules.get((user_choice, bot_choice), ("lose", ""))
    if result == "win":
        return bet, f"✅ Победа! {msg}\n💰 Вы выиграли {bet} монет!"
    return -bet, f"❌ Поражение! {msg}\n😔 Вы проиграли {bet} монет."


@router.message(Command("rps"))
async def cmd_rps(message: types.Message):
    """Камень-ножницы-бумага"""
    user_id = message.from_user.id
    choice = parse_rps_choice(message.text)
    
    if not choice:
        await message.answer(
            "✂️ *Камень-ножницы-бумага*\n\n"
            "Использование: `/rps камень`\n"
            "Варианты: камень, ножницы, бумага\n\n"
            "💰 Ставка: 50 монет",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    bet = 50
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Нужно {bet} монет")
        return
    
    bot_choice = random.choice(["rock", "scissors", "paper"])
    choice_names = {"rock": "🗿 камень", "scissors": "✂️ ножницы", "paper": "📄 бумага"}
    
    result, msg = await play_rps(choice, bot_choice, bet)
    
    await db.update_balance(user_id, result, f"Игра КНБ")
    
    if result > 0:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        upgraded = await update_vip_by_wins(user_id)
        if upgraded:
            msg += "\n\n🎉 *ПОЗДРАВЛЯЮ!* Вы получили новый VIP уровень! 🎉"
    elif result < 0:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    await message.answer(
        f"✂️ *Камень-ножницы-бумага*\n\n"
        f"Вы: {choice_names[choice]}\n"
        f"Бот: {choice_names[bot_choice]}\n\n"
        f"{msg}",
        parse_mode=ParseMode.MARKDOWN
    )


# ==================== ДУЭЛЬ С ДРУГИМ ИГРОКОМ ====================

duel_requests = {}


@router.message(Command("duel"))
async def cmd_duel(message: types.Message):
    """Дуэль с другим игроком"""
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer(
            "⚔️ *Дуэль*\n\n"
            "Использование: `/duel @username 100`\n"
            f"Минимальная ставка: {DUEL_MIN} монет\n\n"
            "Противник должен принять дуэль командой /accept",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    username = args[1].replace('@', '')
    try:
        bet = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    if bet < DUEL_MIN:
        await message.answer(f"❌ Минимальная ставка: {DUEL_MIN} монет")
        return
    
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} монет")
        return
    
    # Находим противника
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, first_name FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{username} не найден")
        return
    
    target_id = row[0]
    target_name = row[1]
    
    if target_id == user_id:
        await message.answer("❌ Нельзя вызвать на дуэль самого себя!")
        return
    
    # Сохраняем запрос на дуэль
    duel_requests[target_id] = {
        "from_id": user_id,
        "from_name": message.from_user.first_name,
        "bet": bet,
        "chat_id": message.chat.id
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять дуэль", callback_data=f"accept_duel_{target_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_duel_{target_id}")]
    ])
    
    await message.answer(
        f"⚔️ *Дуэль!*\n\n"
        f"@{username}, вас вызвал на дуэль {message.from_user.first_name}\n"
        f"💰 Ставка: {bet} монет\n\n"
        f"Нажмите кнопку ниже, чтобы принять вызов.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data and c.data.startswith("accept_duel_"))
async def accept_duel(callback: types.CallbackQuery):
    """Принять дуэль"""
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам адресован вызов!", show_alert=True)
        return
    
    if target_id not in duel_requests:
        await callback.answer("❌ Вызов устарел", show_alert=True)
        return
    
    request = duel_requests[target_id]
    from_id = request["from_id"]
    bet = request["bet"]
    from_name = request["from_name"]
    
    # Проверяем балансы
    user = await db.get_user(user_id)
    from_user = await db.get_user(from_id)
    
    if not user or not from_user:
        await callback.message.edit_text("❌ Ошибка: пользователь не найден")
        await callback.answer()
        return
    
    if user["balance"] < bet:
        await callback.message.edit_text(f"❌ У вас недостаточно средств! Нужно {bet} монет")
        await callback.answer()
        return
    
    if from_user["balance"] < bet:
        await callback.message.edit_text(f"❌ У {from_name} недостаточно средств! Дуэль отменена")
        await callback.answer()
        return
    
    # Списываем ставки
    await db.update_balance(user_id, -bet, f"Дуэль с {from_name} (ставка)")
    await db.update_balance(from_id, -bet, f"Дуэль с {callback.from_user.first_name} (ставка)")
    
    # Играем в КНБ
    choices = ["rock", "scissors", "paper"]
    user_choice = random.choice(choices)
    bot_choice = random.choice(choices)
    
    rules = {
        ("rock", "scissors"): "user",
        ("scissors", "paper"): "user",
        ("paper", "rock"): "user",
        ("scissors", "rock"): "bot",
        ("paper", "scissors"): "bot",
        ("rock", "paper"): "bot",
    }
    
    winner = rules.get((user_choice, bot_choice), "draw")
    
    if winner == "user":
        win_amount = bet * 2
        await db.update_balance(user_id, win_amount, f"Выигрыш в дуэли с {from_name}")
        result_text = f"🎉 Победил {callback.from_user.first_name}! +{win_amount} монет!"
        
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (from_id,))
        conn.commit()
        conn.close()
        
        upgraded = await update_vip_by_wins(user_id)
        if upgraded:
            result_text += "\n\n🎉 *ПОЗДРАВЛЯЮ!* Вы получили новый VIP уровень! 🎉"
        
    elif winner == "bot":
        win_amount = bet * 2
        await db.update_balance(from_id, win_amount, f"Выигрыш в дуэли с {callback.from_user.first_name}")
        result_text = f"🎉 Победил {from_name}! +{win_amount} монет!"
        
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (from_id,))
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        upgraded = await update_vip_by_wins(from_id)
        if upgraded:
            result_text += "\n\n🎉 *ПОЗДРАВЛЯЮ!* Победитель получил новый VIP уровень! 🎉"
        
    else:
        await db.update_balance(user_id, bet, "Ничья в дуэли (возврат)")
        await db.update_balance(from_id, bet, "Ничья в дуэли (возврат)")
        result_text = "🤝 Ничья! Ставки возвращены."
    
    # Удаляем запрос
    del duel_requests[target_id]
    
    await callback.message.edit_text(
        f"⚔️ *Результат дуэли*\n\n"
        f"Участники:\n"
        f"├ {from_name} → {choice_to_emoji(bot_choice)}\n"
        f"└ {callback.from_user.first_name} → {choice_to_emoji(user_choice)}\n\n"
        f"{result_text}",
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
        from_name = request["from_name"]
        del duel_requests[target_id]
        
        await callback.message.edit_text(f"❌ {callback.from_user.first_name} отклонил вызов на дуэль!")
        
        await callback.bot.send_message(
            request["from_id"],
            f"❌ {callback.from_user.first_name} отклонил ваш вызов на дуэль!"
        )
    
    await callback.answer()


# ==================== КНОПКИ ИГР ====================

@router.callback_query(lambda c: c.data == "games")
async def games_menu(callback: types.CallbackQuery):
    """Меню игр"""
    await callback.message.edit_text(
        "🎮 *Игры NEXUS Bot*\n\n"
        "Выберите игру:\n\n"
        "🎰 *Слот* — /slot 100\n"
        "🎡 *Рулетка* — /roulette 100 красный\n"
        "✂️ *КНБ* — /rps камень\n"
        "⚔️ *Дуэль* — /duel @user 100\n\n"
        f"💰 Минимальные ставки:\n"
        f"Слот: {SLOT_COST}, Рулетка: {ROULETTE_MIN}, Дуэль: {DUEL_MIN}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "game_slot")
async def game_slot_info(callback: types.CallbackQuery):
    """Информация о слоте"""
    await callback.message.edit_text(
        "🎰 *Слот-машина*\n\n"
        "Команда: `/slot 100`\n"
        f"Минимальная ставка: {SLOT_COST} монет\n\n"
        "✨ *Выигрыши:*\n"
        "├ 💎💎💎 → x10 от ставки\n"
        "├ ⭐⭐⭐ → x5 от ставки\n"
        "├ 🍒🍒🍒 → x3 от ставки\n"
        "└ 🍒🍒🍊 → x0.5 от ставки\n\n"
        "Пример: `/slot 100` — сделать ставку 100 монет",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "game_roulette")
async def game_roulette_info(callback: types.CallbackQuery):
    """Информация о рулетке"""
    await callback.message.edit_text(
        "🎡 *Рулетка*\n\n"
        "Команда: `/roulette 100 красный`\n"
        f"Минимальная ставка: {ROULETTE_MIN} монет\n\n"
        "Цвета: красный, черный\n"
        "💰 Выигрыш: x2 от ставки\n\n"
        "Пример: `/roulette 100 красный`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "game_rps")
async def game_rps_info(callback: types.CallbackQuery):
    """Информация о КНБ"""
    await callback.message.edit_text(
        "✂️ *Камень-ножницы-бумага*\n\n"
        "Команда: `/rps камень`\n"
        "💰 Ставка: 50 монет\n\n"
        "Варианты: камень, ножницы, бумага\n\n"
        "Пример: `/rps камень`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "game_duel")
async def game_duel_info(callback: types.CallbackQuery):
    """Информация о дуэли"""
    await callback.message.edit_text(
        "⚔️ *Дуэль*\n\n"
        "Команда: `/duel @username 100`\n"
        f"Минимальная ставка: {DUEL_MIN} монет\n\n"
        "1. Вы вызываете игрока на дуэль\n"
        "2. Противник принимает вызов\n"
        "3. Бот случайно определяет победителя\n"
        "4. Победитель забирает обе ставки\n\n"
        "Пример: `/duel @user 100`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()
