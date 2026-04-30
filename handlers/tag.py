#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# ФАЙЛ: handlers/tag.py
# ВЕРСИЯ: 2.6.1-production (исправлены все ошибки)
# ОПИСАНИЕ: Модуль тегов — /all, /tag, /tagrole
# ИСПРАВЛЕНИЯ v2.6.1:
#   ✅ Исправлена синтаксическая ошибка в ConfirmCallback.parse
#   ✅ Исправлена синтаксическая ошибка в _verify_admin_check
#   ✅ Убрана неверная проверка last_underscore == 0
#   ✅ Сохранено детальное логирование для отладки
# =============================================================================

import asyncio
import hashlib
import hmac
import html
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Union

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, User
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramBadRequest,
    TelegramRetryAfter
)

from database import db, DatabaseError

router = Router()
logger = logging.getLogger(__name__)

# =============================================================================
# КОНСТАНТЫ
# =============================================================================

TAG_COOLDOWN: int = 300
BATCH_SIZE: int = 10
BATCH_DELAY: float = 1.0
MAX_MEMBERS_TO_FETCH: int = 200

API_TIMEOUT: float = 30.0
MAX_RETRIES: int = 3

MAX_COOLDOWN_ENTRIES: int = 10000
COOLDOWN_CLEANUP_INTERVAL: int = 3600

_ADMIN_CHECK_SECRET: bytes = hashlib.sha256(b"tag_module_admin_check_v2").digest()
_ADMIN_CHECK_TTL: int = 600

_CALLBACK_PREFIX_CONFIRM: str = "confirm_all_"
_CALLBACK_PREFIX_CANCEL: str = "cancel_all"


# =============================================================================
# ТИПЫ ДАННЫХ
# =============================================================================

@dataclass(frozen=True)
class ConfirmCallback:
    """
    Структурированные данные для подтверждения общего сбора.
    
    Формат callback_ confirm_all_{chat_id}_{timestamp}:{signature}
    
    Примеры:
    >>> # Обычная группа (отрицательный ID)
    >>> ConfirmCallback.parse("confirm_all_-5276597027_1714060800:abc123def4567890")
    ConfirmCallback(chat_id=-5276597027, timestamp=1714060800.0, signature='abc123def4567890')
    
    >>> # Супергруппа (отрицательный ID)
    >>> ConfirmCallback.parse("confirm_all_-1001234567890_1714060800:abc123def4567890")
    ConfirmCallback(chat_id=-1001234567890, timestamp=1714060800.0, signature='abc123def4567890')
    
    >>> # Неверный формат
    >>> ConfirmCallback.parse("invalid") is None
    True
    """
    
    chat_id: int
    timestamp: float
    signature: str
    
    @classmethod
    def parse(cls, data: str) -> Optional["ConfirmCallback"]:
        """
        Надёжный парсер callback_data с детальным логированием.
        
        Алгоритм:
        1. Найти ':' — разделяет timestamp и подпись
        2. Всё после ':' — подпись (ровно 16 hex-символов)
        3. Всё до ':' — "{chat_id}_{timestamp}"
        4. Найти ПОСЛЕДНЕЕ '_' — оно всегда перед timestamp
        5. Парсим chat_id (может быть отрицательным) и timestamp
        """
        logger.debug("🔍 [PARSE] Input: %s", data)
        
        if not data or not isinstance(data, str):
            logger.warning("⚠️ [PARSE] Invalid data type: %s", type(data).__name__)
            return None
        
        try:
            # 1. Проверка префикса
            if not data.startswith(_CALLBACK_PREFIX_CONFIRM):
                logger.warning("⚠️ [PARSE] Wrong prefix. Expected: '%s', Got: '%s'", 
                              _CALLBACK_PREFIX_CONFIRM, data[:30] + "..." if len(data) > 30 else data)
                return None
            logger.debug("✅ [PARSE] Prefix OK")
            
            # 2. Удаляем префикс
            rest = data[len(_CALLBACK_PREFIX_CONFIRM):]
            logger.debug("🔍 [PARSE] After prefix removal: '%s'", rest)
            
            if not rest:
                logger.warning("⚠️ [PARSE] Empty string after prefix removal")
                return None
            
            # 3. Находим двоеточие (разделитель timestamp:signature)
            colon_idx = rest.rfind(':')
            logger.debug("🔍 [PARSE] Colon position: %d, rest length: %d", colon_idx, len(rest))
            
            if colon_idx == -1 or colon_idx == len(rest) - 1:
                logger.warning("⚠️ [PARSE] Invalid colon position: %d", colon_idx)
                return None
            
            signature = rest[colon_idx + 1:]
            before_colon = rest[:colon_idx]
            logger.debug("🔍 [PARSE] Signature: '%s', Before colon: '%s'", signature, before_colon)
            
            # 4. Валидация подписи (ровно 16 hex-символов)
            if len(signature) != 16:
                logger.warning("⚠️ [PARSE] Invalid signature length: %d (expected 16)", len(signature))
                return None
            if not all(c in '0123456789abcdef' for c in signature.lower()):
                logger.warning("⚠️ [PARSE] Invalid signature characters: '%s'", signature)
                return None
            logger.debug("✅ [PARSE] Signature format OK")
            
            # 5. Находим ПОСЛЕДНЕЕ подчёркивание в before_colon
            last_underscore = before_colon.rfind('_')
            logger.debug("🔍 [PARSE] Last underscore position: %d, before_colon length: %d", 
                        last_underscore, len(before_colon))
            
            # ✅ ИСПРАВЛЕНО: убрана проверка last_underscore == 0
            # Отрицательные chat_id (например, -5276597027) дают last_underscore > 0
            if last_underscore == -1 or last_underscore == len(before_colon) - 1:
                logger.warning("⚠️ [PARSE] Invalid underscore position: %d", last_underscore)
                return None
            
            chat_id_str = before_colon[:last_underscore]
            timestamp_str = before_colon[last_underscore + 1:]
            logger.debug("🔍 [PARSE] Chat ID str: '%s', Timestamp str: '%s'", chat_id_str, timestamp_str)
            
            # 6. Валидация и парсинг chat_id (может быть отрицательным)
            if not chat_id_str:
                logger.warning("⚠️ [PARSE] Empty chat_id_str")
                return None
            if not chat_id_str.lstrip('-').isdigit():
                logger.warning("⚠️ [PARSE] chat_id_str is not a valid integer: '%s'", chat_id_str)
                return None
            if chat_id_str == '-':
                logger.warning("⚠️ [PARSE] chat_id_str is only minus sign")
                return None
            
            chat_id = int(chat_id_str)
            logger.debug("✅ [PARSE] Parsed chat_id: %d", chat_id)
            
            # 7. Валидация и парсинг timestamp
            if not timestamp_str or not timestamp_str.isdigit():
                logger.warning("⚠️ [PARSE] Invalid timestamp_str: '%s'", timestamp_str)
                return None
            
            timestamp = float(timestamp_str)
            if timestamp <= 0:
                logger.warning("⚠️ [PARSE] Timestamp <= 0: %f", timestamp)
                return None
            logger.debug("✅ [PARSE] Parsed timestamp: %f", timestamp)
            
            # ✅ УСПЕШНЫЙ ПАРСИНГ
            logger.info("✅ [PARSE] SUCCESS: chat_id=%d, timestamp=%.0f, signature=%s", 
                        chat_id, timestamp, signature)
            
            return cls(chat_id=chat_id, timestamp=timestamp, signature=signature)
            
        except (ValueError, TypeError, IndexError, AttributeError) as e:
            logger.error("❌ [PARSE] Exception: %s", e, exc_info=True)
            return None
    
    def to_callback_data(self) -> str:
        """Генерация callback_data из объекта."""
        return (
            _CALLBACK_PREFIX_CONFIRM +
            str(self.chat_id) + '_' +
            str(int(self.timestamp)) + ':' + 
            self.signature
        )


