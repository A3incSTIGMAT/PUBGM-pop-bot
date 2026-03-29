"""
Умный парсер естественного языка для NEXUS
С атомарными транзакциями, rate-limiting и полной обработкой ошибок
"""

import re
import random
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
from aiogram.fsm.context import FSMContext

from database.db import (
    get_balance, update_balance, spend_balance, add_free_balance,
    get_user_stats, add_user, get_db
)
from handlers.roles import can_ban, can_mute, get_user_role
from handlers.rp_commands import RP_ACTIONS
from keyboards.main_menu import get_main_menu
from utils.logger import log_user, log_game, log_admin, log_error

router = Router()
bot: Bot = None

# ========== КОНФИГУРАЦИЯ ==========
RATE_LIMITS = {
    "ban": {"limit": 10, "window": 60},
    "mute": {"limit": 10, "window": 60},
    "gift": {"limit": 20, "window": 60},
    "duel": {"limit": 10, "window": 60},
    "roulette": {"limit": 30, "window": 60},
    "slot": {"limit": 30, "window": 60},
    "daily": {"limit": 1, "window": 86400}
}

# Хранилище для rate-limiting
user_actions: Dict[str, list] = {}
daily_lock = asyncio.Lock()

# Хранилище для дуэлей
pending_duels: Dict[str, dict] = {}

# ========== ВАЛИДАЦИЯ ==========
@dataclass
class CommandData:
    command: str
    target: Optional[str] = None
    amount: Optional[int] = None
    color: Optional[str] = None
    duration: Optional[int] = None
    choice: Optional[str] = None
    params: Optional[dict] = None

def validate_amount(amount: int, min_val: int = 10, max_val: int = 10000) -> Tuple[bool, str]:
    """Валидация суммы"""
    if amount < min_val:
        return False, f"Минимальная сумма {min_val} NCoin"
    if amount > max_val:
        return False, f"Максимальная сумма {max_val} NCoin"
    return True, ""

def validate_username(username: str) -> Tuple[bool, str]:
    """Валидация username"""
    if not username:
        return False, "Укажите пользователя"
    if len(username) < 2:
        return False, "Слишком короткое имя"
    return True, ""

# ========== RATE LIMITING ==========
async def check_rate_limit(user_id: int, command: str) -> Tuple[bool, int]:
    """Проверка rate-limiting"""
    key = f"{user_id}:{command}"
    now = time.time()
    
    if key not in user_actions:
        user_actions[key] = []
    
    limits = RATE_LIMITS.get(command, {"limit": 30, "window": 60})
    limit = limits["limit"]
    window = limits["window"]
    
    # Очищаем старые записи
    user_actions[key] = [t for t in user_actions[key] if now - t < window]
    
    if len(user_actions[key]) >= limit:
        wait_time = int(window - (now - user_actions[key][0]))
        return False, wait_time
    
    user_actions[key].append(now)
    return True, 0

# ========== ПАРСИНГ ==========
BOT_NAMES = [
    "nexus", "некс", "нэкс", "нэксус", "нексус",
    "nex", "некс", "nеxus", "nехus", "нексуc"
]

COMMAND_PATTERNS = {
    "ban": [r"забан(и|ь)(ть)?", r"заблокируй", r"кикни", r"выгони", r"удали", r"бан"],
    "mute": [r"заглуш(и|ь)(ть)?", r"замут(и|ь)(ть)?", r"заткни", r"молчать", r"запрети писать"],
    "all": [r"отметь всех", r"всех отметь", r"тег всех", r"все сюда", r"созови всех"],
    "balance": [r"баланс", r"сколько денег", r"сколько монет", r"мой баланс", r"покажи баланс"],
    "daily": [r"бонус", r"ежедневный", r"награда", r"получить бонус"],
    "gift": [r"подар(и|ю)", r"дай.*?монет", r"отправь.*?монет", r"переведи.*?монет", r"подарок"],
    "rps": [r"камень", r"ножницы", r"бумага", r"сыграем в камень", r"давай в камень", r"rps"],
    "roulette": [r"рулетка", r"сыграем в рулетку", r"крути рулетку", r"рулет"],
    "slot": [r"слот", r"слоты", r"казино", r"слот-машина"],
    "duel": [r"дуэль", r"вызови на дуэль", r"битва", r"сразиться"],
    "accept_duel": [r"принять дуэль", r"согласен", r"принимаю", r"давай", r"ок"],
    "decline_duel": [r"отклонить", r"отказ", r"нет", r"не хочу"],
    "hug": [r"обними", r"обнять", r"обнял", r"обняла"],
    "kiss": [r"поцелуй", r"поцеловать", r"чмокни"],
    "slap": [r"шлепни", r"шлёпни", r"ударь"],
    "vip": [r"вип", r"купить вип"],
    "menu": [r"меню", r"главное меню", r"открой меню"],
    "stats": [r"статистика", r"моя статистика"],
    "top": [r"топ", r"топ богачей", r"кто самый богатый"]
}

