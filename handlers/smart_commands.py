"""
Умный парсер команд NEXUS Bot
Поддерживает: текст, голос, команды без /
"""

import re
import asyncio
import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import SLOT_COST, ROULETTE_MIN, DUEL_MIN, OPENAI_API_KEY

logger = logging.getLogger(__name__)
router = Router()

# Временное хранилище для состояний
user_states = {}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def extract_number(text: str) -> int:
    """Извлечь число из текста"""
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 0


def extract_color(text: str) -> str:
    """Извлечь цвет (красный/черный)"""
    text = text.lower()
    if 'красн' in text or 'red' in text or '🔴' in text:
        return 'red'
    if 'черн' in text or 'black' in text or '⚫' in text:
        return 'black'
    return None


def extract_choice_rps(text: str) -> str:
    """Извлечь выбор для КНБ"""
    text = text.lower()
    
    # Камень
    if any(word in text for word in ['камень', 'rock', '🗿', 'камен', 'камн']):
        return 'rock'
    
    # Ножницы
    if any(word in text for word in ['ножницы', 'scissors', '✂️', 'ножниц', 'нож']):
        return 'scissors'
    
    # Бумага
    if any(word in text for word in ['бумага', 'paper', '📄', 'бумаг', 'бум']):
        return 'paper'
    
    return None


def extract_username(text: str) -> str:
    """Извлечь username из текста"""
    match = re.search(r'@(\w+)', text)
    return match.group(1) if match else None


def detect_game(text: str) -> str:
    """Определить, в какую игру хочет играть пользователь"""
    text = text.lower()
    
    # Слот
    if any(word in text for word in ['слот', 'slot', 'крути', 'бараба', 'слоты', 'играй слот', 'казино']):
        return 'slot'
    
    # Рулетка
    if any(word in text for word in ['рулетк', 'roulette', 'рулетка', 'колесо', 'ставк', 'красн', 'черн']):
        return 'roulette'
    
    # КНБ
    if any(word in text for word in ['камень', 'ножницы', 'бумага', 'кнб', 'rps']):
        return 'rps'
    
    # Дуэль
    if any(word in text for word in ['дуэль', 'duel', 'бой', 'сражени', 'вызов']) and '@' in text:
        return 'duel'
    
    return None


# ==================== ОБРАБОТЧИК ТЕКСТОВЫХ КОМАНД ====================

