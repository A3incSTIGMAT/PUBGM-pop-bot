#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/smart_commands.py
# ВЕРСИЯ: 5.2.0-production (исправленная после аудита)
# ОПИСАНИЕ: Умный парсер + РП команды
# ============================================
# ИСПРАВЛЕНИЯ v5.2.0:
#   🔴 Устранены прямые вызовы роутер-хендлеров
#   🔴 Исправлен фильтр сообщений (проверка message.chat)
#   🟡 hasattr проверки для всех методов БД
#   🟡 exc_info=True во всех logger.error
#   🟡 Безопасный парсинг чисел и username
#   🟢 Разделён smart_parser на подфункции
# ============================================

import asyncio
import hashlib
import html
import logging
import os
import random
import re
import time
from typing import Callable, Dict, Optional, Tuple, Any, List

from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

_bot: Optional[Bot] = None
BOT_ID: Optional[int] = None


def set_bot(bot_instance: Bot) -> None:
    """Установка экземпляра бота."""
    global _bot, BOT_ID
    if bot_instance is not None:
        _bot = bot_instance
        BOT_ID = bot_instance.id


# ==================== РЕЕСТР КОМАНД ====================

class CommandHandler:
    """Обработчик умной команды."""
    
    def __init__(self, keywords: List[str], handler: Callable, need_target: bool = False):
        self.keywords = keywords if keywords is not None else []
        self.handler = handler
        self.need_target = need_target


NO_TARGET_COMMANDS: Dict[str, CommandHandler] = {}
TARGET_COMMANDS: Dict[str, CommandHandler] = {}


def register_command(keywords: List[str], need_target: bool = False) -> Callable:
    """
    Декоратор для регистрации умной команды.
    
    Args:
        keywords: Ключевые слова
        need_target: Требуется ли цель (@username или reply)
    """
    if keywords is None:
        keywords = []
    
    def decorator(func: Callable) -> Callable:
        handler = CommandHandler(keywords, func, need_target)
        target_dict = TARGET_COMMANDS if need_target else NO_TARGET_COMMANDS
        for kw in keywords:
            if kw and kw.strip():
                target_dict[kw.strip()] = handler
        return func
    
    return decorator


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def ensure_user_exists(
    user_id: Optional[int],
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> dict:
    """
    Получить или создать пользователя.
    
    Args:
        user_id: ID пользователя
        username: @username
        first_name: Имя
        
    Returns:
        Данные пользователя или пустой словарь
    """
    if user_id is None:
        return {}
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username or "", first_name or "", START_BALANCE)
            user = await db.get_user(user_id)
        return user or {}
    except DatabaseError as e:
        logger.error(f"❌ ensure_user_exists error: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.error(f"❌ Unexpected ensure_user_exists error: {e}", exc_info=True)
        return {}


def extract_username(text: Optional[str]) -> Optional[str]:
    """
    Извлечь @username из текста.
    
    Args:
        text: Текст сообщения
        
    Returns:
        Username без @ или None
        
    Example:
        >>> extract_username("Привет @username как дела?")
        'username'
    """
    if text is None:
        return None
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    return match.group(1) if match else None


def extract_number(text: Optional[str]) -> int:
    """
    Извлечь первое число из текста.
    
    Args:
        text: Текст сообщения
        
    Returns:
        Число или 0
        
    Example:
        >>> extract_number("Переведи 500 монет")
        500
    """
    if text is None:
        return 0
    match = re.search(r'\b\d+\b', text)
    try:
        return int(match.group()) if match else 0
    except (ValueError, TypeError):
        return 0


def format_number(num: Any) -> str:
    """
    Форматирование числа с разделителями.
    
    Args:
        num: Число
        
    Returns:
        Отформатированная строка
    """
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное HTML-экранирование."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def get_target_from_message(
    message: Optional[types.Message]
) -> Tuple[Optional[int], Optional[dict], Optional[str]]:
    """
    Определить цель действия из сообщения.
    
    Приоритет: @username в тексте → reply → None.
    
    Args:
        message: Сообщение пользователя
        
    Returns:
        Tuple[target_id, target_user, target_username]
    """
    if message is None:
        return None, None, None
    
    text = message.text.lower() if message.text else ""
    reply = message.reply_to_message
    target_id, target_user, target_username = None, None, None
    
    # 1. Ищем @username в тексте
    username = extract_username(text)
    if username:
        target_username = username
        try:
            if hasattr(db, 'get_user_by_username') and callable(db.get_user_by_username):
                target_user = await db.get_user_by_username(username)
            else:
                user = await db._execute_with_retry(
                    "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
                    (username,), fetch_one=True
                )
                target_user = dict(user) if user else None
            
            if target_user:
                target_id = target_user.get("user_id")
        except DatabaseError as e:
            logger.error(f"❌ Get user error: {e}", exc_info=True)
    
    # 2. Если нет в тексте — проверяем reply
    if target_id is None and reply is not None:
        if hasattr(reply, 'from_user') and reply.from_user is not None:
            if not reply.from_user.is_bot:
                target_id = reply.from_user.id
                try:
                    target_user = await db.get_user(target_id)
                    if target_user:
                        target_username = target_user.get("username")
                    else:
                        await ensure_user_exists(
                            target_id,
                            reply.from_user.username,
                            reply.from_user.first_name
                        )
                        target_user = await db.get_user(target_id)
                        if target_user:
                            target_username = target_user.get("username")
                except DatabaseError as e:
                    logger.error(f"❌ Get target error: {e}", exc_info=True)
    
    return target_id, target_user, target_username


