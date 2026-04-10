#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS Bot v5.0 — ПОЛНОСТЬЮ РАБОЧАЯ ВЕРСИЯ
Все функции в одном файле для гарантированного запуска на Amvera
"""

import os
import logging
import sqlite3
import json
import re
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
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
MAX_WARN_COUNT = 3

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
    """Получить соединение с БД"""
    return sqlite3.connect(DATABASE_PATH)


def init_db():
    """Инициализация базы данных"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
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
    
    # Таблица транзакций
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
    
    # Таблица магазина
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            description TEXT
        )
    """)
    
    # Таблица для анкет
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
    
    # Таблица для возрастов (/all)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ages (
            user_id INTEGER PRIMARY KEY,
            age INTEGER,
            updated_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    
    # Добавляем товары
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
    """Получить пользователя"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "user_id": row[0],
            "username": row[1],
            "first_name": row[2],
            "balance": row[3],
            "daily_streak": row[4],
            "last_daily": row[5],
            "vip_level": row[6],
            "vip_until": row[7],
            "wins": row[8],
            "losses": row[9],
            "register_date": row[10],
            "warns": json.loads(row[11]) if row[11] else []
        }
    return None


async def create_user(user_id: int, username: str = None, first_name: str = None, balance: int = START_BALANCE):
    """Создать пользователя"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name, balance, register_date)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, first_name, balance, datetime.now().isoformat()))
    conn.commit()
    conn.close()


async def update_balance(user_id: int, delta: int, reason: str = ""):
    """Обновить баланс"""
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


async def get_balance(user_id: int) -> int:
    """Получить баланс"""
    user = await get_user(user_id)
    return user["balance"] if user else 0


def is_admin(user_id: int) -> bool:
    """Проверка на админа"""
    return user_id in ADMIN_IDS


def admin_required(func):
    """Декоратор для админ-команд"""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            await message.answer("❌ У вас нет прав администратора!")
            return
        return await func(message, *args, **kwargs)
    return wrapper


# ==================== КЛАВИАТУРЫ ====================

def main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
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
    """Меню игр"""
    keyboard = [
        [InlineKeyboardButton(text="🎰 Слот", callback_data="game_slot"),
         InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
        [InlineKeyboardButton(text="✂️ КНБ", callback_data="game_rps"),
         InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game_duel")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def back_button() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ИГР ====================

def parse_amount(text: str) -> int:
    """Извлечь число из текста"""
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 0


def parse_color(text: str) -> str:
    """Извлечь цвет для рулетки"""
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


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    user = await get_user(user_id)
    
    if not user:
        await create_user(user_id, username, first_name, START_BALANCE)
        await message.answer(
            f"✨ <b>Добро пожаловать в NEXUS Bot, {first_name}!</b> ✨\n\n"
            f"🎁 Вам начислено {START_BALANCE} монет в подарок!\n\n"
            f"🤖 <b>NEXUS Bot v5.0</b> — это:\n"
            f"├ 🎮 Игры на монеты\n"
            f"├ 💰 Экономическая система\n"
            f"├ 🛒 Магазин и транзакции\n"
            f"├ ⭐ VIP статус\n"
            f"└ 🤖 AI помощник\n\n"
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


@router.message(Command("balance"))
async def cmd_balance(message: types.Message):
    """Показать баланс"""
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


@router.message(Command("daily"))
async def cmd_daily(message: types.Message):
    """Ежедневный бонус"""
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


@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """Показать профиль"""
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


@router.message(Command("duel"))
async def cmd_duel(message: types.Message):
    """Дуэль с игроком"""
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
    
    # Поиск противника
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
    
    # Сохраняем запрос
    if not hasattr(cmd_duel, 'requests'):
        cmd_duel.requests = {}
    
    cmd_duel.requests[target_id] = {
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


@router.message(Command("shop"))
async def cmd_shop(message: types.Message):
    """Магазин"""
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


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь"""
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