@router.message(lambda message: message.text and not message.text.startswith('/'))
async def smart_parser(message: types.Message):
    """Умный парсер текстовых команд"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Проверяем, есть ли пользователь в БД
    user = await db.get_user(user_id)
    if not user:
        await message.answer("👋 Привет! Используйте /start для регистрации")
        return
    
    # Определяем игру
    game = detect_game(text)
    
    if game == 'slot':
        await handle_slot(message, text, user)
    elif game == 'roulette':
        await handle_roulette(message, text, user)
    elif game == 'rps':
        await handle_rps(message, text, user)
    elif game == 'duel':
        await handle_duel(message, text, user)
    else:
        # Не распознали игру — показываем меню
        await show_game_help(message)


# ==================== ОБРАБОТЧИК ГОЛОСОВЫХ КОМАНД ====================

@router.message(lambda message: message.voice)
async def voice_command_handler(message: types.Message):
    """Обработка голосовых команд"""
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("👋 Используйте /start для регистрации")
        return
    
    # Отправляем сообщение о распознавании
    processing_msg = await message.answer("🎤 Распознаю голосовую команду... ⏳")
    
    # Пытаемся распознать голос (через OpenAI Whisper)
    recognized_text = await recognize_voice(message)
    
    if not recognized_text:
        await processing_msg.edit_text(
            "❌ Не удалось распознать голосовую команду.\n\n"
            "Попробуйте:\n"
            "• Говорите чётче\n"
            "• Используйте текстовые команды\n"
            "• Напишите /help для списка команд"
        )
        return
    
    await processing_msg.edit_text(f"🎤 Распознано: *{recognized_text}*\n\n🔄 Обрабатываю...", parse_mode=ParseMode.MARKDOWN)
    
    # Обрабатываем распознанный текст
    game = detect_game(recognized_text)
    
    if game == 'slot':
        await handle_slot(message, recognized_text, user, edit_msg=processing_msg)
    elif game == 'roulette':
        await handle_roulette(message, recognized_text, user, edit_msg=processing_msg)
    elif game == 'rps':
        await handle_rps(message, recognized_text, user, edit_msg=processing_msg)
    elif game == 'duel':
        await handle_duel(message, recognized_text, user, edit_msg=processing_msg)
    else:
        await processing_msg.edit_text(
            "🎤 *Голосовая команда*\n\n"
            f"Распознано: \"{recognized_text}\"\n\n"
            "❌ Не удалось определить игру.\n\n"
            "Попробуйте:\n"
            "• \"Слот на 100\"\n"
            "• \"Рулетка 50 красный\"\n"
            "• \"Камень\"\n"
            "• \"Дуэль @user 100\"",
            parse_mode=ParseMode.MARKDOWN
        )


async def recognize_voice(message: types.Message) -> str:
    """Распознавание голосового сообщения через OpenAI Whisper"""
    if not OPENAI_API_KEY:
        # Если нет OpenAI, используем заглушку
        return None
    
    try:
        from openai import AsyncOpenAI
        
        # Получаем файл голосового сообщения
        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_path = f"/tmp/voice_{message.message_id}.ogg"
        
        # Скачиваем файл
        await message.bot.download_file(file.file_path, file_path)
        
        # Отправляем в Whisper
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        with open(file_path, 'rb') as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru"
            )
        
        # Удаляем временный файл
        import os
        os.remove(file_path)
        
        return transcript.text.lower()
        
    except Exception as e:
        logger.error(f"Ошибка распознавания голоса: {e}")
        return None


# ==================== ОБРАБОТЧИКИ ИГР ====================

async def handle_slot(message: types.Message, text: str, user: dict, edit_msg: types.Message = None):
    """Обработка слота"""
    bet = extract_number(text)
    
    if bet == 0:
        response = (
            "🎰 *Слот-машина*\n\n"
            "Напишите: *слот 100*\n"
            f"Минимальная ставка: {SLOT_COST} монет\n\n"
            "✨ *Выигрыши:*\n"
            "├ 💎💎💎 → x10\n"
            "├ ⭐⭐⭐ → x5\n"
            "├ 🍒🍒🍒 → x3\n"
            "└ 🍒🍒🍊 → x0.5\n\n"
            "Пример: *слот на 200 монет*"
        )
        if edit_msg:
            await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer(response, parse_mode=ParseMode.MARKDOWN)
        return
    
    if bet < SLOT_COST:
        response = f"❌ Минимальная ставка: {SLOT_COST} монет"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    if user["balance"] < bet:
        response = f"❌ Недостаточно средств! Ваш баланс: {user['balance']} монет"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    # Играем в слот
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
        
        await db.update_balance(message.from_user.id, win, f"Выигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n{msg}\n💰 +{win} монет!"
        
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet // 2
        await db.update_balance(message.from_user.id, win, f"Выигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n🎉 Выигрыш! +{win} монет!"
        
    else:
        await db.update_balance(message.from_user.id, -bet, f"Проигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n😔 Проигрыш! -{bet} монет."
    
    if edit_msg:
        await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(response, parse_mode=ParseMode.MARKDOWN)


async def handle_roulette(message: types.Message, text: str, user: dict, edit_msg: types.Message = None):
    """Обработка рулетки"""
    bet = extract_number(text)
    color = extract_color(text)
    
    if bet == 0 or not color:
        response = (
            "🎡 *Рулетка*\n\n"
            "Напишите: *рулетка 100 красный*\n"
            f"Минимальная ставка: {ROULETTE_MIN} монет\n\n"
            "Цвета: красный, черный\n"
            "💰 Выигрыш: x2 от ставки\n\n"
            "Примеры:\n"
            "• *рулетка 50 красный*\n"
            "• *сыграй в рулетку на 100 чёрное*"
        )
        if edit_msg:
            await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer(response, parse_mode=ParseMode.MARKDOWN)
        return
    
    if bet < ROULETTE_MIN:
        response = f"❌ Минимальная ставка: {ROULETTE_MIN} монет"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    if user["balance"] < bet:
        response = f"❌ Недостаточно средств! Ваш баланс: {user['balance']} монет"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    result_color = random.choice(["red", "black"])
    color_names = {"red": "🔴 КРАСНОЕ", "black": "⚫ ЧЁРНОЕ"}
    
    if color == result_color:
        win = bet * 2
        await db.update_balance(message.from_user.id, win, f"Выигрыш в рулетке")
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n🎉 ВЫ ВЫИГРАЛИ! +{win} монет!"
    else:
        await db.update_balance(message.from_user.id, -bet, f"Проигрыш в рулетке")
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n😔 Вы проиграли {bet} монет."
    
    if edit_msg:
        await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(response, parse_mode=ParseMode.MARKDOWN)


async def handle_rps(message: types.Message, text: str, user: dict, edit_msg: types.Message = None):
    """Обработка КНБ"""
    choice = extract_choice_rps(text)
    
    if not choice:
        response = (
            "✂️ *Камень-ножницы-бумага*\n\n"
            "Напишите: *камень*, *ножницы* или *бумага*\n"
            "💰 Ставка: 50 монет\n\n"
            "Примеры:\n"
            "• *камень*\n"
            "• *играем в ножницы*\n"
            "• *давай бумага*"
        )
        if edit_msg:
            await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer(response, parse_mode=ParseMode.MARKDOWN)
        return
    
    bet = 50
    
    if user["balance"] < bet:
        response = f"❌ Недостаточно средств! Нужно {bet} монет"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    bot_choice = random.choice(["rock", "scissors", "paper"])
    choice_names = {"rock": "🗿 камень", "scissors": "✂️ ножницы", "paper": "📄 бумага"}
    
    # Определяем победителя
    if choice == bot_choice:
        result = 0
        result_text = "🤝 Ничья!"
    elif (choice == "rock" and bot_choice == "scissors") or \
         (choice == "scissors" and bot_choice == "paper") or \
         (choice == "paper" and bot_choice == "rock"):
        result = bet
        result_text = f"✅ Победа! +{bet} монет!"
    else:
        result = -bet
        result_text = f"❌ Поражение! -{bet} монет"
    
    await db.update_balance(message.from_user.id, result, f"Игра КНБ")
    
    response = (
        f"✂️ *Камень-ножницы-бумага*\n\n"
        f"Вы: {choice_names[choice]}\n"
        f"Бот: {choice_names[bot_choice]}\n\n"
        f"{result_text}"
    )
    
    if edit_msg:
        await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(response, parse_mode=ParseMode.MARKDOWN)


async def handle_duel(message: types.Message, text: str, user: dict, edit_msg: types.Message = None):
    """Обработка дуэли"""
    username = extract_username(text)
    bet = extract_number(text)
    
    if not username or bet == 0:
        response = (
            "⚔️ *Дуэль*\n\n"
            "Напишите: *дуэль @username 100*\n"
            f"Минимальная ставка: {DUEL_MIN} монет\n\n"
            "Пример: *дуэль @user 100*"
        )
        if edit_msg:
            await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer(response, parse_mode=ParseMode.MARKDOWN)
        return
    
    if bet < DUEL_MIN:
        response = f"❌ Минимальная ставка: {DUEL_MIN} монет"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    if user["balance"] < bet:
        response = f"❌ Недостаточно средств! Ваш баланс: {user['balance']} монет"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    # Находим противника
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, first_name FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        response = f"❌ Пользователь @{username} не найден"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    target_id = row[0]
    target_name = row[1]
    
    if target_id == message.from_user.id:
        response = "❌ Нельзя вызвать на дуэль самого себя!"
        if edit_msg:
            await edit_msg.edit_text(response)
        else:
            await message.answer(response)
        return
    
    # Сохраняем запрос
    if not hasattr(handle_duel, 'duel_requests'):
        handle_duel.duel_requests = {}
    
    handle_duel.duel_requests[target_id] = {
        "from_id": message.from_user.id,
        "from_name": message.from_user.first_name,
        "bet": bet,
        "chat_id": message.chat.id
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять дуэль", callback_data=f"accept_duel_{target_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_duel_{target_id}")]
    ])
    
    response = f"⚔️ *Дуэль!*\n\n@{username}, вас вызвал на дуэль {message.from_user.first_name}\n💰 Ставка: {bet} монет"
    
    if edit_msg:
        await edit_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    else:
        await message.answer(response, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


async def show_game_help(message: types.Message):
    """Показать помощь по играм"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Слот", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="game_rps"),
         InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main_menu")]
    ])
    
    await message.answer(
        "🎮 *Доступные игры*\n\n"
        "Просто напишите:\n"
        "• *слот 100* — сыграть в слот\n"
        "• *рулетка 100 красный* — рулетка\n"
        "• *камень* — камень-ножницы-бумага\n"
        "• *дуэль @user 100* — дуэль с другом\n\n"
        "🗣️ *Голосовые команды*\n"
        "Отправьте голосовое сообщение, и я распознаю команду!\n\n"
        "Примеры:\n"
        "• \"Слот на 200\"\n"
        "• \"Рулетка 50 красный\"\n"
        "• \"Камень\"\n"
        "• \"Дуэль @user 100\"",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


# ==================== КОМАНДА /ALL С ВОЗРАСТОМ ====================

@router.message(Command("all"))
async def cmd_all(message: types.Message):
    """Команда /all — запрос возраста перед упоминанием"""
    user_id = message.from_user.id
    
    # Проверяем, есть ли пользователь в БД
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    # Сохраняем состояние — ожидаем возраст
    user_states[user_id] = {"action": "waiting_age_for_all"}
    
    await message.answer(
        "📢 *Команда /all*\n\n"
        "Для массового упоминания участников, пожалуйста, укажите ваш возраст.\n\n"
        "Напишите ваш возраст (число):",
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(lambda message: user_states.get(message.from_user.id, {}).get("action") == "waiting_age_for_all")
async def process_age_for_all(message: types.Message):
    """Обработка возраста для /all"""
    user_id = message.from_user.id
    
    try:
        age = int(message.text.strip())
        if age < 1 or age > 150:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректный возраст (число от 1 до 150)")
        return
    
    # Сохраняем возраст в БД (если есть таблица)
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Создаём таблицу возрастов, если её нет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ages (
            user_id INTEGER PRIMARY KEY,
            age INTEGER,
            updated_at TEXT
        )
    """)
    
    from datetime import datetime
    cursor.execute("""
        INSERT OR REPLACE INTO user_ages (user_id, age, updated_at)
        VALUES (?, ?, ?)
    """, (user_id, age, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Очищаем состояние
    del user_states[user_id]
    
    # Получаем участников чата (это сложно, но для примера)
    # В реальности нужно получать список участников группы
    await message.answer(
        f"✅ Спасибо! Ваш возраст ({age}) сохранён.\n\n"
        "📢 *ВНИМАНИЕ ВСЕМ УЧАСТНИКАМ!*\n\n"
        f"Пользователь {message.from_user.first_name} обращается к сообществу!\n\n"
        "Пожалуйста, обратите внимание на это сообщение.",
        parse_mode=ParseMode.MARKDOWN
    )


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data == "accept_duel_")
async def accept_duel_callback(callback: types.CallbackQuery):
    """Принять дуэль из callback"""
    # Получаем ID из data (нужно доработать)
    target_id = int(callback.data.split("_")[2])
    # ... логика дуэли
    await callback.answer()


@router.callback_query(lambda c: c.data == "reject_duel_")
async def reject_duel_callback(callback: types.CallbackQuery):
    """Отклонить дуэль из callback"""
    await callback.answer("❌ Вы отклонили вызов")
    await callback.message.edit_text("❌ Дуэль отклонена")


# Импортируем random для слот-машины
import random