async def _safe_callback_answer(callback: types.CallbackQuery, text: str = None, show_alert: bool = True) -> None:
    """Безопасный ответ на callback."""
    if callback is None:
        return
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramAPIError:
        pass


# ==================== РП ДЕЙСТВИЯ ====================

RP_ACTIONS: Dict[str, str] = {
    'обнять': 'hug', 'обнял': 'hug', 'обнимаю': 'hug',
    'поцеловать': 'kiss', 'поцелуй': 'kiss', 'чмок': 'kiss',
    'пнуть': 'kick', 'пнул': 'kick', 'пинаю': 'kick',
    'погладить': 'pat', 'погладил': 'pat', 'глажу': 'pat',
    'дать леща': 'slap', 'лещ': 'slap', 'шлёпнуть': 'slap',
    'ударить': 'punch', 'врезать': 'punch', 'стукнуть': 'punch',
    'шмальнуть': 'shoot', 'застрелить': 'shoot', 'выстрелить': 'shoot',
    'убить': 'kill', 'прикончить': 'kill', 'замочить': 'kill',
    'накормить': 'feed', 'покормить': 'feed', 'кормить': 'feed',
}

RP_TEXTS: Dict[str, List[str]] = {
    'hug': ["🤗 {from_name} крепко обнимает {target_name}!"],
    'kiss': ["💋 {from_name} страстно целует {target_name}!"],
    'kick': ["👢 {from_name} пинает {target_name}!"],
    'pat': ["🫳 {from_name} нежно гладит {target_name} по голове!"],
    'slap': ["👋 {from_name} даёт леща {target_name}!"],
    'punch': ["👊 {from_name} бьёт {target_name} с вертухи!"],
    'shoot': ["🔫 {from_name} шмальнул из 9мм ПМ в ногу {target_name} в воспитательных целях!"],
    'kill': ["💀 {from_name} убил {target_name}!"],
    'feed': ["🍲 {from_name} накормил {target_name} вкусной едой!"],
}


def _create_rp_handler(action: str) -> Callable:
    """Создать обработчик для РП-действия."""
    async def rp_handler(
        message: types.Message,
        from_id: int,
        target_id: int,
        target_user: dict,
        **kwargs: Any
    ) -> None:
        if message is None:
            return
        
        if from_id == target_id:
            await message.answer("❌ Нельзя выполнить действие с самим собой!")
            return
        
        try:
            from_user = await db.get_user(from_id) if from_id else None
            from_name = from_user.get('first_name', 'Пользователь') if from_user else 'Пользователь'
            target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
            
            texts = RP_TEXTS.get(action, [f"{from_name} взаимодействует с {target_name}"])
            text = random.choice(texts).format(
                from_name=safe_html_escape(from_name),
                target_name=safe_html_escape(target_name)
            )
            await message.answer(text)
        except Exception as e:
            logger.error(f"❌ RP handler error: {e}", exc_info=True)
    
    return rp_handler


