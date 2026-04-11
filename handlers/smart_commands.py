"""
Умный парсер команд NEXUS Bot
Понимает: игры, экономику, тэги, РП команды, голос
"""

import re
import random
import logging
from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import SLOT_COST, ROULETTE_MIN, DUEL_MIN, OPENAI_API_KEY

logger = logging.getLogger(__name__)
router = Router()

# Хранилище запросов дуэлей
duel_requests = {}
# Хранилище состояний
user_states = {}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def extract_number(text: str) -> int:
    """Извлечь число из текста (первое число)"""
    match = re.search(r'\b\d+\b', text)
    return int(match.group()) if match else 0


def extract_color(text: str) -> str:
    """Извлечь цвет для рулетки"""
    text = text.lower()
    if any(word in text for word in ['красн', 'red', '🔴']):
        return 'red'
    if any(word in text for word in ['черн', 'black', '⚫']):
        return 'black'
    return None


def extract_choice_rps(text: str) -> str:
    """Извлечь выбор для КНБ"""
    text = text.lower()
    if any(word in text for word in ['камень', 'rock', '🗿', 'камн']):
        return 'rock'
    if any(word in text for word in ['ножницы', 'scissors', '✂️', 'ножниц']):
        return 'scissors'
    if any(word in text for word in ['бумага', 'paper', '📄', 'бумаг']):
        return 'paper'
    return None


def extract_username(text: str) -> str:
    """Извлечь username из текста"""
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    return match.group(1) if match else None


def extract_amount(text: str) -> int:
    """Извлечь сумму перевода"""
    match = re.search(r'\b\d+\b', text)
    return int(match.group()) if match else 0


# ==================== ОБРАБОТЧИК ВСЕХ ТЕКСТОВЫХ КОМАНД ====================

@router.message(lambda message: message.text and not message.text.startswith('/'))
async def smart_parser(message: types.Message):
    """Универсальный умный парсер"""
    user_id = message.from_user.id
    text = message.text.strip().lower()
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("👋 Используйте /start для регистрации")
        return
    
    # ==================== ЭКОНОМИКА ====================
    if any(word in text for word in ['баланс', 'balance', 'сколько монет', 'мой баланс']):
        await handle_balance(message, user)
        return
    
    if any(word in text for word in ['ежедневный', 'daily', 'бонус', 'забрать бонус']):
        await handle_daily(message, user)
        return
    
    if 'переведи' in text or 'перевод' in text or 'transfer' in text:
        await handle_transfer(message, text, user)
        return
    
    # ==================== ПРОФИЛЬ ====================
    if any(word in text for word in ['профиль', 'profile', 'моя страница']):
        await handle_profile(message, user)
        return
    
    # ==================== ПОМОЩЬ ====================
    if any(word in text for word in ['помощь', 'help', 'что умеешь', 'команды']):
        await handle_help(message)
        return
    
    # ==================== ИГРЫ ====================
    # Слот
    if any(word in text for word in ['слот', 'slot', 'крути', 'барабаны', 'казино']):
        await handle_slot(message, message.text, user)
        return
    
    # Рулетка
    if any(word in text for word in ['рулетк', 'roulette', 'колесо']):
        await handle_roulette(message, message.text, user)
        return
    
    # КНБ
    if any(word in text for word in ['камень', 'ножницы', 'бумага', 'кнб', 'rps']):
        await handle_rps(message, message.text, user)
        return
    
    # Дуэль
    if any(word in text for word in ['дуэль', 'duel', 'бой', 'сражение']) and '@' in text:
        await handle_duel(message, message.text, user)
        return
    
    # ==================== ТЭГИ ====================
    if any(word in text for word in ['нексус', 'нэксус', 'nexus', 'некс', 'нэкс']):
        if any(word in text for word in ['оповести всех', 'общий сбор', 'собери всех', 'отметь всех', 'тэг всех']):
            await handle_tag_all(message)
            return
    
    # Обычный тэг пользователя
    if '@' in text and not any(word in text for word in ['дуэль', 'duel']):
        await handle_tag_user(message, text)
        return
    
    # ==================== РП КОМАНДЫ ====================
    rp_responses = {
        'привет': 'Привет! 👋 Рад тебя видеть!',
        'пока': 'Пока! 👋 Заходи ещё!',
        'спасибо': 'Пожалуйста! 🤗 Всегда рад помочь!',
        'молодец': 'Спасибо! 😊 Я стараюсь!',
        'красава': 'Благодарю! 🤝',
        'лох': 'Сам такой! 😜',
        'дурак': 'Без оскорблений, пожалуйста! 😇',
    }
    
    for key, response in rp_responses.items():
        if key in text:
            await message.answer(response)
            return
    
    # Если ничего не распознали — молчим (не спамим)


