"""
Умный парсер естественного языка для NEXUS
Понимает обращения к боту: NEXUS, некс, нэкс, нэксус, Нексус и т.д.
"""

import re
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database.db import get_balance, update_balance, spend_balance, add_free_balance
from handlers.roles import can_ban, can_mute, get_user_role
from handlers.rp_commands import RP_ACTIONS
from utils.logger import log_user, log_game, log_admin

router = Router()
bot: Bot = None

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
    "ban": [
        r"забан(и|ь)(ть)?",
        r"заблокируй",
        r"кикни",
        r"выгони",
        r"удали",
        r"бан",
        r"block",
        r"ban"
    ],
    "mute": [
        r"заглуш(и|ь)(ть)?",
        r"замут(и|ь)(ть)?",
        r"заткни",
        r"молчать",
        r"запрети писать",
        r"mute"
    ],
    "all": [
        r"отметь всех",
        r"всех отметь",
        r"тег всех",
        r"тегирование",
        r"все сюда",
        r"созови всех",
        r"позови всех"
    ],
    "balance": [
        r"баланс",
        r"сколько денег",
        r"сколько монет",
        r"мой баланс",
        r"покажи баланс"
    ],
    "daily": [
        r"бонус",
        r"ежедневный",
        r"награда",
        r"получить бонус"
    ],
    "gift": [
        r"подар(и|ю)",
        r"дай (.*?) монет",
        r"отправь (.*?) монет",
        r"переведи (.*?) монет",
        r"gift"
    ],
    "rps": [
        r"камень",
        r"ножницы",
        r"бумага",
        r"сыграем в камень",
        r"давай в камень"
    ],
    "roulette": [
        r"рулетка",
        r"сыграем в рулетку",
        r"крути рулетку"
    ],
    "slot": [
        r"слот",
        r"слоты",
        r"казино",
        r"слот-машина"
    ],
    "duel": [
        r"дуэль",
        r"вызови на дуэль",
        r"битва",
        r"сразиться"
    ],
    "hug": [
        r"обними",
        r"обнять",
        r"обнял",
        r"обняла"
    ],
    "kiss": [
        r"поцелуй",
        r"поцеловать",
        r"чмокни"
    ],
    "slap": [
        r"шлепни",
        r"шлёпни",
        r"ударь"
    ],
    "vip": [
        r"вип",
        r"купить вип",
        r"vip"
    ],
    "menu": [
        r"меню",
        r"главное меню",
        r"открой меню",
        r"покажи меню"
    ]
}

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
        r'(\d+)\s*монет',
        r'(\d+)\s*ncoin',
        r'(\d+)\s*нкоин',
        r'(\d+)\s*руб',
        r'(\d+)\s*₽'
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
    return None

def extract_choice(text: str) -> str:
    """Извлекает выбор для камень-ножницы-бумага"""
    if 'камень' in text.lower():
        return 'камень'
    if 'ножниц' in text.lower():
        return 'ножницы'
    if 'бумаг' in text.lower():
        return 'бумага'
    return None