# =============================================================================
# ГЛОБАЛЬНОЕ СОСТОЯНИЕ
# =============================================================================

_cooldown_storage: OrderedDict[str, float] = OrderedDict()
_cooldown_lock: asyncio.Lock = asyncio.Lock()
_cleanup_task: Optional[asyncio.Task] = None
_shutdown_event: asyncio.Event = asyncio.Event()


# =============================================================================
# УПРАВЛЕНИЕ ФОНОВЫМИ ЗАДАЧАМИ
# =============================================================================

async def start_background_tasks() -> None:
    """Запуск фоновых задач модуля."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info("🔄 Tag module cleanup task started")


async def stop_background_tasks() -> None:
    """Остановка фоновых задач модуля."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _shutdown_event.set()
        try:
            await asyncio.wait_for(_cleanup_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if _cleanup_task:
                _cleanup_task.cancel()
                try:
                    await _cleanup_task
                except asyncio.CancelledError:
                    pass
        finally:
            _cleanup_task = None
            _shutdown_event.clear()
            logger.info("🛑 Tag module cleanup task stopped")


async def _cleanup_loop() -> None:
    """Фоновый цикл очистки устаревших кулдаунов."""
    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(COOLDOWN_CLEANUP_INTERVAL)
            if _shutdown_event.is_set():
                break
            await _cleanup_expired_cooldowns()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("❌ Cleanup loop error: %s", e, exc_info=True)


async def _cleanup_expired_cooldowns() -> None:
    """Очистка истекших кулдаунов с защитой от утечек памяти."""
    current_time = time.time()
    expired_keys: List[str] = []
    
    async with _cooldown_lock:
        for key, timestamp in list(_cooldown_storage.items()):
            if current_time - timestamp > TAG_COOLDOWN:
                expired_keys.append(key)
        
        for key in expired_keys:
            _cooldown_storage.pop(key, None)
        
        while len(_cooldown_storage) > MAX_COOLDOWN_ENTRIES:
            _cooldown_storage.popitem(last=False)
        
        if expired_keys:
            logger.debug("🧹 Cleaned %d expired cooldowns", len(expired_keys))


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование строки для HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception as e:
        logger.warning("⚠️ HTML escape failed: %s", e)
        return str(text) if isinstance(text, str) else ""


def _safe_int(value: Optional[Union[int, str]], default: int = 0) -> int:
    """Безопасное преобразование в int с дефолтным значением."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


async def _safe_get_chat_member(
    bot: Optional[Bot],
    chat_id: int,
    user_id: int
) -> Optional[object]:
    """Безопасное получение информации о участнике чата."""
    if bot is None:
        return None
    
    try:
        return await asyncio.wait_for(
            bot.get_chat_member(chat_id, user_id),
            timeout=API_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout getting chat member %s in %s", user_id, chat_id)
        return None
    except TelegramAPIError as e:
        logger.warning("⚠️ API error getting chat member: %s", e)
        return None
    except Exception as e:
        logger.error("❌ Unexpected error getting chat member: %s", e, exc_info=True)
        return None


async def is_admin_in_chat(bot: Optional[Bot], user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь администратором чата."""
    if bot is None:
        logger.warning("⚠️ Bot is None in is_admin_in_chat")
        return False
    
    member = await _safe_get_chat_member(bot, chat_id, user_id)
    if member is None:
        return False
    
    try:
        status = getattr(member, 'status', None)
        return status in ('creator', 'administrator')
    except Exception as e:
        logger.warning("⚠️ Error checking admin status: %s", e)
        return False


async def is_bot_admin(bot: Optional[Bot], chat_id: int) -> bool:
    """Проверяет, является ли бот администратором чата."""
    if bot is None:
        logger.warning("⚠️ Bot is None in is_bot_admin")
        return False
    
    try:
        bot_me = await asyncio.wait_for(bot.get_me(), timeout=API_TIMEOUT)
        bot_id = getattr(bot_me, 'id', None)
        if bot_id is None:
            return False
        
        member = await _safe_get_chat_member(bot, chat_id, bot_id)
        if member is None:
            return False
        
        status = getattr(member, 'status', None)
        return status in ('creator', 'administrator')
        
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout checking bot admin status")
        return False
    except Exception as e:
        logger.warning("⚠️ Error checking bot admin: %s", e)
        return False


def _sign_admin_check(user_id: int, chat_id: int, timestamp: float) -> str:
    """Генерация подписи проверки прав администратора."""
    payload = f"{user_id}:{chat_id}:{int(timestamp)}"
    signature = hmac.new(
        _ADMIN_CHECK_SECRET,
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:16]
    return f"{int(timestamp)}:{signature}"


def _verify_admin_check(user_id: int, chat_id: int, signed_data: str) -> bool:
    """
    Проверка подписи прав администратора.
    
    Args:
        user_id: ID пользователя для проверки
        chat_id: ID чата для проверки
        signed_data: Подпись в формате "timestamp:signature"
        
    Returns:
        True если подпись валидна и не просрочена, иначе False
    """
    try:
        if not signed_data or not isinstance(signed_data, str):
            return False
        
        colon_idx = signed_data.find(':')
        if colon_idx == -1 or colon_idx == 0:
            return False
        
        timestamp_str = signed_data[:colon_idx]
        provided_sig = signed_data[colon_idx + 1:]
        
        if not provided_sig or len(provided_sig) != 16:
            return False
        if not all(c in '0123456789abcdef' for c in provided_sig.lower()):
            return False
        
        timestamp = float(timestamp_str)
        
        if time.time() - timestamp > _ADMIN_CHECK_TTL:
            return False
        if timestamp <= 0:
            return False
        
        expected_payload = f"{user_id}:{chat_id}:{int(timestamp)}"
        expected_sig = hmac.new(
            _ADMIN_CHECK_SECRET,
            expected_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:16]
        
        return hmac.compare_digest(provided_sig, expected_sig)
        
    except (ValueError, TypeError, IndexError):
        return False


async def try_acquire_cooldown(chat_id: int) -> Tuple[bool, int]:
    """Атомарная проверка и установка кулдауна."""
    cooldown_key = f"all:{chat_id}"
    current_time = time.time()
    
    async with _cooldown_lock:
        last_used = _cooldown_storage.get(cooldown_key)
        if last_used is not None:
            elapsed = current_time - last_used
            if elapsed < TAG_COOLDOWN:
                remaining = max(0, int(TAG_COOLDOWN - elapsed))
                return False, remaining
        
        _cooldown_storage[cooldown_key] = current_time
        _cooldown_storage.move_to_end(cooldown_key)
        return True, 0


def format_time_remaining(seconds: int) -> str:
    """Форматирует оставшееся время в читаемый вид."""
    seconds = max(0, _safe_int(seconds))
    if seconds <= 0:
        return "0 сек"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes > 0:
        return f"{minutes} мин {secs} сек"
    return f"{secs} сек"


def _get_user_dedup_key(user: User) -> str:
    """Генерация уникального ключа для дедупликации пользователя."""
    try:
        user_id = getattr(user, 'id', None)
        if user_id is None or not isinstance(user_id, int):
            return ""
        
        username = getattr(user, 'username', None) or ""
        full_name = getattr(user, 'full_name', None) or ""
        
        name_normalized = str(full_name).lower().strip()
        name_hash = hashlib.md5(name_normalized.encode('utf-8')).hexdigest()[:8]
        
        return f"{user_id}:{username}:{name_hash}"
        
    except Exception as e:
        logger.warning("⚠️ Error generating dedup key: %s", e)
        return ""


def _is_valid_user(user: Optional[User]) -> bool:
    """Проверка валидности объекта User."""
    if user is None:
        return False
    try:
        user_id = getattr(user, 'id', None)
        if user_id is None or not isinstance(user_id, int):
            return False
        if getattr(user, 'is_bot', True):
            return False
        return True
    except Exception:
        return False


def format_mentions(members: List[User]) -> List[str]:
    """Форматирует список участников в HTML-упоминания."""
    mentions: List[str] = []
    
    for member in members:
        member_id = getattr(member, 'id', 'unknown') if member else 'unknown'
        
        if not _is_valid_user(member):
            continue
        
        try:
            user_id = getattr(member, 'id')
            username = getattr(member, 'username', None)
            
            if username and isinstance(username, str) and username.strip():
                mentions.append("@" + safe_html_escape(username.strip()))
            else:
                full_name = getattr(member, 'full_name', None)
                if full_name and isinstance(full_name, str) and full_name.strip():
                    name = safe_html_escape(full_name.strip())
                else:
                    name = f"User#{user_id}"
                mentions.append(f'<a href="tg://user?id={user_id}">{name}</a>')
                
        except Exception as e:
            logger.warning("⚠️ Skip mention for user %s: %s", member_id, e)
            continue
    
    return mentions


async def send_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    max_retries: int = MAX_RETRIES
) -> Optional[Message]:
    """Отправка сообщения с повторами при rate limit."""
    if not text:
        logger.warning("⚠️ Attempt to send empty message")
        return None
    
    last_error: Optional[Exception] = None
    
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(
                bot.send_message(
                    chat_id,
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                ),
                timeout=API_TIMEOUT
            )
            
        except TelegramRetryAfter as e:
            wait_time = min(getattr(e, 'retry_after', 30) + 1, 60)
            last_error = e
            logger.warning("⏱ Rate limit (429), waiting %ds (attempt %d/%d)",
                          wait_time, attempt + 1, max_retries)
            await asyncio.sleep(wait_time)
            
        except TelegramForbiddenError:
            logger.warning("🚫 Bot blocked in chat %s", chat_id)
            return None
            
        except TelegramBadRequest as e:
            err_msg = str(e).lower()
            if "message is not modified" in err_msg or "message can't be edited" in err_msg:
                return None
            logger.error("❌ BadRequest: %s", e)
            return None
            
        except asyncio.TimeoutError:
            last_error = asyncio.TimeoutError()
            logger.warning("⏱ API timeout (attempt %d/%d)", attempt + 1, max_retries)
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                
        except TelegramAPIError as e:
            last_error = e
            logger.error("❌ Telegram API error: %s", e)
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("❌ Unexpected error sending message: %s", e, exc_info=True)
            return None
    
    logger.error("❌ Failed to send message after %d retries: %s", max_retries, last_error)
    return None


