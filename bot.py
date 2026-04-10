#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS Bot v5.0 — ПОЛНОСТЬЮ РАБОЧАЯ ВЕРСИЯ
"""

import os
import logging
import sqlite3
import json
import re
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
from functools import wraps

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DATA_DIR = "/data"
DATABASE_PATH = os.getenv("DATABASE_PATH", f"{DATA_DIR}/nexus.db")
START_BALANCE = 1000
DAILY_BONUS = 500
SLOT_COST = 50
ROULETTE_MIN = 50
DUEL_MIN = 100

# Создаём папку для данных
os.makedirs(DATA_DIR, exist_ok=True)

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не задан!")
    exit(1)

# ==================== БАЗА ДАННЫХ ====================

def get_connection():
    return sqlite3.connect(DATABASE_PATH)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 1000,
            daily_streak INTEGER DEFAULT 0,
            last_daily TEXT,
            vip_level INTEGER DEFAULT 0,
            vip_until TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            register_date TEXT,
            warns TEXT DEFAULT '[]'
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id INTEGER,
            to_id INTEGER,
            amount INTEGER,
            reason TEXT,
            date TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            description TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            age INTEGER,
            city TEXT,
            timezone TEXT,
            about TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ages (
            user_id INTEGER PRIMARY KEY,
            age INTEGER,
            updated_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    
    add_default_shop_items()


def add_default_shop_items():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM shop_items")
    if cursor.fetchone()[0] == 0:
        items = [
            ("⭐ VIP 1 месяц", 5000, "Доступ к VIP-комнатам + бонусы"),
            ("🎰 10 билетов на слот", 400, "10 игр в слот-машину"),
            ("💎 1000 монет", 100, "Пополнение баланса"),
            ("🎁 Случайный подарок", 200, "Получи случайную награду")
        ]
        cursor.executemany("INSERT INTO shop_items (name, price, description) VALUES (?, ?, ?)", items)
        conn.commit()
    conn.close()


async def get_user(user_id: int) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "user_id": row[0], "username": row[1], "first_name": row[2],
            "balance": row[3], "daily_streak": row[4], "last_daily": row[5],
            "vip_level": row[6], "vip_until": row[7], "wins": row[8],
            "losses": row[9], "register_date": row[10],
            "warns": json.loads(row[11]) if row[11] else []
        }
    return None


async def create_user(user_id: int, username: str = None, first_name: str = None, balance: int = START_BALANCE):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name, balance, register_date)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, first_name, balance, datetime.now().isoformat()))
    conn.commit()
    conn.close()


async def update_balance(user_id: int, delta: int, reason: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    conn.close()
    
    if reason:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (from_id, to_id, amount, reason, date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, user_id, delta, reason, datetime.now().isoformat()))
        conn.commit()
        conn.close()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ==================== КЛАВИАТУРЫ ====================

def main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games"),
         InlineKeyboardButton(text="🛒 Магазин", callback_data="shop")],
        [InlineKeyboardButton(text="⭐ VIP", callback_data="vip"),
         InlineKeyboardButton(text="🤖 AI", callback_data="ai")],
        [InlineKeyboardButton(text="📢 Тэги", callback_data="tag_menu"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def games_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎰 Слот", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="game_rps"),
         InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def parse_amount(text: str) -> int:
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 0


def parse_color(text: str) -> str:
    text = text.lower()
    if 'красн' in text or 'red' in text:
        return 'red'
    if 'черн' in text or 'black' in text:
        return 'black'
    return None


def parse_rps_choice(text: str) -> str:
    text = text.lower()
    if any(word in text for word in ['камень', 'rock', '🗿']):
        return 'rock'
    if any(word in text for word in ['ножницы', 'scissors', '✂️']):
        return 'scissors'
    if any(word in text for word in ['бумага', 'paper', '📄']):
        return 'paper'
    return None


def choice_to_emoji(choice: str) -> str:
    emojis = {"rock": "🗿", "scissors": "✂️", "paper": "📄"}
    return emojis.get(choice, "?")


# ==================== СОЗДАНИЕ БОТА ====================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Хранилище для запросов дуэлей
duel_requests = {}
# Хранилище для ожидания возраста
waiting_ages = {}


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    user = await get_user(user_id)
    
    if not user:
        await create_user(user_id, username, first_name, START_BALANCE)
        await message.answer(
            f"✨ <b>Добро пожаловать в NEXUS Bot, {first_name}!</b> ✨\n\n"
            f"🎁 Вам начислено {START_BALANCE} монет в подарок!\n\n"
            f"📌 <b>Быстрый старт:</b>\n"
            f"• /daily — получить ежедневный бонус\n"
            f"• /slot 100 — сыграть в слот\n"
            f"• /balance — проверить баланс\n\n"
            f"Приятной игры! 🎯",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
    else:
        await message.answer(
            f"👋 <b>С возвращением, {first_name}!</b>\n\n"
            f"💰 Ваш баланс: {user['balance']} монет\n"
            f"⭐ VIP статус: {'Да' if user['vip_level'] > 0 else 'Нет'}\n\n"
            f"Выберите действие в меню 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    await message.answer(
        f"💰 <b>Ваш баланс:</b> {user['balance']} монет\n\n"
        f"📊 Статистика:\n"
        f"├ Побед: {user['wins']}\n"
        f"└ Поражений: {user['losses']}",
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    today = datetime.now().date().isoformat()
    last = user.get("last_daily")
    
    if last == today:
        await message.answer("⏰ Вы уже получили бонус сегодня! Возвращайтесь завтра.")
        return
    
    if last and (datetime.now().date() - datetime.fromisoformat(last).date()).days == 1:
        streak = user["daily_streak"] + 1
        bonus = DAILY_BONUS + (streak * 50)
    else:
        streak = 1
        bonus = DAILY_BONUS
    
    await update_balance(user_id, bonus, f"Ежедневный бонус (стрик: {streak})")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?", 
                   (streak, today, user_id))
    conn.commit()
    conn.close()
    
    await message.answer(
        f"🎁 <b>Ежедневный бонус!</b>\n\n"
        f"💰 Получено: {bonus} монет\n"
        f"🔥 Стрик: {streak} дней\n"
        f"💎 Баланс: {user['balance'] + bonus} монет",
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Моя анкета", callback_data="view_profile"),
         InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await message.answer(
        f"👤 <b>Профиль пользователя</b>\n\n"
        f"📛 Имя: {user.get('first_name', 'Не указано')}\n"
        f"🆔 ID: {user_id}\n"
        f"📅 Регистрация: {user.get('register_date', 'Неизвестно')[:10]}\n\n"
        f"💰 Баланс: {user['balance']} монет\n"
        f"⭐ VIP: {'Да' if user['vip_level'] > 0 else 'Нет'}\n"
        f"🏆 Победы: {user['wins']} | Поражения: {user['losses']}\n"
        f"🔥 Стрик: {user['daily_streak']} дней",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@dp.message(Command("slot"))
async def cmd_slot(message: types.Message):
    user_id = message.from_user.id
    bet = parse_amount(message.text)
    
    if bet == 0:
        await message.answer(
            "🎰 *Слот-машина*\n\n"
            "Использование: `/slot 100`\n"
            f"Минимальная ставка: {SLOT_COST} монет\n\n"
            "Выигрыши:\n"
            "├ 💎💎💎 → x10\n"
            "├ ⭐⭐⭐ → x5\n"
            "└ 🍒🍒🍒 → x3",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if bet < SLOT_COST:
        await message.answer(f"❌ Минимальная ставка: {SLOT_COST} монет")
        return
    
    user = await get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} монет")
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
        
        await update_balance(user_id, win, f"Выигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n{msg}\n💰 +{win} монет!"
        
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet // 2
        await update_balance(user_id, win, f"Выигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n🎉 Выигрыш! +{win} монет!"
    else:
        await update_balance(user_id, -bet, f"Проигрыш в слоте")
        response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n😔 Проигрыш! -{bet} монет"
    
    await message.answer(response)


@dp.message(Command("roulette"))
async def cmd_roulette(message: types.Message):
    user_id = message.from_user.id
    bet = parse_amount(message.text)
    color = parse_color(message.text)
    
    if bet == 0 or not color:
        await message.answer(
            "🎡 *Рулетка*\n\n"
            "Использование: `/roulette 100 красный`\n"
            f"Минимальная ставка: {ROULETTE_MIN} монет\n\n"
            "Цвета: красный, черный\n"
            "💰 Выигрыш: x2",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if bet < ROULETTE_MIN:
        await message.answer(f"❌ Минимальная ставка: {ROULETTE_MIN} монет")
        return
    
    user = await get_user(user_id)
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
        await update_balance(user_id, win, f"Выигрыш в рулетке")
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n🎉 ВЫ ВЫИГРАЛИ! +{win} монет!"
    else:
        await update_balance(user_id, -bet, f"Проигрыш в рулетке")
        response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n😔 Вы проиграли {bet} монет"
    
    await message.answer(response, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("rps"))
async def cmd_rps(message: types.Message):
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
    user = await get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Нужно {bet} монет")
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
        msg = f"✅ Победа! +{bet} монет!"
    else:
        result = -bet
        msg = f"❌ Поражение! -{bet} монет"
    
    await update_balance(user_id, result, f"Игра КНБ")
    
    await message.answer(
        f"✂️ *Камень-ножницы-бумага*\n\n"
        f"Вы: {choice_names[choice]}\n"
        f"Бот: {choice_names[bot_choice]}\n\n"
        f"{msg}",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message(Command("duel"))
async def cmd_duel(message: types.Message):
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer(
            "⚔️ *Дуэль*\n\n"
            "Использование: `/duel @username 100`\n"
            f"Минимальная ставка: {DUEL_MIN} монет",
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
    user = await get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} монет")
        return
    
    conn = get_connection()
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
    
    duel_requests[target_id] = {
        "from_id": user_id,
        "from_name": message.from_user.first_name,
        "bet": bet,
        "chat_id": message.chat.id
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_duel_{target_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_duel_{target_id}")]
    ])
    
    await message.answer(
        f"⚔️ *Дуэль!*\n\n"
        f"@{username}, вас вызвал {message.from_user.first_name}\n"
        f"💰 Ставка: {bet} монет",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, description FROM shop_items")
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await message.answer("🛒 Магазин временно пуст!")
        return
    
    text = "🛒 *Магазин NEXUS*\n\n"
    keyboard = []
    
    for item in items:
        text += f"📦 {item[1]}\n💰 {item[2]} монет\n📝 {item[3]}\n\n"
        keyboard.append([InlineKeyboardButton(f"Купить {item[1]}", callback_data=f"buy_{item[0]}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🤖 *NEXUS Bot v5.0 — Помощь*\n\n"
        "*💰 Экономика*\n"
        "/balance — баланс\n"
        "/daily — бонус дня\n"
        "/transfer @user 100 — перевод\n\n"
        "*🎮 Игры*\n"
        "/slot 100 — слот\n"
        "/roulette 100 красный — рулетка\n"
        "/rps камень — КНБ\n"
        "/duel @user 100 — дуэль\n\n"
        "*👤 Профиль*\n"
        "/profile — профиль\n"
        "/shop — магазин\n"
        "/vip — VIP статус\n\n"
        "*📢 Тэги*\n"
        "/tag @user — тэгнуть\n"
        "/all — тэгнуть всех\n"
        "/tagrole админы — тэгнуть админов\n\n"
        "*ℹ️ Прочее*\n"
        "/ask вопрос — AI\n"
        "/about — о боте",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message(Command("about"))
async def cmd_about(message: types.Message):
    await message.answer(
        "🤖 *NEXUS Bot v5.0*\n\n"
        "Многофункциональный Telegram бот с играми, экономикой и AI.\n\n"
        "*Возможности:*\n"
        "├ Экономическая система\n"
        "├ Игры на монеты\n"
        "├ Магазин и транзакции\n"
        "├ VIP статус\n"
        "└ Тэги участников\n\n"
        "📝 Разработан для Amvera Cloud\n\n"
        "Используйте /help для списка команд",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message(Command("ask"))
async def cmd_ask(message: types.Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "🤖 *AI помощник*\n\n"
            "Использование: `/ask вопрос`\n"
            "Пример: `/ask как заработать монеты?`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    question = args[1]
    
    answers = {
        "монеты": "💰 Монеты можно получить через /daily, выигрывая в играх или покупая в магазине.",
        "игра": "🎮 Доступны: /slot, /roulette, /rps, /duel",
        "вип": "⭐ VIP даёт бонусы к играм и увеличенный ежедневный бонус.",
        "магазин": "🛒 Магазин доступен по команде /shop",
    }
    
    for key, answer in answers.items():
        if key in question.lower():
            await message.answer(f"🤖 *Ответ:*\n\n{answer}", parse_mode=ParseMode.MARKDOWN)
            return
    
    await message.answer(
        f"🤖 *Вопрос:* {question}\n\n"
        "Попробуйте спросить:\n"
        "- Как заработать монеты?\n"
        "- Какие есть игры?\n"
        "- Что такое VIP?",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message(Command("transfer"))
async def cmd_transfer(message: types.Message):
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer("❌ Использование: `/transfer @user 100`", parse_mode=ParseMode.MARKDOWN)
        return
    
    username = args[1].replace('@', '')
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной!")
        return
    
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["balance"] < amount:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']} монет")
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{username} не найден")
        return
    
    target_id = row[0]
    
    if target_id == user_id:
        await message.answer("❌ Нельзя перевести монеты самому себе!")
        return
    
    await update_balance(user_id, -amount, f"Перевод @{username}")
    await update_balance(target_id, amount, f"Получен перевод от {message.from_user.username or message.from_user.first_name}")
    
    await message.answer(f"✅ Переведено {amount} монет пользователю @{username}!")


@dp.message(Command("vip"))
async def cmd_vip(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if user["vip_level"] > 0:
        await message.answer(
            f"⭐ *Ваш VIP статус*\n\n"
            f"Уровень: {user['vip_level']}\n"
            f"Действует до: {user['vip_until']}\n\n"
            f"🔹 Бонус к играм: +{user['vip_level'] * 10}%\n"
            f"🔹 Ежедневный бонус: +{user['vip_level'] * 100} монет",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        keyboard = [[InlineKeyboardButton(text="💎 Купить VIP", callback_data="buy_vip")]]
        await message.answer(
            "⭐ *VIP статус*\n\n"
            "VIP даёт преимущества:\n"
            "• +20% к выигрышам\n"
            "• Увеличенный бонус\n"
            "• Эксклюзивные команды\n\n"
            "💰 Цена: 5000 монет за 30 дней",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )


@dp.message(Command("tag"))
async def cmd_tag(message: types.Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "📢 *Как тэгать:*\n\n"
            "`/tag @username текст` — упомянуть пользователя",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    text = args[1]
    username_match = re.search(r'@(\w+)', text)
    
    if not username_match:
        await message.answer("❌ Укажите @username пользователя")
        return
    
    username = username_match.group(1)
    clean_text = re.sub(r'@\w+', '', text).strip()
    
    if clean_text:
        result = f"🔔 {clean_text}\n\n👉 @{username}"
    else:
        result = f"🔔 Вас упомянул {message.from_user.full_name}\n\n👉 @{username}"
    
    await message.answer(result)


@dp.message(Command("all"))
async def cmd_all(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    
    # Проверяем, что это группа/супергруппа
    if chat_type not in ['group', 'supergroup']:
        await message.answer(
            "❌ Команда /all работает только в группах!\n\n"
            "Добавьте бота в группу и сделайте его администратором."
        )
        return
    
    user = await get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    # Сохраняем состояние для запроса возраста
    waiting_ages[user_id] = {"chat_id": chat_id}
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтверждаю", callback_data="confirm_all"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_all")]
    ])
    
    await message.answer(
        "📢 *МАССОВОЕ УПОМИНАНИЕ*\n\n"
        "⚠️ Вы собираетесь упомянуть всех участников чата.\n\n"
        "Подтвердите, что вам есть 18 лет:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@dp.message(Command("tagrole"))
async def cmd_tag_role(message: types.Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "📢 *Как тэгать по роли:*\n\n"
            "`/tagrole админы текст` — упомянуть админов",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    text = args[1]
    role_match = re.match(r'(админы?|модераторы?)\s*(.*)', text, re.IGNORECASE)
    
    if not role_match:
        await message.answer("❌ Не распознана роль. Используйте: админы или модераторы")
        return
    
    role = role_match.group(1).lower()
    clean_text = role_match.group(2).strip()
    
    chat_id = message.chat.id
    admins = []
    
    try:
        administrators = await bot.get_chat_administrators(chat_id)
        for admin in administrators:
            if not admin.user.is_bot:
                admins.append(admin.user)
                if len(admins) >= 20:
                    break
    except Exception as e:
        await message.answer(f"❌ Ошибка получения администраторов: {e}")
        return
    
    if not admins:
        await message.answer("❌ Нет администраторов в этом чате")
        return
    
    mentions = [f"@{a.username}" if a.username else f"[{a.full_name}](tg://user?id={a.id})" for a in admins]
    
    if clean_text:
        result = f"🔔 {clean_text}\n\n{' '.join(mentions)}"
    else:
        result = f"🔔 Обращение к {role}:\n\n{' '.join(mentions)}"
    
    await message.answer(result, parse_mode=ParseMode.MARKDOWN)


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🏠 *Главное меню NEXUS Bot*\n\nВыберите действие:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await callback.message.edit_text("❌ Используйте /start для регистрации")
        await callback.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Моя анкета", callback_data="view_profile"),
         InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        f"👤 *Профиль пользователя*\n\n"
        f"📛 Имя: {user.get('first_name', 'Не указано')}\n"
        f"🆔 ID: {user_id}\n"
        f"💰 Баланс: {user['balance']} монет\n"
        f"⭐ VIP: {'Да' if user['vip_level'] > 0 else 'Нет'}\n"
        f"🏆 Победы: {user['wins']} | Поражения: {user['losses']}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "balance")
async def balance_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await callback.message.edit_text("❌ Используйте /start для регистрации")
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"💰 *Ваш баланс:* {user['balance']} монет\n\n"
        f"📊 Побед: {user['wins']} | Поражений: {user['losses']}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_button()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "games")
async def games_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🎮 *Игры NEXUS Bot*\n\nВыберите игру:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "game_slot")
async def game_slot_info(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🎰 *Слот-машина*\n\n"
        "Команда: `/slot 100`\n"
        f"Минимальная ставка: {SLOT_COST} монет\n\n"
        "✨ *Выигрыши:*\n"
        "├ 💎💎💎 → x10\n"
        "├ ⭐⭐⭐ → x5\n"
        "└ 🍒🍒🍒 → x3",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "game_roulette")
async def game_roulette_info(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🎡 *Рулетка*\n\n"
        "Команда: `/roulette 100 красный`\n"
        f"Минимальная ставка: {ROULETTE_MIN} монет\n\n"
        "💰 Выигрыш: x2 от ставки",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "game_rps")
async def game_rps_info(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "✂️ *Камень-ножницы-бумага*\n\n"
        "Команда: `/rps камень`\n"
        "💰 Ставка: 50 монет",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "game_duel")
async def game_duel_info(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚔️ *Дуэль*\n\n"
        "Команда: `/duel @user 100`\n"
        f"Минимальная ставка: {DUEL_MIN} монет",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "shop")
async def shop_callback(callback: types.CallbackQuery):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, description FROM shop_items")
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await callback.message.edit_text("🛒 Магазин временно пуст!")
        await callback.answer()
        return
    
    text = "🛒 *Магазин NEXUS*\n\n"
    keyboard = []
    
    for item in items:
        text += f"📦 {item[1]}\n💰 {item[2]} монет\n📝 {item[3]}\n\n"
        keyboard.append([InlineKeyboardButton(f"Купить {item[1]}", callback_data=f"buy_{item[0]}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@dp.callback_query(lambda c: c.data == "vip")
async def vip_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await callback.message.edit_text("❌ Используйте /start для регистрации")
        await callback.answer()
        return
    
    if user["vip_level"] > 0:
        await callback.message.edit_text(
            f"⭐ *Ваш VIP статус*\n\n"
            f"Уровень: {user['vip_level']}\n"
            f"Действует до: {user['vip_until']}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_button()
        )
    else:
        keyboard = [[InlineKeyboardButton(text="💎 Купить VIP", callback_data="buy_vip")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]]
        await callback.message.edit_text(
            "⭐ *VIP статус*\n\n"
            "💰 Цена: 5000 монет за 30 дней",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "ai")
async def ai_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤖 *AI помощник*\n\n"
        "Используйте команду: `/ask вопрос`\n\n"
        "Пример: `/ask как заработать монеты?`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_button()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Тэгнуть всех", callback_data="confirm_all")],
        [InlineKeyboardButton(text="🔔 Как пользоваться", callback_data="tag_help")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Тэги и упоминания*\n\n"
        "*Как пользоваться:*\n\n"
        "📝 *Текст:*\n"
        "• `/all` — упомянуть всех\n"
        "• `/tag @user` — упомянуть пользователя\n"
        "• `/tagrole админы` — упомянуть админов",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "help")
async def help_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤖 *NEXUS Bot v5.0 — Помощь*\n\n"
        "*💰 Экономика*\n"
        "/balance — баланс\n"
        "/daily — бонус дня\n"
        "/transfer @user 100 — перевод\n\n"
        "*🎮 Игры*\n"
        "/slot 100 — слот\n"
        "/roulette 100 красный — рулетка\n"
        "/rps камень — КНБ\n"
        "/duel @user 100 — дуэль\n\n"
        "*📢 Тэги*\n"
        "/tag @user — тэгнуть\n"
        "/all — тэгнуть всех\n"
        "/tagrole админы — тэгнуть админов",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_button()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "confirm_all")
async def confirm_all_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # Проверяем права бота
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if bot_member.status not in ['creator', 'administrator']:
            await callback.message.edit_text(
                "❌ *Ошибка:* Бот не является администратором чата!\n\n"
                "Чтобы использовать /all, добавьте бота в группу и выдайте ему права администратора.\n\n"
                "Необходимые права: `Получать список участников`",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка проверки прав: {e}")
        await callback.answer()
        return
    
    waiting_ages[user_id] = {"chat_id": chat_id}
    
    await callback.message.edit_text(
        "📢 *МАССОВОЕ УПОМИНАНИЕ*\n\n"
        "Напишите ваш возраст (число от 1 до 150):",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in waiting_ages:
        del waiting_ages[user_id]
    
    await callback.message.edit_text("❌ Отменено.", reply_markup=back_button())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "tag_help")
async def tag_help_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="tag_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Помощь по тэгам*\n\n"
        "*Примеры:*\n"
        "• `/all` — упомянуть всех\n"
        "• `/tag @user Привет` — упомянуть пользователя\n"
        "• `/tagrole админы Срочно!` — упомянуть админов",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("buy_"))
async def buy_item_callback(callback: types.CallbackQuery):
    item_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, price FROM shop_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    
    if not item:
        await callback.answer("❌ Товар не найден!", show_alert=True)
        return
    
    name, price = item
    
    user = await get_user(user_id)
    if not user:
        await callback.answer("❌ Используйте /start для регистрации", show_alert=True)
        return
    
    if user["balance"] < price:
        await callback.answer(f"❌ Недостаточно монет! Нужно {price}", show_alert=True)
        return
    
    await update_balance(user_id, -price, f"Покупка: {name}")
    
    if "VIP" in name:
        new_until = (datetime.now() + timedelta(days=30)).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET vip_level = 1, vip_until = ? WHERE user_id = ?", (new_until, user_id))
        conn.commit()
        conn.close()
        await callback.message.edit_text(f"✅ Вы купили {name}!\n\n⭐ VIP активирован до {new_until[:10]}", reply_markup=back_button())
    elif "Случайный" in name:
        rand_bonus = random.randint(100, 1000)
        await update_balance(user_id, rand_bonus, "Случайный подарок")
        await callback.message.edit_text(f"🎁 Вы купили {name}!\n\n✨ Вам выпало +{rand_bonus} монет!", reply_markup=back_button())
    else:
        await callback.message.edit_text(f"✅ Вы купили {name}!\n\n💰 С баланса списано {price} монет", reply_markup=back_button())
    
    await callback.answer()


@dp.callback_query(lambda c: c.data == "buy_vip")
async def buy_vip_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    price = 5000
    
    user = await get_user(user_id)
    if not user:
        await callback.answer("❌ Используйте /start для регистрации", show_alert=True)
        return
    
    if user["balance"] < price:
        await callback.answer(f"❌ Недостаточно монет! Нужно {price}", show_alert=True)
        return
    
    await update_balance(user_id, -price, "Покупка VIP")
    
    new_until = (datetime.now() + timedelta(days=30)).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET vip_level = 1, vip_until = ? WHERE user_id = ?", (new_until, user_id))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        f"✅ Вы купили VIP статус!\n\n"
        f"⭐ Активирован до {new_until[:10]}\n"
        f"💰 Остаток: {user['balance'] - price} монет",
        reply_markup=back_button()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "view_profile")
async def view_profile_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, age, city, timezone, about FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await callback.message.edit_text(
            "❌ Анкета не найдена!\n\nИспользуйте /setprofile для создания",
            reply_markup=back_button()
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"👤 *Ваша анкета*\n\n"
        f"📛 Имя: {row[0]}\n"
        f"📅 Возраст: {row[1]}\n"
        f"🏙️ Город: {row[2]}\n"
        f"🕐 Часовой пояс: {row[3]}\n"
        f"📝 О себе: {row[4]}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_button()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "fill_profile")
async def fill_profile_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📝 *Создание анкеты*\n\n"
        "Используйте команду `/setprofile` в чате.\n\n"
        "Бот задаст 5 вопросов для создания анкеты.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_button()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("accept_duel_"))
async def accept_duel_callback(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if target_id not in duel_requests:
        await callback.answer("❌ Вызов устарел", show_alert=True)
        return
    
    request = duel_requests[target_id]
    from_id = request["from_id"]
    from_name = request["from_name"]
    bet = request["bet"]
    
    user = await get_user(user_id)
    from_user = await get_user(from_id)
    
    if not user or not from_user:
        await callback.message.edit_text("❌ Ошибка: пользователь не найден")
        await callback.answer()
        return
    
    if user["balance"] < bet:
        await callback.message.edit_text(f"❌ У вас недостаточно средств! Нужно {bet} монет")
        await callback.answer()
        return
    
    if from_user["balance"] < bet:
        await callback.message.edit_text(f"❌ У {from_name} недостаточно средств!")
        await callback.answer()
        return
    
    await update_balance(user_id, -bet, f"Дуэль с {from_name}")
    await update_balance(from_id, -bet, f"Дуэль с {callback.from_user.first_name}")
    
    winner_id = random.choice([user_id, from_id])
    
    if winner_id == user_id:
        win_amount = bet * 2
        await update_balance(user_id, win_amount, f"Выигрыш в дуэли с {from_name}")
        result_text = f"🎉 Победил {callback.from_user.first_name}! +{win_amount} монет!"
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (from_id,))
        conn.commit()
        conn.close()
    else:
        win_amount = bet * 2
        await update_balance(from_id, win_amount, f"Выигрыш в дуэли с {callback.from_user.first_name}")
        result_text = f"🎉 Победил {from_name}! +{win_amount} монет!"
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (from_id,))
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    del duel_requests[target_id]
    
    await callback.message.edit_text(f"⚔️ *Результат дуэли*\n\n{result_text}", parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("reject_duel_"))
async def reject_duel_callback(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if target_id in duel_requests:
        request = duel_requests[target_id]
        del duel_requests[target_id]
        
        await callback.message.edit_text(f"❌ {callback.from_user.first_name} отклонил вызов на дуэль!")
        
        await bot.send_message(
            request["from_id"],
            f"❌ {callback.from_user.first_name} отклонил ваш вызов на дуэль!"
        )
    
    await callback.answer()


# ==================== ОБРАБОТЧИК ВОЗРАСТА (МАССОВОЕ УПОМИНАНИЕ) ====================

@dp.message(lambda message: message.from_user.id in waiting_ages)
async def process_age_input(message: types.Message):
    user_id = message.from_user.id
    data = waiting_ages.get(user_id)
    
    if not data:
        return
    
    try:
        age = int(message.text.strip())
        if age < 1 or age > 150:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректный возраст (число от 1 до 150)")
        return
    
    # Сохраняем возраст
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO user_ages (user_id, age, updated_at) VALUES (?, ?, ?)",
                   (user_id, age, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    del waiting_ages[user_id]
    chat_id = data["chat_id"]
    
    # Отправляем "печатает" для реалистичности
    await bot.send_chat_action(chat_id, "typing")
    
    # Получаем участников чата
    members = []
    try:
        # Получаем администраторов (их всегда можно получить)
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot:
                members.append(admin.user)
        
        # Пытаемся получить обычных участников
        try:
            async for member in bot.get_chat_members(chat_id):
                if not member.user.is_bot and member.user.id not in [m.id for m in members]:
                    members.append(member.user)
                    if len(members) >= 80:
                        break
        except Exception as e:
            logger.warning(f"Не удалось получить всех участников: {e}")
            
    except Exception as e:
        await message.answer(f"❌ Ошибка получения участников: {e}")
        return
    
    if not members:
        await message.answer(
            "❌ Не удалось получить список участников.\n\n"
            "Убедитесь, что бот является администратором чата.\n"
            "Необходимые права: `Получать список участников`"
        )
        return
    
    # Формируем текст оповещения
    notification_text = (
        f"🔔 *ОБЩИЙ СБОР! ВНИМАНИЕ ВСЕМ!* 🔔\n\n"
        f"👤 *{message.from_user.full_name}* (возраст: {age})\n\n"
        f"📢 Важное сообщение для всех участников!\n\n"
        f"👇👇👇\n\n"
    )
    
    # Формируем упоминания
    mentions = []
    for member in members:
        if member.username:
            mentions.append(f"@{member.username}")
        else:
            mentions.append(f"[{member.full_name}](tg://user?id={member.id})")
    
    # Отправляем ОДНО сообщение со всеми упоминаниями
    mention_groups = []
    current_group = []
    current_length = 0
    
    for mention in mentions:
        # Учитываем длину строки (Telegram лимит ~4000 символов)
        mention_len = len(mention) + 1
        if current_length + mention_len > 3500:
            mention_groups.append(" ".join(current_group))
            current_group = [mention]
            current_length = mention_len
        else:
            current_group.append(mention)
            current_length += mention_len
    
    if current_group:
        mention_groups.append(" ".join(current_group))
    
    # Отправляем первое сообщение с текстом + первой группой упоминаний
    if mention_groups:
        first_message = notification_text + mention_groups[0]
        await message.answer(first_message, parse_mode=ParseMode.MARKDOWN)
        
        # Если есть ещё группы, отправляем их отдельно
        for i, group in enumerate(mention_groups[1:], 2):
            await message.answer(f"📢 *Продолжение ({i}/{len(mention_groups)})*\n\n{group}", parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.5)
    
    await message.answer(
        f"✅ *Оповещение отправлено!*\n\n"
        f"📊 Всего упомянуто участников: {len(mentions)}\n"
        f"📨 Количество сообщений: {len(mention_groups)}",
        parse_mode=ParseMode.MARKDOWN
    )


# ==================== ОБРАБОТЧИК АНКЕТЫ /setprofile ====================

# Хранилище состояний для анкеты
profile_states = {}

@dp.message(Command("setprofile"))
async def cmd_setprofile(message: types.Message):
    user_id = message.from_user.id
    profile_states[user_id] = {'step': 1}
    
    await message.answer(
        "📝 *Создание анкеты*\n\n"
        "Шаг 1 из 5: Введите ваше имя\n\n"
        "Пример: `Александр`\n\n"
        "❌ Отмена: /cancel_profile",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message(Command("cancel_profile"))
async def cmd_cancel_profile(message: types.Message):
    user_id = message.from_user.id
    if user_id in profile_states:
        del profile_states[user_id]
    await message.answer("❌ Заполнение анкеты отменено.")


@dp.message(lambda message: message.from_user.id in profile_states)
async def process_profile_step(message: types.Message):
    user_id = message.from_user.id
    state = profile_states[user_id]
    step = state['step']
    
    if step == 1:
        state['full_name'] = message.text
        state['step'] = 2
        await message.answer(
            "📝 *Шаг 2 из 5*\n\n"
            "Введите ваш возраст (число):\n\n"
            "Пример: `25`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 2:
        try:
            age = int(message.text)
            if age < 1 or age > 150:
                raise ValueError
            state['age'] = age
            state['step'] = 3
            await message.answer(
                "📝 *Шаг 3 из 5*\n\n"
                "Введите ваш город:\n\n"
                "Пример: `Москва`",
                parse_mode=ParseMode.MARKDOWN
            )
        except ValueError:
            await message.answer("❌ Введите корректный возраст (число от 1 до 150)")
    
    elif step == 3:
        state['city'] = message.text
        state['step'] = 4
        await message.answer(
            "📝 *Шаг 4 из 5*\n\n"
            "Введите ваш часовой пояс (UTC):\n\n"
            "Пример: `UTC+3` или `+3`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 4:
        state['timezone'] = message.text
        state['step'] = 5
        await message.answer(
            "📝 *Шаг 5 из 5*\n\n"
            "Расскажите немного о себе:\n\n"
            "Пример: `Люблю игры и программирование`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 5:
        state['about'] = message.text
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_profiles 
            (user_id, full_name, age, city, timezone, about, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM user_profiles WHERE user_id = ?), ?), ?)
        """, (
            user_id, state['full_name'], state['age'], state['city'], 
            state['timezone'], state['about'], user_id, datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        
        await message.answer(
            "✅ *Анкета сохранена!*\n\n"
            f"📛 Имя: {state['full_name']}\n"
            f"📅 Возраст: {state['age']}\n"
            f"🏙️ Город: {state['city']}\n"
            f"🕐 Часовой пояс: {state['timezone']}\n"
            f"📝 О себе: {state['about']}\n\n"
            "Используйте /profile для просмотра анкеты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        del profile_states[user_id]


# ==================== ЗАПУСК БОТА ====================

async def on_startup():
    init_db()
    logger.info("✅ NEXUS Bot v5.0 успешно запущен на Amvera!")


async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
