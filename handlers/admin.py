"""
admin.py — Административные команды для бота Nexus (PRODUCTION v2.2)
=====================================================================

Полный набор команд для управления чатом:

🛡️ МОДЕРАЦИЯ:
- /ban [причина] — забанить пользователя
- /unban [ID|@username] — разбанить пользователя  
- /mute [время] [причина] — замутить пользователя (30s, 5m, 1h, 1d, 1w)
- /unmute [ID|@username] — снять мут
- /kick [причина] — кикнуть пользователя (без бана)

⚠️ ПРЕДУПРЕЖДЕНИЯ:
- /warn [причина] — выдать предупреждение
- /warns [ID|@username] — показать предупреждения пользователя
- /delwarn [ID] — удалить предупреждение

🧹 УПРАВЛЕНИЕ ЧАТОМ:
- /clear [количество] — очистить чат (1-100 сообщений)
- /pin — закрепить сообщение
- /unpin — открепить сообщение

📊 СТАТИСТИКА:
- /stats — статистика бота (только админам)
- /admin_list — список администраторов чата
- /bot_info — информация о боте
- /mod_logs [количество] — показать логи модерации

🏆 ОСОБЕННОСТИ:
✓ Двойная проверка прав (глобальные админы + админы чата)
✓ TTL-кэширование прав для производительности
✓ Защита от rate limit Telegram API
✓ Полное логирование всех действий в БД
✓ Автоматическая очистка старых логов
✓ Система предупреждений с авто-баном
✓ Поддержка множественных причин бана/мута
✓ HTML-форматирование для красивого вывода
✓ Авто-удаление команд модераторов
"""

# ============================================================================
# 📦 ИМПОРТЫ
# ============================================================================

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any, Union
from collections import defaultdict
from functools import wraps

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject, ChatMemberUpdatedFilter
from aiogram.types import (
    Message, ChatPermissions, User, Chat, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError,
    TelegramRetryAfter, TelegramAPIError
)
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорт конфигурации
from config import (
    ADMIN_IDS, DATABASE_PATH, LOG_LEVEL, RATE_LIMIT_SECONDS,
    MAX_WARN_COUNT, MAX_CLEAR_MESSAGES, MAX_MUTE_DAYS,
    AUTO_MODERATION_ENABLED, FORBIDDEN_PATTERNS
)

# Импорт базы данных и утилит
from database import db
from utils.logger import logger

# ============================================================================
# 🎛️ КОНСТАНТЫ И НАСТРОЙКИ
# ============================================================================

router = Router()

# Форматы времени для мута (расширенные)
MUTE_FORMATS = {
    "s": 1, "sec": 1, "seconds": 1,
    "m": 60, "min": 60, "minutes": 60,
    "h": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
    "month": 2592000, "months": 2592000,
}

# Белый список доменов для авто-модерации
ALLOWED_DOMAINS = [
    "t.me", "telegram.me", "youtube.com", "youtu.be",
    "github.com", "stackoverflow.com", "habr.com", "medium.com"
]

# Сообщения об ошибках (локализованные)
ERROR_MESSAGES = {
    "no_permission": "🔒 <b>Доступ запрещен</b>\n\nТолько для администраторов.",
    "bot_no_permission": "⚠️ <b>Ошибка прав бота</b>\n\nБот должен быть администратором с правом <b>«Блокировка пользователей»</b>",
    "bot_no_delete": "⚠️ У бота нет прав на <b>удаление сообщений</b>",
    "user_not_found": "❌ <b>Пользователь не найден</b>",
    "self_action": "❌ <b>Нельзя выполнить это действие над собой</b>",
    "creator_protected": "⛔ <b>Нельзя применить</b> к <b>создателю чата</b>",
    "admin_protected": "⛔ <b>Нельзя применить</b> к <b>администратору</b>",
    "already_banned": "⚠️ Пользователь уже <b>забанен</b>",
    "already_muted": "⚠️ Пользователь уже <b>ограничен</b>",
    "not_muted": "ℹ️ Пользователь не <b>ограничен</b>",
    "rate_limit": "⏳ <b>Слишком быстро!</b> Подождите <code>{seconds}</code> сек.",
    "invalid_duration": "❌ <b>Неверный формат времени</b>\n\nПримеры: <code>30s</code>, <code>5m</code>, <code>1h</code>, <code>2d</code>, <code>1w</code>",
    "no_message_to_pin": "❌ <b>Нет сообщения для закрепления</b>\n\nОтветьте на сообщение командой /pin",
    "no_message_to_clear": "❌ <b>Нет сообщений для очистки</b>",
}


# ============================================================================
# 🗄️ КЭШ ПРАВ АДМИНИСТРАТОРОВ
# ============================================================================

