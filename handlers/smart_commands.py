# ============================================
# ФАЙЛ: handlers/smart_commands.py
# ОПИСАНИЕ: Умный парсер команд NEXUS Bot
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# АВТОРЕГИСТРАЦИЯ: При любом взаимодействии
# ============================================

import re
import logging
import time
import hashlib
import asyncio
import html
import random
from aiogram import Router, types, F, Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# Глобальный экземпляр бота
bot: Bot = None

def set_bot(bot_instance: Bot):
    """Установка экземпляра бота"""
    global bot
    bot = bot_instance

# Хранилище состояний анкеты
profile_states = {}

# Словарь умных тегов
TAG_KEYWORDS = {
    'pubg': ['пубг', 'pubg', 'пабг', 'королевская битва', 'сквад', 'ранкед'],
    'cs2': ['кс2', 'cs2', 'counter-strike', 'катка', 'матчмейкинг'],
    'dota': ['дота', 'dota', 'дота 2', 'пати'],
    'mafia': ['мафия', 'mafia', 'партия'],
    'video_call': ['звонок', 'созвон', 'видеозвонок', 'discord'],
    'important': ['важный вопрос', 'помогите', 'нужна помощь'],
    'giveaway': ['розыгрыш', 'giveaway', 'конкурс'],
    'offtopic': ['флуд', 'оффтоп', 'offtopic'],
    'tech': ['техническое', 'баг', 'ошибка', 'bug'],
    'urgent': ['срочно', 'urgent', 'помощь админам'],
}