async def get_chat_members_safe(
    bot: Optional[Bot],
    chat_id: int
) -> Tuple[List[User], bool]:
    """Безопасное получение списка участников чата."""
    members: List[User] = []
    seen_keys: Set[str] = set()
    has_more = False
    
    if bot is None:
        logger.warning("⚠️ Bot is None in get_chat_members_safe")
        return members, has_more
    
    try:
        admins = await asyncio.wait_for(
            bot.get_chat_administrators(chat_id),
            timeout=API_TIMEOUT
        )
        if admins:
            for admin in admins:
                user = getattr(admin, 'user', None)
                if _is_valid_user(user):
                    dedup_key = _get_user_dedup_key(user)
                    if dedup_key and dedup_key not in seen_keys:
                        members.append(user)
                        seen_keys.add(dedup_key)
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout fetching admins for chat %s", chat_id)
    except TelegramAPIError as e:
        logger.warning("⚠️ Could not fetch admins for chat %s: %s", chat_id, e)
    except Exception as e:
        logger.error("❌ Error fetching admins: %s", e, exc_info=True)
    
    try:
        member_count = 0
        async for member in bot.get_chat_members(chat_id):
            if member_count >= MAX_MEMBERS_TO_FETCH:
                has_more = True
                logger.info("⚠️ Reached MAX_MEMBERS_TO_FETCH (%d) for chat %s",
                           MAX_MEMBERS_TO_FETCH, chat_id)
                break
            
            user = getattr(member, 'user', None)
            if _is_valid_user(user):
                dedup_key = _get_user_dedup_key(user)
                if dedup_key and dedup_key not in seen_keys:
                    members.append(user)
                    seen_keys.add(dedup_key)
            member_count += 1
            
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout fetching members for chat %s", chat_id)
    except TelegramAPIError as e:
        logger.warning("⚠️ Could not fetch all members for chat %s: %s", chat_id, e)
    except Exception as e:
        logger.error("❌ Error fetching members: %s", e, exc_info=True)
    
    logger.info("📊 Fetched %d members for chat %s (has_more=%s)",
                len(members), chat_id, str(has_more))
    return members, has_more


