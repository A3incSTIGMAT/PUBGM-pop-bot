#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/smart_commands.py
# ВЕРСИЯ: 5.1.0-production
# ОПИСАНИЕ: Умный парсер + РП команды — ИСПРАВЛЕН chat_id в track_user_activity
# ============================================

import re
import logging
import time
import hashlib
import asyncio
import html
import random
from typing import Callable, Dict, Optional, Tuple, Any, List
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

bot: Optional[Bot] = None
BOT_ID: Optional[int] = None


def set_bot(bot_instance: Bot) -> None:
    global bot, BOT_ID
    if bot_instance is not None:
        bot = bot_instance
        BOT_ID = bot_instance.id


# ==================== РЕЕСТР КОМАНД ====================

class CommandHandler:
    def __init__(self, keywords: List[str], handler: Callable, need_target: bool = False):
        self.keywords = keywords if keywords is not None else []
        self.handler = handler
        self.need_target = need_target


NO_TARGET_COMMANDS: Dict[str, CommandHandler] = {}
TARGET_COMMANDS: Dict[str, CommandHandler] = {}


def register_command(keywords: List[str], need_target: bool = False) -> Callable:
    if keywords is None: keywords = []
    def decorator(func: Callable) -> Callable:
        handler = CommandHandler(keywords, func, need_target)
        target_dict = TARGET_COMMANDS if need_target else NO_TARGET_COMMANDS
        for kw in keywords:
            if kw and kw.strip(): target_dict[kw.strip()] = handler
        return func
    return decorator


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

async def ensure_user_exists(user_id: Optional[int], username: Optional[str] = None, first_name: Optional[str] = None) -> dict:
    if user_id is None: return {}
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username or "", first_name or "", START_BALANCE)
            user = await db.get_user(user_id)
        return user or {}
    except Exception as e:
        logger.error(f"ensure_user_exists error: {e}")
        return {}


def extract_username(text: Optional[str]) -> Optional[str]:
    if text is None: return None
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    return match.group(1) if match else None


def extract_number(text: Optional[str]) -> int:
    if text is None: return 0
    match = re.search(r'\b\d+\b', text)
    try: return int(match.group()) if match else 0
    except: return 0


def format_number(num: Any) -> str:
    if num is None: return "0"
    try: return f"{int(num):,}".replace(",", " ")
    except: return "0"


def safe_html_escape(text: Optional[str]) -> str:
    if text is None: return ""
    try: return html.escape(str(text))
    except: return ""


async def get_target_from_message(message: Optional[types.Message]) -> Tuple[Optional[int], Optional[dict], Optional[str]]:
    if message is None: return None, None, None
    text = message.text.lower() if message.text else ""
    reply = message.reply_to_message
    target_id, target_user, target_username = None, None, None
    
    username = extract_username(text)
    if username:
        target_username = username
        try:
            target_user = await db.get_user_by_username(username)
            if target_user: target_id = target_user.get("user_id")
        except Exception as e: logger.error(f"Get user error: {e}")
    
    if target_id is None and reply is not None and hasattr(reply, 'from_user') and reply.from_user is not None:
        if not reply.from_user.is_bot:
            target_id = reply.from_user.id
            try:
                target_user = await db.get_user(target_id)
                if target_user: target_username = target_user.get("username")
                else:
                    await ensure_user_exists(target_id, reply.from_user.username, reply.from_user.first_name)
                    target_user = await db.get_user(target_id)
                    if target_user: target_username = target_user.get("username")
            except Exception as e: logger.error(f"Get target error: {e}")
    
    return target_id, target_user, target_username


# ==================== РП ДЕЙСТВИЯ ====================