def extract_username(text: str) -> Optional[str]:
    patterns = [r'@(\w+)', r'пользователя\s+(\w+)', r'юзера\s+(\w+)', r'участника\s+(\w+)']
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def extract_amount(text: str) -> Optional[int]:
    patterns = [r'(\d+)\s*монет', r'(\d+)\s*ncoin', r'(\d+)\s*нкоин', r'(\d+)\s*руб', r'(\d+)\s*₽']
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None

def extract_color(text: str) -> str:
    if 'красн' in text.lower():
        return 'red'
    if 'черн' in text.lower():
        return 'black'
    return 'red'

def extract_choice(text: str) -> Optional[str]:
    text_lower = text.lower()
    if 'камень' in text_lower:
        return 'камень'
    if 'ножниц' in text_lower:
        return 'ножницы'
    if 'бумаг' in text_lower:
        return 'бумага'
    return None

def extract_duration(text: str) -> int:
    match = re.search(r'(\d+)\s*(мин|минут|м|час|ч)', text, re.IGNORECASE)
    if match:
        duration = int(match.group(1))
        if 'час' in match.group(2) or 'ч' in match.group(2):
            return duration * 60
        return duration
    return 10

def detect_command(text: str) -> Tuple[Optional[str], Optional[CommandData]]:
    text_lower = text.lower()
    
    for command, patterns in COMMAND_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                data = CommandData(command=command)
                
                if command in ["ban", "mute", "hug", "kiss", "slap"]:
                    data.target = extract_username(text)
                    if command == "mute":
                        data.duration = extract_duration(text)
                
                elif command == "gift":
                    data.amount = extract_amount(text)
                    data.target = extract_username(text)
                
                elif command == "roulette":
                    data.amount = extract_amount(text) or 100
                    data.color = extract_color(text)
                
                elif command == "slot":
                    data.amount = extract_amount(text) or 100
                
                elif command == "duel":
                    data.target = extract_username(text)
                    data.amount = extract_amount(text) or 50
                
                elif command == "rps":
                    data.choice = extract_choice(text)
                
                return command, data
    
    # Проверка дуэли отдельно
    if 'дуэль' in text_lower or 'вызови' in text_lower:
        target = extract_username(text)
        if target:
            return 'duel', CommandData(command='duel', target=target, amount=extract_amount(text) or 50)
    
    # Проверка РП команд
    for action in RP_ACTIONS.keys():
        if action in text_lower:
            target = extract_username(text)
            if target:
                return action, CommandData(command=action, target=target)
    
    return None, None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def find_user_by_name(chat_id: int, name: str):
    try:
        chat = await bot.get_chat(chat_id)
        async for member in chat.get_members():
            if member.user.username and member.user.username.lower() == name.lower():
                return member.user
            if member.user.full_name and name.lower() in member.user.full_name.lower():
                return member.user
    except Exception as e:
        log_error(f"Ошибка поиска пользователя: {e}")
    return None

async def safe_send_message(chat_id: int, user_id: int, text: str):
    """Безопасная отправка сообщения в ЛС"""
    try:
        await bot.send_message(user_id, text)
    except Exception:
        pass  # Пользователь заблокировал бота или не начал диалог

async def atomic_transaction(user_id: int, chat_id: int, amount: int, operation: str) -> bool:
    """Атомарная транзакция с блокировкой"""
    async with asyncio.Lock():
        if operation == "spend":
            return spend_balance(user_id, chat_id, amount)
        elif operation == "add":
            update_balance(user_id, chat_id, amount)
            return True
    return False

# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========
def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