# =============================================================================
# ОБРАБОТЧИКИ КОМАНД
# =============================================================================

@router.message(Command("all"))
async def cmd_all(message: Message) -> None:
    """Команда общего сбора (только для админов)."""
    logger.info("📥 Command /all from user %s in chat %s", 
                getattr(message.from_user, 'id', None) if message.from_user else None,
                getattr(message.chat, 'id', None) if message.chat else None)
    
    if message is None:
        return
    
    from_user = getattr(message, 'from_user', None)
    chat = getattr(message, 'chat', None)
    
    if from_user is None or chat is None:
        logger.warning("⚠️ Missing from_user or chat in message")
        return
    
    user_id = getattr(from_user, 'id', None)
    chat_id = getattr(chat, 'id', None)
    
    if user_id is None or chat_id is None:
        logger.warning("⚠️ Missing user_id or chat_id")
        return
    
    chat_type = getattr(chat, 'type', None)
    if chat_type not in ('group', 'supergroup'):
        await message.answer("❌ Команда /all работает только в группах!")
        return
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await message.answer("❌ Используйте /start для регистрации")
            return
    except DatabaseError as e:
        logger.error("❌ Database error in cmd_all: %s", e)
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
        return
    except Exception as e:
        logger.error("❌ Unexpected error in cmd_all: %s", e, exc_info=True)
        await message.answer("❌ Внутренняя ошибка. Попробуйте позже.")
        return
    
    if not await is_admin_in_chat(message.bot, user_id, chat_id):
        await message.answer(
            "❌ <b>Нет прав!</b>\n\nТолько администраторы чата могут использовать /all.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not await is_bot_admin(message.bot, chat_id):
        await message.answer(
            "❌ <b>Ошибка:</b> Бот не является администратором чата!\n"
            "Дайте боту права на упоминание участников.",
            parse_mode=ParseMode.HTML
        )
        return
    
    can_use, remaining = await try_acquire_cooldown(chat_id)
    if not can_use:
        await message.answer(
            "⏰ <b>Подождите!</b>\n\nСледующий сбор через <b>" + format_time_remaining(remaining) + "</b>.",
            parse_mode=ParseMode.HTML
        )
        return
    
    current_time = time.time()
    admin_check_sig = _sign_admin_check(user_id, chat_id, current_time)
    callback = ConfirmCallback(chat_id=chat_id, timestamp=current_time, signature=admin_check_sig)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=callback.to_callback_data()),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data=_CALLBACK_PREFIX_CANCEL)]
    ])
    
    safe_name = safe_html_escape(getattr(from_user, 'full_name', None))
    await message.answer(
        "📢 <b>ОБЩИЙ СБОР</b> 📢\n\n"
        "⚠️ <b>Внимание!</b>\n"
        "После подтверждения будет отправлено сообщение с упоминанием всех участников.\n\n"
        "👤 Инициатор: " + safe_name + "\n"
        "🛡️ Права: Администратор (проверено)\n\n"
        "✅ <b>Подтвердите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    logger.info("✅ Sent confirmation message for chat %d", chat_id)


@router.message(Command("tag"))
async def cmd_tag(message: Message) -> None:
    """Команда для упоминания конкретного пользователя."""
    if message is None:
        return
    
    from_user = getattr(message, 'from_user', None)
    chat = getattr(message, 'chat', None)
    
    if from_user is None or chat is None:
        return
    
    chat_type = getattr(chat, 'type', None)
    if chat_type not in ('group', 'supergroup'):
        await message.answer("❌ Команда работает только в группах!")
        return
    
    text = getattr(message, 'text', None)
    if text is None:
        return
    
    args = text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 <b>Как тэгать:</b>\n\n"
            "<code>/tag @username текст</code> — упомянуть пользователя\n"
            "Пример: <code>/tag @user Привет!</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    command_text = args[1]
    match = re.search(r'@([a-zA-Z0-9_]+)', command_text)
    if not match:
        await message.answer("❌ Укажите @username пользователя")
        return
    
    username = match.group(1)
    clean_text = re.sub(r'@\w+', '', command_text).strip()
    
    safe_author = safe_html_escape(getattr(from_user, 'full_name', None))
    if clean_text:
        result = "🔔 " + safe_html_escape(clean_text) + "\n\n👉 @" + safe_html_escape(username)
    else:
        result = "🔔 Вас упомянул " + safe_author + "\n\n👉 @" + safe_html_escape(username)
    
    await message.answer(result, parse_mode=ParseMode.HTML)


@router.message(Command("tagrole"))
async def cmd_tag_role(message: Message) -> None:
    """Команда для упоминания всех администраторов."""
    if message is None:
        return
    
    from_user = getattr(message, 'from_user', None)
    chat = getattr(message, 'chat', None)
    
    if from_user is None or chat is None:
        return
    
    chat_type = getattr(chat, 'type', None)
    if chat_type not in ('group', 'supergroup'):
        await message.answer("❌ Команда работает только в группах!")
        return
    
    text = getattr(message, 'text', None)
    if text is None:
        return
    
    args = text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 <b>Как тэгать по роли:</b>\n\n"
            "<code>/tagrole админы текст</code> — упомянуть всех админов",
            parse_mode=ParseMode.HTML
        )
        return
    
    command_text = args[1]
    role_match = re.match(r'(админы?)\s*(.*)', command_text, re.IGNORECASE)
    
    if not role_match:
        await message.answer(
            "❌ Используйте: <code>/tagrole админы текст</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    clean_text = role_match.group(2).strip()
    
    try:
        administrators = await asyncio.wait_for(
            message.bot.get_chat_administrators(chat.id),
            timeout=API_TIMEOUT
        )
        admins = [
            admin.user for admin in administrators
            if admin and hasattr(admin, 'user') and _is_valid_user(admin.user)
        ]
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout fetching admins for tagrole")
        await message.answer("❌ Ошибка: таймаут при получении списка админов")
        return
    except TelegramAPIError as e:
        logger.error("❌ Failed to get admins: %s", e)
        await message.answer("❌ Ошибка: " + safe_html_escape(str(e)), parse_mode=ParseMode.HTML)
        return
    except Exception as e:
        logger.error("❌ Unexpected error in tagrole: %s", e, exc_info=True)
        await message.answer("❌ Внутренняя ошибка")
        return
    
    if not admins:
        await message.answer("❌ Нет администраторов в этом чате", parse_mode=ParseMode.HTML)
        return
    
    mentions = format_mentions(admins)
    
    if clean_text:
        result = "🔔 " + safe_html_escape(clean_text) + "\n\n" + " ".join(mentions)
    else:
        result = "🛡️ <b>Обращение к администраторам:</b>\n\n" + " ".join(mentions)
    
    await message.answer(result, parse_mode=ParseMode.HTML)


# =============================================================================
# ОБРАБОТЧИКИ CALLBACK
# =============================================================================

@router.callback_query(F.data.startswith(_CALLBACK_PREFIX_CONFIRM))
async def confirm_all(callback: CallbackQuery) -> None:
    """Подтверждение общего сбора."""
    logger.info("📥 Confirm callback received from user %s", 
                getattr(callback.from_user, 'id', None) if callback.from_user else None)
    logger.debug("📥 Callback  %s", callback.data)
    
    if callback is None:
        return
    
    cb_message = getattr(callback, 'message', None)
    from_user = getattr(callback, 'from_user', None)
    
    if cb_message is None or from_user is None:
        logger.warning("⚠️ Missing message or from_user in callback")
        return
    
    # Надёжный парсинг callback_data
    parsed = ConfirmCallback.parse(callback.data)
    if parsed is None:
        logger.error("❌ Failed to parse callback: %s", callback.data)
        await callback.answer("❌ Неверный формат запроса", show_alert=True)
        return
    
    logger.info("✅ Parsed callback: chat_id=%d, timestamp=%f", parsed.chat_id, parsed.timestamp)
    
    chat_id = parsed.chat_id
    user_id = getattr(from_user, 'id', None)
    
    if user_id is None:
        logger.warning("⚠️ Missing user_id")
        await callback.answer("❌ Ошибка авторизации", show_alert=True)
        return
    
    msg_chat = getattr(cb_message, 'chat', None)
    if msg_chat and getattr(msg_chat, 'id', None) != chat_id:
        logger.warning("⚠️ Chat ID mismatch: callback=%d, message=%d", 
                      chat_id, getattr(msg_chat, 'id', None))
        await callback.answer("❌ Несоответствие чата", show_alert=True)
        return
    
    if not _verify_admin_check(user_id, chat_id, parsed.signature):
        logger.warning("⚠️ Admin check signature invalid for user %s in chat %s", user_id, chat_id)
        await callback.answer("❌ Проверка прав не пройдена", show_alert=True)
        return
    
    await callback.answer("🔄 Собираю участников...")
    
    status_msg_id: Optional[int] = getattr(cb_message, 'message_id', None)
    
    try:
        await cb_message.edit_text(
            "🔄 <b>Общий сбор:</b> Загрузка участников...",
            parse_mode=ParseMode.HTML
        )
    except TelegramAPIError:
        pass
    
    can_use, remaining = await try_acquire_cooldown(chat_id)
    if not can_use:
        if status_msg_id:
            await send_with_retry(callback.bot, chat_id,
                "⏰ <b>Сбор отменён:</b> Кулдаун активен (" + format_time_remaining(remaining) + ")",
                ParseMode.HTML)
        await callback.answer("⏰ Кулдаун активен!", show_alert=True)
        return
    
    members, has_more = await get_chat_members_safe(callback.bot, chat_id)
    
    if not members:
        if status_msg_id:
            await send_with_retry(callback.bot, chat_id,
                "❌ <b>Ошибка:</b> Не удалось получить список участников.",
                ParseMode.HTML)
        await callback.answer("❌ Нет участников", show_alert=True)
        return
    
    mentions = format_mentions(members)
    safe_initiator = safe_html_escape(getattr(from_user, 'full_name', None))
    
    total_batches = (len(mentions) + BATCH_SIZE - 1) // BATCH_SIZE
    sent_batches = 0
    failed_batches = 0
    
    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(mentions))
        batch_mentions = mentions[start:end]
        batch_text = " ".join(batch_mentions)
        
        if batch_idx == 0:
            response = (
                "📢 <b>ОБЩИЙ СБОР!</b> 📢\n\n"
                "👤 <b>" + safe_initiator + "</b> (администратор)\n\n"
                "🔔 <b>ВНИМАНИЕ ВСЕМ УЧАСТНИКАМ!</b>\n\n"
                + batch_text
            )
        else:
            response = (
                "📢 <b>Продолжение (" + str(batch_idx + 1) + "/" + str(total_batches) + ")</b>\n\n"
                + batch_text
            )
        
        result = await send_with_retry(callback.bot, chat_id, response, ParseMode.HTML)
        if result is not None:
            sent_batches += 1
        else:
            failed_batches += 1
            logger.warning("⚠️ Failed to send batch %d/%d", batch_idx + 1, total_batches)
        
        if batch_idx < total_batches - 1:
            await asyncio.sleep(BATCH_DELAY)
    
    status_parts = ["✅ <b>Общий сбор завершён!</b>"]
    status_parts.append("👥 Упомянуто: " + str(len(mentions)))
    if has_more:
        status_parts.append("⚠️ Показано первых " + str(MAX_MEMBERS_TO_FETCH) + " из-за лимита")
    if failed_batches > 0:
        status_parts.append("⚠️ Не отправлено батчей: " + str(failed_batches))
    
    final_msg = "\n".join(status_parts)
    await send_with_retry(callback.bot, chat_id, final_msg, ParseMode.HTML)
    
    if status_msg_id:
        try:
            msg_chat_id = getattr(cb_message, 'chat_id', chat_id)
            await callback.bot.edit_message_text(
                "✅ <b>Готово!</b>\n📤 Отправлено: " + str(sent_batches) + "/" + str(total_batches) + " батчей",
                chat_id=msg_chat_id,
                message_id=status_msg_id,
                parse_mode=ParseMode.HTML
            )
        except TelegramAPIError:
            pass
    
    await callback.answer("✅ Общий сбор завершён!")
    logger.info("✅ Confirm callback completed for chat %d", chat_id)