RP_ACTIONS: Dict[str, str] = {
    'обнять':'hug','обнял':'hug','обнимаю':'hug','поцеловать':'kiss','поцелуй':'kiss','чмок':'kiss',
    'пнуть':'kick','пнул':'kick','пинаю':'kick','погладить':'pat','погладил':'pat','глажу':'pat',
    'дать леща':'slap','лещ':'slap','шлёпнуть':'slap','ударить':'punch','врезать':'punch','стукнуть':'punch',
    'шмальнуть':'shoot','застрелить':'shoot','выстрелить':'shoot','трахнуть':'fuck','выебать':'fuck','отодрать':'fuck',
    'убить':'kill','прикончить':'kill','замочить':'kill','обоссать':'piss','обоссал':'piss','ссать':'piss',
    'накормить':'feed','покормить':'feed','кормить':'feed',
}

RP_TEXTS: Dict[str, List[str]] = {
    'hug':["🤗 {from_name} крепко обнимает {target_name}!"],
    'kiss':["💋 {from_name} страстно целует {target_name}!"],
    'kick':["👢 {from_name} пинает {target_name}!"],
    'pat':["🫳 {from_name} нежно гладит {target_name} по голове!"],
    'slap':["👋 {from_name} даёт леща {target_name}!"],
    'punch':["👊 {from_name} бьёт {target_name} с вертухи!"],
    'shoot':["🔫 {from_name} шмальнул из 9мм ПМ в ногу {target_name} в воспитательных целях!"],
    'fuck':["🍆 {from_name} трахнул {target_name}!"],
    'kill':["💀 {from_name} убил {target_name}!"],
    'piss':["💦 {from_name} обоссал {target_name}!"],
    'feed':["🍲 {from_name} накормил {target_name} вкусной едой!"],
}


def _create_rp_handler(action: str) -> Callable:
    async def rp_handler(message: types.Message, from_id: int, target_id: int, target_user: dict, **kwargs: Any) -> None:
        if message is None: return
        if from_id == target_id: await message.answer("❌ Нельзя выполнить действие с самим собой!"); return
        try:
            from_user = await db.get_user(from_id) if from_id else None
            from_name = from_user.get('first_name','Пользователь') if from_user else 'Пользователь'
            target_name = target_user.get('first_name','Пользователь') if target_user else 'Пользователь'
            texts = RP_TEXTS.get(action, [f"{from_name} взаимодействует с {target_name}"])
            text = random.choice(texts).format(from_name=safe_html_escape(from_name), target_name=safe_html_escape(target_name))
            await message.answer(text)
        except Exception as e: logger.error(f"RP handler error: {e}")
    return rp_handler


def _register_rp_actions() -> None:
    for rp_word, rp_action in RP_ACTIONS.items():
        if rp_word and rp_action:
            handler = _create_rp_handler(rp_action)
            register_command([rp_word], need_target=True)(handler)

_register_rp_actions()


# ==================== ДИНАМИЧЕСКАЯ РЕГИСТРАЦИЯ ====================

async def register_custom_command(command: str, action: str) -> None:
    if not command or not action: return
    command, action = command.strip().lower(), action.strip()
    if not command or not action: return
    RP_ACTIONS[command], RP_TEXTS[command] = command, [action]
    
    async def custom_handler(message: types.Message, from_id: int, target_id: int, target_user: dict, **kwargs: Any) -> None:
        if message is None: return
        if from_id == target_id: await message.answer("❌ Нельзя выполнить действие с самим собой!"); return
        try:
            from_user = await db.get_user(from_id) if from_id else None
            from_name = from_user.get('first_name','Пользователь') if from_user else 'Пользователь'
            target_name = target_user.get('first_name','Пользователь') if target_user else 'Пользователь'
            await message.answer(f"✨ {safe_html_escape(from_name)} {action} {safe_html_escape(target_name)}!")
        except Exception as e: logger.error(f"Custom RP error: {e}")
    
    TARGET_COMMANDS[command] = CommandHandler([command], custom_handler, need_target=True)
    logger.info(f"✅ Registered custom command: {command}")


async def unregister_custom_command(command: str) -> None:
    if not command: return
    command = command.strip().lower()
    RP_ACTIONS.pop(command, None); RP_TEXTS.pop(command, None); TARGET_COMMANDS.pop(command, None)


