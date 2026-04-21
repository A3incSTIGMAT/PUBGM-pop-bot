# ============================================
# ФАЙЛ: handlers/smart_commands.py
# ОПИСАНИЕ: Умный парсер + ДИНАМИЧЕСКАЯ РЕГИСТРАЦИЯ КАСТОМНЫХ РП
# ИСПРАВЛЕНО: Кастомные команды работают сразу после добавления
# ============================================

import re
import logging
import time
import hashlib
import asyncio
import html
import random
from typing import Callable, Dict, Optional, Tuple, Any
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# Глобальный экземпляр бота
bot: Optional[Bot] = None


def set_bot(bot_instance: Bot) -> None:
    """Установка экземпляра бота"""
    global bot
    if bot_instance is not None:
        bot = bot_instance


# ==================== РЕЕСТР КОМАНД ====================

class CommandHandler:
    """Обработчик команды"""
    def __init__(self, keywords: list, handler: Callable, need_target: bool = False):
        self.keywords = keywords if keywords is not None else []
        self.handler = handler
        self.need_target = need_target


NO_TARGET_COMMANDS: Dict[str, CommandHandler] = {}
TARGET_COMMANDS: Dict[str, CommandHandler] = {}


def register_command(keywords: list, need_target: bool = False) -> Callable:
    """Декоратор для регистрации команды"""
    if keywords is None:
        keywords = []
        
    def decorator(func: Callable) -> Callable:
        handler = CommandHandler(keywords, func, need_target)
        if need_target:
            for kw in keywords:
                if kw is not None and kw.strip():
                    TARGET_COMMANDS[kw.strip()] = handler
        else:
            for kw in keywords:
                if kw is not None and kw.strip():
                    NO_TARGET_COMMANDS[kw.strip()] = handler
        return func
    return decorator


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def ensure_user_exists(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Гарантирует, что пользователь существует в БД"""
    if user_id is None:
        return {}
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            logger.info(f"Auto-registered user {user_id} in smart_commands")
        return user or {}
    except Exception as e:
        logger.error(f"Error ensuring user exists: {e}")
        return {}


def extract_username(text: str) -> Optional[str]:
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


def format_number(num: Any) -> str:
    """Форматирование числа"""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


async def get_target_from_message(message: types.Message) -> Tuple[Optional[int], Optional[dict], Optional[str]]:
    """Получить цель из сообщения (@username или reply) — с авторегистрацией"""
    if message is None:
        return None, None, None
        
    text = message.text.lower() if message.text else ""
    reply = message.reply_to_message
    
    target_id = None
    target_user = None
    target_username = None
    
    # Способ 1: @username в тексте
    username = extract_username(text)
    if username:
        target_username = username
        try:
            target_user = await db.get_user_by_username(username)
            if target_user:
                target_id = target_user.get("user_id")
                logger.info(f"🔍 Target found by @username: {username} -> id={target_id}")
            else:
                logger.info(f"🔍 Target @{username} not found in DB")
        except Exception as e:
            logger.error(f"Error getting user by username: {e}")
    
    # Способ 2: Ответ на сообщение (reply) — ИГНОРИРУЕМ БОТОВ
    if not target_id and reply and reply.from_user:
        if not reply.from_user.is_bot:
            target_id = reply.from_user.id
            try:
                target_user = await db.get_user(target_id)
                if target_user:
                    target_username = target_user.get("username")
                    logger.info(f"🔍 Target found by reply: id={target_id}, username={target_username}")
                else:
                    # 🔥 АВТОРЕГИСТРАЦИЯ ЦЕЛИ
                    logger.info(f"🔍 Target not registered, auto-creating user {target_id}")
                    await ensure_user_exists(
                        target_id,
                        reply.from_user.username,
                        reply.from_user.first_name
                    )
                    target_user = await db.get_user(target_id)
                    if target_user:
                        target_username = target_user.get("username")
            except Exception as e:
                logger.error(f"Error getting target by reply: {e}")
    
    return target_id, target_user, target_username


# ==================== РП ДЕЙСТВИЯ (БАЗОВЫЕ) ====================

RP_ACTIONS: Dict[str, str] = {
    'обнять': 'hug', 'обнял': 'hug', 'обнимаю': 'hug',
    'поцеловать': 'kiss', 'поцелуй': 'kiss', 'чмок': 'kiss',
    'пнуть': 'kick', 'пнул': 'kick', 'пинаю': 'kick',
    'погладить': 'pat', 'погладил': 'pat', 'глажу': 'pat',
    'дать леща': 'slap', 'лещ': 'slap', 'шлёпнуть': 'slap',
    'ударить': 'punch', 'врезать': 'punch', 'стукнуть': 'punch',
    'шмальнуть': 'shoot', 'застрелить': 'shoot', 'выстрелить': 'shoot',
    'трахнуть': 'fuck', 'выебать': 'fuck', 'отодрать': 'fuck',
    'убить': 'kill', 'прикончить': 'kill', 'замочить': 'kill',
    'обоссать': 'piss', 'обоссал': 'piss', 'ссать': 'piss',
    'накормить': 'feed', 'покормить': 'feed', 'кормить': 'feed',
}

RP_TEXTS: Dict[str, list] = {
    'hug': ["🤗 {from_name} крепко обнимает {target_name}!"],
    'kiss': ["💋 {from_name} страстно целует {target_name}!"],
    'kick': ["👢 {from_name} пинает {target_name}!"],
    'pat': ["🫳 {from_name} нежно гладит {target_name} по голове!"],
    'slap': ["👋 {from_name} даёт леща {target_name}!"],
    'punch': ["👊 {from_name} бьёт {target_name} с вертухи!"],
    'shoot': ["🔫 {from_name} шмальнул из 9мм ПМ в ногу {target_name} в воспитательных целях!"],
    'fuck': ["🍆 {from_name} трахнул {target_name}!"],
    'kill': ["💀 {from_name} убил {target_name}!"],
    'piss': ["💦 {from_name} обоссал {target_name}!"],
    'feed': ["🍲 {from_name} накормил {target_name} вкусной едой!"],
}


def _register_rp_actions() -> None:
    """Вспомогательная функция для регистрации РП действий"""
    for rp_word, rp_action in RP_ACTIONS.items():
        if not rp_word or not rp_action:
            continue
            
        @register_command([rp_word], need_target=True)
        async def rp_handler(message: types.Message, from_id: int, target_id: int,
                             target_user: dict, action: str = rp_action) -> None:
            if message is None:
                return
                
            try:
                from_user = await db.get_user(from_id)
                from_name = from_user.get('first_name', 'Пользователь') if from_user else 'Пользователь'
                target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
                
                texts = RP_TEXTS.get(action, [f"{from_name} взаимодействует с {target_name}"])
                if texts:
                    text = random.choice(texts).format(
                        from_name=html.escape(from_name) if from_name else "Пользователь",
                        target_name=html.escape(target_name) if target_name else "Пользователь"
                    )
                else:
                    text = f"{from_name} взаимодействует с {target_name}"
                    
                await message.answer(text)
            except Exception as e:
                logger.error(f"Error in RP handler: {e}")
                await message.answer("❌ Произошла ошибка при выполнении действия.")


_register_rp_actions()


# ==================== КОМАНДЫ БЕЗ ЦЕЛИ ====================

@register_command(['общий сбор', 'оповести всех', 'собери всех'])
async def cmd_gather(message: types.Message, **kwargs: Any) -> None:
    """Общий сбор участников"""
    if message is None:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
    ])
    await message.answer(
        "📢 <b>ОБЩИЙ СБОР</b>\n\nНачать?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@register_command(['крестики', 'нолики', 'xo', 'tic', 'tac'])
async def cmd_xo_game(message: types.Message, **kwargs: Any) -> None:
    """Запуск крестиков-ноликов"""
    if message is None:
        return
    try:
        from handlers.tictactoe import cmd_xo
        await cmd_xo(message)
    except Exception as e:
        logger.error(f"Error starting XO game: {e}")
        await message.answer("❌ Игра временно недоступна.")


@register_command(['статистика', 'стата', 'stats'])
async def cmd_show_stats(message: types.Message, **kwargs: Any) -> None:
    """Показать статистику"""
    if message is None:
        return
    try:
        from handlers.stats import cmd_stats
        await cmd_stats(message)
    except Exception as e:
        logger.error(f"Error showing stats: {e}")
        await message.answer("❌ Статистика временно недоступна.")


@register_command(['помощь', 'помоги', 'help', 'что ты умеешь'])
async def cmd_show_help(message: types.Message, **kwargs: Any) -> None:
    """Показать помощь"""
    if message is None:
        return
    
    help_text = (
        "🤖 <b>ЧТО Я УМЕЮ:</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🗣️ УМНЫЕ КОМАНДЫ (обращайтесь ко мне):</b>\n"
        "• <code>Нексус, оповести всех</code> — общий сбор\n"
        "• <code>Нексус, найди сквад в PUBG</code>\n"
        "• <code>Нексус, крестики-нолики</code> — играть\n"
        "• <code>Нексус, статистика</code>\n\n"
        "<b>👤 ДЕЙСТВИЯ (reply + слово):</b>\n"
        "• Ответь на сообщение + <code>обнять</code>\n"
        "• Ответь на сообщение + <code>шмальнуть</code>\n"
        "• Ответь на сообщение + <code>крестики 100</code>\n"
        "• Ответь на сообщение + <code>анкета</code>\n"
        "• Ответь на сообщение + <code>500</code> — перевод\n\n"
        "<b>✨ КАСТОМНЫЕ РП КОМАНДЫ:</b>\n"
        "• <code>add_rp команда действие</code> — добавить свою команду\n"
        "• <code>my_rp</code> — мои команды\n"
        "• <code>del_rp команда</code> — удалить команду\n\n"
        "<b>📌 ОСНОВНЫЕ КОМАНДЫ:</b>\n"
        "• /start — главное меню\n"
        "• /daily — ежедневный бонус\n"
        "• /balance — проверить баланс\n"
        "• /stats — статистика\n"
        "• /top — топы"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@register_command(['привет', 'здарова', 'хай', 'ку'])
async def cmd_greet(message: types.Message, **kwargs: Any) -> None:
    """Приветствие"""
    if message is None:
        return
    name = message.from_user.first_name or ""
    await message.answer(f"👋 Привет, {html.escape(name)}!")


# 🔥 КАСТОМНЫЕ РП КОМАНДЫ БЕЗ СЛЕША
@register_command(['add_rp', 'добавить рп', 'add rp'])
async def cmd_add_rp_smart(message: types.Message, **kwargs: Any) -> None:
    """Добавить кастомную РП команду через умный парсер"""
    if message is None:
        return
    await cmd_add_custom_rp(message)


@register_command(['del_rp', 'удалить рп', 'delete rp'])
async def cmd_del_rp_smart(message: types.Message, **kwargs: Any) -> None:
    """Удалить кастомную РП команду через умный парсер"""
    if message is None:
        return
    await cmd_del_custom_rp(message)


@register_command(['my_rp', 'мои рп', 'my rp'])
async def cmd_my_rp_smart(message: types.Message, **kwargs: Any) -> None:
    """Показать мои РП команды через умный парсер"""
    if message is None:
        return
    await cmd_my_custom_rp(message)


# ==================== КОМАНДЫ С ЦЕЛЬЮ ====================

@register_command(['крестики', 'нолики', 'xo'], need_target=True)
async def cmd_challenge_xo(message: types.Message, from_id: int, target_id: int,
                           target_user: dict, **kwargs: Any) -> None:
    """Вызвать на крестики-нолики"""
    if message is None:
        return
        
    if from_id == target_id:
        await message.answer("❌ Нельзя вызвать самого себя!")
        return
    
    bet = extract_number(message.text)
    
    await ensure_user_exists(from_id, message.from_user.username, message.from_user.first_name)
    
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
        "chat_id": message.chat.id if message.chat else None,
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
    
    from_name = message.from_user.first_name or "Игрок"
    target_name = target_user.get("first_name") or kwargs.get("target_username", "Игрок")
    
    msg = await message.answer(
        f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
        f"👤 {html.escape(from_name)} вызывает {html.escape(target_name)}!\n"
        f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n\n"
        f"⏰ Вызов действителен 60 секунд\n\n"
        f"⚠️ ТОЛЬКО {html.escape(target_name)} может принять или отклонить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    
    try:
        from handlers.tictactoe import auto_cancel_challenge
        if msg.chat and msg.message_id:
            asyncio.create_task(auto_cancel_challenge(game_id, msg.chat.id, msg.message_id))
    except Exception as e:
        logger.error(f"Error setting auto-cancel: {e}")


@register_command(['анкета', 'профиль', 'profile'], need_target=True)
async def cmd_show_profile(message: types.Message, target_id: int, target_user: dict, **kwargs: Any) -> None:
    """Показать анкету пользователя"""
    if message is None:
        return
        
    try:
        profile = await db.get_profile(target_id)
        balance = await db.get_balance(target_id)
        
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
    except Exception as e:
        logger.error(f"Error showing profile: {e}")
        await message.answer("❌ Не удалось загрузить анкету.")


@register_command(['перевод', 'перевести', 'transfer'], need_target=True)
async def cmd_transfer_coins(message: types.Message, from_id: int, target_id: int,
                             target_user: dict, **kwargs: Any) -> None:
    """Перевести монеты"""
    if message is None:
        return
        
    amount = extract_number(message.text)
    
    if from_id == target_id:
        await message.answer("❌ Нельзя перевести монеты самому себе!")
        return
    
    if amount < 10:
        await message.answer("❌ Минимальная сумма перевода: 10 NCoin")
        return
    
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


# ==================== УМНЫЕ ТЕГИ ====================

TAG_KEYWORDS: Dict[str, list] = {
    'pubg': ['пубг', 'pubg', 'пабг', 'сквад', 'ранкед'],
    'cs2': ['кс2', 'cs2', 'катка', 'матчмейкинг'],
    'dota': ['дота', 'dota', 'пати'],
    'mafia': ['мафия', 'mafia', 'партия'],
    'video_call': ['звонок', 'созвон', 'видеозвонок', 'discord'],
    'important': ['важный вопрос', 'помогите', 'нужна помощь'],
    'giveaway': ['розыгрыш', 'giveaway', 'конкурс'],
    'offtopic': ['флуд', 'оффтоп', 'offtopic'],
    'tech': ['техническое', 'баг', 'ошибка', 'bug'],
    'urgent': ['срочно', 'urgent', 'помощь админам'],
}


# ==================== ДИНАМИЧЕСКАЯ РЕГИСТРАЦИЯ КАСТОМНЫХ РП ====================

async def register_custom_command(command: str, action: str) -> None:
    """Динамически зарегистрировать кастомную РП команду"""
    if not command or not action:
        return
    
    command = command.strip().lower()
    action = action.strip()
    
    # Добавляем в словари
    RP_ACTIONS[command] = command
    RP_TEXTS[command] = [action]
    
    # 🔥 СОЗДАЁМ ОБРАБОТЧИК
    async def custom_handler(message: types.Message, from_id: int, target_id: int,
                             target_user: dict, cmd: str = command, act: str = action) -> None:
        if message is None:
            return
        try:
            from_user = await db.get_user(from_id)
            from_name = from_user.get('first_name', 'Пользователь') if from_user else 'Пользователь'
            target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
            await message.answer(
                f"✨ {html.escape(from_name) if from_name else 'Пользователь'} "
                f"{act} {html.escape(target_name) if target_name else 'Пользователь'}!"
            )
        except Exception as e:
            logger.error(f"Error in custom RP handler '{cmd}': {e}")
    
    # 🔥 РЕГИСТРИРУЕМ В РЕЕСТРЕ
    handler = CommandHandler([command], custom_handler, need_target=True)
    TARGET_COMMANDS[command] = handler
    logger.info(f"✅ Registered custom command: {command}")


async def unregister_custom_command(command: str) -> None:
    """Удалить кастомную РП команду из реестра"""
    if not command:
        return
    
    command = command.strip().lower()
    
    if command in RP_ACTIONS:
        del RP_ACTIONS[command]
    if command in RP_TEXTS:
        del RP_TEXTS[command]
    if command in TARGET_COMMANDS:
        del TARGET_COMMANDS[command]
    
    logger.info(f"🗑️ Unregistered custom command: {command}")


async def load_custom_rp_commands() -> None:
    """Загрузить все кастомные РП команды из БД при старте"""
    try:
        all_custom = await db.get_all_custom_rp()
        
        loaded = 0
        for user_id, commands in all_custom.items():
            for cmd, action in commands.items():
                if cmd and cmd.strip() and action:
                    await register_custom_command(cmd, action)
                    loaded += 1
        
        logger.info(f"✅ Loaded {loaded} custom RP commands from database")
    except Exception as e:
        logger.error(f"Error loading custom RP commands: {e}")


# ==================== КАСТОМНЫЕ РП КОМАНДЫ (СЛЕШ) ====================

@router.message(Command("add_rp"))
async def cmd_add_custom_rp(message: types.Message) -> None:
    """Добавить кастомную РП команду: /add_rp команда действие"""
    if message is None:
        return
        
    args = message.text.split(maxsplit=2) if message.text else []
    
    if len(args) < 3:
        await message.answer(
            "✨ <b>ДОБАВЛЕНИЕ РП КОМАНДЫ</b>\n\n"
            "<code>/add_rp команда действие</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>/add_rp шмальнуть шмальнул из 9мм ПМ в ногу</code>\n\n"
            "После добавления используйте:\n"
            "• Ответьте на сообщение + <code>шмальнуть</code>\n"
            "• Или <code>@user шмальнуть</code>\n\n"
            "⚠️ Максимум 10 команд. Удалить: <code>/del_rp команда</code>\n"
            "📋 Мои команды: <code>/my_rp</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    command = args[1].lower().strip()
    action = args[2].strip()
    
    if len(command) < 2:
        await message.answer("❌ Команда должна быть не короче 2 символов!")
        return
    
    if len(action) < 3:
        await message.answer("❌ Действие должно быть не короче 3 символов!")
        return
    
    user_id = message.from_user.id
    
    try:
        count = await db.count_custom_rp(user_id)
        
        if count >= 10:
            await message.answer("❌ Вы уже добавили максимум 10 команд! Удалите ненужные через /del_rp")
            return
        
        exists = await db.check_custom_rp_exists(user_id, command)
        if exists:
            await message.answer(
                f"❌ Команда <code>{command}</code> уже существует! Используйте /del_rp {command}",
                parse_mode=ParseMode.HTML
            )
            return
        
        await db.add_custom_rp(user_id, command, action)
        
        # 🔥 ДИНАМИЧЕСКАЯ РЕГИСТРАЦИЯ
        await register_custom_command(command, action)
        
        await message.answer(
            f"✅ <b>Команда добавлена!</b>\n\n"
            f"Команда: <code>{command}</code>\n"
            f"Действие: {action}\n\n"
            f"Теперь можно использовать:\n"
            f"• Ответ на сообщение + <code>{command}</code>\n"
            f"• <code>@user {command}</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error adding custom RP: {e}")
        await message.answer("❌ Ошибка при добавлении команды.")


@router.message(Command("del_rp"))
async def cmd_del_custom_rp(message: types.Message) -> None:
    """Удалить кастомную РП команду: /del_rp команда"""
    if message is None:
        return
        
    args = message.text.split() if message.text else []
    
    if len(args) < 2:
        await message.answer(
            "🗑️ <b>УДАЛЕНИЕ РП КОМАНДЫ</b>\n\n"
            "<code>/del_rp команда</code>\n\n"
            "Пример: <code>/del_rp шмальнуть</code>\n\n"
            "📋 Посмотреть свои команды: <code>/my_rp</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    command = args[1].lower().strip()
    user_id = message.from_user.id
    
    try:
        deleted = await db.delete_custom_rp(user_id, command)
        
        if deleted:
            # 🔥 УДАЛЯЕМ ИЗ РЕЕСТРА
            await unregister_custom_command(command)
            await message.answer(f"✅ Команда <code>{command}</code> удалена!", parse_mode=ParseMode.HTML)
        else:
            await message.answer(f"❌ Команда <code>{command}</code> не найдена!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error deleting custom RP: {e}")
        await message.answer("❌ Ошибка при удалении команды.")


@router.message(Command("my_rp"))
async def cmd_my_custom_rp(message: types.Message) -> None:
    """Показать мои кастомные РП команды"""
    if message is None:
        return
        
    user_id = message.from_user.id
    
    try:
        commands = await db.get_custom_rp(user_id)
        
        if not commands:
            await message.answer(
                "✨ <b>ВАШИ РП КОМАНДЫ</b>\n\n"
                "У вас пока нет кастомных команд.\n\n"
                "<b>Добавьте:</b>\n"
                "<code>/add_rp команда действие</code>\n\n"
                "Пример:\n"
                "<code>/add_rp шмальнуть шмальнул из 9мм ПМ в ногу</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        text = "✨ <b>ВАШИ РП КОМАНДЫ</b>\n\n"
        for cmd, action in commands.items():
            text += f"• <code>{cmd}</code> — {action}\n"
        
        text += f"\n📊 Всего: {len(commands)}/10\n"
        text += "🗑️ Удалить: <code>/del_rp команда</code>"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error getting custom RP: {e}")
        await message.answer("❌ Ошибка при загрузке команд.")


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================

@router.message(F.text, lambda message: not message.text.startswith('/'))
async def smart_parser(message: types.Message) -> None:
    """Умный парсер — обрабатывает ТОЛЬКО текст, не начинающийся с /"""
    
    if message is None or message.from_user is None or message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    
    if not text:
        return
    
    if message.reply_to_message:
        reply_user = message.reply_to_message.from_user
        if reply_user:
            logger.info(f"🔍 REPLY DETECTED! reply_to={reply_user.id} (@{reply_user.username}), text='{text[:50]}'")
    
    logger.info(f"🔍 SMART PARSER: user={user_id}, text='{text[:50]}'")
    
    # Трекинг статистики
    try:
        activity_type = "message"
        if message.sticker:
            activity_type = "sticker"
        elif message.voice:
            activity_type = "voice"
        elif message.video:
            activity_type = "video"
        elif message.photo:
            activity_type = "photo"
        elif message.animation:
            activity_type = "gif"
        
        await db.track_user_activity(user_id, activity_type, 1)
    except Exception as e:
        logger.error(f"Stats tracking error: {e}")
    
    # Логирование слов
    try:
        if message.chat and message.chat.id:
            await db.log_chat_message(message.chat.id, user_id, text)
    except Exception as e:
        logger.error(f"Chat word logging error: {e}")
    
    # Авторегистрация
    user = await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    if not user:
        await message.answer("👋 Используйте /start для регистрации")
        return
    
    bot_called = any(word in text for word in ['нексус', 'нэксус', 'nexus', 'некс', 'нэкс', 'бот'])
    
    # Умные теги (только при обращении)
    if bot_called:
        for slug, keywords in TAG_KEYWORDS.items():
            for keyword in keywords:
                if keyword and keyword in text:
                    try:
                        from handlers.tag_categories import get_chat_enabled_slugs
                        chat_id = message.chat.id if message.chat else None
                        enabled_slugs = await get_chat_enabled_slugs(chat_id) if chat_id else set()
                        
                        if slug in enabled_slugs:
                            msg_parts = text.split(keyword, 1)
                            msg_text = msg_parts[1].strip() if len(msg_parts) > 1 else "Внимание!"
                            
                            from handlers.tag_trigger import trigger_tag
                            await trigger_tag(message, slug, msg_text)
                            return
                    except Exception as e:
                        logger.error(f"Tag trigger error: {e}")
    
    # Получаем цель
    target_id, target_user, target_username = await get_target_from_message(message)
    logger.info(f"🔍 TARGET RESULT: id={target_id}, user_exists={target_user is not None}")
    
    # 🔥 КОМАНДЫ С ЦЕЛЬЮ — ПРОВЕРЯЕМ В ПЕРВУЮ ОЧЕРЕДЬ
    if target_id and target_user:
        found_keywords = [kw for kw in TARGET_COMMANDS.keys() if kw and kw in text]
        logger.info(f"🔍 Keywords in text: {found_keywords}")
        
        for keyword in found_keywords:
            handler = TARGET_COMMANDS[keyword]
            logger.info(f"✅ Executing TARGET command: {keyword}")
            try:
                await handler.handler(
                    message,
                    from_id=user_id,
                    target_id=target_id,
                    target_user=target_user,
                    target_username=target_username
                )
                return
            except Exception as e:
                logger.error(f"Error executing target command {keyword}: {e}")
        
        # Чистый перевод
        amount = extract_number(text)
        if amount > 0:
            try:
                await cmd_transfer_coins(
                    message,
                    from_id=user_id,
                    target_id=target_id,
                    target_user=target_user
                )
                return
            except Exception as e:
                logger.error(f"Error in transfer: {e}")
    
    # ==================== КОМАНДЫ БЕЗ ЦЕЛИ ====================
    for keyword, handler in NO_TARGET_COMMANDS.items():
        if keyword and keyword in text:
            # Для кастомных РП команд не требуем bot_called
            if keyword in ['add_rp', 'добавить рп', 'add rp', 'del_rp', 'удалить рп', 'delete rp', 'my_rp', 'мои рп', 'my rp']:
                logger.info(f"✅ Executing NO_TARGET command (custom RP): {keyword}")
                try:
                    await handler.handler(message)
                    return
                except Exception as e:
                    logger.error(f"Error executing custom RP command: {e}")
            elif bot_called:
                logger.info(f"✅ Executing NO_TARGET command: {keyword}")
                try:
                    await handler.handler(message)
                    return
                except Exception as e:
                    logger.error(f"Error executing no-target command: {e}")
    
    # ==================== РП ОТВЕТЫ БЕЗ ЦЕЛИ (ТОЛЬКО ПРИ ОБРАЩЕНИИ) ====================
    if bot_called:
        rp_responses = {
            'привет': 'Привет! 👋',
            'пока': 'Пока! 👋',
            'спасибо': 'Пожалуйста! 🤗',
            'доброе утро': 'Доброе утро! ☀️',
            'добрый вечер': 'Добрый вечер! 🌙',
            'спокойной ночи': 'Сладких снов! 😴',
        }
        
        for key, response in rp_responses.items():
            if key and key in text:
                await message.answer(response)
                return


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery) -> None:
    """Запуск общего сбора"""
    if callback is None:
        return
    try:
        from handlers.tag import cmd_all
        await cmd_all(callback.message)
    except Exception as e:
        logger.error(f"Error in start_all: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery) -> None:
    """Отмена общего сбора"""
    if callback is None:
        return
    try:
        await callback.message.edit_text("❌ Общий сбор отменён.")
    except Exception as e:
        logger.error(f"Error in cancel_all: {e}")
    await callback.answer()
