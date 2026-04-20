"""
Умный парсер команд NEXUS Bot
Обрабатывает ТОЛЬКО текст, НЕ начинающийся с /
Умные теги, общий сбор, РП команды, крестики-нолики, действия через @ и reply
"""

import re
import logging
import time
import hashlib
import asyncio
from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# Хранилище состояний анкеты (из profile.py)
profile_states = {}

# Словарь соответствия фраз -> slug категорий для умных тегов
TAG_KEYWORDS = {
    'pubg': ['пубг', 'pubg', 'пабг', 'королевская битва', 'сквад', 'ранкед', 'игроков в пубг'],
    'cs2': ['кс2', 'cs2', 'counter-strike', 'катка', 'матчмейкинг', 'игроков в кс'],
    'dota': ['дота', 'dota', 'дота 2', 'пати', 'катка', 'игроков в доту'],
    'mafia': ['мафия', 'mafia', 'партия', 'сбор', 'игроков в мафию'],
    'video_call': ['звонок', 'созвон', 'видеозвонок', 'скайп', 'discord', 'позвонить'],
    'important': ['важный вопрос', 'помогите', 'нужна помощь', 'вопрос', 'совет', 'подскажите'],
    'giveaway': ['розыгрыш', 'giveaway', 'конкурс', 'ивент', 'приз'],
    'offtopic': ['флуд', 'оффтоп', 'offtopic', 'болталка', 'поболтать'],
    'tech': ['техническое', 'баг', 'ошибка', 'bug', 'сломалась', 'не работает'],
    'urgent': ['срочно', 'urgent', 'помощь админам', 'внимание админы', 'срочная помощь'],
}