async def load_custom_rp_commands() -> None:
    try:
        all_custom = await db.get_all_custom_rp()
        loaded = 0
        for uid, commands in (all_custom or {}).items():
            if commands:
                for cmd, action in commands.items():
                    if cmd and cmd.strip() and action:
                        await register_custom_command(cmd, action); loaded += 1
        logger.info(f"✅ Loaded {loaded} custom RP commands")
    except Exception as e: logger.error(f"Load custom RP error: {e}")


# ==================== КАСТОМНЫЕ РП (СЛЕШ) ====================

@router.message(Command("add_rp"))
async def cmd_add_custom_rp(message: types.Message) -> None:
    if not message or not message.text: return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("✨ <b>ДОБАВЛЕНИЕ РП КОМАНДЫ</b>\n\n<code>/add_rp команда действие</code>\nПример: <code>/add_rp шмальнуть шмальнул из 9мм ПМ в ногу</code>\n⚠️ Максимум 10 команд.", parse_mode=ParseMode.HTML); return
    
    command, action = args[1].lower().strip(), args[2].strip()
    if len(command) < 2: await message.answer("❌ Команда должна быть не короче 2 символов!"); return
    if len(action) < 3: await message.answer("❌ Действие должно быть не короче 3 символов!"); return
    if not message.from_user: return
    
    user_id = message.from_user.id
    try:
        if await db.count_custom_rp(user_id) >= 10: await message.answer("❌ Максимум 10 команд!"); return
        if await db.check_custom_rp_exists(user_id, command): await message.answer(f"❌ Команда <code>{safe_html_escape(command)}</code> уже существует!", parse_mode=ParseMode.HTML); return
        await db.add_custom_rp(user_id, command, action)
        await register_custom_command(command, action)
        await message.answer(f"✅ <b>Команда добавлена!</b>\n\n<code>{safe_html_escape(command)}</code> — {safe_html_escape(action)}", parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(f"Add RP error: {e}"); await message.answer("❌ Ошибка при добавлении.")


@router.message(Command("del_rp"))
async def cmd_del_custom_rp(message: types.Message) -> None:
    if not message or not message.text: return
    args = message.text.split()
    if len(args) < 2: await message.answer("🗑️ <b>УДАЛЕНИЕ</b>\n<code>/del_rp команда</code>", parse_mode=ParseMode.HTML); return
    if not message.from_user: return
    
    command = args[1].lower().strip()
    try:
        if await db.delete_custom_rp(message.from_user.id, command):
            await unregister_custom_command(command)
            await message.answer(f"✅ Команда <code>{safe_html_escape(command)}</code> удалена!", parse_mode=ParseMode.HTML)
        else: await message.answer(f"❌ Команда не найдена!", parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(f"Del RP error: {e}"); await message.answer("❌ Ошибка при удалении.")


@router.message(Command("my_rp"))
async def cmd_my_custom_rp(message: types.Message) -> None:
    if not message or not message.from_user: return
    try:
        commands = await db.get_custom_rp(message.from_user.id)
        if not commands: await message.answer("✨ <b>ВАШИ РП КОМАНДЫ</b>\n\nУ вас пока нет кастомных команд.\n<code>/add_rp команда действие</code>", parse_mode=ParseMode.HTML); return
        text = "✨ <b>ВАШИ РП КОМАНДЫ</b>\n\n"
        for cmd, action in commands.items():
            if cmd and action: text += f"• <code>{safe_html_escape(cmd)}</code> — {safe_html_escape(action)}\n"
        text += f"\n📊 Всего: {len(commands)}/10"
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(f"My RP error: {e}"); await message.answer("❌ Ошибка при загрузке.")


# ==================== КОМАНДЫ БЕЗ ЦЕЛИ ====================

@register_command(['add_rp','добавить рп','add rp'])
async def cmd_add_rp_smart(message: types.Message, **kwargs: Any) -> None:
    if message: await cmd_add_custom_rp(message)

@register_command(['del_rp','удалить рп','delete rp'])
async def cmd_del_rp_smart(message: types.Message, **kwargs: Any) -> None:
    if message: await cmd_del_custom_rp(message)

@register_command(['my_rp','мои рп','my rp'])
async def cmd_my_rp_smart(message: types.Message, **kwargs: Any) -> None:
    if message: await cmd_my_custom_rp(message)

@register_command(['общий сбор','оповести всех','собери всех'])
async def cmd_gather(message: types.Message, **kwargs: Any) -> None:
    if not message: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"), InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]])
    await message.answer("📢 <b>ОБЩИЙ СБОР</b>\n\nНачать?", parse_mode=ParseMode.HTML, reply_markup=kb)

@register_command(['крестики','нолики','xo','tic','tac'])
async def cmd_xo_game(message: types.Message, **kwargs: Any) -> None:
    if not message: return
    try: from handlers.tictactoe import cmd_xo; await cmd_xo(message)
    except Exception as e: logger.error(f"XO error: {e}"); await message.answer("❌ Игра временно недоступна.")

@register_command(['статистика','стата','stats'])
async def cmd_show_stats(message: types.Message, **kwargs: Any) -> None:
    if not message: return
    try: from handlers.stats import cmd_stats; await cmd_stats(message)
    except Exception as e: logger.error(f"Stats error: {e}"); await message.answer("❌ Статистика недоступна.")

@register_command(['помощь','помоги','help','что ты умеешь'])
async def cmd_show_help(message: types.Message, **kwargs: Any) -> None:
    if not message: return
    text = ("🤖 <b>ЧТО Я УМЕЮ:</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🗣️ УМНЫЕ КОМАНДЫ:</b>\n• Нексус, оповести всех\n• Нексус, найди сквад в PUBG\n• Нексус, крестики-нолики\n\n"
            "<b>👤 ДЕЙСТВИЯ (reply + слово):</b>\n• обнять, шмальнуть, крестики 100, анкета, 500\n\n"
            "<b>📌 ОСНОВНЫЕ:</b>\n/start /daily /balance /stats /top")
    await message.answer(text, parse_mode=ParseMode.HTML)

@register_command(['привет','здарова','хай','ку'])
async def cmd_greet(message: types.Message, **kwargs: Any) -> None:
    if not message: return
    name = safe_html_escape(message.from_user.first_name) if message.from_user else ""
    await message.answer(f"👋 Привет, {name}!")


# ==================== КОМАНДЫ С ЦЕЛЬЮ ====================

@register_command(['крестики','нолики','xo'], need_target=True)
async def cmd_challenge_xo(message: types.Message, from_id: int, target_id: int, target_user: dict, **kwargs: Any) -> None:
    if not message or from_id is None or target_id is None: return
    if from_id == target_id: await message.answer("❌ Нельзя вызвать самого себя!"); return
    
    bet = extract_number(message.text)
    if message.from_user: await ensure_user_exists(from_id, message.from_user.username, message.from_user.first_name)
    if not target_user or not target_user.get("user_id"): await message.answer("❌ Пользователь не активировал бота!"); return
    if bet > 0:
        balance = await db.get_balance(from_id)
        if not balance or balance < bet: await message.answer(f"❌ Недостаточно средств! Баланс: {format_number(balance)} NCoin"); return
    
    game_id = f"xo_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    try:
        from handlers.tictactoe import active_games, auto_cancel_challenge
    except ImportError: await message.answer("❌ Игра недоступна"); return
    
    for gid, game in active_games.items():
        if game and game.get("pending"):
            if (game.get("player_x")==from_id and game.get("player_o")==target_id) or (game.get("player_x")==target_id and game.get("player_o")==from_id):
                await message.answer("❌ Уже есть активный вызов!"); return
    
    from_name = safe_html_escape(message.from_user.first_name) if message.from_user else "Игрок"
    target_name = safe_html_escape(target_user.get("first_name","Игрок"))
    
    active_games[game_id] = {"type":"pvp","board":[[" "," "," "],[" "," "," "],[" "," "," "]],"player_x":from_id,"player_o":target_id,
        "current_turn":"X","bet":bet or 0,"chat_id":message.chat.id if message.chat else None,"created_at":time.time(),
        "last_move":time.time(),"pending":True,"challenger_name":from_name,"challenged_name":target_name}
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]])
    
    msg = await message.answer(f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n👤 {from_name} вызывает {target_name}!\n💰 Ставка: <b>{format_number(bet)} NCoin</b>\n⏰ 60 секунд",
        parse_mode=ParseMode.HTML, reply_markup=kb)
    if msg and msg.chat and msg.message_id: asyncio.create_task(auto_cancel_challenge(game_id, msg.chat.id, msg.message_id))