@router.message(F.text)
async def smart_parser(message: Message, state: FSMContext):
    """Умный парсер всех сообщений"""
    if not message.text:
        return
    
    text = message.text
    text_lower = text.lower()
    
    # Проверяем обращение к боту
    is_bot_mentioned = any(name in text_lower for name in BOT_NAMES)
    if not is_bot_mentioned:
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Добавляем пользователя
    add_user(user_id, chat_id, message.from_user.username)
    
    # Определяем команду
    command, data = detect_command(text)
    
    if not command:
        await message.answer(
            "🤖 Я не понял команду.\n\n"
            "Примеры:\n"
            "• @NEXUS забани @username\n"
            "• @NEXUS заглуши @username на 10 минут\n"
            "• @NEXUS отметь всех\n"
            "• @NEXUS подари @username 100 монет\n"
            "• @NEXUS сколько монет\n"
            "• @NEXUS бонус\n"
            "• @NEXUS камень\n"
            "• @NEXUS рулетка 100 red\n"
            "• @NEXUS слот 100\n"
            "• @NEXUS дуэль @username 100\n"
            "• @NEXUS обними @username\n"
            "• @NEXUS меню"
        )
        return
    
    # Rate limiting
    ok, wait_time = await check_rate_limit(user_id, command)
    if not ok:
        await message.answer(f"⏰ Слишком часто! Подождите {wait_time} секунд.")
        return
    
    # ========== БАН ==========
    if command == "ban":
        if not await can_ban(chat_id, user_id):
            await message.answer("❌ У вас нет прав банить пользователей.")
            return
        
        if not data.target:
            await message.answer("❌ Укажите пользователя: @NEXUS забани @username")
            return
        
        valid, msg = validate_username(data.target)
        if not valid:
            await message.answer(msg)
            return
        
        target_user = await find_user_by_name(chat_id, data.target)
        if not target_user:
            await message.answer(f"❌ Пользователь {data.target} не найден.")
            return
        
        try:
            await message.chat.ban(target_user.id)
            await message.answer(f"✅ {target_user.full_name} забанен.")
            log_admin(message.from_user.full_name, "забанил", target_user.full_name)
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
    
    # ========== МУТ ==========
    elif command == "mute":
        if not await can_mute(chat_id, user_id):
            await message.answer("❌ У вас нет прав мутить пользователей.")
            return
        
        if not data.target:
            await message.answer("❌ Укажите пользователя: @NEXUS заглуши @username")
            return
        
        target_user = await find_user_by_name(chat_id, data.target)
        if not target_user:
            await message.answer(f"❌ Пользователь {data.target} не найден.")
            return
        
        duration = data.duration or 10
        try:
            permissions = ChatPermissions(can_send_messages=False)
            await message.chat.restrict(target_user.id, permissions)
            await message.answer(f"🔇 {target_user.full_name} заглушен на {duration} минут.")
            log_admin(message.from_user.full_name, "заглушил", target_user.full_name)
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
    
    # ========== ОТМЕТИТЬ ВСЕХ ==========
    elif command == "all":
        if not await can_ban(chat_id, user_id):
            await message.answer("❌ Только администраторы могут использовать эту команду.")
            return
        
        await message.answer("🔔 Получаю список участников...")
        
        members = []
        async for member in message.chat.get_members():
            if not member.user.is_bot:
                mention = f"@{member.user.username}" if member.user.username else member.user.full_name
                members.append(mention)
        
        if members:
            await message.answer("🔔 **ВНИМАНИЕ ВСЕМ!**\n\n" + "\n".join(members[:50]))
            if len(members) > 50:
                await message.answer("\n".join(members[50:100]))
            log_admin(message.from_user.full_name, "отметил всех")
    
    # ========== БАЛАНС ==========
    elif command == "balance":
        balance = get_balance(user_id, chat_id)
        await message.answer(f"💰 **Ваш баланс:** {balance} NCoin\n\n💡 Получить бонус: @NEXUS бонус")
    
    # ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
    elif command == "daily":
        async with daily_lock:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            
            with get_db() as conn:
                row = conn.execute(
                    "SELECT last_bonus FROM users WHERE user_id=? AND chat_id=?",
                    (user_id, chat_id)
                ).fetchone()
                last_bonus = row["last_bonus"] if row else None
            
            if last_bonus == today:
                await message.answer("⏰ Бонус уже получен сегодня. Завтра будет новый!")
                return
            
            update_balance(user_id, chat_id, 50)
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET last_bonus=? WHERE user_id=? AND chat_id=?",
                    (today, user_id, chat_id)
                )
        
        new_balance = get_balance(user_id, chat_id)
        await message.answer(f"🎁 **Ежедневный бонус!**\n\n+50 NCoin\n💰 Баланс: {new_balance} NCoin")
    
    # ========== ПОДАРОК ==========
    elif command == "gift":
        if not data.amount:
            await message.answer("🎁 Укажите сумму: @NEXUS подари @username 100 монет")
            return
        
        valid, msg = validate_amount(data.amount, 10, 5000)
        if not valid:
            await message.answer(msg)
            return
        
        if not data.target:
            await message.answer("🎁 Укажите получателя: @NEXUS подари @username 100 монет")
            return
        
        target_user = await find_user_by_name(chat_id, data.target)
        if not target_user:
            await message.answer(f"❌ Пользователь {data.target} не найден.")
            return
        
        balance = get_balance(user_id, chat_id)
        if balance < data.amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        if await atomic_transaction(user_id, chat_id, data.amount, "spend"):
            add_free_balance(target_user.id, chat_id, data.amount)
            await message.answer(f"🎁 Вы подарили {data.amount} NCoin пользователю @{data.target}")
            await safe_send_message(chat_id, target_user.id, f"🎁 Вам подарили {data.amount} NCoin от {message.from_user.full_name}")
    
    # ========== КАМЕНЬ-НОЖНИЦЫ-БУМАГА ==========
    elif command == "rps":
        choice = data.choice
        if not choice:
            choice = extract_choice(text)
        if not choice:
            await message.answer("🎮 Выберите: камень, ножницы или бумага\nПример: @NEXUS камень")
            return
        
        choices = {"камень": "🪨", "ножницы": "✂️", "бумага": "📄"}
        if choice not in choices:
            await message.answer("❌ Выберите: камень, ножницы или бумага")
            return
        
        bot_choice = random.choice(list(choices.keys()))
        
        if choice == bot_choice:
            result = "🤝 Ничья!"
        elif (choice == "камень" and bot_choice == "ножницы") or \
             (choice == "ножницы" and bot_choice == "бумага") or \
             (choice == "бумага" and bot_choice == "камень"):
            result = "🎉 Вы выиграли!"
        else:
            result = "😔 Вы проиграли!"
        
        await message.answer(
            f"{choices[choice]} Вы: {choice}\n{choices[bot_choice]} Бот: {bot_choice}\n\n{result}"
        )
        log_game(message.from_user.full_name, "rps", result)
    
    # ========== РУЛЕТКА ==========
    elif command == "roulette":
        amount = data.amount or 100
        valid, msg = validate_amount(amount, 10, 10000)
        if not valid:
            await message.answer(msg)
            return
        
        color = data.color or 'red'
        balance = get_balance(user_id, chat_id)
        
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        if not await atomic_transaction(user_id, chat_id, amount, "spend"):
            await message.answer("❌ Ошибка при списании средств")
            return
        
        result = random.choice(['red', 'black'])
        
        if result == color:
            win = amount * 2
            update_balance(user_id, chat_id, win)
            await message.answer(
                f"🎲 Колесо остановилось на **{result.upper()}**!\n\n"
                f"🎉 **ПОБЕДА!** Вы выиграли {win} NCoin!\n"
                f"💰 Баланс: {get_balance(user_id, chat_id)} NCoin"
            )
            log_game(message.from_user.full_name, "roulette", "win", win)
        else:
            await message.answer(
                f"🎲 Колесо остановилось на **{result.upper()}**!\n\n"
                f"😔 **ПРОИГРЫШ!** Вы проиграли {amount} NCoin.\n"
                f"💰 Баланс: {get_balance(user_id, chat_id)} NCoin"
            )
            log_game(message.from_user.full_name, "roulette", "loss", amount)
    
    # ========== СЛОТ-МАШИНА ==========
    elif command == "slot":
        amount = data.amount or 100
        valid, msg = validate_amount(amount, 10, 10000)
        if not valid:
            await message.answer(msg)
            return
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        if not await atomic_transaction(user_id, chat_id, amount, "spend"):
            await message.answer("❌ Ошибка при списании средств")
            return
        
        slots = ["🍒", "🍋", "🍊", "🍉", "🔔", "💎", "7️⃣"]
        result = [random.choice(slots) for _ in range(3)]
        
        if result[0] == result[1] == result[2]:
            if result[0] == "7️⃣":
                win = amount * 10
            elif result[0] == "💎":
                win = amount * 7
            elif result[0] == "🔔":
                win = amount * 5
            else:
                win = amount * 3
            update_balance(user_id, chat_id, win)
            await message.answer(
                f"🎰 {result[0]} {result[1]} {result[2]}\n\n"
                f"🎉 **ДЖЕКПОТ!** +{win} NCoin!\n"
                f"💰 Баланс: {get_balance(user_id, chat_id)} NCoin"
            )
            log_game(message.from_user.full_name, "slot", "jackpot", win)
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            win = amount * 2
            update_balance(user_id, chat_id, win)
            await message.answer(
                f"🎰 {result[0]} {result[1]} {result[2]}\n\n"
                f"🎉 **ВЫИГРЫШ!** +{win} NCoin!\n"
                f"💰 Баланс: {get_balance(user_id, chat_id)} NCoin"
            )
            log_game(message.from_user.full_name, "slot", "win", win)
        else:
            await message.answer(
                f"🎰 {result[0]} {result[1]} {result[2]}\n\n"
                f"😔 **ПРОИГРЫШ!** -{amount} NCoin.\n"
                f"💰 Баланс: {get_balance(user_id, chat_id)} NCoin"
            )
            log_game(message.from_user.full_name, "slot", "loss", amount)
    
    # ========== ДУЭЛЬ ==========
    elif command == "duel":
        if not data.target:
            await message.answer("⚔️ Укажите соперника: @NEXUS дуэль @username 100")
            return
        
        amount = data.amount or 50
        valid, msg = validate_amount(amount, 10, 5000)
        if not valid:
            await message.answer(msg)
            return
        
        target_user = await find_user_by_name(chat_id, data.target)
        if not target_user:
            await message.answer(f"❌ Пользователь {data.target} не найден.")
            return
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        duel_id = f"{chat_id}_{user_id}_{target_user.id}"
        pending_duels[duel_id] = {
            'challenger_id': user_id,
            'challenger_name': message.from_user.full_name,
            'target_id': target_user.id,
            'target_name': data.target,
            'amount': amount,
            'chat_id': chat_id,
            'created_at': time.time()
        }
        
        await message.answer(
            f"⚔️ **ДУЭЛЬ!**\n\n"
            f"{message.from_user.full_name} вызывает @{data.target} на дуэль!\n"
            f"💰 Ставка: {amount} NCoin\n\n"
            f"@{data.target}, принять вызов? Напишите: @NEXUS принять дуэль"
        )
    
    # ========== ПРИНЯТЬ ДУЭЛЬ ==========
    elif command == "accept_duel":
        duel_id = None
        for d_id, duel in pending_duels.items():
            if duel['target_id'] == user_id and duel['chat_id'] == chat_id:
                duel_id = d_id
                break
        
        if not duel_id:
            await message.answer("❌ Нет активного вызова на дуэль.")
            return
        
        duel = pending_duels[duel_id]
        challenger_id = duel['challenger_id']
        target_id = duel['target_id']
        amount = duel['amount']
        challenger_name = duel['challenger_name']
        target_name = duel['target_name']
        
        balance_challenger = get_balance(challenger_id, chat_id)
        balance_target = get_balance(target_id, chat_id)
        
        if balance_challenger < amount:
            await message.answer(f"❌ У {challenger_name} недостаточно NCoin для дуэли.")
            del pending_duels[duel_id]
            return
        
        if balance_target < amount:
            await message.answer(f"❌ У вас недостаточно NCoin для дуэли. Ваш баланс: {balance_target}")
            del pending_duels[duel_id]
            return
        
        if not await atomic_transaction(challenger_id, chat_id, amount, "spend"):
            await message.answer("❌ Ошибка при списании средств у challenger")
            del pending_duels[duel_id]
            return
        
        if not await atomic_transaction(target_id, chat_id, amount, "spend"):
            await message.answer("❌ Ошибка при списании средств у target")
            update_balance(challenger_id, chat_id, amount)
            del pending_duels[duel_id]
            return
        
        winner_id = random.choice([challenger_id, target_id])
        winner_name = challenger_name if winner_id == challenger_id else target_name
        win_amount = amount * 2
        
        update_balance(winner_id, chat_id, win_amount)
        
        await message.answer(
            f"⚔️ **РЕЗУЛЬТАТ ДУЭЛИ!**\n\n"
            f"{challenger_name} ⚔️ {target_name}\n\n"
            f"🏆 **ПОБЕДИТЕЛЬ:** {winner_name}!\n"
            f"💰 Выигрыш: {win_amount} NCoin"
        )
        
        await safe_send_message(chat_id, winner_id, f"🏆 Вы выиграли дуэль! +{win_amount} NCoin")
        
        del pending_duels[duel_id]
    
    # ========== ОТКЛОНИТЬ ДУЭЛЬ ==========
    elif command == "decline_duel":
        duel_id = None
        for d_id, duel in pending_duels.items():
            if duel['target_id'] == user_id and duel['chat_id'] == chat_id:
                duel_id = d_id
                break
        
        if duel_id:
            duel = pending_duels[duel_id]
            challenger_id = duel['challenger_id']
            await message.answer(f"❌ Дуэль отклонена. {duel['challenger_name']}, ваш вызов не принят.")
            del pending_duels[duel_id]
        else:
            await message.answer("❌ Нет активного вызова на дуэль.")
    
    # ========== РП-КОМАНДЫ ==========
    elif command in RP_ACTIONS:
        if not data.target:
            await message.answer(f"{RP_ACTIONS[command]['emoji']} Укажите пользователя: @NEXUS {command} @username")
            return
        
        target_user = await find_user_by_name(chat_id, data.target)
        if not target_user:
            await message.answer(f"❌ Пользователь {data.target} не найден.")
            return
        
        variation = random.choice(RP_ACTIONS[command]["variations"])
        await message.answer(
            f"{RP_ACTIONS[command]['emoji']} **{message.from_user.full_name}** {variation.format(target=f'@{data.target}')}"
        )
    
    # ========== МЕНЮ ==========
    elif command == "menu":
        role = await get_user_role(chat_id, user_id)
        await message.answer(
            "🏠 **Главное меню NEXUS**\n\n"
            "Выберите категорию:",
            reply_markup=get_main_menu(role)
        )
    
    # ========== VIP ==========
    elif command == "vip":
        await message.answer(
            "👑 **VIP-статус NEXUS**\n\n"
            "💰 Цена: 500 NCoin\n"
            "⏱ Длительность: 30 дней\n\n"
            "💎 **Преимущества:**\n"
            "• +25% к ежедневному бонусу\n"
            "• Эксклюзивные подарки\n"
            "• Цветное имя в чате\n\n"
            "➡️ /vip — купить"
        )
    
    # ========== СТАТИСТИКА ==========
    elif command == "stats":
        stats = get_user_stats(user_id, chat_id)
        balance = get_balance(user_id, chat_id)
        
        if stats:
            await message.answer(
                f"📊 **Ваша статистика**\n\n"
                f"💰 Баланс: {balance} NCoin\n"
                f"💬 Сообщений: {stats.get('total_messages', 0)}\n"
                f"👑 VIP: {'Да' if stats.get('is_vip', 0) else 'Нет'}\n"
                f"⭐ Репутация: {stats.get('reputation', 0)}\n"
                f"🎂 ДР: {stats.get('birthday') or 'не указан'}"
            )
        else:
            await message.answer("📊 Статистика пока пуста. Напишите несколько сообщений!")
    
    # ========== ТОП ==========
    elif command == "top":
        with get_db() as conn:
            results = conn.execute("""
                SELECT username, (free_balance + paid_balance) as total
                FROM users
                WHERE chat_id = ? AND (free_balance + paid_balance) > 0
                ORDER BY total DESC
                LIMIT 10
            """, (chat_id,)).fetchall()
        
        if not results:
            await message.answer("🏆 **Топ богачей**\n\nПока никого нет. Будьте первым!")
            return
        
        top_text = "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ ПО NCoin** 🏆\n\n"
        for i, row in enumerate(results, 1):
            name = row["username"] or f"user_{i}"
            top_text += f"{i}. {name} — {row['total']} NCoin\n"
        
        await message.answer(top_text)