@router.callback_query(F.data == _CALLBACK_PREFIX_CANCEL)
async def cancel_all(callback: CallbackQuery) -> None:
    """Отмена общего сбора."""
    logger.info("📥 Cancel callback from user %s", 
                getattr(callback.from_user, 'id', None) if callback.from_user else None)
    
    if callback is None or callback.message is None:
        return
    
    try:
        await callback.message.edit_text("❌ Общий сбор отменён.", parse_mode=ParseMode.HTML)
    except TelegramAPIError:
        pass
    await callback.answer("✅ Отменено")


@router.callback_query(F.data == "tag_menu")
@router.callback_query(F.data == "menu_all")
async def tag_menu(callback: CallbackQuery) -> None:
    """Меню управления тегами."""
    if callback is None or callback.message is None:
        return
    
    from_user = getattr(callback, 'from_user', None)
    if from_user is None:
        return
    
    user_id = getattr(from_user, 'id', None)
    chat_id = getattr(callback.message, 'chat_id', 0)
    
    if user_id is None:
        return
    
    is_admin = await is_admin_in_chat(callback.bot, user_id, chat_id)
    
    if is_admin:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР (/all)", callback_data="start_all")],
            [InlineKeyboardButton(text="🛡️ НАПИСАТЬ АДМИНАМ", callback_data="tag_admins")],
            [InlineKeyboardButton(text="🔔 КАК ПОЛЬЗОВАТЬСЯ", callback_data="tag_help")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        text = (
            "📢 <b>УПРАВЛЕНИЕ ТЭГАМИ</b> (АДМИНИСТРАТОР)\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "• <code>/all</code> — общий сбор (1 раз в 5 минут)\n"
            "• <code>/tag @user</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы</code> — написать админам"
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛡️ НАПИСАТЬ АДМИНАМ", callback_data="tag_admins")],
            [InlineKeyboardButton(text="🔔 КАК ПОЛЬЗОВАТЬСЯ", callback_data="tag_help")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        text = (
            "📢 <b>УПРАВЛЕНИЕ ТЭГАМИ</b>\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "• <code>/tag @user</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы</code> — написать админам\n\n"
            "⚠️ <b>Общий сбор (/all)</b>\nДоступен только для администраторов."
        )
    
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramAPIError as e:
        logger.warning("⚠️ Failed to edit tag_menu: %s", e)
    
    await callback.answer()


@router.callback_query(F.data == "start_all")
async def start_all_callback(callback: CallbackQuery) -> None:
    """Запуск общего сбора через меню."""
    if callback is None or callback.message is None:
        return
    
    from_user = getattr(callback, 'from_user', None)
    if from_user is None:
        return
    
    user_id = getattr(from_user, 'id', None)
    chat_id = getattr(callback.message, 'chat_id', 0)
    
    if user_id is None:
        return
    
    if not await is_admin_in_chat(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только администраторы!", show_alert=True)
        return
    
    if not await is_bot_admin(callback.bot, chat_id):
        await callback.answer("❌ Бот не администратор!", show_alert=True)
        return
    
    can_use, remaining = await try_acquire_cooldown(chat_id)
    if not can_use:
        await callback.answer("⏰ Подождите " + format_time_remaining(remaining), show_alert=True)
        return
    
    current_time = time.time()
    admin_check_sig = _sign_admin_check(user_id, chat_id, current_time)
    cb = ConfirmCallback(chat_id=chat_id, timestamp=current_time, signature=admin_check_sig)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=cb.to_callback_data()),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data=_CALLBACK_PREFIX_CANCEL)]
    ])
    
    safe_name = safe_html_escape(getattr(from_user, 'full_name', None))
    
    try:
        await callback.message.edit_text(
            "📢 <b>ОБЩИЙ СБОР</b> 📢\n\n"
            "⚠️ <b>Внимание!</b>\n"
            "После подтверждения будет отправлено сообщение с упоминанием всех участников.\n\n"
            "👤 Инициатор: " + safe_name + "\n"
            "🛡️ Права: Администратор (проверено)\n\n"
            "✅ <b>Подтвердите действие:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except TelegramAPIError as e:
        logger.warning("⚠️ Failed to edit start_all: %s", e)
    
    await callback.answer()


@router.callback_query(F.data == "tag_admins")
async def tag_admins_callback(callback: CallbackQuery) -> None:
    """Показать список администраторов чата."""
    if callback is None or callback.message is None:
        return
    
    chat_id = getattr(callback.message, 'chat_id', 0)
    
    try:
        administrators = await asyncio.wait_for(
            callback.bot.get_chat_administrators(chat_id),
            timeout=API_TIMEOUT
        )
        admins = [
            admin.user for admin in administrators
            if admin and hasattr(admin, 'user') and _is_valid_user(admin.user)
        ]
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout fetching admins")
        await callback.answer("❌ Таймаут: попробуйте позже", show_alert=True)
        return
    except TelegramAPIError as e:
        logger.error("❌ Failed to get admins: %s", e)
        await callback.answer("❌ Ошибка доступа", show_alert=True)
        return
    
    if not admins:
        await callback.answer("❌ Нет администраторов", show_alert=True)
        return
    
    mentions = format_mentions(admins)
    
    try:
        await callback.message.edit_text(
            "🛡️ <b>АДМИНИСТРАТОРЫ ЧАТА:</b>\n\n" + " ".join(mentions),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_menu")]
            ])
        )
    except TelegramAPIError as e:
        logger.warning("⚠️ Failed to edit tag_admins: %s", e)
    
    await callback.answer()


@router.callback_query(F.data == "tag_help")
async def tag_help_callback(callback: CallbackQuery) -> None:
    """Справка по командам тегов."""
    if callback is None or callback.message is None:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_menu")]
    ])
    
    try:
        await callback.message.edit_text(
            "📢 <b>ПОМОЩЬ ПО ТЭГАМ</b>\n\n"
            "<b>📝 КОМАНДЫ ДЛЯ ВСЕХ:</b>\n"
            "• <code>/tag @user текст</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы текст</code> — написать администраторам\n\n"
            "<b>👑 КОМАНДЫ ДЛЯ АДМИНОВ:</b>\n"
            "• <code>/all</code> — общий сбор (1 раз в 5 минут)",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except TelegramAPIError as e:
        logger.warning("⚠️ Failed to edit tag_help: %s", e)
    
    await callback.answer()