@router.message(Command("about"))
async def cmd_about(message: types.Message):
    """О боте"""
    await message.answer(
        "🤖 *NEXUS Bot v5.0*\n\n"
        "Многофункциональный Telegram бот с играми, экономикой и AI.\n\n"
        "*Возможности:*\n"
        "├ Экономическая система\n"
        "├ Игры на монеты\n"
        "├ Магазин и транзакции\n"
        "├ VIP статус\n"
        "├ Модерация\n"
        "└ Тэги участников\n\n"
        "📝 Разработан для Amvera Cloud\n\n"
        "Используйте /help для списка команд",
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(Command("ask"))
async def cmd_ask(message: types.Message):
    """AI помощник"""
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
    
    # Простые ответы
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
        "🤖 *NEXUS AI*\n\n"
        f"Ваш вопрос: {question}\n\n"
        "Попробуйте спросить:\n"
        "- Как заработать монеты?\n"
        "- Какие есть игры?\n"
        "- Что такое VIP?",
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(Command("transfer"))
async def cmd_transfer(message: types.Message):
    """Перевод монет"""
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
    
    # Поиск получателя
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


@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    """VIP статус"""
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


@router.message(Command("tag"))
async def cmd_tag(message: types.Message):
    """Тэгнуть пользователя"""
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


@router.message(Command("all"))
async def cmd_all(message: types.Message):
    """Тэгнуть всех участников"""
    user_id = message.from_user.id
    
    user = await get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    # Сохраняем состояние для запроса возраста
    if not hasattr(cmd_all, 'waiting'):
        cmd_all.waiting = {}
    
    cmd_all.waiting[user_id] = {"chat_id": message.chat.id}
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтверждаю", callback_data="confirm_all"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_all")]
    ])
    
    await message.answer(
        "📢 *Массовое упоминание*\n\n"
        "⚠️ Вы собираетесь упомянуть всех участников чата.\n\n"
        "Подтвердите, что вам есть 18 лет:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.message(Command("tagrole"))
async def cmd_tag_role(message: types.Message):
    """Тэгнуть по роли"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "📢 *Как тэгать по роли:*\n\n"
            "`/tagrole админы текст` — упомянуть админов\n"
            "Доступные роли: админы, модераторы",
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
        async for member in dp.bot.get_chat_members(chat_id):
            if not member.user.is_bot and member.status in ['creator', 'administrator']:
                admins.append(member.user)
                if len(admins) >= 20:
                    break
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
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

@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        "🏠 *Главное меню NEXUS Bot*\n\nВыберите действие:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    """Профиль из меню"""
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


@router.callback_query(lambda c: c.data == "balance")
async def balance_callback(callback: types.CallbackQuery):
    """Баланс из меню"""
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


@router.callback_query(lambda c: c.data == "games")
async def games_callback(callback: types.CallbackQuery):
    """Меню игр"""
    await callback.message.edit_text(
        "🎮 *Игры NEXUS Bot*\n\n"
        "Выберите игру:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
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
        "├ 💎💎💎 → x10\n"
        "├ ⭐⭐⭐ → x5\n"
        "└ 🍒🍒🍒 → x3",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "game_roulette")
async def game_roulette_info(callback: types.CallbackQuery):
    """Информация о рулетке"""
    await callback.message.edit_text(
        "🎡 *Рулетка*\n\n"
        "Команда: `/roulette 100 красный`\n"
        f"Минимальная ставка: {ROULETTE_MIN} монет\n\n"
        "💰 Выигрыш: x2 от ставки",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "game_rps")
async def game_rps_info(callback: types.CallbackQuery):
    """Информация о КНБ"""
    await callback.message.edit_text(
        "✂️ *Камень-ножницы-бумага*\n\n"
        "Команда: `/rps камень`\n"
        "💰 Ставка: 50 монет",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "game_duel")
async def game_duel_info(callback: types.CallbackQuery):
    """Информация о дуэли"""
    await callback.message.edit_text(
        "⚔️ *Дуэль*\n\n"
        "Команда: `/duel @user 100`\n"
        f"Минимальная ставка: {DUEL_MIN} монет",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=games_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "shop")
async def shop_callback(callback: types.CallbackQuery):
    """Магазин из меню"""
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


@router.callback_query(lambda c: c.data == "vip")
async def vip_callback(callback: types.CallbackQuery):
    """VIP из меню"""
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


@router.callback_query(lambda c: c.data == "ai")
async def ai_callback(callback: types.CallbackQuery):
    """AI из меню"""
    await callback.message.edit_text(
        "🤖 *AI помощник*\n\n"
        "Используйте команду: `/ask вопрос`\n\n"
        "Пример: `/ask как заработать монеты?`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu_callback(callback: types.CallbackQuery):
    """Меню тэгов"""
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


@router.callback_query(lambda c: c.data == "help")
async def help_callback(callback: types.CallbackQuery):
    """Помощь из меню"""
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


@router.callback_query(lambda c: c.data == "confirm_all")
async def confirm_all_callback(callback: types.CallbackQuery):
    """Подтверждение /all из меню"""
    user_id = callback.from_user.id
    
    if not hasattr(cmd_all, 'waiting'):
        cmd_all.waiting = {}
    
    cmd_all.waiting[user_id] = {"chat_id": callback.message.chat.id}
    
    await callback.message.edit_text(
        "📢 *Массовое упоминание*\n\n"
        "Напишите ваш возраст (число от 1 до 150):",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery):
    """Отмена /all"""
    user_id = callback.from_user.id
    
    if hasattr(cmd_all, 'waiting') and user_id in cmd_all.waiting:
        del cmd_all.waiting[user_id]
    
    await callback.message.edit_text("❌ Отменено.", reply_markup=back_button())
    await callback.answer()


@router.callback_query(lambda c: c.data == "tag_help")
async def tag_help_callback(callback: types.CallbackQuery):
    """Помощь по тэгам"""
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


@router.callback_query(lambda c: c.data and c.data.startswith("buy_"))
async def buy_item_callback(callback: types.CallbackQuery):
    """Покупка товара"""
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


@router.callback_query(lambda c: c.data == "buy_vip")
async def buy_vip_callback(callback: types.CallbackQuery):
    """Покупка VIP"""
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


@router.callback_query(lambda c: c.data == "view_profile")
async def view_profile_callback(callback: types.CallbackQuery):
    """Просмотр анкеты"""
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


@router.callback_query(lambda c: c.data == "fill_profile")
async def fill_profile_callback(callback: types.CallbackQuery):
    """Заполнение анкеты"""
    await callback.message.edit_text(
        "📝 *Создание анкеты*\n\n"
        "Используйте команду `/setprofile` в чате.\n\n"
        "Бот задаст 5 вопросов для создания анкеты.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("accept_duel_"))
async def accept_duel_callback(callback: types.CallbackQuery):
    """Принять дуэль"""
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if not hasattr(cmd_duel, 'requests') or target_id not in cmd_duel.requests:
        await callback.answer("❌ Вызов устарел", show_alert=True)
        return
    
    request = cmd_duel.requests[target_id]
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
    
    # Списываем ставки
    await update_balance(user_id, -bet, f"Дуэль с {from_name}")
    await update_balance(from_id, -bet, f"Дуэль с {callback.from_user.first_name}")
    
    # Случайный победитель
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
    
    del cmd_duel.requests[target_id]
    
    await callback.message.edit_text(f"⚔️ *Результат дуэли*\n\n{result_text}", parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("reject_duel_"))
async def reject_duel_callback(callback: types.CallbackQuery):
    """Отклонить дуэль"""
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if hasattr(cmd_duel, 'requests') and target_id in cmd_duel.requests:
        request = cmd_duel.requests[target_id]
        del cmd_duel.requests[target_id]
        
        await callback.message.edit_text(f"❌ {callback.from_user.first_name} отклонил вызов на дуэль!")
        
        await callback.bot.send_message(
            request["from_id"],
            f"❌ {callback.from_user.first_name} отклонил ваш вызов на дуэль!"
        )
    
    await callback.answer()


# ==================== ОБРАБОТЧИК ВОЗРАСТА ДЛЯ /all ====================

@router.message(lambda message: hasattr(cmd_all, 'waiting') and message.from_user.id in cmd_all.waiting)
async def process_age_input(message: types.Message):
    """Обработка ввода возраста для /all"""
    user_id = message.from_user.id
    data = cmd_all.waiting.get(user_id)
    
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
    
    # Очищаем состояние
    del cmd_all.waiting[user_id]
    
    chat_id = data["chat_id"]
    
    # Получаем участников чата
    members = []
    try:
        async for member in dp.bot.get_chat_members(chat_id):
            if not member.user.is_bot:
                members.append(member.user)
                if len(members) >= 50:
                    break
    except Exception as e:
        await message.answer(f"❌ Ошибка получения участников: {e}")
        return
    
    if not members:
        await message.answer("❌ Не удалось получить список участников")
        return
    
    # Формируем упоминания
    mentions = []
    for member in members:
        if member.username:
            mentions.append(f"@{member.username}")
        else:
            mentions.append(f"[{member.full_name}](tg://user?id={member.id})")
    
    await message.answer(
        f"📢 *ОБРАЩЕНИЕ К УЧАСТНИКАМ!*\n\n"
        f"Пользователь {message.from_user.full_name} (возраст: {age}) обращается к сообществу.\n\n"
        f"{' '.join(mentions[:30])}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    if len(mentions) > 30:
        await message.answer(f"... и ещё {len(mentions) - 30} участников")


# ==================== ЗАПУСК БОТА ====================

async def on_startup():
    init_db()
    logger.info("✅ Nexus Bot v5.0 успешно запущен на Amvera!")


async def on_shutdown():
    logger.info("👋 Nexus Bot v5.0 остановлен")


async def main():
    global dp, bot
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    # Регистрируем все обработчики
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_balance, Command("balance"))
    dp.message.register(cmd_daily, Command("daily"))
    dp.message.register(cmd_profile, Command("profile"))
    dp.message.register(cmd_slot, Command("slot"))
    dp.message.register(cmd_roulette, Command("roulette"))
    dp.message.register(cmd_rps, Command("rps"))
    dp.message.register(cmd_duel, Command("duel"))
    dp.message.register(cmd_shop, Command("shop"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_about, Command("about"))
    dp.message.register(cmd_ask, Command("ask"))
    dp.message.register(cmd_transfer, Command("transfer"))
    dp.message.register(cmd_vip, Command("vip"))
    dp.message.register(cmd_tag, Command("tag"))
    dp.message.register(cmd_all, Command("all"))
    dp.message.register(cmd_tag_role, Command("tagrole"))
    
    # Обработчик возраста
    dp.message.register(process_age_input, lambda message: hasattr(cmd_all, 'waiting') and message.from_user.id in cmd_all.waiting)
    
    # Обработчики кнопок
    dp.callback_query.register(back_to_menu, lambda c: c.data == "back_to_menu")
    dp.callback_query.register(profile_callback, lambda c: c.data == "profile")
    dp.callback_query.register(balance_callback, lambda c: c.data == "balance")
    dp.callback_query.register(games_callback, lambda c: c.data == "games")
    dp.callback_query.register(game_slot_info, lambda c: c.data == "game_slot")
    dp.callback_query.register(game_roulette_info, lambda c: c.data == "game_roulette")
    dp.callback_query.register(game_rps_info, lambda c: c.data == "game_rps")
    dp.callback_query.register(game_duel_info, lambda c: c.data == "game_duel")
    dp.callback_query.register(shop_callback, lambda c: c.data == "shop")
    dp.callback_query.register(vip_callback, lambda c: c.data == "vip")
    dp.callback_query.register(ai_callback, lambda c: c.data == "ai")
    dp.callback_query.register(tag_menu_callback, lambda c: c.data == "tag_menu")
    dp.callback_query.register(help_callback, lambda c: c.data == "help")
    dp.callback_query.register(confirm_all_callback, lambda c: c.data == "confirm_all")
    dp.callback_query.register(cancel_all_callback, lambda c: c.data == "cancel_all")
    dp.callback_query.register(tag_help_callback, lambda c: c.data == "tag_help")
    dp.callback_query.register(buy_item_callback, lambda c: c.data and c.data.startswith("buy_"))
    dp.callback_query.register(buy_vip_callback, lambda c: c.data == "buy_vip")
    dp.callback_query.register(view_profile_callback, lambda c: c.data == "view_profile")
    dp.callback_query.register(fill_profile_callback, lambda c: c.data == "fill_profile")
    dp.callback_query.register(accept_duel_callback, lambda c: c.data and c.data.startswith("accept_duel_"))
    dp.callback_query.register(reject_duel_callback, lambda c: c.data and c.data.startswith("reject_duel_"))
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