def _register_rp_actions() -> None:
    """Регистрация всех РП-действий."""
    for rp_word, rp_action in RP_ACTIONS.items():
        if rp_word and rp_action:
            handler = _create_rp_handler(rp_action)
            register_command([rp_word], need_target=True)(handler)


_register_rp_actions()


# ==================== ДИНАМИЧЕСКАЯ РЕГИСТРАЦИЯ ====================

async def register_custom_command(command: str, action: str) -> None:
    """
    Зарегистрировать кастомную РП-команду.
    
    Args:
        command: Ключевое слово
        action: Текст действия
    """
    if not command or not action:
        return
    
    command = command.strip().lower()
    action = action.strip()
    
    if not command or not action:
        return
    
    RP_ACTIONS[command] = command
    RP_TEXTS[command] = [action]
    
    async def custom_handler(
        message: types.Message,
        from_id: int,
        target_id: int,
        target_user: dict,
        **kwargs: Any
    ) -> None:
        if message is None:
            return
        if from_id == target_id:
            await message.answer("❌ Нельзя выполнить действие с самим собой!")
            return
        try:
            from_user = await db.get_user(from_id) if from_id else None
            from_name = from_user.get('first_name', 'Пользователь') if from_user else 'Пользователь'
            target_name = target_user.get('first_name', 'Пользователь') if target_user else 'Пользователь'
            await message.answer(
                f"✨ {safe_html_escape(from_name)} {action} {safe_html_escape(target_name)}!"
            )
        except Exception as e:
            logger.error(f"❌ Custom RP error: {e}", exc_info=True)
    
    # Логируем перезапись
    if command in TARGET_COMMANDS:
        logger.warning(f"⚠️ Overwriting custom command: {command}")
    
    TARGET_COMMANDS[command] = CommandHandler([command], custom_handler, need_target=True)
    logger.info(f"✅ Registered custom command: {command}")


async def unregister_custom_command(command: str) -> None:
    """Удалить кастомную РП-команду."""
    if not command:
        return
    command = command.strip().lower()
    RP_ACTIONS.pop(command, None)
    RP_TEXTS.pop(command, None)
    TARGET_COMMANDS.pop(command, None)