# РП действия
RP_ACTIONS = {
    'обнять': 'hug', 'обнял': 'hug', 'обнимаю': 'hug',
    'поцеловать': 'kiss', 'поцелуй': 'kiss', 'чмок': 'kiss',
    'пнуть': 'kick', 'пнул': 'kick', 'пинаю': 'kick',
    'погладить': 'pat', 'погладил': 'pat', 'глажу': 'pat',
    'дать леща': 'slap', 'лещ': 'slap', 'шлёпнуть': 'slap',
    'ударить': 'punch', 'врезать': 'punch', 'стукнуть': 'punch',
    'привет': 'hello', 'здарова': 'hello', 'хай': 'hello',
    'пока': 'bye', 'прощай': 'bye',
    'спасибо': 'thanks', 'благодарю': 'thanks',
    'извини': 'sorry', 'прости': 'sorry', 'сорри': 'sorry',
    'поздравляю': 'congrats', 'с днём рождения': 'congrats',
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def ensure_user_exists(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Гарантирует, что пользователь существует в БД"""
    if user_id is None:
        return {}
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Auto-registered user {user_id} in smart_commands")
    return user or {}


def extract_username(text: str) -> str:
    """Извлечь username из текста"""
    if not text:
        return None
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    return match.group(1) if match else None


def extract_number(text: str) -> int:
    """Извлечь число из текста"""
    if not text:
        return 0
    match = re.search(r'\b\d+\b', text)
    return int(match.group()) if match else 0


def format_number(num: any) -> str:
    """Форматирование числа"""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


# ==================== РП ДЕЙСТВИЯ ====================

RP_TEXTS = {
    'hug': ["🤗 {from_name} обнимает {target_name}!"],
    'kiss': ["💋 {from_name} целует {target_name}!"],
    'kick': ["👢 {from_name} пинает {target_name}!"],
    'pat': ["🫳 {from_name} гладит {target_name} по голове!"],
    'slap': ["👋 {from_name} даёт леща {target_name}!"],
    'punch': ["👊 {from_name} бьёт {target_name}!"],
    'hello': ["👋 {from_name} приветствует {target_name}!"],
    'bye': ["👋 {from_name} прощается с {target_name}!"],
    'thanks': ["🙏 {from_name} благодарит {target_name}!"],
    'sorry': ["😔 {from_name} извиняется перед {target_name}!"],
    'congrats': ["🎉 {from_name} поздравляет {target_name}!"],
}


async def send_rp_action(message: types.Message, from_id: int, target_id: int, target_user: dict, action: str):
    """Отправить РП действие"""
    from_user = await db.get_user(from_id)
    from_name = from_user.get('first_name', 'Пользователь') if from_user else 'Пользователь'
    target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
    
    texts = RP_TEXTS.get(action, [f"{from_name} взаимодействует с {target_name}"])
    text = random.choice(texts).format(
        from_name=html.escape(from_name),
        target_name=html.escape(target_name)
    )
    
    await message.answer(text)


async def challenge_xo(message: types.Message, from_id: int, target_id: int, target_user: dict, bet: int = 0):
    """Вызвать на крестики-нолики"""
    if from_id == target_id:
        await message.answer("❌ Нельзя вызвать самого себя!")
        return
    
    # 🔥 АВТОРЕГИСТРАЦИЯ ВЫЗЫВАЮЩЕГО
    await ensure_user_exists(from_id, message.from_user.username, message.from_user.first_name)
    
    # Проверяем, что цель существует
    if not target_user or not target_user.get("user_id"):
        await message.answer(
            f"❌ <b>Пользователь не активировал бота!</b>\n\n"
            f"Попросите его написать /start.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if bet > 0:
        balance = await db.get_balance(from_id)
        if balance < bet:
            await message.answer(f"❌ У вас недостаточно средств! Баланс: {format_number(balance)} NCoin")
            return
    
    game_id = f"xo_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    try:
        from handlers.tictactoe import active_games
    except ImportError:
        await message.answer("❌ Игра временно недоступна")
        return
    
    # Проверяем, нет ли уже активного вызова
    for gid, game in active_games.items():
        if game.get("pending", False):
            if (game.get("player_x") == from_id and game.get("player_o") == target_id) or \
               (game.get("player_x") == target_id and game.get("player_o") == from_id):
                await message.answer("❌ У вас уже есть активный вызов! Дождитесь ответа.")
                return
    
    active_games[game_id] = {
        "type": "pvp",
        "board": [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]],
        "player_x": from_id,
        "player_o": target_id,
        "current_turn": "X",
        "bet": bet if bet is not None else 0,
        "chat_id": message.chat.id,
        "created_at": time.time(),
        "last_move": time.time(),
        "pending": True,
        "challenger_name": html.escape(message.from_user.first_name or "Игрок"),
        "challenged_name": html.escape(target_user.get("first_name") or "Игрок"),
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]
    ])
    
    from_user = await db.get_user(from_id)
    from_name = from_user.get('first_name', 'Пользователь') if from_user else 'Пользователь'
    target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
    target_username = target_user.get('username', target_name) if target_user else ''
    
    bet_text = f"<b>{format_number(bet)} NCoin</b>" if bet > 0 else "<b>без ставки</b>"
    
    msg = await message.answer(
        f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
        f"👤 {html.escape(from_name)} вызывает {html.escape(target_name)}!\n"
        f"💰 Ставка: {bet_text}\n\n"
        f"⏰ Вызов действителен 60 секунд\n\n"
        f"⚠️ ТОЛЬКО @{html.escape(target_username)} может принять или отклонить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    
    # Автоотмена через 60 секунд
    from handlers.tictactoe import auto_cancel_challenge
    asyncio.create_task(auto_cancel_challenge(game_id, msg.chat.id, msg.message_id))


async def show_profile(message: types.Message, target_id: int, target_user: dict):
    """Показать анкету пользователя"""
    profile = await db.get_profile(target_id)
    balance = await db.get_balance(target_id)
    user = await db.get_user(target_id)
    
    target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
    
    if not profile:
        await message.answer(
            f"👤 <b>{html.escape(target_name)}</b>\n\n"
            f"❌ Анкета не заполнена\n"
            f"💰 Баланс: <b>{format_number(balance)}</b> NCoin",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = (
        f"👤 <b>АНКЕТА {html.escape(target_name)}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Имя: <b>{html.escape(profile.get('full_name', '') or 'Не указано')}</b>\n"
        f"🎂 Возраст: <b>{profile.get('age', '') or 'Не указано'}</b>\n"
        f"🏙️ Город: <b>{html.escape(profile.get('city', '') or 'Не указано')}</b>\n"
        f"📝 О себе: {html.escape(profile.get('about', '') or 'Не указано')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Баланс: <b>{format_number(balance)}</b> NCoin"
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
    
    # 🔥 АВТОРЕГИСТРАЦИЯ ОТПРАВИТЕЛЯ
    await ensure_user_exists(from_id, message.from_user.username, message.from_user.first_name)
    
    balance = await db.get_balance(from_id)
    if balance < amount:
        await message.answer(f"❌ Недостаточно средств! Баланс: {format_number(balance)} NCoin")
        return
    
    try:
        target_username = target_user.get('username') if target_user else None
        if not target_username:
            await message.answer(f"❌ Не удалось определить получателя!")
            return
            
        success = await db.transfer_coins(from_id, target_username, amount, "transfer")
        if not success:
            await message.answer(f"❌ Не удалось перевести монеты")
            return
        
        new_balance = await db.get_balance(from_id)
        target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
        
        await message.answer(
            f"✅ <b>ПЕРЕВОД ВЫПОЛНЕН!</b>\n\n"
            f"📤 Отправлено: <b>{format_number(amount)} NCoin</b>\n"
            f"📥 Получатель: {html.escape(target_name)}\n"
            f"💰 Ваш новый баланс: <b>{format_number(new_balance)}</b> NCoin",
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
        "<b>🗣️ УМНЫЕ КОМАНДЫ:</b>\n"
        "• <code>Нексус, оповести всех</code> — общий сбор\n"
        "• <code>Нексус, найди сквад в PUBG</code>\n"
        "• <code>Нексус, крестики-нолики</code> — играть\n"
        "• <code>Нексус, статистика</code>\n\n"
        "<b>👤 ДЕЙСТВИЯ:</b>\n"
        "• <code>@user обнять</code>\n"
        "• <code>@user крестики 100</code> — вызвать на игру\n"
        "• <code>@user анкета</code> — посмотреть анкету\n"
        "• <code>@user 500</code> — перевести монеты\n\n"
        "<b>📌 КОМАНДЫ:</b>\n"
        "• /start — меню\n"
        "• /daily — бонус\n"
        "• /stats — статистика\n"
        "• /top — топы"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================

@router.message(F.text, lambda message: not message.text.startswith('/'))
async def smart_parser(message: types.Message):
    """Умный парсер — обрабатывает ТОЛЬКО текст, не начинающийся с /"""
    
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    reply = message.reply_to_message
    
    if not text:
        return
    
    # 🔥 ТРЕКИНГ СТАТИСТИКИ
    try:
        from handlers.stats import track_message
        await track_message(user_id, message)
    except Exception as e:
        logger.error(f"Stats tracking error: {e}")
    
    # 🔥 ЛОГИРОВАНИЕ СЛОВ ДЛЯ АНАЛИТИКИ ЧАТА
    try:
        if message.chat and message.chat.id:
            await db.log_chat_message(message.chat.id, user_id, text)
    except Exception as e:
        logger.error(f"Chat word logging error: {e}")
    
    # 🔥 АВТОРЕГИСТРАЦИЯ
    user = await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    if not user:
        await message.answer("👋 Используйте /start для регистрации")
        return
    
    # Проверка заполнения анкеты
    if user_id in profile_states:
        return
    
    # ==================== ОПРЕДЕЛЯЕМ ЦЕЛЕВОГО ПОЛЬЗОВАТЕЛЯ ====================
    target_user = None
    target_id = None
    
    username = extract_username(text)
    if username:
        target_user = await db.get_user_by_username(username)
        if target_user:
            target_id = target_user.get("user_id")
    
    if reply and reply.from_user and not reply.from_user.is_bot:
        if reply.from_user.id != user_id:
            target_id = reply.from_user.id
            target_user = await db.get_user(target_id)
    
    # ==================== ЕСЛИ ЕСТЬ ЦЕЛЬ ====================
    if target_id and target_user:
        action = None
        amount = extract_number(text)
        
        for word, act in RP_ACTIONS.items():
            if word in text:
                action = ('rp', act)
                break
        
        if not action and ('крестики' in text or 'нолики' in text or 'xo' in text):
            bet = amount if amount > 0 else 0
            action = ('xo', bet)
        
        if not action and ('анкета' in text or 'профиль' in text or 'profile' in text):
            action = ('profile', None)
        
        if not action and amount > 0 and username:
            if not any(word in text for word in ['крестики', 'xo', 'анкета', 'профиль']):
                action = ('transfer', amount)
        
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
    bot_called = any(word in text for word in ['нексус', 'нэксус', 'nexus', 'некс', 'бот'])
    
    if bot_called:
        # Умные теги
        for slug, keywords in TAG_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    try:
                        from handlers.tag_categories import get_chat_enabled_slugs
                        chat_id = message.chat.id
                        enabled_slugs = await get_chat_enabled_slugs(chat_id) if chat_id else set()
                        
                        if slug in enabled_slugs:
                            msg_parts = text.split(keyword, 1)
                            msg_text = msg_parts[1].strip() if len(msg_parts) > 1 else "Внимание!"
                            
                            from handlers.tag_trigger import trigger_tag
                            await trigger_tag(message, slug, msg_text)
                            return
                    except Exception as e:
                        logger.error(f"Tag trigger error: {e}")
        
        # Общий сбор
        if 'оповести всех' in text or 'общий сбор' in text or 'собери всех' in text:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"),
                 InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
            ])
            
            await message.answer(
                "📢 <b>ОБЩИЙ СБОР</b>\n\nНачать?",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return
        
        # Крестики-нолики
        if 'крестики' in text or 'нолики' in text or 'xo' in text:
            from handlers.tictactoe import cmd_xo
            await cmd_xo(message)
            return
        
        # Статистика
        if 'статистика' in text or 'стата' in text or 'stats' in text:
            from handlers.stats import cmd_stats
            await cmd_stats(message)
            return
        
        # Помощь
        if 'помоги' in text or 'помощь' in text or 'что ты умеешь' in text:
            await send_help(message)
            return
        
        # Приветствие
        if 'привет' in text or 'здарова' in text or 'хай' in text:
            await message.answer(f"👋 Привет, {html.escape(message.from_user.first_name or '')}!")
            return
    
    # ==================== РП КОМАНДЫ БЕЗ ЦЕЛИ ====================
    rp_responses = {
        'привет': 'Привет! 👋',
        'пока': 'Пока! 👋',
        'спасибо': 'Пожалуйста! 🤗',
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
    if callback is None:
        return
    from handlers.tag import cmd_all
    await cmd_all(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    await callback.message.edit_text("❌ Общий сбор отменён.")
    await callback.answer()