# ==================== ОБРАБОТЧИКИ ЭКОНОМИКИ ====================

async def handle_balance(message: types.Message, user: dict):
    """Показать баланс"""
    await message.answer(
        f"💰 *Ваш баланс:* {user['balance']} NCoins\n\n"
        f"📊 Побед: {user['wins']} | Поражений: {user['losses']}",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_daily(message: types.Message, user: dict):
    """Ежедневный бонус"""
    from datetime import datetime
    
    today = datetime.now().date().isoformat()
    last = user.get("last_daily")
    
    if last == today:
        await message.answer("⏰ Вы уже получили бонус сегодня! Возвращайтесь завтра.")
        return
    
    if last and (datetime.now().date() - datetime.fromisoformat(last).date()).days == 1:
        streak = user["daily_streak"] + 1
        bonus = 500 + (streak * 50)
    else:
        streak = 1
        bonus = 500
    
    await db.update_balance(message.from_user.id, bonus, f"Ежедневный бонус (стрик: {streak})")
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?", 
                   (streak, today, message.from_user.id))
    conn.commit()
    conn.close()
    
    await message.answer(
        f"🎁 *Ежедневный бонус!*\n\n"
        f"💰 +{bonus} NCoins\n"
        f"🔥 Стрик: {streak} дней",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_transfer(message: types.Message, text: str, user: dict):
    """Перевод монет"""
    username = extract_username(text)
    amount = extract_amount(text)
    
    if not username or amount == 0:
        await message.answer("❌ Использование: *переведи @user 100*", parse_mode=ParseMode.MARKDOWN)
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной!")
        return
    
    if user["balance"] < amount:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} NCoins")
        return
    
    # Поиск получателя
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{username} не найден")
        return
    
    target_id = row[0]
    
    if target_id == message.from_user.id:
        await message.answer("❌ Нельзя перевести монеты самому себе!")
        return
    
    await db.update_balance(message.from_user.id, -amount, f"Перевод @{username}")
    await db.update_balance(target_id, amount, f"Получен перевод от @{message.from_user.username or message.from_user.first_name}")
    
    await message.answer(f"✅ Переведено {amount} NCoins пользователю @{username}!")


async def handle_profile(message: types.Message, user: dict):
    """Показать профиль"""
    await message.answer(
        f"👤 *Профиль пользователя*\n\n"
        f"📛 Имя: {user.get('first_name', 'Не указано')}\n"
        f"💰 Баланс: {user['balance']} NCoins\n"
        f"⭐ VIP: {'Да' if user.get('vip_level', 0) > 0 else 'Нет'}\n"
        f"🏆 Победы: {user['wins']} | Поражения: {user['losses']}\n"
        f"🔥 Стрик: {user.get('daily_streak', 0)} дней",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_help(message: types.Message):
    """Показать помощь"""
    help_text = """
🤖 *NEXUS Bot — Помощь*

*💰 Экономика*
• баланс — проверить баланс
• ежедневный — бонус дня
• переведи @user 100 — перевод

*🎮 Игры*
• слот 100 — сыграть в слот
• рулетка 100 красный — рулетка
• камень — КНБ
• дуэль @user 100 — дуэль

*📢 Тэги*
• Нексус, оповести всех — общий сбор
• @user текст — упомянуть пользователя

*🔗 Рефералка*
• моя ссылка — получить реферальную ссылку

*📋 Команды*
• /start — начать
• /profile — профиль
• /vip — VIP статус
• /privacy — политика
• /delete_my_data — удалить данные
"""
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)