@register_command(['анкета','профиль','profile'], need_target=True)
async def cmd_show_profile(message: types.Message, target_id: int, target_user: dict, **kwargs: Any) -> None:
    if not message or target_id is None: return
    try:
        profile = await db.get_profile(target_id)
        balance = await db.get_balance(target_id)
        target_name = safe_html_escape(target_user.get('first_name','Пользователь')) if target_user else 'Пользователь'
        if not profile: await message.answer(f"👤 <b>{target_name}</b>\n\n❌ Анкета не заполнена\n💰 Баланс: <b>{format_number(balance)}</b> NCoin", parse_mode=ParseMode.HTML); return
        text = (f"👤 <b>АНКЕТА {target_name}</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📛 Имя: <b>{safe_html_escape(profile.get('full_name','') or 'Не указано')}</b>\n"
                f"🎂 Возраст: <b>{profile.get('age','') or 'Не указано'}</b>\n"
                f"🏙️ Город: <b>{safe_html_escape(profile.get('city','') or 'Не указано')}</b>\n"
                f"📝 О себе: {safe_html_escape(profile.get('about','') or 'Не указано')}\n\n"
                f"💰 Баланс: <b>{format_number(balance)}</b> NCoin")
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(f"Profile error: {e}")


@register_command(['перевод','перевести','transfer'], need_target=True)
async def cmd_transfer_coins(message: types.Message, from_id: int, target_id: int, target_user: dict, **kwargs: Any) -> None:
    if not message or from_id is None or target_id is None: return
    amount = extract_number(message.text)
    if from_id == target_id: await message.answer("❌ Нельзя перевести самому себе!"); return
    if amount < 10: await message.answer("❌ Минимум 10 NCoin"); return
    
    if message.from_user: await ensure_user_exists(from_id, message.from_user.username, message.from_user.first_name)
    balance = await db.get_balance(from_id)
    if not balance or balance < amount: await message.answer(f"❌ Недостаточно средств! Баланс: {format_number(balance)} NCoin"); return
    
    try:
        target_username = target_user.get('username') if target_user else None
        if not target_username: await message.answer("❌ Не удалось определить получателя!"); return
        if not await db.transfer_coins(from_id, target_username, amount, "transfer"): await message.answer("❌ Не удалось перевести"); return
        new_balance = await db.get_balance(from_id)
        target_name = safe_html_escape(target_user.get('first_name','Пользователь')) if target_user else 'Пользователь'
        await message.answer(f"✅ <b>ПЕРЕВОД ВЫПОЛНЕН!</b>\n\n📤 {format_number(amount)} NCoin\n📥 {target_name}\n💰 Новый баланс: <b>{format_number(new_balance)}</b> NCoin", parse_mode=ParseMode.HTML)
    except Exception as e: logger.error(f"Transfer error: {e}")