class AdminPermissionCache:
    """
    TTL-кэш для проверки прав администратора.
    Снижает нагрузку на Telegram API при частых проверках.
    
    Features:
        - Автоматическая инвалидация по TTL
        - Ручная инвалидация по чату/пользователю
        - Статистика использования кэша
    """
    
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache: Dict[Tuple[int, int], Tuple[bool, float]] = {}
        self._timestamps: Dict[Tuple[int, int], float] = {}
        self._hits = 0
        self._misses = 0
    
    def _get_key(self, chat_id: int, user_id: int) -> Tuple[int, int]:
        return (chat_id, user_id)
    
    def _is_valid(self, key: Tuple[int, int]) -> bool:
        if key not in self._timestamps:
            return False
        return (datetime.now().timestamp() - self._timestamps[key]) < self.ttl
    
    async def check(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """Проверить права с использованием кэша"""
        key = self._get_key(chat_id, user_id)
        
        if self._is_valid(key) and key in self._cache:
            self._hits += 1
            return self._cache[key][0]
        
        self._misses += 1
        
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
        except Exception as e:
            logger.error(f"Error checking admin status for user {user_id}: {e}")
            is_admin = False
        
        now = datetime.now().timestamp()
        self._cache[key] = (is_admin, now)
        self._timestamps[key] = now
        
        return is_admin
    
    def invalidate(self, chat_id: int, user_id: Optional[int] = None):
        """Очистить кэш для чата или конкретного пользователя"""
        if user_id:
            key = self._get_key(chat_id, user_id)
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
        else:
            keys = [k for k in self._cache if k[0] == chat_id]
            for k in keys:
                self._cache.pop(k, None)
                self._timestamps.pop(k, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику кэша"""
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / (self._hits + self._misses) * 100):.1f}%" if (self._hits + self._misses) > 0 else "0%"
        }

# Глобальный экземпляр кэша
admin_cache = AdminPermissionCache(ttl_seconds=300)


# ============================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

async def is_admin(message: Message, user_id: Optional[int] = None) -> bool:
    """
    Проверка прав администратора с кэшированием
    
    Args:
        message: Исходное сообщение
        user_id: ID пользователя (если None, берётся из message.from_user)
    
    Returns:
        bool: True если пользователь имеет права администратора
    """
    user_id = user_id or message.from_user.id
    
    if user_id in ADMIN_IDS:
        return True
    
    return await admin_cache.check(message.bot, message.chat.id, user_id)


async def can_restrict(bot: Bot, chat_id: int) -> Tuple[bool, Optional[str]]:
    """
    Проверка прав бота на ограничение участников
    
    Returns:
        Tuple[bool, Optional[str]]: (может_ли, сообщение_об_ошибке)
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
        
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False, "Бот не является администратором чата"
        
        if not member.can_restrict_members:
            return False, "У бота нет права «Блокировка пользователей»"
        
        return True, None
        
    except TelegramForbiddenError:
        return False, "Бот заблокирован в этом чате"
    except Exception as e:
        logger.error(f"Error checking bot permissions: {e}")
        return False, f"Ошибка проверки прав: {e}"


async def can_delete_messages(bot: Bot, chat_id: int) -> bool:
    """Проверка права бота на удаление сообщений"""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
        return getattr(member, 'can_delete_messages', False)
    except Exception:
        return False


async def get_target_user(message: Message, command: CommandObject) -> Tuple[Optional[User], Optional[str]]:
    """
    Получить целевого пользователя из команды
    
    Поддерживает:
    - Ответ на сообщение (приоритет)
    - Упоминание @username
    - Прямой ID пользователя
    
    Returns:
        Tuple[Optional[User], Optional[str]]: (пользователь, ошибка)
    """
    # 1. Ответ на сообщение
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user, None
    
    # 2. Аргументы команды
    if command and command.args:
        args = command.args.strip().split()
        if not args:
            return None, ERROR_MESSAGES["user_not_found"]
        
        target = args[0]
        
        # Поиск по числовому ID
        if target.isdigit():
            try:
                chat_obj = await message.bot.get_chat(chat_id=int(target))
                user = _chat_to_user(chat_obj)
                return user, None
            except TelegramBadRequest:
                return None, f"❌ Пользователь с ID <code>{target}</code> не найден"
            except Exception as e:
                logger.error(f"Error fetching user by ID {target}: {e}")
                return None, f"❌ Ошибка поиска: {e}"
        
        # Поиск по @username
        if target.startswith('@'):
            try:
                chat_obj = await message.bot.get_chat(chat_id=target)
                user = _chat_to_user(chat_obj)
                return user, None
            except TelegramBadRequest:
                return None, f"❌ Пользователь <code>{target}</code> не найден"
            except Exception as e:
                logger.error(f"Error fetching user by username {target}: {e}")
                return None, f"❌ Ошибка поиска: {e}"
    
    return None, (
        "❌ <b>Укажите пользователя</b>\n\n"
        "• Ответьте на его сообщение и введите команду\n"
        "• Укажите ID: <code>/ban 123456789</code>\n"
        "• Укажите username: <code>/ban @username</code>"
    )


def _chat_to_user(chat_obj: Chat) -> User:
    """Конвертирует объект Chat в User для единообразия работы"""
    return User(
        id=chat_obj.id,
        is_bot=getattr(chat_obj, 'is_bot', False),
        first_name=getattr(chat_obj, 'first_name', 'Unknown'),
        last_name=getattr(chat_obj, 'last_name', None),
        username=getattr(chat_obj, 'username', None),
        language_code=getattr(chat_obj, 'language_code', None),
    )


def parse_duration(duration_str: str) -> Optional[int]:
    """
    Парсит строку длительности в секунды
    
    Поддерживаемые форматы:
    - 30s, 30sec, 30seconds
    - 5m, 5min, 5minutes  
    - 2h, 2hour, 2hours
    - 1d, 1day, 1days
    - 1w, 1week, 1weeks
    
    Returns:
        Optional[int]: секунды или None если не удалось распарсить
    """
    if not duration_str:
        return None
    
    duration_str = duration_str.lower().strip()
    
    # Прямое совпадение
    if duration_str in MUTE_FORMATS:
        return min(MUTE_FORMATS[duration_str], MAX_MUTE_DAYS * 86400)
    
    # Парсинг формата: число + единица
    match = re.match(r'^(\d+)([a-z]+)$', duration_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        
        if unit in MUTE_FORMATS:
            seconds = value * MUTE_FORMATS[unit]
            return min(seconds, MAX_MUTE_DAYS * 86400)
    
    return None


def format_duration(seconds: int) -> str:
    """Форматирует секунды в человекочитаемый формат"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds // 60} мин"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ч" + (f" {minutes} мин" if minutes else "")
    elif seconds < 604800:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days} д" + (f" {hours} ч" if hours else "")
    else:
        weeks = seconds // 604800
        days = (seconds % 604800) // 86400
        return f"{weeks} нед" + (f" {days} д" if days else "")


def extract_reason(command: CommandObject, skip_first_arg: bool = False) -> str:
    """
    Извлекает причину из аргументов команды
    
    Args:
        command: Объект команды
        skip_first_arg: Пропустить первый аргумент (если это время или ID)
    
    Returns:
        str: Причина или значение по умолчанию
    """
    if not command or not command.args:
        return "Нарушение правил"
    
    args = command.args.strip().split()
    
    if skip_first_arg and len(args) > 1:
        args = args[1:]
    
    reason = ' '.join(args).strip()
    return reason if reason else "Нарушение правил"


async def check_target_status(message: Message, user: User) -> Tuple[bool, Optional[str]]:
    """
    Проверка статуса целевого пользователя
    
    Returns:
        Tuple[bool, Optional[str]]: (можно_ли_действовать, сообщение_об_ошибке)
    """
    try:
        member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=user.id
        )
        
        if member.status == ChatMemberStatus.CREATOR:
            return False, ERROR_MESSAGES["creator_protected"]
        
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            if message.from_user.id not in ADMIN_IDS:
                return False, ERROR_MESSAGES["admin_protected"]
        
        if member.status == ChatMemberStatus.KICKED:
            return False, ERROR_MESSAGES["already_banned"]
        
        if member.status == ChatMemberStatus.LEFT:
            return False, "⚠️ Пользователь <b>не в чате</b>"
            
        return True, None
        
    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            return False, ERROR_MESSAGES["user_not_found"]
        logger.error(f"Error checking target status: {e}")
        return False, f"❌ Ошибка: {e}"
    except Exception as e:
        logger.error(f"Unexpected error checking status: {e}")
        return False, "❌ Ошибка проверки пользователя"


async def log_admin_action(
    action: str,
    admin: User,
    target: User,
    chat_id: int,
    reason: str = "",
    duration: int = None,
    extra: dict = None
) -> None:
    """Логирование действий администратора в БД и в лог-файл"""
    log_entry = {
        "action": action,
        "admin_id": admin.id,
        "admin_name": admin.full_name,
        "admin_username": admin.username,
        "target_id": target.id,
        "target_name": target.full_name,
        "target_username": target.username,
        "chat_id": chat_id,
        "reason": reason,
        "duration_seconds": duration,
        "timestamp": datetime.now().isoformat(),
        **(extra or {})
    }
    
    logger.info(f"ADMIN_ACTION: {log_entry}")
    
    try:
        if hasattr(db, 'log_moderation_action'):
            await db.log_moderation_action(log_entry)
    except Exception as e:
        logger.error(f"Failed to save moderation log to DB: {e}")


def get_mention(user: User) -> str:
    """Возвращает HTML-упоминание пользователя"""
    if user.username:
        return f'<a href="https://t.me/{user.username}">{user.full_name}</a>'
    return f'<b>{user.full_name}</b>'


def get_mention_by_id(user_id: int, name: str = None) -> str:
    """Возвращает HTML-упоминание по ID"""
    if name:
        return f'<a href="tg://user?id={user_id}">{name}</a>'
    return f'<a href="tg://user?id={user_id}">Пользователь</a>'


# ============================================================================
# 🛡️ RATE LIMIT DECORATOR
# ============================================================================

_rate_limits: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

def rate_limit(seconds: float = RATE_LIMIT_SECONDS):
    """
    Декоратор для ограничения частоты вызова команд
    
    Args:
        seconds: Минимальный интервал между вызовами
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(message: Message, *args, **kwargs):
            user_id = message.from_user.id
            chat_id = message.chat.id
            key = f"{chat_id}:{user_id}"
            now = datetime.now().timestamp()
            
            last_call = _rate_limits[key].get(func.__name__, 0)
            if now - last_call < seconds:
                wait_time = int(seconds - (now - last_call)) + 1
                await message.answer(
                    ERROR_MESSAGES["rate_limit"].format(seconds=wait_time),
                    parse_mode="HTML",
                    delete_after=wait_time + 1
                )
                return
            
            _rate_limits[key][func.__name__] = now
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# 🔨 КОМАНДА BAN
# ============================================================================

@router.message(Command("ban"))
@rate_limit(seconds=3)
async def cmd_ban(message: Message, command: CommandObject):
    """
    Бан пользователя
    Использование: /ban [причина] или ответ на сообщение + /ban [причина]
    """
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    can_restr, error = await can_restrict(message.bot, message.chat.id)
    if not can_restr:
        await message.answer(f"⚠️ <b>Ошибка:</b> {error}", parse_mode="HTML")
        return
    
    target, error = await get_target_user(message, command)
    if error:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    if target.id == message.from_user.id:
        await message.answer(ERROR_MESSAGES["self_action"], parse_mode="HTML")
        await message.delete()
        return
    
    allowed, error = await check_target_status(message, target)
    if not allowed:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    reason = extract_reason(command, skip_first_arg=False)
    
    try:
        await message.bot.ban_chat_member(
            chat_id=message.chat.id,
            user_id=target.id
        )
        
        if message.reply_to_message:
            try:
                await message.reply_to_message.delete()
            except Exception:
                pass
        
        admin_cache.invalidate(message.chat.id, target.id)
        
        await message.delete()
        
        text = (
            f"🔨 <b>ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН</b> 🔨\n\n"
            f"👤 {get_mention(target)}\n"
            f"🆔 <code>{target.id}</code>\n"
            f"📝 Причина: {reason}\n"
            f"👮 Админ: {get_mention(message.from_user)}\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await message.answer(text, parse_mode="HTML")
        
        await log_admin_action(
            action="ban",
            admin=message.from_user,
            target=target,
            chat_id=message.chat.id,
            reason=reason
        )
        
    except TelegramBadRequest as e:
        logger.error(f"Ban error: {e}")
        await message.answer(f"⚠️ Ошибка: <code>{e}</code>", parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Unexpected ban error: {e}")
        await message.answer("⚠️ Произошла непредвиденная ошибка.")


# ============================================================================
# 🔓 КОМАНДА UNBAN
# ============================================================================

@router.message(Command("unban"))
@rate_limit(seconds=3)
async def cmd_unban(message: Message, command: CommandObject):
    """Разбан пользователя: /unban [ID|@username] или ответ + /unban"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    can_restr, error = await can_restrict(message.bot, message.chat.id)
    if not can_restr:
        await message.answer(f"⚠️ {error}")
        return
    
    target, error = await get_target_user(message, command)
    if error:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    try:
        await message.bot.unban_chat_member(
            chat_id=message.chat.id,
            user_id=target.id
        )
        
        admin_cache.invalidate(message.chat.id, target.id)
        
        await message.delete()
        
        text = (
            f"🔓 <b>ПОЛЬЗОВАТЕЛЬ РАЗБАНЕН</b> 🔓\n\n"
            f"👤 {get_mention(target)}\n"
            f"🆔 <code>{target.id}</code>\n"
            f"👮 Админ: {get_mention(message.from_user)}"
        )
        
        await message.answer(text, parse_mode="HTML")
        
        await log_admin_action(
            action="unban",
            admin=message.from_user,
            target=target,
            chat_id=message.chat.id
        )
        
    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            await message.answer("⚠️ Пользователь не найден в чате")
        else:
            await message.answer(f"⚠️ Ошибка: <code>{e}</code>", parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Unban error: {e}")
        await message.answer("⚠️ Произошла ошибка")


# ============================================================================
# 🔇 КОМАНДА MUTE
# ============================================================================

@router.message(Command("mute"))
@rate_limit(seconds=3)
async def cmd_mute(message: Message, command: CommandObject):
    """
    Мут пользователя
    Использование: /mute [время] [причина]
    Время: 30s, 5m, 1h, 2d, 1w (по умолчанию 5 минут)
    """
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    can_restr, error = await can_restrict(message.bot, message.chat.id)
    if not can_restr:
        await message.answer(f"⚠️ {error}")
        return
    
    target, error = await get_target_user(message, command)
    if error:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    if target.id == message.from_user.id:
        await message.answer(ERROR_MESSAGES["self_action"], parse_mode="HTML")
        await message.delete()
        return
    
    allowed, error = await check_target_status(message, target)
    if not allowed:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    # Парсинг длительности и причины
    duration_seconds = 300
    reason = "Нарушение правил"
    
    if command and command.args:
        args = command.args.strip().split()
        if args:
            parsed_duration = parse_duration(args[0])
            if parsed_duration:
                duration_seconds = parsed_duration
                reason = extract_reason(command, skip_first_arg=True)
            else:
                reason = extract_reason(command, skip_first_arg=False)
    
    try:
        until_date = datetime.now() + timedelta(seconds=duration_seconds)
        
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
        )
        
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target.id,
            permissions=permissions,
            until_date=int(until_date.timestamp())
        )
        
        if message.reply_to_message:
            try:
                await message.reply_to_message.delete()
            except Exception:
                pass
        
        await message.delete()
        
        text = (
            f"🔇 <b>ПОЛЬЗОВАТЕЛЬ ЗАМУЧЕН</b> 🔇\n\n"
            f"👤 {get_mention(target)}\n"
            f"⏰ Длительность: {format_duration(duration_seconds)}\n"
            f"📝 Причина: {reason}\n"
            f"👮 Админ: {get_mention(message.from_user)}"
        )
        
        await message.answer(text, parse_mode="HTML")
        
        await log_admin_action(
            action="mute",
            admin=message.from_user,
            target=target,
            chat_id=message.chat.id,
            reason=reason,
            duration=duration_seconds,
            extra={"until": until_date.isoformat()}
        )
        
    except TelegramBadRequest as e:
        if "not enough rights" in str(e).lower():
            await message.answer("⚠️ У бота недостаточно прав для мута")
        elif "user is an administrator" in str(e).lower():
            await message.answer(ERROR_MESSAGES["admin_protected"], parse_mode="HTML")
        else:
            await message.answer(f"⚠️ Ошибка: <code>{e}</code>", parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Unexpected mute error: {e}")
        await message.answer("⚠️ Произошла ошибка")


# ============================================================================
# 🔊 КОМАНДА UNMUTE
# ============================================================================

@router.message(Command("unmute"))
@rate_limit(seconds=3)
async def cmd_unmute(message: Message, command: CommandObject):
    """Снятие мута: /unmute [ID|@username] или ответ + /unmute"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    can_restr, error = await can_restrict(message.bot, message.chat.id)
    if not can_restr:
        await message.answer(f"⚠️ {error}")
        return
    
    target, error = await get_target_user(message, command)
    if error:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        )
        
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target.id,
            permissions=permissions
        )
        
        await message.delete()
        
        text = (
            f"🔊 <b>МУТ СНЯТ</b> 🔊\n\n"
            f"👤 {get_mention(target)}\n"
            f"👮 Админ: {get_mention(message.from_user)}"
        )
        
        await message.answer(text, parse_mode="HTML")
        
        await log_admin_action(
            action="unmute",
            admin=message.from_user,
            target=target,
            chat_id=message.chat.id
        )
        
    except TelegramBadRequest as e:
        if "not enough rights" in str(e).lower():
            await message.answer("⚠️ У бота недостаточно прав")
        else:
            await message.answer(f"⚠️ Ошибка: <code>{e}</code>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Unmute error: {e}")
        await message.answer(f"⚠️ Ошибка: {e}")


# ============================================================================
# 👢 КОМАНДА KICK
# ============================================================================

@router.message(Command("kick"))
@rate_limit(seconds=3)
async def cmd_kick(message: Message, command: CommandObject):
    """Кик пользователя (бан + мгновенный разбан): /kick [причина]"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    can_restr, error = await can_restrict(message.bot, message.chat.id)
    if not can_restr:
        await message.answer(f"⚠️ {error}")
        return
    
    target, error = await get_target_user(message, command)
    if error:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    if target.id == message.from_user.id:
        await message.answer(ERROR_MESSAGES["self_action"], parse_mode="HTML")
        await message.delete()
        return
    
    allowed, error = await check_target_status(message, target)
    if not allowed:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    reason = extract_reason(command, skip_first_arg=False)
    
    try:
        await message.bot.ban_chat_member(
            chat_id=message.chat.id,
            user_id=target.id
        )
        await message.bot.unban_chat_member(
            chat_id=message.chat.id,
            user_id=target.id
        )
        
        admin_cache.invalidate(message.chat.id, target.id)
        
        await message.delete()
        
        text = (
            f"👢 <b>ПОЛЬЗОВАТЕЛЬ КИКНУТ</b> 👢\n\n"
            f"👤 {get_mention(target)}\n"
            f"📝 Причина: {reason}\n"
            f"👮 Админ: {get_mention(message.from_user)}"
        )
        
        await message.answer(text, parse_mode="HTML")
        
        await log_admin_action(
            action="kick",
            admin=message.from_user,
            target=target,
            chat_id=message.chat.id,
            reason=reason
        )
        
    except Exception as e:
        logger.error(f"Kick error: {e}")
        await message.answer(f"⚠️ Ошибка: {e}")


# ============================================================================
# ⚠️ СИСТЕМА ПРЕДУПРЕЖДЕНИЙ (WARN)
# ============================================================================

@router.message(Command("warn"))
@rate_limit(seconds=3)
async def cmd_warn(message: Message, command: CommandObject):
    """Выдать предупреждение: /warn [причина] или ответ + /warn [причина]"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    target, error = await get_target_user(message, command)
    if error:
        await message.answer(error, parse_mode="HTML")
        await message.delete()
        return
    
    if target.id == message.from_user.id:
        await message.answer(ERROR_MESSAGES["self_action"], parse_mode="HTML")
        await message.delete()
        return
    
    # Нельзя предупреждать админов
    if message.from_user.id not in ADMIN_IDS:
        try:
            member = await message.bot.get_chat_member(message.chat.id, target.id)
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                await message.answer(ERROR_MESSAGES["admin_protected"], parse_mode="HTML")
                await message.delete()
                return
        except Exception:
            pass
    
    reason = extract_reason(command, skip_first_arg=False)
    
    try:
        warn_count = await db.add_warn(
            chat_id=message.chat.id,
            user_id=target.id,
            admin_id=message.from_user.id,
            reason=reason
        )
        
        await message.delete()
        
        text = f"⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b> ⚠️\n\n👤 {get_mention(target)}\n📝 {reason}"
        
        if warn_count >= MAX_WARN_COUNT:
            text += f"\n\n🔨 <b>АВТО-БАН</b> (достигнут лимит: {warn_count}/{MAX_WARN_COUNT})"
            try:
                await message.bot.ban_chat_member(
                    chat_id=message.chat.id,
                    user_id=target.id
                )
                admin_cache.invalidate(message.chat.id, target.id)
            except Exception as e:
                logger.error(f"Auto-ban after warns failed: {e}")
                text += "\n❌ Не удалось выполнить авто-бан"
        
        text += f"\n📊 Предупреждений: {warn_count}/{MAX_WARN_COUNT}"
        text += f"\n👮 Админ: {get_mention(message.from_user)}"
        
        await message.answer(text, parse_mode="HTML")
        
        await log_admin_action(
            action="warn",
            admin=message.from_user,
            target=target,
            chat_id=message.chat.id,
            reason=reason,
            extra={"warn_count": warn_count, "max_warns": MAX_WARN_COUNT}
        )
        
    except Exception as e:
        logger.exception(f"Warn error: {e}")
        await message.answer("⚠️ Ошибка при выдаче предупреждения")


@router.message(Command("warns"))
async def cmd_warns(message: Message, command: CommandObject):
    """Показать предупреждения пользователя: /warns [ID|@username]"""
    
    if not await is_admin(message):
        target = message.from_user
    else:
        target, error = await get_target_user(message, command)
        if error:
            target = message.from_user
    
    try:
        warns = await db.get_user_warns(message.chat.id, target.id)
        
        if not warns:
            await message.answer(f"ℹ️ У {get_mention(target)} <b>нет предупреждений</b>", parse_mode="HTML")
            return
        
        text = f"📋 <b>ПРЕДУПРЕЖДЕНИЯ</b> {get_mention(target)}\n\n"
        
        for i, warn in enumerate(warns[-10:], 1):
            text += f"{i}. {warn['reason']}\n"
            text += f"   👮 {warn.get('admin_name', 'Админ')} • {warn['timestamp'][:16]}\n\n"
        
        text += f"📊 Всего: {len(warns)} | Лимит: {MAX_WARN_COUNT}"
        
        if len(warns) > 10:
            text += f"\n\n<i>Показаны последние 10 из {len(warns)}</i>"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Warns fetch error: {e}")
        await message.answer("⚠️ Ошибка загрузки предупреждений")


@router.message(Command("delwarn"))
@rate_limit(seconds=3)
async def cmd_delwarn(message: Message, command: CommandObject):
    """Удалить предупреждение: /delwarn [ID предупреждения] или /delwarn @username"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    if not command.args:
        await message.answer(
            "❌ <b>Укажите ID предупреждения</b>\n\n"
            "Использование: <code>/delwarn 1</code>\n"
            "ID можно посмотреть в /warns",
            parse_mode="HTML"
        )
        return
    
    try:
        warn_id = int(command.args.strip())
        deleted = await db.delete_warn(warn_id, message.chat.id)
        
        if deleted:
            await message.answer(f"✅ <b>Предупреждение #{warn_id} удалено</b>", parse_mode="HTML")
            await log_admin_action(
                action="delwarn",
                admin=message.from_user,
                target=message.from_user,
                chat_id=message.chat.id,
                reason=f"Warn #{warn_id} deleted"
            )
        else:
            await message.answer(f"❌ Предупреждение #{warn_id} не найдено", parse_mode="HTML")
            
    except ValueError:
        await message.answer("❌ <b>ID должен быть числом</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Delwarn error: {e}")
        await message.answer("⚠️ Ошибка при удалении предупреждения")


# ============================================================================
# 🧹 КОМАНДА CLEAR (очистка чата)
# ============================================================================

@router.message(Command("clear"))
@rate_limit(seconds=5)
async def cmd_clear(message: Message, command: CommandObject):
    """
    Очистка сообщений чата
    Использование: /clear [количество] (1-100, по умолчанию 10)
    """
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    if not await can_delete_messages(message.bot, message.chat.id):
        await message.answer(ERROR_MESSAGES["bot_no_delete"], parse_mode="HTML")
        return
    
    count = 10
    if command.args and command.args.isdigit():
        count = min(max(1, int(command.args)), MAX_CLEAR_MESSAGES)
    
    try:
        deleted = 0
        errors = 0
        command_msg_id = message.message_id
        
        async for msg in message.bot.get_chat_history(
            chat_id=message.chat.id,
            limit=count + 1
        ):
            if deleted >= count:
                break
            
            if msg.message_id == command_msg_id:
                continue
            
            try:
                await msg.delete()
                deleted += 1
                
                if deleted % 10 == 0:
                    await asyncio.sleep(0.3)
                    
            except TelegramBadRequest as e:
                if "message can't be deleted" not in str(e).lower():
                    errors += 1
            except Exception:
                errors += 1
        
        result = f"✅ <b>Удалено:</b> {deleted}"
        if errors:
            result += f" | <b>Не удалось:</b> {errors}"
        
        notify = await message.answer(result, parse_mode="HTML")
        await asyncio.sleep(3)
        
        await message.delete()
        try:
            await notify.delete()
        except Exception:
            pass
        
        logger.info(f"Clear: {deleted}/{count} messages deleted in chat {message.chat.id}")
        
    except Exception as e:
        logger.exception(f"Clear command error: {e}")
        await message.answer("⚠️ Ошибка при очистке чата")


# ============================================================================
# 📌 КОМАНДЫ PIN / UNPIN
# ============================================================================

@router.message(Command("pin"))
@rate_limit(seconds=3)
async def cmd_pin(message: Message):
    """Закрепить сообщение: ответьте на сообщение и введите /pin"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    if not message.reply_to_message:
        await message.answer(ERROR_MESSAGES["no_message_to_pin"], parse_mode="HTML")
        await message.delete()
        return
    
    try:
        await message.bot.pin_chat_message(
            chat_id=message.chat.id,
            message_id=message.reply_to_message.message_id,
            disable_notification=False
        )
        
        await message.delete()
        
        await message.answer(
            f"📌 <b>Сообщение закреплено</b>\n\n👮 Админ: {get_mention(message.from_user)}",
            parse_mode="HTML"
        )
        
        await log_admin_action(
            action="pin",
            admin=message.from_user,
            target=message.reply_to_message.from_user,
            chat_id=message.chat.id
        )
        
    except TelegramBadRequest as e:
        if "message is already pinned" in str(e).lower():
            await message.answer("⚠️ Сообщение уже закреплено")
        else:
            await message.answer(f"⚠️ Ошибка: {e}")


@router.message(Command("unpin"))
@rate_limit(seconds=3)
async def cmd_unpin(message: Message):
    """Открепить сообщение: /unpin"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        await message.delete()
        return
    
    try:
        await message.bot.unpin_chat_message(
            chat_id=message.chat.id
        )
        
        await message.delete()
        
        await message.answer(
            f"📌 <b>Сообщение откреплено</b>\n\n👮 Админ: {get_mention(message.from_user)}",
            parse_mode="HTML"
        )
        
        await log_admin_action(
            action="unpin",
            admin=message.from_user,
            target=message.from_user,
            chat_id=message.chat.id
        )
        
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")


# ============================================================================
# 📊 КОМАНДА STATS
# ============================================================================

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показать статистику бота (только для админов)"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        return
    
    try:
        total_users = await db.get_total_users() if hasattr(db, 'get_total_users') else "N/A"
        total_chats = await db.get_total_chats() if hasattr(db, 'get_total_chats') else "N/A"
        total_mod_actions = await db.get_total_moderation_actions() if hasattr(db, 'get_total_moderation_actions') else "N/A"
        
        cache_stats = admin_cache.get_stats()
        
        bot_info = await message.bot.get_me()
        chat_member = await message.bot.get_chat_member(message.chat.id, bot_info.id)
        
        text = (
            f"📊 <b>СТАТИСТИКА БОТА</b> 📊\n\n"
            f"👥 <b>Пользователи:</b>\n"
            f"• Всего: {total_users}\n"
            f"• Чатов: {total_chats}\n\n"
            f"🛡️ <b>Модерация:</b>\n"
            f"• Действий: {total_mod_actions}\n"
            f"• Кэш прав: {cache_stats['size']} записей\n"
            f"• Hit rate: {cache_stats['hit_rate']}\n\n"
            f"🤖 <b>Бот:</b>\n"
            f"• Статус: {chat_member.status}\n"
            f"• Версия: 2.2.0\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await message.answer("❌ Ошибка загрузки статистики")


# ============================================================================
# 📋 КОМАНДА ADMIN_LIST
# ============================================================================

@router.message(Command("admin_list"))
async def cmd_admin_list(message: Message):
    """Показать список администраторов чата"""
    
    try:
        admins = await message.bot.get_chat_administrators(chat_id=message.chat.id)
        
        if not admins:
            await message.answer("ℹ️ В чате нет администраторов")
            return
        
        text = "👥 <b>АДМИНИСТРАТОРЫ ЧАТА</b> 👥\n\n"
        
        for member in admins[:20]:
            user = member.user
            icon = "👑" if member.status == ChatMemberStatus.CREATOR else "👮"
            
            mention = f"@{user.username}" if user.username else user.full_name or "Unknown"
            text += f"{icon} {mention}\n"
        
        if len(admins) > 20:
            text += f"\n<i>...и ещё {len(admins) - 20} администраторов</i>"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Admin list error: {e}")
        await message.answer("⚠️ Ошибка получения списка администраторов")


# ============================================================================
# 📜 КОМАНДА MOD_LOGS
# ============================================================================

@router.message(Command("mod_logs"))
@rate_limit(seconds=5)
async def cmd_mod_logs(message: Message, command: CommandObject):
    """Показать логи модерации: /mod_logs [количество] (по умолчанию 10)"""
    
    if not await is_admin(message):
        await message.answer(ERROR_MESSAGES["no_permission"], parse_mode="HTML")
        return
    
    limit = 10
    if command.args and command.args.isdigit():
        limit = min(int(command.args), 50)
    
    try:
        logs = await db.get_moderation_logs(message.chat.id, limit) if hasattr(db, 'get_moderation_logs') else []
        
        if not logs:
            await message.answer("📜 <b>Логи модерации пусты</b>", parse_mode="HTML")
            return
        
        text = f"📜 <b>ЛОГИ МОДЕРАЦИИ</b> (последние {len(logs)})\n\n"
        
        action_icons = {
            "ban": "🔨", "unban": "🔓", "mute": "🔇", "unmute": "🔊",
            "kick": "👢", "warn": "⚠️", "delwarn": "✅", "pin": "📌", "unpin": "📌"
        }
        
        for log in logs[:limit]:
            icon = action_icons.get(log['action'], "🛡️")
            time = log['timestamp'][:16] if isinstance(log['timestamp'], str) else log['timestamp'].strftime("%d.%m %H:%M")
            
            text += f"{icon} {time} | <b>{log['action'].upper()}</b>\n"
            text += f"   👤 {get_mention_by_id(log['target_id'], log.get('target_name', 'User'))}\n"
            text += f"   👮 {get_mention_by_id(log['admin_id'], log.get('admin_name', 'Admin'))}\n"
            
            if log.get('reason'):
                text += f"   📝 {log['reason'][:50]}\n"
            text += "\n"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Mod logs error: {e}")
        await message.answer("⚠️ Ошибка загрузки логов")


# ============================================================================
# ℹ️ КОМАНДА BOT_INFO
# ============================================================================

@router.message(Command("bot_info"))
async def cmd_bot_info(message: Message):
    """Информация о боте"""
    
    bot = await message.bot.get_me()
    
    text = (
        f"🤖 <b>ИНФОРМАЦИЯ О БОТЕ</b> 🤖\n\n"
        f"📛 Имя: {bot.full_name}\n"
        f"🆔 Username: @{bot.username}\n"
        f"🆔 ID: <code>{bot.id}</code>\n"
        f"📝 Версия: 2.2.0 (production)\n"
        f"👨‍💻 Разработчик: @nexus_dev\n\n"
        f"⚙️ <b>Доступные команды:</b>\n"
        f"🎮 /slot, /duel, /roulette — игры\n"
        f"📊 /stats, /games_history — статистика\n"
        f"🔨 /ban, /mute, /kick — модерация\n"
        f"⚠️ /warn, /warns, /delwarn — предупреждения\n"
        f"📌 /pin, /unpin — закрепление\n"
        f"🧹 /clear — очистка чата\n"
        f"📜 /mod_logs — логи модерации\n"
        f"👥 /admin_list — список админов"
    )
    
    await message.answer(text, parse_mode="HTML")


# ============================================================================
# 🛡️ АВТО-МОДЕРАЦИЯ
# ============================================================================

@router.message(F.text & ~F.from_user.is_bot)
async def auto_moderation(message: Message):
    """
    Автоматическая модерация сообщений
    """
    if not AUTO_MODERATION_ENABLED:
        return
    
    can_restr, _ = await can_restrict(message.bot, message.chat.id)
    if not can_restr:
        return
    
    if await is_admin(message, message.from_user.id):
        return
    
    text = message.text.lower()
    
    # Проверка ссылок с белым списком
    if 'http' in text:
        is_allowed = any(domain in text for domain in ALLOWED_DOMAINS)
        if is_allowed:
            return
    
    for pattern in FORBIDDEN_PATTERNS:
        if not pattern:
            continue
        try:
            if re.search(pattern, text, re.IGNORECASE):
                await message.delete()
                notify = await message.answer(
                    f"⚠️ {get_mention(message.from_user)}, <b>сообщение удалено</b>",
                    parse_mode="HTML"
                )
                await asyncio.sleep(3)
                try:
                    await notify.delete()
                except Exception:
                    pass
                logger.info(f"Auto-mod deleted message from {message.from_user.id}")
                break
        except re.error:
            continue


# ============================================================================
# 🔄 ОБРАБОТЧИК ИЗМЕНЕНИЙ СТАТУСА БОТА
# ============================================================================

@router.chat_member(F.update.new_chat_member.user.id == F.bot.id)
async def on_bot_member_update(update: ChatMemberUpdated):
    """Очистка кэша при изменении статуса бота в чате"""
    if update.chat:
        admin_cache.invalidate(update.chat.id)
        logger.info(f"Cleared admin cache for chat {update.chat.id} after member update")


# ============================================================================
# 🎯 ЭКСПОРТ
# ============================================================================

__all__ = ["router"]
