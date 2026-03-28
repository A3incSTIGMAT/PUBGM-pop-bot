"""
Умный парсер естественного языка для NEXUS
Понимает обращения к боту и команды в любом формате
"""

import re
import random
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    get_balance, update_balance, spend_balance, add_free_balance,
    get_user_stats, add_user
)
from handlers.roles import can_ban, can_mute, get_user_role
from handlers.rp_commands import RP_ACTIONS
from keyboards.main_menu import get_main_menu
from utils.logger import log_user, log_game, log_admin

router = Router()
bot: Bot = None

# Состояния для дуэли
class DuelState(StatesGroup):
    waiting_accept = State()

# Хранилище ожидающих дуэлей
pending_duels = {}

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

# Варианты обращения к боту
BOT_NAMES = [
    "nexus", "некс", "нэкс", "нэксус", "нексус",
    "nex", "некс", "nеxus", "nехus", "нексуc"
]

# Ключевые слова для распознавания команд
COMMAND_PATTERNS = {
    "ban": [r"забан(и|ь)(ть)?", r"заблокируй", r"кикни", r"выгони", r"удали", r"бан", r"block", r"ban"],
    "mute": [r"заглуш(и|ь)(ть)?", r"замут(и|ь)(ть)?", r"заткни", r"молчать", r"запрети писать", r"mute"],
    "all": [r"отметь всех", r"всех отметь", r"тег всех", r"все сюда", r"созови всех", r"позови всех"],
    "balance": [r"баланс", r"сколько денег", r"сколько монет", r"мой баланс", r"покажи баланс", r"сколько у меня"],
    "daily": [r"бонус", r"ежедневный", r"награда", r"получить бонус"],
    "gift": [r"подар(и|ю)", r"дай (.*?) монет", r"отправь (.*?) монет", r"переведи (.*?) монет", r"gift", r"подарок"],
    "rps": [r"камень", r"ножницы", r"бумага", r"сыграем в камень", r"давай в камень", r"камень-ножницы-бумага", r"rps"],
    "roulette": [r"рулетка", r"сыграем в рулетку", r"крути рулетку", r"рулет", r"roulette"],
    "slot": [r"слот", r"слоты", r"казино", r"слот-машина", r"slot"],
    "duel": [r"дуэль", r"вызови на дуэль", r"битва", r"сразиться", r"duel"],
    "accept_duel": [r"принять дуэль", r"согласен", r"принимаю", r"давай", r"ок"],
    "decline_duel": [r"отклонить", r"отказ", r"нет", r"не хочу"],
    "hug": [r"обними", r"обнять", r"обнял", r"обняла"],
    "kiss": [r"поцелуй", r"поцеловать", r"чмокни"],
    "slap": [r"шлепни", r"шлёпни", r"ударь"],
    "vip": [r"вип", r"купить вип", r"vip"],
    "menu": [r"меню", r"главное меню", r"открой меню", r"покажи меню"],
    "stats": [r"статистика", r"моя статистика", r"стата"],
    "top": [r"топ", r"топ богачей", r"кто самый богатый"]
}

# Хранилище для ежедневного бонуса
last_daily = {}