# ==================== ОБРАБОТЧИКИ ИГР ====================

async def handle_slot(message: types.Message, text: str, user: dict):
    """Слот-машина"""
    bet = extract_number(text)
    
    if bet == 0:
        await message.answer(
            "🎰 *Слот-машина*\n\n"
            "Напишите: *слот 100*\n"
            f"Минимальная ставка: {SLOT_COST} NCoins",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if bet < SLOT_COST:
        await message.answer(f"❌ Минимальная ставка: {SLOT_COST} NCoins")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} NCoins")
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
        
        await db.update_balance(message.from_user.id, win, "Выигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n{msg}\n💰 +{win} NCoins!"
        
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet // 2
        await db.update_balance(message.from_user.id, win, "Выигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n🎉 Выигрыш! +{win} NCoins!"
    else:
        await db.update_balance(message.from_user.id, -bet, "Проигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n😔 Проигрыш! -{bet} NCoins"
    
    await message.answer(response, parse_mode=ParseMode.MARKDOWN)


async def handle_roulette(message: types.Message, text: str, user: dict):
    """Рулетка"""
    bet = extract_number(text)
    color = extract_color(text)
    
    if bet == 0 or not color:
        await message.answer(
            "🎡 *Рулетка*\n\n"
            "Напишите: *рулетка 100 красный*\n"
            f"Минимальная ставка: {ROULETTE_MIN} NCoins",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if bet < ROULETTE_MIN:
        await message.answer(f"❌ Минимальная ставка: {ROULETTE_MIN} NCoins")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} NCoins")
        return
    
    result_color = random.choice(["red", "black"])
    color_names = {"red": "🔴 КРАСНОЕ", "black": "⚫ ЧЁРНОЕ"}
    
    if color == result_color:
        win = bet * 2
        await db.update_balance(message.from_user.id, win, "Выигрыш в рулетке")
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n\n🎉 ВЫ ВЫИГРАЛИ! +{win} NCoins!"
    else:
        await db.update_balance(message.from_user.id, -bet, "Проигрыш в рулетке")
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n\n😔 Вы проиграли {bet} NCoins"
    
    await message.answer(response, parse_mode=ParseMode.MARKDOWN)


async def handle_rps(message: types.Message, text: str, user: dict):
    """Камень-ножницы-бумага"""
    choice = extract_choice_rps(text)
    
    if not choice:
        await message.answer(
            "✂️ *Камень-ножницы-бумага*\n\n"
            "Напишите: *камень*, *ножницы* или *бумага*\n"
            "💰 Ставка: 50 NCoins",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    bet = 50
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Нужно {bet} NCoins")
        return
    
    bot_choice = random.choice(["rock", "scissors", "paper"])
    choice_names = {"rock": "🗿 камень", "scissors": "✂️ ножницы", "paper": "📄 бумага"}
    
    if choice == bot_choice:
        result = 0
        msg = "🤝 Ничья!"
    elif (choice == "rock" and bot_choice == "scissors") or \
         (choice == "scissors" and bot_choice == "paper") or \
         (choice == "paper" and bot_choice == "rock"):
        result = bet
        msg = f"✅ Победа! +{bet} NCoins!"
    else:
        result = -bet
        msg = f"❌ Поражение! -{bet} NCoins"
    
    await db.update_balance(message.from_user.id, result, "Игра КНБ")
    
    await message.answer(
        f"✂️ *Камень-ножницы-бумага*\n\n"
        f"Вы: {choice_names[choice]}\n"
        f"Бот: {choice_names[bot_choice]}\n\n"
        f"{msg}",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_duel(message: types.Message, text: str, user: dict):
    """Дуэль с игроком"""
    username = extract_username(text)
    bet = extract_number(text)
    
    if not username or bet == 0:
        await message.answer(
            "⚔️ *Дуэль*\n\n"
            "Напишите: *дуэль @user 100*\n"
            f"Минимальная ставка: {DUEL_MIN} NCoins",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if bet < DUEL_MIN:
        await message.answer(f"❌ Минимальная ставка: {DUEL_MIN} NCoins")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} NCoins")
        return
    
    # Поиск противника
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
    
    if target_id == message.from_user.id:
        await message.answer("❌ Нельзя вызвать на дуэль самого себя!")
        return
    
    target = await db.get_user(target_id)
    if not target or target["balance"] < bet:
        await message.answer(f"❌ У @{username} недостаточно средств для дуэли!")
        return
    
    # Сохраняем запрос
    duel_requests[target_id] = {
        "from_id": message.from_user.id,
        "from_name": message.from_user.first_name,
        "bet": bet,
        "chat_id": message.chat.id
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"accept_duel_{target_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"reject_duel_{target_id}")]
    ])
    
    await message.answer(
        f"⚔️ *ДУЭЛЬ!*\n\n"
        f"@{username}, вас вызвал на дуэль {message.from_user.first_name}\n"
        f"💰 Ставка: {bet} NCoins",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


# ==================== ТЭГИ ====================

async def handle_tag_all(message: types.Message):
    """Общий сбор"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
    ])
    
    await message.answer(
        "📢 *ОБЩИЙ СБОР*\n\n"
        "Будет отправлено несколько сообщений с упоминаниями участников.\n\n"
        "⚠️ Каждый участник получит ЛИЧНОЕ уведомление!\n\n"
        "Начать?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def handle_tag_user(message: types.Message, text: str):
    """Тэг пользователя"""
    username_match = re.search(r'@([a-zA-Z0-9_]+)', text)
    if not username_match:
        return
    
    username = username_match.group(1)
    clean_text = re.sub(r'@\w+', '', text).strip()
    
    if clean_text:
        result = f"🔔 {clean_text}\n\n👉 @{username}"
    else:
        result = f"🔔 Вас упомянул {message.from_user.full_name}\n\n👉 @{username}"
    
    await message.answer(result)


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data and c.data.startswith("accept_duel_"))
async def accept_duel_callback(callback: types.CallbackQuery):
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
    else:
        win_amount = bet * 2
        await db.update_balance(from_id, win_amount, f"Выигрыш в дуэли")
        result_text = f"🎉 ПОБЕДИЛ {from_name}! +{win_amount} NCoins!"
    
    del duel_requests[target_id]
    
    await callback.message.edit_text(f"⚔️ *РЕЗУЛЬТАТ ДУЭЛИ*\n\n{result_text}", parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("reject_duel_"))
async def reject_duel_callback(callback: types.CallbackQuery):
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


@router.callback_query(lambda c: c.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery):
    """Начать общий сбор"""
    from handlers.tag import start_all
    await start_all(callback)


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery):
    """Отменить общий сбор"""
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


# ==================== ГОЛОСОВЫЕ КОМАНДЫ ====================

@router.message(lambda message: message.voice)
async def voice_handler(message: types.Message):
    """Обработка голосовых команд"""
    if not OPENAI_API_KEY:
        # Без OpenAI просто игнорируем голос
        return
    
    try:
        from openai import AsyncOpenAI
        import aiofiles
        
        processing_msg = await message.answer("🎤 Распознаю голос...")
        
        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_path = f"/tmp/voice_{message.message_id}.ogg"
        
        await message.bot.download_file(file.file_path, file_path)
        
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        async with aiofiles.open(file_path, 'rb') as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru"
            )
        
        import os
        os.remove(file_path)
        
        recognized_text = transcript.text.lower()
        
        await processing_msg.edit_text(f"🎤 Распознано: *{recognized_text}*", parse_mode=ParseMode.MARKDOWN)
        
        # Подменяем текст и обрабатываем
        message.text = recognized_text
        await smart_parser(message)
        
    except Exception as e:
        logger.error(f"Голос: {e}")