def extract_duration(text: str) -> int:
    """Извлекает время для мута"""
    patterns = [
        r'(\d+)\s*мин',
        r'(\d+)\s*минут',
        r'на (\d+)\s*мин',
        r'(\d+)\s*м'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 10

def detect_command(text: str) -> tuple:
    """Определяет команду по тексту"""
    text_lower = text.lower()
    
    # Проверяем все паттерны
    for command, patterns in COMMAND_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return command, None
    
    # Проверка на наличие username (для gift)
    if extract_username(text):
        amount = extract_amount(text)
        if amount:
            return 'gift', amount
    
    # Проверка на дуэль с username
    if 'дуэль' in text_lower or 'вызови' in text_lower:
        username = extract_username(text)
        if username:
            amount = extract_amount(text) or 50
            return 'duel', {'target': username, 'amount': amount}
    
    # Проверка на РП-команды
    for action in RP_ACTIONS.keys():
        if action in text_lower:
            username = extract_username(text)
            if username:
                return action, username
    
    # Проверка на рулетку
    if 'рулетк' in text_lower:
        amount = extract_amount(text) or 100
        color = extract_color(text) or 'red'
        return 'roulette', {'amount': amount, 'color': color}
    
    # Проверка на слот-машину
    if 'слот' in text_lower or 'казино' in text_lower:
        amount = extract_amount(text) or 100
        return 'slot', amount
    
    # Проверка на камень-ножницы-бумага
    choice = extract_choice(text)
    if choice:
        return 'rps', choice
    
    return None, None

async def find_user_by_name(chat_id: int, name: str):
    """Находит пользователя по имени или username"""
    try:
        async for member in bot.get_chat(chat_id).get_members():
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
    is_bot_mentioned = False
    for name in BOT_NAMES:
        if name in text_lower:
            is_bot_mentioned = True
            break
    
    if not is_bot_mentioned and not any(cmd in text_lower for cmd in ['/ask', '/balance', '/daily', '/rps', '/roulette', '/slot', '/duel', '/hug', '/kiss', '/slap', '/vip', '/menu']):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Определяем команду
    command, params = detect_command(text)
    
    if not command:
        return
    
    # Обрабатываем команды
    if command == "ban":
        if not await can_ban(chat_id, user_id):
            await message.answer("❌ У вас нет прав банить пользователей.")
            return
        
        username = extract_username(text)
        if not username:
            await message.answer("❌ Укажите пользователя: @username")
            return
        
        target_user = await find_user_by_name(chat_id, username)
        if not target_user:
            await message.answer(f"❌ Пользователь {username} не найден.")
            return
        
        await message.chat.ban(target_user.id)
        await message.answer(f"✅ {target_user.full_name} забанен.")
        log_admin(message.from_user.full_name, "забанил", target_user.full_name)
    
    elif command == "mute":
        if not await can_mute(chat_id, user_id):
            await message.answer("❌ У вас нет прав мутить пользователей.")
            return
        
        username = extract_username(text)
        if not username:
            await message.answer("❌ Укажите пользователя: @username")
            return
        
        target_user = await find_user_by_name(chat_id, username)
        if not target_user:
            await message.answer(f"❌ Пользователь {username} не найден.")
            return
        
        duration = extract_duration(text)
        await message.chat.restrict(target_user.id, permissions=ChatPermissions(can_send_messages=False))
        await message.answer(f"🔇 {target_user.full_name} заглушен на {duration} минут.")
        log_admin(message.from_user.full_name, "заглушил", target_user.full_name)
    
    elif command == "all":
        if not await can_ban(chat_id, user_id):
            await message.answer("❌ Только администраторы могут использовать эту команду.")
            return
        
        members = []
        async for member in message.chat.get_members():
            if not member.user.is_bot:
                mention = f"@{member.user.username}" if member.user.username else member.user.full_name
                members.append(mention)
        
        if members:
            await message.answer("🔔 **ВНИМАНИЕ ВСЕМ!**\n\n" + "\n".join(members[:50]))
            log_admin(message.from_user.full_name, "отметил всех")
    
    elif command == "balance":
        balance = get_balance(user_id, chat_id)
        await message.answer(f"💰 Ваш баланс: {balance} NCoin")
    
    elif command == "daily":
        from datetime import datetime, timedelta
        last_daily = {}
        now = datetime.now()
        last = last_daily.get(user_id)
        
        if last and now - last < timedelta(hours=24):
            await message.answer("⏰ Бонус уже получен сегодня.")
            return
        
        update_balance(user_id, chat_id, 50)
        last_daily[user_id] = now
        await message.answer("🎁 +50 NCoin!")
    
    elif command == "gift":
        amount = params if isinstance(params, int) else None
        if not amount:
            amount = extract_amount(text)
        if not amount:
            await message.answer("🎁 Укажите сумму: подари @username 100 монет")
            return
        
        username = extract_username(text)
        if not username:
            await message.answer("🎁 Укажите получателя: подари @username 100 монет")
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
    
    elif command == "rps":
        choice = params
        if not choice:
            choice = extract_choice(text)
        if not choice:
            await message.answer("🎮 Выберите: камень, ножницы или бумага")
            return
        
        import random
        choices = {"камень": "🪨", "ножницы": "✂️", "бумага": "📄"}
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
    
    elif command == "roulette":
        if isinstance(params, dict):
            amount = params.get('amount', 100)
            color = params.get('color', 'red')
        else:
            amount = extract_amount(text) or 100
            color = extract_color(text) or 'red'
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        import random
        result = random.choice(['red', 'black'])
        
        if result == color:
            win = amount * 2
            update_balance(user_id, chat_id, win)
            await message.answer(f"🎲 Выпало {result.upper()}! 🎉 Вы выиграли {win} NCoin!")
        else:
            spend_balance(user_id, chat_id, amount)
            await message.answer(f"🎲 Выпало {result.upper()}! 😔 Вы проиграли {amount} NCoin.")
    
    elif command == "slot":
        amount = params if isinstance(params, int) else extract_amount(text) or 100
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        import random
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
            await message.answer(f"🎰 {result[0]} {result[1]} {result[2]}\n\n🎉 **ДЖЕКПОТ!** +{win} NCoin!")
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            win = amount * 2
            update_balance(user_id, chat_id, win)
            await message.answer(f"🎰 {result[0]} {result[1]} {result[2]}\n\n🎉 **ВЫИГРЫШ!** +{win} NCoin!")
        else:
            spend_balance(user_id, chat_id, amount)
            await message.answer(f"🎰 {result[0]} {result[1]} {result[2]}\n\n😔 **ПРОИГРЫШ!** -{amount} NCoin.")
    
    elif command == "duel":
        if isinstance(params, dict):
            target_name = params.get('target')
            amount = params.get('amount', 50)
        else:
            target_name = extract_username(text)
            amount = extract_amount(text) or 50
        
        if not target_name:
            await message.answer("⚔️ Укажите соперника: дуэль @username 100")
            return
        
        target_user = await find_user_by_name(chat_id, target_name)
        if not target_user:
            await message.answer(f"❌ Пользователь {target_name} не найден.")
            return
        
        balance = get_balance(user_id, chat_id)
        if balance < amount:
            await message.answer(f"❌ Недостаточно NCoin. Ваш баланс: {balance}")
            return
        
        await message.answer(
            f"⚔️ **Дуэль!**\n\n"
            f"{message.from_user.full_name} вызывает @{target_name} на дуэль!\n"
            f"💰 Ставка: {amount} NCoin\n\n"
            f"Для принятия напишите: @{target_name}, принять дуэль"
        )
    
    elif command in RP_ACTIONS:
        username = params if isinstance(params, str) else extract_username(text)
        if not username:
            await message.answer(f"{RP_ACTIONS[command]['emoji']} Укажите пользователя: {command} @username")
            return
        
        target_user = await find_user_by_name(chat_id, username)
        if not target_user:
            await message.answer(f"❌ Пользователь {username} не найден.")
            return
        
        import random
        variation = random.choice(RP_ACTIONS[command]["variations"])
        await message.answer(
            f"{RP_ACTIONS[command]['emoji']} **{message.from_user.full_name}** {variation.format(target=f'@{username}')}"
        )
    
    elif command == "menu":
        from keyboards.main_menu import get_main_menu
        role = await get_user_role(chat_id, user_id)
        await message.answer(
            "🏠 **Главное меню NEXUS**\n\n"
            "Выберите категорию:",
            reply_markup=get_main_menu(role)
        )
    
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