def extract_username(text: str) -> str:
    """Извлекает username из текста"""
    patterns = [
        r'@(\w+)',
        r'пользователя\s+(\w+)',
        r'юзера\s+(\w+)',
        r'участника\s+(\w+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def extract_amount(text: str) -> int:
    """Извлекает сумму из текста"""
    patterns = [
        r'(\d+)\s*монет', r'(\d+)\s*ncoin', r'(\d+)\s*нкоин',
        r'(\d+)\s*руб', r'(\d+)\s*₽', r'(\d+)\s*шт'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None

def extract_color(text: str) -> str:
    """Извлекает цвет для рулетки"""
    if 'красн' in text.lower():
        return 'red'
    if 'черн' in text.lower():
        return 'black'
    return 'red'

def extract_choice(text: str) -> str:
    """Извлекает выбор для камень-ножницы-бумага"""
    if 'камень' in text.lower() or 'камень' in text.lower():
        return 'камень'
    if 'ножниц' in text.lower():
        return 'ножницы'
    if 'бумаг' in text.lower():
        return 'бумага'
    return None

def extract_duration(text: str) -> int:
    """Извлекает время для мута"""
    patterns = [r'(\d+)\s*мин', r'(\d+)\s*минут', r'(\d+)\s*м', r'(\d+)\s*час', r'(\d+)\s*ч']
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            duration = int(match.group(1))
            if 'час' in pattern or 'ч' in pattern:
                return duration * 60
            return duration
    return 10

def detect_command(text: str) -> tuple:
    """Определяет команду по тексту"""
    text_lower = text.lower()
    
    for command, patterns in COMMAND_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return command, None
    
    username = extract_username(text)
    if username:
        amount = extract_amount(text)
        if amount:
            return 'gift', amount
    
    if 'дуэль' in text_lower or 'вызови' in text_lower:
        username = extract_username(text)
        if username:
            amount = extract_amount(text) or 50
            return 'duel', {'target': username, 'amount': amount}
    
    for action in RP_ACTIONS.keys():
        if action in text_lower:
            username = extract_username(text)
            if username:
                return action, username
    
    if 'рулетк' in text_lower:
        amount = extract_amount(text) or 100
        color = extract_color(text)
        return 'roulette', {'amount': amount, 'color': color}
    
    if 'слот' in text_lower:
        amount = extract_amount(text) or 100
        return 'slot', amount
    
    choice = extract_choice(text)
    if choice:
        return 'rps', choice
    
    return None, None

async def find_user_by_name(chat_id: int, name: str):
    """Находит пользователя по имени или username"""
    try:
        chat = await bot.get_chat(chat_id)
        async for member in chat.get_members():
            if member.user.username and member.user.username.lower() == name.lower():
                return member.user
            if member.user.full_name and name.lower() in member.user.full_name.lower():
                return member.user
    except:
        pass
    return None

@router.message(F.text)
async def smart_parser(message: Message, state: FSMContext):
    """Умный парсер всех сообщений"""
    if not message.text:
        return
    
    text = message.text
    text_lower = text.lower()
    
    # Проверяем, обращаются ли к боту
    is_bot_mentioned = any(name in text_lower for name in BOT_NAMES)
    
    # Проверяем команды со слешем (всегда работают)
    if text_lower.startswith('/'):
        return  # пропускаем, они обрабатываются другими роутерами
    
    # Если не обращаются к боту — пропускаем
    if not is_bot_mentioned:
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    add_user(user_id, chat_id, message.from_user.username)
    
    command, params = detect_command(text)
    
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
    
    # ========== БАН ==========
    if command == "ban":
        if not await can_ban(chat_id, user_id):
            await message.answer("❌ У вас нет прав банить пользователей.")
            return
        
        username = extract_username(text)
        if not username:
            await message.answer("❌ Укажите пользователя: @NEXUS забани @username")
            return
        
        target_user = await find_user_by_name(chat_id, username)
        if not target_user:
            await message.answer(f"❌ Пользователь {username} не найден.")
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
        
        username = extract_username(text)
        if not username:
            await message.answer("❌ Укажите пользователя: @NEXUS заглуши @username")
            return
        
        target_user = await find_user_by_name(chat_id, username)
        if not target_user:
            await message.answer(f"❌ Пользователь {username} не найден.")
            return
        
        duration = extract_duration(text)
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
        now = datetime.now()
        last = last_daily.get(user_id)
        
        if last and now - last < timedelta(hours=24):
            hours_left = 24 - (now - last).seconds // 3600
            await message.answer(f"⏰ Бонус уже получен сегодня. Следующий через {hours_left} часов.")
            return
        
        update_balance(user_id, chat_id, 50)
        last_daily[user_id] = now
        add_user(user_id, chat_id, message.from_user.username)
        
        new_balance = get_balance(user_id, chat_id)
        await message.answer(f"🎁 **Ежедневный бонус!**\n\n+50 NCoin\n💰 Баланс: {new_balance} NCoin")
    
    # ========== ПОДАРОК ==========
    elif command == "gift":
        amount = params if isinstance(params, int) else extract_amount(text)
        if not amount:
            await message.answer("🎁 Укажите сумму: @NEXUS подари @username 100 монет")
            return
        
        username = extract_username(text)
        if not username:
            await message.answer("🎁 Укажите получателя: @NEXUS подари @username 100 монет")
            return
        
        target_user = await find_user_by_name(chat_id, username)
        if not target_user:
            await message.answer(f"❌ Пользователь {username} не найден.")
            return
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        spend_balance(user_id, chat_id, amount)
        add_free_balance(target_user.id, chat_id, amount)
        
        await message.answer(f"🎁 Вы подарили {amount} NCoin пользователю @{username}")
        try:
            await bot.send_message(target_user.id, f"🎁 Вам подарили {amount} NCoin от {message.from_user.full_name}")
        except:
            pass
    
    # ========== КАМЕНЬ-НОЖНИЦЫ-БУМАГА ==========
    elif command == "rps":
        choice = params if isinstance(params, str) else extract_choice(text)
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
        if isinstance(params, dict):
            amount = params.get('amount', 100)
            color = params.get('color', 'red')
        else:
            amount = extract_amount(text) or 100
            color = extract_color(text)
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        # Списываем ставку
        spend_balance(user_id, chat_id, amount)
        
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
        amount = params if isinstance(params, int) else extract_amount(text) or 100
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        # Списываем ставку
        spend_balance(user_id, chat_id, amount)
        
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
        if isinstance(params, dict):
            target_name = params.get('target')
            amount = params.get('amount', 50)
        else:
            target_name = extract_username(text)
            amount = extract_amount(text) or 50
        
        if not target_name:
            await message.answer("⚔️ Укажите соперника: @NEXUS дуэль @username 100")
            return
        
        target_user = await find_user_by_name(chat_id, target_name)
        if not target_user:
            await message.answer(f"❌ Пользователь {target_name} не найден.")
            return
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        # Сохраняем дуэль
        duel_id = f"{chat_id}_{user_id}_{target_user.id}"
        pending_duels[duel_id] = {
            'challenger_id': user_id,
            'challenger_name': message.from_user.full_name,
            'target_id': target_user.id,
            'target_name': target_name,
            'amount': amount,
            'chat_id': chat_id
        }
        
        await message.answer(
            f"⚔️ **ДУЭЛЬ!**\n\n"
            f"{message.from_user.full_name} вызывает @{target_name} на дуэль!\n"
            f"💰 Ставка: {amount} NCoin\n\n"
            f"@{target_name}, принять вызов? Напишите: @NEXUS принять дуэль"
        )
    
    # ========== ПРИНЯТЬ ДУЭЛЬ ==========
    elif command == "accept_duel":
        # Ищем ожидающую дуэль
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
        
        # Проверяем баланс у обоих
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
        
        # Списываем ставки
        spend_balance(challenger_id, chat_id, amount)
        spend_balance(target_id, chat_id, amount)
        
        # Результат дуэли (случайный победитель)
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
        
        # Уведомляем победителя
        try:
            await bot.send_message(winner_id, f"🏆 Вы выиграли дуэль! +{win_amount} NCoin")
        except:
            pass
        
        del pending_duels[duel_id]
    
    # ========== РП-КОМАНДЫ ==========
    elif command in RP_ACTIONS:
        username = params if isinstance(params, str) else extract_username(text)
        if not username:
            await message.answer(f"{RP_ACTIONS[command]['emoji']} Укажите пользователя: @NEXUS {command} @username")
            return
        
        target_user = await find_user_by_name(chat_id, username)
        if not target_user:
            await message.answer(f"❌ Пользователь {username} не найден.")
            return
        
        variation = random.choice(RP_ACTIONS[command]["variations"])
        await message.answer(
            f"{RP_ACTIONS[command]['emoji']} **{message.from_user.full_name}** {variation.format(target=f'@{username}')}"
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
        from database.db import get_db
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