# ==================== УМНЫЕ ТЕГИ ====================

TAG_KEYWORDS: Dict[str, List[str]] = {
    'pubg':['пубг','pubg','пабг','сквад','ранкед'],'cs2':['кс2','cs2','катка','матчмейкинг'],
    'dota':['дота','dota','пати'],'mafia':['мафия','mafia','партия'],
    'video_call':['звонок','созвон','видеозвонок','discord'],'important':['важный вопрос','помогите','нужна помощь'],
    'giveaway':['розыгрыш','giveaway','конкурс'],'offtopic':['флуд','оффтоп','offtopic'],
    'tech':['техническое','баг','ошибка','bug'],'urgent':['срочно','urgent','помощь админам'],
}


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================

@router.message(F.text, lambda message: not message.text.startswith('/') if message and message.text else False)
async def smart_parser(message: types.Message) -> None:
    if not message or not message.from_user or message.from_user.is_bot: return
    if BOT_ID and message.from_user.id == BOT_ID: return
    
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    if not text: return
    if message.via_bot: return
    
    # Трекинг статистики С chat_id
    try:
        chat_id = message.chat.id if message.chat else 0
        activity_type = "message"
        if message.sticker: activity_type = "sticker"
        elif message.voice: activity_type = "voice"
        elif message.video: activity_type = "video"
        elif message.photo: activity_type = "photo"
        elif message.animation: activity_type = "gif"
        await db.track_user_activity(user_id, chat_id, activity_type, 1)
    except Exception as e: logger.error(f"Stats error: {e}")
    
    # Логирование слов
    try:
        if message.chat: await db.log_chat_message(message.chat.id, user_id, text)
    except Exception as e: logger.error(f"Log error: {e}")
    
    user = await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    if not user: await message.answer("👋 Используйте /start для регистрации"); return
    
    bot_called = any(w in text for w in ['нексус','нэксус','nexus','некс','нэкс','бот'])
    
    # Умные теги
    if bot_called:
        for slug, keywords in TAG_KEYWORDS.items():
            for kw in keywords:
                if kw and kw in text:
                    try:
                        from handlers.tag_categories import get_chat_enabled_slugs
                        chat_id = message.chat.id if message.chat else None
                        enabled = await get_chat_enabled_slugs(chat_id) if chat_id else set()
                        if slug in enabled:
                            parts = text.split(kw, 1)
                            msg_text = parts[1].strip() if len(parts) > 1 else "Внимание!"
                            from handlers.tag_trigger import trigger_tag
                            await trigger_tag(message, slug, msg_text); return
                    except Exception as e: logger.error(f"Tag error: {e}")
    
    target_id, target_user, target_username = await get_target_from_message(message)
    
    # Команды с целью
    if target_id and target_user:
        found = [kw for kw in TARGET_COMMANDS if kw and kw in text]
        for kw in found:
            try:
                await TARGET_COMMANDS[kw].handler(message, from_id=user_id, target_id=target_id, target_user=target_user, target_username=target_username); return
            except Exception as e: logger.error(f"Target cmd error: {e}")
        
        amount = extract_number(text)
        if amount > 0:
            try: await cmd_transfer_coins(message, from_id=user_id, target_id=target_id, target_user=target_user); return
            except Exception as e: logger.error(f"Transfer error: {e}")
    
    # Команды без цели
    for kw, handler in NO_TARGET_COMMANDS.items():
        if kw and kw in text:
            if kw in ['add_rp','добавить рп','add rp','del_rp','удалить рп','delete rp','my_rp','мои рп','my rp']:
                try: await handler.handler(message); return
                except Exception as e: logger.error(f"Custom RP error: {e}")
            elif bot_called:
                try: await handler.handler(message); return
                except Exception as e: logger.error(f"No-target error: {e}")
    
    # РП ответы
    if bot_called:
        responses = {'привет':'Привет! 👋','пока':'Пока! 👋','спасибо':'Пожалуйста! 🤗','доброе утро':'Доброе утро! ☀️','добрый вечер':'Добрый вечер! 🌙','спокойной ночи':'Сладких снов! 😴'}
        for k, v in responses.items():
            if k and k in text: await message.answer(v); return


# ==================== КНОПКИ ====================

@router.callback_query(F.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery) -> None:
    if not callback: return
    try: from handlers.tag import cmd_all; await cmd_all(callback.message)
    except Exception as e: logger.error(f"start_all error: {e}"); await callback.answer("❌ Ошибка", show_alert=True)
    await callback.answer()

@router.callback_query(F.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery) -> None:
    if not callback: return
    try:
        if callback.message: await callback.message.edit_text("❌ Общий сбор отменён.")
    except Exception as e: logger.error(f"cancel_all error: {e}")
    await callback.answer()