# РП действия
RP_ACTIONS = {
    # Объятия
    'обнять': 'hug', 'обнял': 'hug', 'обнимаю': 'hug', 'обнимает': 'hug',
    # Поцелуи
    'поцеловать': 'kiss', 'поцелуй': 'kiss', 'чмок': 'kiss', 'чмокнуть': 'kiss',
    'целовать': 'kiss', 'засос': 'kiss',
    # Пнуть
    'пнуть': 'kick', 'пнул': 'kick', 'пинаю': 'kick', 'пинает': 'kick',
    # Погладить
    'погладить': 'pat', 'погладил': 'pat', 'глажу': 'pat', 'гладит': 'pat',
    'потрепать': 'pat',
    # Дать леща
    'дать леща': 'slap', 'лещ': 'slap', 'шлёпнуть': 'slap', 'шлёпает': 'slap',
    'дать пощечину': 'slap', 'пощечина': 'slap',
    # Ударить
    'ударить': 'punch', 'врезать': 'punch', 'стукнуть': 'punch',
    'дать в табло': 'punch', 'втащить': 'punch',
    # Приветствие
    'привет': 'hello', 'здарова': 'hello', 'приветствую': 'hello',
    'ку': 'hello', 'хай': 'hello',
    # Пока
    'пока': 'bye', 'прощай': 'bye', 'до свидания': 'bye',
    # Поблагодарить
    'спасибо': 'thanks', 'благодарю': 'thanks', 'спс': 'thanks',
    # Извиниться
    'извини': 'sorry', 'прости': 'sorry', 'извиняюсь': 'sorry', 'сорри': 'sorry',
    # Поздравить
    'поздравляю': 'congrats', 'с днём рождения': 'congrats', 'с др': 'congrats',
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Получить пользователя или создать если не существует"""
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Auto-registered user {user_id} in smart_commands")
    return user


def extract_username(text: str) -> str:
    """Извлечь username из текста"""
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    return match.group(1) if match else None


def extract_number(text: str) -> int:
    """Извлечь число из текста"""
    match = re.search(r'\b\d+\b', text)
    return int(match.group()) if match else 0


def _escape_html(text: str) -> str:
    """Экранирование HTML"""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ==================== РП ДЕЙСТВИЯ ====================

RP_TEXTS = {
    'hug': [
        "🤗 {from_name} крепко обнимает {target_name}!",
        "🫂 {from_name} заключает {target_name} в тёплые объятия!",
        "💕 {from_name} нежно обнимает {target_name}!",
    ],
    'kiss': [
        "💋 {from_name} целует {target_name}!",
        "😘 {from_name} чмокает {target_name} в щёчку!",
        "❤️ {from_name} страстно целует {target_name}!",
    ],
    'kick': [
        "👢 {from_name} пинает {target_name}!",
        "🦵 {from_name} даёт пинка {target_name}!",
        "💢 {from_name} со всей дури пинает {target_name}!",
    ],
    'pat': [
        "🫳 {from_name} гладит {target_name} по голове!",
        "🐾 {from_name} нежно треплет {target_name}!",
        "✨ {from_name} ласково гладит {target_name}!",
    ],
    'slap': [
        "👋 {from_name} даёт леща {target_name}!",
        "💥 {from_name} отвешивает пощёчину {target_name}!",
        "😠 {from_name} шлёпает {target_name}!",
    ],
    'punch': [
        "👊 {from_name} бьёт {target_name}!",
        "💢 {from_name} врезает {target_name}!",
        "🥊 {from_name} прописывает {target_name} в табло!",
    ],
    'hello': [
        "👋 {from_name} приветствует {target_name}!",
        "✨ {from_name} здоровается с {target_name}!",
        "🤝 {from_name} жмёт руку {target_name}!",
    ],
    'bye': [
        "👋 {from_name} прощается с {target_name}!",
        "😢 {from_name} говорит «пока» {target_name}!",
        "🌙 {from_name} желает спокойной ночи {target_name}!",
    ],
    'thanks': [
        "🙏 {from_name} благодарит {target_name}!",
        "💖 {from_name} говорит спасибо {target_name}!",
        "🤗 {from_name} очень признателен {target_name}!",
    ],
    'sorry': [
        "😔 {from_name} извиняется перед {target_name}!",
        "🙇 {from_name} просит прощения у {target_name}!",
        "💔 {from_name} сожалеет, {target_name}!",
    ],
    'congrats': [
        "🎉 {from_name} поздравляет {target_name}!",
        "🎊 {from_name} радуется за {target_name}!",
        "🏆 {from_name} жмёт руку {target_name} в знак уважения!",
    ],
}


async def send_rp_action(message: types.Message, from_id: int, target_id: int, target_user: dict, action: str):
    """Отправить РП действие"""
    from_user = await db.get_user(from_id)
    from_name = from_user.get('first_name', 'Пользователь') if from_user else 'Пользователь'
    target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
    
    texts = RP_TEXTS.get(action, [f"{from_name} взаимодействует с {target_name}"])
    import random
    text = random.choice(texts).format(from_name=from_name, target_name=target_name)
    
    await message.answer(text)


async def challenge_xo(message: types.Message, from_id: int, target_id: int, target_user: dict, bet: int = 0):
    """Вызвать на крестики-нолики"""
    if from_id == target_id:
        await message.answer("❌ Нельзя вызвать самого себя!")
        return
    
    if bet > 0:
        balance = await db.get_balance(from_id)
        if balance < bet:
            await message.answer(f"❌ У вас недостаточно средств! Баланс: {balance} NCoin")
            return
    
    game_id = f"xo_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    try:
        from handlers.tictactoe import active_games
    except ImportError:
        await message.answer("❌ Игра временно недоступна")
        return
    
    active_games[game_id] = {
        "type": "pvp",
        "board": [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]],
        "player_x": from_id,
        "player_o": target_id,
        "current_turn": "X",
        "bet": bet,
        "chat_id": message.chat.id,
        "created_at": time.time(),
        "last_move": time.time(),
        "pending": True,
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]
    ])
    
    from_name = (await db.get_user(from_id)).get('first_name', 'Пользователь')
    target_name = target_user.get('first_name', 'Пользователь')
    target_username = target_user.get('username', target_name)
    
    bet_text = f"<b>{bet} NCoin</b>" if bet > 0 else "<b>без ставки</b>"
    
    await message.answer(
        f"🎮 <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
        f"👤 {_escape_html(from_name)} вызывает {_escape_html(target_name)}!\n"
        f"💰 Ставка: {bet_text}\n\n"
        f"@{target_username}, примите вызов!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def show_profile(message: types.Message, target_id: int, target_user: dict):
    """Показать анкету пользователя"""
    profile = await db.get_profile(target_id)
    balance = await db.get_balance(target_id)
    user = await db.get_user(target_id)
    
    target_name = target_user.get('first_name', 'Пользователь')
    
    if not profile:
        await message.answer(
            f"👤 <b>{_escape_html(target_name)}</b>\n\n"
            f"❌ Анкета не заполнена\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"🏆 Побед: {user.get('wins', 0)} | Поражений: {user.get('losses', 0)}",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = (
        f"👤 <b>АНКЕТА {_escape_html(target_name)}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Имя: <b>{_escape_html(profile.get('full_name', 'Не указано'))}</b>\n"
        f"🎂 Возраст: <b>{profile.get('age', 'Не указано')}</b>\n"
        f"🏙️ Город: <b>{_escape_html(profile.get('city', 'Не указано'))}</b>\n"
        f"🌍 Часовой пояс: <b>{_escape_html(profile.get('timezone', 'Не указано'))}</b>\n"
        f"📝 О себе: {_escape_html(profile.get('about', 'Не указано'))}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Баланс: <b>{balance}</b> NCoin\n"
        f"🏆 Побед: {user.get('wins', 0)} | Поражений: {user.get('losses', 0)}"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML)


async def transfer_coins(message: types.Message, from_id: int, target_id: int, target_user: dict, amount: int):
    """Перевести монеты"""
    if from_id == target_id:
        await message.answer("❌ Нельзя перевести монеты самому себе!")
        return
    
    if amount < 10:
        await message.answer("❌ Минимальная сумма перевода: 10 NCoin")
        return
    
    balance = await db.get_balance(from_id)
    if balance < amount:
        await message.answer(f"❌ У вас недостаточно средств! Баланс: {balance} NCoin")
        return
    
    try:
        success = await db.transfer_coins(from_id, target_user.get('username'), amount, "transfer")
        if not success:
            await message.answer(f"❌ Не удалось перевести монеты")
            return
        
        new_balance = await db.get_balance(from_id)
        target_name = target_user.get('first_name', 'Пользователь')
        
        await message.answer(
            f"✅ <b>ПЕРЕВОД ВЫПОЛНЕН!</b>\n\n"
            f"📤 Отправлено: <b>{amount} NCoin</b>\n"
            f"📥 Получатель: {_escape_html(target_name)}\n"
            f"💰 Ваш новый баланс: <b>{new_balance}</b> NCoin",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Transfer error: {e}")
        await message.answer("❌ Ошибка перевода. Попробуйте позже.")


async def send_help(message: types.Message):
    """Отправить помощь"""
    help_text = (
        "🤖 <b>ЧТО Я УМЕЮ:</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🗣️ УМНЫЕ КОМАНДЫ (пишите в чат):</b>\n\n"
        "• <code>Нексус, оповести всех</code> — общий сбор\n"
        "• <code>Нексус, найди сквад в PUBG</code> — тег по категории\n"
        "• <code>Нексус, собери пати в доту</code>\n"
        "• <code>Нексус, крестики-нолики</code> — играть с ботом\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>👤 ДЕЙСТВИЯ С ПОЛЬЗОВАТЕЛЯМИ:</b>\n\n"
        "• <code>@user обнять</code> — РП действие\n"
        "• <code>@user крестики 100</code> — вызвать на игру\n"
        "• <code>@user анкета</code> — посмотреть анкету\n"
        "• <code>@user 500</code> — перевести монеты\n\n"
        "💡 <i>Также работают ответы на сообщения (reply)!</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📌 ОСНОВНЫЕ КОМАНДЫ:</b>\n"
        "• /start — главное меню\n"
        "• /daily — ежедневный бонус\n"
        "• /balance — проверить баланс\n"
        "• /help — полная помощь"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)


# ==================== ОБРАБОТЧИК ТОЛЬКО ДЛЯ ТЕКСТА БЕЗ / ====================

@router.message(F.text, lambda message: not message.text.startswith('/'))
async def smart_parser(message: types.Message):
    """Умный парсер — обрабатывает ТОЛЬКО текст, не начинающийся с /"""
    
    # Игнорируем сообщения от ботов
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    reply = message.reply_to_message  # Ответ на сообщение
    
    if not text:
        return
    
    # Проверка: если пользователь заполняет анкету — НЕ обрабатываем другие команды
    if user_id in profile_states:
        return
    
    # Проверяем регистрацию
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    if not user:
        await message.answer("👋 Используйте /start для регистрации")
        return
    
    # ==================== ОПРЕДЕЛЯЕМ ЦЕЛЕВОГО ПОЛЬЗОВАТЕЛЯ ====================
    target_user = None
    target_id = None
    
    # Способ 1: @username в тексте
    username = extract_username(text)
    if username:
        target_user = await db.get_user_by_username(username)
        if target_user:
            target_id = target_user["user_id"]
    
    # Способ 2: Ответ на сообщение (reply)
    if reply and reply.from_user.id != user_id and not reply.from_user.is_bot:
        target_id = reply.from_user.id
        target_user = await db.get_user(target_id)
    
    # ==================== ЕСЛИ ЕСТЬ ЦЕЛЬ — ОБРАБАТЫВАЕМ ДЕЙСТВИЕ ====================
    if target_id and target_user:
        action = None
        amount = extract_number(text)
        
        # 1. Проверяем РП действия
        for word, act in RP_ACTIONS.items():
            if word in text:
                action = ('rp', act)
                break
        
        # 2. Крестики-нолики
        if not action and ('крестики' in text or 'нолики' in text or 'xo' in text or 'tic' in text or 'тактик' in text):
            bet = amount if amount > 0 else 0
            action = ('xo', bet)
        
        # 3. Посмотреть анкету
        if not action and ('анкета' in text or 'профиль' in text or 'profile' in text or 'инфо' in text):
            action = ('profile', None)
        
        # 4. Передать монеты (если только число и @username)
        if not action and amount > 0 and username and not any(word in text for word in ['крестики', 'xo', 'ставка', 'анкета', 'профиль']):
            action = ('transfer', amount)
        
        # Выполняем действие
        if action:
            action_type, data = action
            
            if action_type == 'rp':
                await send_rp_action(message, user_id, target_id, target_user, data)
                return
            elif action_type == 'xo':
                await challenge_xo(message, user_id, target_id, target_user, data)
                return
            elif action_type == 'profile':
                await show_profile(message, target_id, target_user)
                return
            elif action_type == 'transfer':
                await transfer_coins(message, user_id, target_id, target_user, data)
                return
    
    # ==================== ОБРАБОТКА БЕЗ ЦЕЛИ ====================
    
    # Проверка обращения к боту
    bot_called = any(word in text for word in ['нексус', 'нэксус', 'nexus', 'некс', 'нэкс', 'бот'])
    
    # ==================== УМНЫЕ ТЕГИ (КАТЕГОРИИ) ====================
    if bot_called:
        for slug, keywords in TAG_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    try:
                        from handlers.tag_categories import get_chat_enabled_slugs
                        chat_id = message.chat.id
                        enabled_slugs = await get_chat_enabled_slugs(chat_id)
                        
                        if slug in enabled_slugs:
                            msg_parts = text.split(keyword, 1)
                            msg_text = msg_parts[1].strip() if len(msg_parts) > 1 else "Внимание!"
                            
                            from handlers.tag_trigger import trigger_tag
                            await trigger_tag(message, slug, msg_text)
                            return
                    except ImportError:
                        pass
                    except Exception as e:
                        logger.error(f"Tag trigger error: {e}")
    
    # ==================== ТЭГ ВСЕХ (ОБЩИЙ СБОР) ====================
    if bot_called and ('оповести всех' in text or 'общий сбор' in text or 'собери всех' in text):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"),
             InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
        ])
        
        await message.answer(
            "📢 <b>ОБЩИЙ СБОР</b>\n\n"
            "Будет отправлено сообщение с упоминанием всех участников.\n\n"
            "Начать?",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        return
    
    # ==================== КРЕСТИКИ-НОЛИКИ С БОТОМ ====================
    if bot_called and ('крестики' in text or 'нолики' in text or 'xo' in text):
        from handlers.tictactoe import cmd_xo
        await cmd_xo(message)
        return
    
    # ==================== ПОМОЩЬ ====================
    if bot_called and ('помоги' in text or 'помощь' in text or 'help' in text or 'что ты умеешь' in text):
        await send_help(message)
        return
    
    # ==================== ПРИВЕТСТВИЕ БОТА ====================
    if bot_called and ('привет' in text or 'здарова' in text or 'ку' in text or 'хай' in text):
        await message.answer(f"👋 Привет, {message.from_user.first_name}!")
        return
    
    # ==================== РП КОМАНДЫ (БЕЗ ЦЕЛИ) ====================
    rp_responses = {
        'привет': 'Привет! 👋',
        'пока': 'Пока! 👋',
        'спасибо': 'Пожалуйста! 🤗',
        'молодец': 'Спасибо! 😊',
        'красава': 'Благодарю! 🤝',
        'доброе утро': 'Доброе утро! ☀️',
        'добрый вечер': 'Добрый вечер! 🌙',
        'спокойной ночи': 'Сладких снов! 😴',
    }
    
    for key, response in rp_responses.items():
        if key in text:
            await message.answer(response)
            return


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery):
    """Запуск общего сбора"""
    from handlers.tag import cmd_all
    await cmd_all(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery):
    """Отмена общего сбора"""
    await callback.message.edit_text("❌ Общий сбор отменён.")
    await callback.answer()