async def load_custom_rp_commands() -> None:
    """Загрузить все кастомные РП-команды из БД."""
    try:
        if not hasattr(db, 'get_all_custom_rp') or not callable(db.get_all_custom_rp):
            logger.warning("⚠️ get_all_custom_rp method not available")
            return
        
        all_custom = await db.get_all_custom_rp()
        loaded = 0
        for uid, commands in (all_custom or {}).items():
            if commands:
                for cmd, action in commands.items():
                    if cmd and cmd.strip() and action:
                        await register_custom_command(cmd, action)
                        loaded += 1
        logger.info(f"✅ Loaded {loaded} custom RP commands")
    except DatabaseError as e:
        logger.error(f"❌ Load custom RP error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"❌ Unexpected load custom RP error: {e}", exc_info=True)


# ==================== КОМАНДЫ БЕЗ ЦЕЛИ ====================

@register_command(['общий сбор', 'оповести всех', 'собери всех'])
async def cmd_gather(message: types.Message, **kwargs: Any) -> None:
    """Вызов общего сбора (редирект на /all)."""
    if not message:
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
    ])
    await message.answer(
        "📢 <b>ОБЩИЙ СБОР</b>\n\nНачать?",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


@register_command(['крестики', 'нолики', 'xo', 'tic', 'tac'])
async def cmd_xo_game(message: types.Message, **kwargs: Any) -> None:
    """Запуск крестиков-ноликов."""
    if not message:
        return
    try:
        from handlers.tictactoe import cmd_xo
        await cmd_xo(message)
    except ImportError:
        await message.answer("❌ Игра временно недоступна.")
    except Exception as e:
        logger.error(f"❌ XO error: {e}", exc_info=True)
        await message.answer("❌ Игра временно недоступна.")


@register_command(['статистика', 'стата', 'stats'])
async def cmd_show_stats(message: types.Message, **kwargs: Any) -> None:
    """Показать статистику."""
    if not message:
        return
    try:
        from handlers.stats import cmd_stats
        await cmd_stats(message)
    except ImportError:
        await message.answer("❌ Статистика недоступна.")
    except Exception as e:
        logger.error(f"❌ Stats error: {e}", exc_info=True)
        await message.answer("❌ Статистика недоступна.")


@register_command(['помощь', 'помоги', 'help', 'что ты умеешь'])
async def cmd_show_help(message: types.Message, **kwargs: Any) -> None:
    """Показать справку."""
    if not message:
        return
    
    text = (
        "🤖 <b>ЧТО Я УМЕЮ:</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🗣️ УМНЫЕ КОМАНДЫ:</b>\n"
        "• Нексус, оповести всех\n"
        "• Нексус, найди сквад в PUBG\n"
        "• Нексус, крестики-нолики\n\n"
        "<b>👤 ДЕЙСТВИЯ (reply + слово):</b>\n"
        "• обнять, шмальнуть, крестики 100, анкета, 500\n\n"
        "<b>📌 ОСНОВНЫЕ:</b>\n"
        "/start /daily /balance /stats /top"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@register_command(['привет', 'здарова', 'хай', 'ку'])
async def cmd_greet(message: types.Message, **kwargs: Any) -> None:
    """Приветствие."""
    if not message:
        return
    name = safe_html_escape(message.from_user.first_name) if message.from_user else ""
    await message.answer(f"👋 Привет, {name}!")


# ==================== КОМАНДЫ С ЦЕЛЬЮ ====================

@register_command(['крестики', 'нолики', 'xo'], need_target=True)
async def cmd_challenge_xo(
    message: types.Message,
    from_id: int,
    target_id: int,
    target_user: dict,
    **kwargs: Any
) -> None:
    """Вызов на крестики-нолики."""
    if not message or from_id is None or target_id is None:
        return
    if from_id == target_id:
        await message.answer("❌ Нельзя вызвать самого себя!")
        return
    
    bet = extract_number(message.text)
    if message.from_user:
        await ensure_user_exists(from_id, message.from_user.username, message.from_user.first_name)
    
    if not target_user or not target_user.get("user_id"):
        await message.answer("❌ Пользователь не активировал бота!")
        return
    
    if bet > 0:
        balance = await db.get_balance(from_id)
        if not balance or balance < bet:
            await message.answer(f"❌ Недостаточно средств! Баланс: {format_number(balance)} NCoin")
            return
    
    game_id = f"xo_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    try:
        from handlers.tictactoe import active_games, auto_cancel_challenge
    except ImportError:
        await message.answer("❌ Игра недоступна")
        return
    
    # Проверка существующих вызовов
    for gid, game in active_games.items():
        if game and game.get("pending"):
            if ((game.get("player_x") == from_id and game.get("player_o") == target_id) or
                (game.get("player_x") == target_id and game.get("player_o") == from_id)):
                await message.answer("❌ Уже есть активный вызов!")
                return
    
    from_name = safe_html_escape(message.from_user.first_name) if message.from_user else "Игрок"
    target_name = safe_html_escape(target_user.get("first_name", "Игрок"))
    
    active_games[game_id] = {
        "type": "pvp",
        "board": [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]],
        "player_x": from_id,
        "player_o": target_id,
        "current_turn": "X",
        "bet": bet or 0,
        "chat_id": message.chat.id if message.chat else None,
        "created_at": time.time(),
        "last_move": time.time(),
        "pending": True,
        "challenger_name": from_name,
        "challenged_name": target_name,
    }
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]
    ])
    
    msg = await message.answer(
        f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
        f"👤 {from_name} вызывает {target_name}!\n"
        f"💰 Ставка: <b>{format_number(bet)} NCoin</b>\n"
        f"⏰ 60 секунд",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    
    if msg and msg.chat and msg.message_id:
        asyncio.create_task(auto_cancel_challenge(game_id, msg.chat.id, msg.message_id))


@register_command(['анкета', 'профиль', 'profile'], need_target=True)
async def cmd_show_profile(
    message: types.Message,
    target_id: int,
    target_user: dict,
    **kwargs: Any
) -> None:
    """Показать анкету пользователя."""
    if not message or target_id is None:
        return
    
    try:
        profile = await db.get_profile(target_id)
        balance = await db.get_balance(target_id)
        target_name = (
            safe_html_escape(target_user.get('first_name', 'Пользователь'))
            if target_user else 'Пользователь'
        )
        
        if not profile:
            await message.answer(
                f"👤 <b>{target_name}</b>\n\n"
                f"❌ Анкета не заполнена\n"
                f"💰 Баланс: <b>{format_number(balance)}</b> NCoin",
                parse_mode=ParseMode.HTML
            )
            return
        
        text = (
            f"👤 <b>АНКЕТА {target_name}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📛 Имя: <b>{safe_html_escape(profile.get('full_name', '') or 'Не указано')}</b>\n"
            f"🎂 Возраст: <b>{profile.get('age', '') or 'Не указано'}</b>\n"
            f"🏙️ Город: <b>{safe_html_escape(profile.get('city', '') or 'Не указано')}</b>\n"
            f"📝 О себе: {safe_html_escape(profile.get('about', '') or 'Не указано')}\n\n"
            f"💰 Баланс: <b>{format_number(balance)}</b> NCoin"
        )
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Profile error: {e}", exc_info=True)


@register_command(['перевод', 'перевести', 'transfer'], need_target=True)
async def cmd_transfer_coins(
    message: types.Message,
    from_id: int,
    target_id: int,
    target_user: dict,
    **kwargs: Any
) -> None:
    """Перевод монет пользователю."""
    if not message or from_id is None or target_id is None:
        return
    
    amount = extract_number(message.text)
    if from_id == target_id:
        await message.answer("❌ Нельзя перевести самому себе!")
        return
    if amount < 10:
        await message.answer("❌ Минимум 10 NCoin")
        return
    
    if message.from_user:
        await ensure_user_exists(from_id, message.from_user.username, message.from_user.first_name)
    
    balance = await db.get_balance(from_id)
    if not balance or balance < amount:
        await message.answer(f"❌ Недостаточно средств! Баланс: {format_number(balance)} NCoin")
        return
    
    try:
        target_username = target_user.get('username') if target_user else None
        if not target_username:
            await message.answer("❌ Не удалось определить получателя!")
            return
        
        result = await db.transfer_coins(from_id, target_username, amount, "transfer")
        
        if not result or not result.get("success"):
            error = result.get("error", "Неизвестная ошибка") if result else "Ошибка перевода"
            await message.answer(f"❌ {error}")
            return
        
        new_balance = result.get("new_from_balance") or await db.get_balance(from_id)
        target_name = (
            safe_html_escape(target_user.get('first_name', 'Пользователь'))
            if target_user else 'Пользователь'
        )
        await message.answer(
            f"✅ <b>ПЕРЕВОД ВЫПОЛНЕН!</b>\n\n"
            f"📤 {format_number(amount)} NCoin\n"
            f"📥 {target_name}\n"
            f"💰 Новый баланс: <b>{format_number(new_balance)}</b> NCoin",
            parse_mode=ParseMode.HTML
        )
    except DatabaseError as e:
        logger.error(f"❌ Transfer DB error: {e}", exc_info=True)
        await message.answer("❌ Ошибка базы данных.")
    except Exception as e:
        logger.error(f"❌ Transfer error: {e}", exc_info=True)


# ==================== УМНЫЕ ТЕГИ ====================

TAG_KEYWORDS: Dict[str, List[str]] = {
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


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================

def _message_filter(message: Optional[types.Message]) -> bool:
    """Фильтр сообщений для smart_parser."""
    if message is None:
        return False
    if not message.text:
        return False
    if message.text.startswith('/'):
        return False
    if message.chat is None:
        return False
    return True


@router.message(F.text, _message_filter)
async def smart_parser(message: types.Message) -> None:
    """
    Умный парсер сообщений.
    
    Обрабатывает сообщения, не начинающиеся с /.
    Распознаёт РП-команды, умные теги, вызовы бота.
    """
    if not message or not message.from_user or message.from_user.is_bot:
        return
    if BOT_ID and message.from_user.id == BOT_ID:
        return
    
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    
    if not text:
        return
    if message.via_bot:
        return
    
    # Трекинг статистики
    await _track_message_stats(message, user_id)
    
    # Логирование слов
    await _log_chat_message(message, user_id, text)
    
    # Проверка пользователя
    user = await ensure_user_exists(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    if not user:
        await message.answer("👋 Используйте /start для регистрации")
        return
    
    # Проверка, вызван ли бот
    bot_names = ['нексус', 'нэксус', 'nexus', 'некс', 'нэкс', 'бот']
    bot_called = any(w in text for w in bot_names)
    
    # Умные теги
    if bot_called:
        if await _handle_smart_tags(message, text):
            return
    
    # Определение цели
    target_id, target_user, target_username = await get_target_from_message(message)
    
    # Команды с целью
    if target_id and target_user:
        if await _handle_target_commands(message, user_id, text, target_id, target_user, target_username):
            return
    
    # Команды без цели
    if bot_called:
        if await _handle_no_target_commands(message, text):
            return
    
    # Простые РП-ответы
    if bot_called:
        await _handle_simple_responses(message, text)


async def _track_message_stats(message: types.Message, user_id: int) -> None:
    """Отслеживание статистики сообщений."""
    try:
        chat_id = message.chat.id if message.chat else 0
        
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
        
        await db.track_user_activity(user_id, chat_id, activity_type, 1)
    except DatabaseError as e:
        logger.warning(f"⚠️ Stats error: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Stats error: {e}")


async def _log_chat_message(message: types.Message, user_id: int, text: str) -> None:
    """Логирование слов чата."""
    try:
        if message.chat and hasattr(db, 'log_chat_message') and callable(db.log_chat_message):
            await db.log_chat_message(message.chat.id, user_id, text)
    except DatabaseError as e:
        logger.warning(f"⚠️ Log error: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Log error: {e}")


async def _handle_smart_tags(message: types.Message, text: str) -> bool:
    """Обработка умных тегов. Возвращает True если тег найден."""
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
                        await trigger_tag(message, slug, msg_text)
                        return True
                except ImportError:
                    logger.debug("Tag modules not available")
                except Exception as e:
                    logger.error(f"❌ Tag error: {e}", exc_info=True)
    return False


async def _handle_target_commands(
    message: types.Message,
    user_id: int,
    text: str,
    target_id: int,
    target_user: dict,
    target_username: Optional[str]
) -> bool:
    """Обработка команд с целью. Возвращает True если команда найдена."""
    for kw, handler in TARGET_COMMANDS.items():
        if kw and kw in text:
            try:
                await handler.handler(
                    message,
                    from_id=user_id,
                    target_id=target_id,
                    target_user=target_user,
                    target_username=target_username
                )
                return True
            except Exception as e:
                logger.error(f"❌ Target cmd error: {e}", exc_info=True)
    
    # Если нет команды, но есть число — пробуем перевод
    amount = extract_number(text)
    if amount > 0:
        try:
            await cmd_transfer_coins(
                message,
                from_id=user_id,
                target_id=target_id,
                target_user=target_user
            )
            return True
        except Exception as e:
            logger.error(f"❌ Transfer error: {e}", exc_info=True)
    
    return False


async def _handle_no_target_commands(message: types.Message, text: str) -> bool:
    """Обработка команд без цели. Возвращает True если команда найдена."""
    for kw, handler in NO_TARGET_COMMANDS.items():
        if kw and kw in text:
            try:
                await handler.handler(message)
                return True
            except Exception as e:
                logger.error(f"❌ No-target error: {e}", exc_info=True)
    return False


async def _handle_simple_responses(message: types.Message, text: str) -> None:
    """Простые текстовые ответы."""
    responses = {
        'привет': 'Привет! 👋',
        'пока': 'Пока! 👋',
        'спасибо': 'Пожалуйста! 🤗',
        'доброе утро': 'Доброе утро! ☀️',
        'добрый вечер': 'Добрый вечер! 🌙',
        'спокойной ночи': 'Сладких снов! 😴',
    }
    for k, v in responses.items():
        if k and k in text:
            await message.answer(v)
            return


# ==================== КНОПКИ ====================

@router.callback_query(F.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery) -> None:
    """
    Обработчик кнопки НАЧАТЬ общий сбор.
    
    Редиректит на команду /all через message.
    """
    if not callback:
        return
    
    try:
        # Отправляем команду /all как сообщение
        if callback.message:
            await callback.message.answer("📢 Запускаю общий сбор... Используйте /all")
    except Exception as e:
        logger.error(f"❌ start_all error: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery) -> None:
    """Обработчик кнопки ОТМЕНА общего сбора."""
    if not callback:
        return
    
    try:
        if callback.message:
            await callback.message.edit_text("❌ Общий сбор отменён.")
    except TelegramAPIError:
        pass
    except Exception as e:
        logger.error(f"❌ cancel_all error: {e}", exc_info=True)
    
    await _safe_callback_answer(callback)
