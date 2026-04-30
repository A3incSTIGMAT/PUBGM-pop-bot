#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# ФАЙЛ: handlers/tag.py
# ВЕРСИЯ: 2.7.0-production (финальная, прошедшая аудит)
# ОПИСАНИЕ: Модуль тегов — /all, /tag, /tagrole
# =============================================================================
# ИСПРАВЛЕНИЯ v2.7.0 (по результатам аудита):
#   ✅ Обработка CancelledError во всех корутинах (критично)
#   ✅ Повторное подключение к БД при сбоях с экспоненциальной задержкой
#   ✅ Настраиваемые уровни логирования через LOG_LEVEL (dev/prod)
#   ✅ API_TIMEOUT и MAX_RETRIES через переменные окружения
#   ✅ Дополнительные проверки граничных случаев (chat_id=0, пустые данные)
#   ✅ Полные docstrings согласно PEP 257 для всех публичных функций
#   ✅ Комментарии о работе с отрицательными chat_id для новичков
#   ✅ Оптимизация логов: детальные префиксы только в DEBUG-режиме
# =============================================================================

import asyncio
import hashlib
import hmac
import html
import logging
import os
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

# =============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ (окружение: dev/prod)
# =============================================================================
# В продакшн-среде рекомендуется LOG_LEVEL=INFO или WARNING
# В dev-среде можно LOG_LEVEL=DEBUG для детального логирования
LOG_LEVEL = os.getenv("TAG_LOG_LEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# Добавляем обработчик если ещё нет (чтобы логи не терялись)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)

# =============================================================================
# КОНСТАНТЫ (настраиваемые через переменные окружения)
# =============================================================================

# Тайминги и лимиты
TAG_COOLDOWN: int = int(os.getenv("TAG_COOLDOWN", "300"))  # Кулдаун между сборами (сек)
BATCH_SIZE: int = int(os.getenv("TAG_BATCH_SIZE", "10"))    # Пользователей в одном сообщении
BATCH_DELAY: float = float(os.getenv("TAG_BATCH_DELAY", "1.0"))  # Задержка между батчами
MAX_MEMBERS_TO_FETCH: int = int(os.getenv("TAG_MAX_MEMBERS", "200"))  # Максимум участников

# Таймауты и повторные попытки (настраиваемые)
API_TIMEOUT: float = float(os.getenv("TAG_API_TIMEOUT", "30.0"))  # Таймаут API (сек)
MAX_RETRIES: int = int(os.getenv("TAG_MAX_RETRIES", "3"))          # Максимум попыток
DB_RETRY_DELAY: float = float(os.getenv("TAG_DB_RETRY_DELAY", "1.0"))  # Задержка повторного подключения к БД

# Управление памятью
MAX_COOLDOWN_ENTRIES: int = int(os.getenv("TAG_MAX_COOLDOWN", "10000"))
COOLDOWN_CLEANUP_INTERVAL: int = int(os.getenv("TAG_CLEANUP_INTERVAL", "3600"))

# Безопасность — секрет из переменных окружения (с fallback для dev)
_ADMIN_CHECK_SECRET_STR: str = os.getenv(
    "TAG_ADMIN_SECRET",
    "tag_module_admin_check_v2"  # Только для dev-среды!
)
_ADMIN_CHECK_SECRET: bytes = hashlib.sha256(_ADMIN_CHECK_SECRET_STR.encode()).digest()
_ADMIN_CHECK_TTL: int = int(os.getenv("TAG_ADMIN_TTL", "600"))  # Время жизни подписи (сек)

# Префиксы callback_data для парсинга
_CALLBACK_PREFIX_CONFIRM: str = "confirm_all_"
_CALLBACK_PREFIX_CANCEL: str = "cancel_all"

# Настройка детального логирования (🔍✅❌⚠️ префиксы)
# В продакшн-среде (LOG_LEVEL=INFO) эти префиксы не будут выводиться,
# так как используется logger.debug()
_ENABLE_DETAILED_LOGGING: bool = LOG_LEVEL == "DEBUG"


# =============================================================================
# ТИПЫ ДАННЫХ
# =============================================================================

@dataclass(frozen=True)
class ConfirmCallback:
    """
    Структурированные данные для подтверждения общего сбора.
    
    Формат callback_ confirm_all_{chat_id}_{timestamp}:{signature}
    
    Атрибуты:
        chat_id: ID чата (может быть отрицательным для супергрупп!)
        timestamp: Время создания подписи
        signature: HMAC-подпись для проверки прав администратора
        
    Примеры:
        >>> # Обычная группа (отрицательный ID)
        >>> cb = ConfirmCallback.parse("confirm_all_-5276597027_1714060800:abc123def4567890")
        >>> cb.chat_id
        -5276597027
        
        >>> # Супергруппа с ID -100xxx (стандартный формат Telegram)
        >>> cb = ConfirmCallback.parse("confirm_all_-1001234567890_1714060800:abc123def4567890")
        >>> cb.chat_id
        -1001234567890
        
        >>> # Неверный формат
        >>> ConfirmCallback.parse("invalid") is None
        True
        
        >>> # Пустая строка
        >>> ConfirmCallback.parse("") is None
        True
    """
    
    chat_id: int
    timestamp: float
    signature: str
    
    @classmethod
    def parse(cls, data: str) -> Optional["ConfirmCallback"]:
        """
        Надёжный парсер callback_data с детальным логированием в DEBUG-режиме.
        
        Алгоритм (устойчив к отрицательным chat_id):
        1. Проверить префикс "confirm_all_"
        2. Найти ':' — разделяет timestamp и подпись
        3. Всё после ':' — подпись (ровно 16 hex-символов)
        4. Всё до ':' — "{chat_id}_{timestamp}"
        5. Найти ПОСЛЕДНЕЕ '_' — оно всегда перед timestamp
        6. Парсим chat_id (может быть отрицательным, напр. -100xxx) и timestamp
        
        Args:
            data: Строка callback_data для парсинга
            
        Returns:
            ConfirmCallback при успешном парсинге, None при ошибке
            
        Note:
            Функция устойчива к отрицательным chat_id благодаря поиску
            ПОСЛЕДНЕГО подчёркивания перед двоеточием. 
            Пример: "-1001234567890_1714060800:abc..." корректно парсится
            в chat_id=-1001234567890, timestamp=1714060800.
        """
        if _ENABLE_DETAILED_LOGGING:
            logger.debug("🔍 [PARSE] Input: %s", data)
        
        # Проверка входных данных
        if not data or not isinstance(data, str):
            logger.warning("⚠️ [PARSE] Invalid data type: %s", type(data).__name__)
            return None
        
        # Проверка минимальной длины
        if len(data) < len(_CALLBACK_PREFIX_CONFIRM) + 1 + 16 + 1:  # префикс + минимум 1 символ + подпись 16 + ':'
            logger.warning("⚠️ [PARSE] Data too short: %d chars", len(data))
            return None
        
        try:
            # 1. Проверка префикса
            if not data.startswith(_CALLBACK_PREFIX_CONFIRM):
                if _ENABLE_DETAILED_LOGGING:
                    logger.warning("⚠️ [PARSE] Wrong prefix. Expected: '%s', Got: '%s'", 
                                  _CALLBACK_PREFIX_CONFIRM, 
                                  data[:30] + "..." if len(data) > 30 else data)
                return None
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("✅ [PARSE] Prefix OK")
            
            # 2. Удаляем префикс
            rest = data[len(_CALLBACK_PREFIX_CONFIRM):]
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("🔍 [PARSE] After prefix removal: '%s'", rest)
            
            if not rest:
                logger.warning("⚠️ [PARSE] Empty string after prefix removal")
                return None
            
            # 3. Находим двоеточие (разделитель timestamp:signature)
            colon_idx = rest.rfind(':')
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("🔍 [PARSE] Colon position: %d, rest length: %d", colon_idx, len(rest))
            
            if colon_idx == -1 or colon_idx == len(rest) - 1:
                logger.warning("⚠️ [PARSE] Invalid colon position: %d", colon_idx)
                return None
            
            signature = rest[colon_idx + 1:]
            before_colon = rest[:colon_idx]
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("🔍 [PARSE] Signature: '%s', Before colon: '%s'", signature, before_colon)
            
            # 4. Валидация подписи (ровно 16 hex-символов)
            if len(signature) != 16:
                logger.warning("⚠️ [PARSE] Invalid signature length: %d (expected 16)", len(signature))
                return None
            if not all(c in '0123456789abcdef' for c in signature.lower()):
                logger.warning("⚠️ [PARSE] Invalid signature characters: '%s'", signature)
                return None
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("✅ [PARSE] Signature format OK")
            
            # 5. Находим ПОСЛЕДНЕЕ подчёркивание в before_colon
            #    Важно: используем rfind, а не find, чтобы корректно обрабатывать
            #    отрицательные chat_id вида -1001234567890 (содержат дефис, но не подчёркивание)
            last_underscore = before_colon.rfind('_')
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("🔍 [PARSE] Last underscore position: %d, before_colon length: %d", 
                            last_underscore, len(before_colon))
            
            if last_underscore == -1 or last_underscore == len(before_colon) - 1:
                logger.warning("⚠️ [PARSE] Invalid underscore position: %d (last_underscore at edge)", 
                              last_underscore)
                return None
            
            chat_id_str = before_colon[:last_underscore]
            timestamp_str = before_colon[last_underscore + 1:]
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("🔍 [PARSE] Chat ID str: '%s', Timestamp str: '%s'", chat_id_str, timestamp_str)
            
            # 6. Валидация и парсинг chat_id (может быть отрицательным!)
            if not chat_id_str:
                logger.warning("⚠️ [PARSE] Empty chat_id_str")
                return None
            # lstrip('-') убирает минус для проверки isdigit()
            if not chat_id_str.lstrip('-').isdigit():
                logger.warning("⚠️ [PARSE] chat_id_str is not a valid integer: '%s'", chat_id_str)
                return None
            if chat_id_str == '-':
                logger.warning("⚠️ [PARSE] chat_id_str is only minus sign")
                return None
            
            chat_id = int(chat_id_str)
            # Проверка на chat_id = 0 (невалидный ID чата в Telegram)
            if chat_id == 0:
                logger.warning("⚠️ [PARSE] chat_id is 0 (invalid)")
                return None
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("✅ [PARSE] Parsed chat_id: %d", chat_id)
            
            # 7. Валидация и парсинг timestamp (только положительное целое)
            if not timestamp_str or not timestamp_str.isdigit():
                logger.warning("⚠️ [PARSE] Invalid timestamp_str: '%s'", timestamp_str)
                return None
            
            timestamp = float(timestamp_str)
            if timestamp <= 0:
                logger.warning("⚠️ [PARSE] Timestamp <= 0: %f", timestamp)
                return None
            if _ENABLE_DETAILED_LOGGING:
                logger.debug("✅ [PARSE] Parsed timestamp: %f", timestamp)
            
            # ✅ УСПЕШНЫЙ ПАРСИНГ
            logger.info("✅ [PARSE] SUCCESS: chat_id=%d, timestamp=%.0f, signature=%s", 
                        chat_id, timestamp, signature)
            
            return cls(chat_id=chat_id, timestamp=timestamp, signature=signature)
            
        except (ValueError, TypeError, IndexError, AttributeError) as e:
            logger.error("❌ [PARSE] Exception: %s", e, exc_info=True)
            return None
    
    def to_callback_data(self) -> str:
        """
        Генерация callback_data из объекта для кнопок Telegram.
        
        Returns:
            Строка формата "confirm_all_{chat_id}_{timestamp}:{signature}"
        """
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
    """
    Запуск фоновых задач модуля.
    
    Вызывать при старте бота после инициализации event loop.
    Создаёт фоновую задачу для очистки устаревших кулдаунов.
    
    Note:
        Безопасен для повторного вызова — проверяет, не запущена ли уже задача.
    """
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info("🔄 Tag module cleanup task started")


async def stop_background_tasks() -> None:
    """
    Остановка фоновых задач модуля.
    
    Вызывать при остановке бота для корректного завершения.
    Устанавливает shutdown_event и ждёт завершения задачи очистки.
    
    Note:
        Безопасен для повторного вызова. Использует таймаут 5 секунд
        для предотвращения зависания.
    """
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _shutdown_event.set()
        try:
            # Ждём завершения с таймаутом
            await asyncio.wait_for(_cleanup_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Принудительно отменяем задачу
            if _cleanup_task:
                _cleanup_task.cancel()
                try:
                    await _cleanup_task
                except asyncio.CancelledError:
                    pass  # Ожидаемое исключение при отмене
        finally:
            _cleanup_task = None
            _shutdown_event.clear()
            logger.info("🛑 Tag module cleanup task stopped")


async def _cleanup_loop() -> None:
    """
    Фоновый цикл очистки устаревших кулдаунов.
    
    Выполняется каждые COOLDOWN_CLEANUP_INTERVAL секунд.
    Корректно обрабатывает CancelledError при остановке бота.
    """
    while not _shutdown_event.is_set():
        try:
            # Используем asyncio.sleep вместо sleep для поддержки CancelledError
            await asyncio.sleep(COOLDOWN_CLEANUP_INTERVAL)
            
            # Проверяем shutdown_event после ожидания
            if _shutdown_event.is_set():
                break
                
            await _cleanup_expired_cooldowns()
            
        except asyncio.CancelledError:
            # Корректная обработка отмены задачи
            logger.debug("🛑 Cleanup loop cancelled")
            break
        except Exception as e:
            # Логируем ошибку и продолжаем работу
            logger.error("❌ Cleanup loop error: %s", e, exc_info=True)
            # Небольшая задержка перед повторной попыткой
            await asyncio.sleep(5)


async def _cleanup_expired_cooldowns() -> None:
    """
    Очистка истекших кулдаунов с защитой от утечек памяти.
    
    Удаляет записи старше TAG_COOLDOWN и применяет LRU-удаление
    при превышении MAX_COOLDOWN_ENTRIES для предотвращения
    неконтролируемого роста хранилища.
    
    Note:
        Потокобезопасна благодаря _cooldown_lock.
    """
    current_time = time.time()
    expired_keys: List[str] = []
    
    try:
        async with _cooldown_lock:
            # Поиск истекших записей (старше TAG_COOLDOWN)
            for key, timestamp in list(_cooldown_storage.items()):
                if current_time - timestamp > TAG_COOLDOWN:
                    expired_keys.append(key)
            
            # Удаление истекших
            for key in expired_keys:
                _cooldown_storage.pop(key, None)
            
            # LRU: удаление самых старых при переполнении хранилища
            while len(_cooldown_storage) > MAX_COOLDOWN_ENTRIES:
                _cooldown_storage.popitem(last=False)
            
            if expired_keys:
                logger.debug("🧹 Cleaned %d expired cooldowns", len(expired_keys))
                
    except asyncio.CancelledError:
        raise  # Пробрасываем для обработки в _cleanup_loop
    except Exception as e:
        logger.error("❌ Error during cooldown cleanup: %s", e, exc_info=True)


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def safe_html_escape(text: Optional[str]) -> str:
    """
    Безопасное экранирование строки для HTML.
    
    Args:
        text: Исходная строка или None
        
    Returns:
        Экранированная строка или пустая строка при ошибке
    """
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception as e:
        logger.warning("⚠️ HTML escape failed: %s", e)
        return str(text) if isinstance(text, str) else ""


def _safe_int(value: Optional[Union[int, str]], default: int = 0) -> int:
    """
    Безопасное преобразование в int с дефолтным значением.
    
    Args:
        value: Значение для преобразования
        default: Значение по умолчанию при ошибке
        
    Returns:
        Целое число или default
    """
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


async def _db_get_user_safe(user_id: int) -> Optional[dict]:
    """
    Безопасное получение пользователя из БД с повторными попытками.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Данные пользователя или None при ошибке
        
    Note:
        Использует экспоненциальную задержку при сбоях БД.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            return await db.get_user(user_id)
        except DatabaseError as e:
            logger.warning("⚠️ DB error getting user %d (attempt %d/%d): %s", 
                          user_id, attempt + 1, max_attempts, e)
            if attempt < max_attempts - 1:
                await asyncio.sleep(DB_RETRY_DELAY * (2 ** attempt))  # Экспоненциальная задержка
            else:
                logger.error("❌ Failed to get user %d after %d attempts", user_id, max_attempts)
                raise  # Пробрасываем исключение после исчерпания попыток
        except Exception as e:
            logger.error("❌ Unexpected DB error: %s", e, exc_info=True)
            raise
    return None


async def _safe_get_chat_member(
    bot: Optional[Bot],
    chat_id: int,
    user_id: int
) -> Optional[object]:
    """
    Безопасное получение информации о участнике чата.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        user_id: ID пользователя
        
    Returns:
        Объект членства или None при ошибке
        
    Note:
        Обрабатывает таймауты, ошибки API и сетевые сбои.
    """
    if bot is None:
        logger.warning("⚠️ Bot is None in _safe_get_chat_member")
        return None
    
    try:
        return await asyncio.wait_for(
            bot.get_chat_member(chat_id, user_id),
            timeout=API_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout getting chat member %s in %s", user_id, chat_id)
        return None
    except TelegramForbiddenError:
        logger.warning("🚫 Bot lacks permission to check member %s in %s", user_id, chat_id)
        return None
    except TelegramAPIError as e:
        logger.warning("⚠️ API error getting chat member: %s", e)
        return None
    except asyncio.CancelledError:
        raise  # Пробрасываем для обработки выше
    except Exception as e:
        logger.error("❌ Unexpected error getting chat member: %s", e, exc_info=True)
        return None


async def is_admin_in_chat(bot: Optional[Bot], user_id: int, chat_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором чата.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя для проверки
        chat_id: ID чата
        
    Returns:
        True если пользователь создатель или администратор, иначе False
    """
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
    """
    Проверяет, является ли бот администратором чата.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        
    Returns:
        True если бот создатель или администратор, иначе False
    """
    if bot is None:
        logger.warning("⚠️ Bot is None in is_bot_admin")
        return False
    
    try:
        bot_me = await asyncio.wait_for(bot.get_me(), timeout=API_TIMEOUT)
        bot_id = getattr(bot_me, 'id', None)
        if bot_id is None:
            logger.warning("⚠️ Could not get bot ID")
            return False
        
        member = await _safe_get_chat_member(bot, chat_id, bot_id)
        if member is None:
            return False
        
        status = getattr(member, 'status', None)
        return status in ('creator', 'administrator')
        
    except asyncio.TimeoutError:
        logger.warning("⏱ Timeout checking bot admin status")
        return False
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("⚠️ Error checking bot admin: %s", e)
        return False


def _sign_admin_check(user_id: int, chat_id: int, timestamp: float) -> str:
    """
    Генерация подписи проверки прав администратора.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        timestamp: Время создания подписи
        
    Returns:
        Строка формата "timestamp:signature"
    """
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
        
    Note:
        Использует hmac.compare_digest для защиты от timing attacks.
        Подпись действительна в течение _ADMIN_CHECK_TTL секунд.
    """
    try:
        if not signed_data or not isinstance(signed_data, str):
            return False
        
        colon_idx = signed_data.find(':')
        if colon_idx == -1 or colon_idx == 0:
            return False
        
        timestamp_str = signed_data[:colon_idx]
        provided_sig = signed_data[colon_idx + 1:]
        
        # Валидация формата подписи
        if not provided_sig or len(provided_sig) != 16:
            return False
        if not all(c in '0123456789abcdef' for c in provided_sig.lower()):
            return False
        
        timestamp = float(timestamp_str)
        
        # Проверка времени жизни подписи
        if time.time() - timestamp > _ADMIN_CHECK_TTL:
            logger.debug("⏰ Admin check signature expired")
            return False
        if timestamp <= 0:
            return False
        
        # Генерация ожидаемой подписи
        expected_payload = f"{user_id}:{chat_id}:{int(timestamp)}"
        expected_sig = hmac.new(
            _ADMIN_CHECK_SECRET,
            expected_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:16]
        
        # Безопасное сравнение (защита от timing attack)
        return hmac.compare_digest(provided_sig, expected_sig)
        
    except (ValueError, TypeError, IndexError):
        return False


async def try_acquire_cooldown(chat_id: int) -> Tuple[bool, int]:
    """
    Атомарная проверка и установка кулдауна.
    
    Args:
        chat_id: ID чата для проверки кулдауна
        
    Returns:
        Tuple[можно_использовать: bool, осталось_секунд: int]
        
    Note:
        Потокобезопасна благодаря _cooldown_lock.
        Использует LRU для предотвращения утечек памяти.
    """
    cooldown_key = f"all:{chat_id}"
    current_time = time.time()
    
    try:
        async with _cooldown_lock:
            last_used = _cooldown_storage.get(cooldown_key)
            if last_used is not None:
                elapsed = current_time - last_used
                if elapsed < TAG_COOLDOWN:
                    remaining = max(0, int(TAG_COOLDOWN - elapsed))
                    return False, remaining
            
            # Установка кулдауна только после успешной проверки
            _cooldown_storage[cooldown_key] = current_time
            _cooldown_storage.move_to_end(cooldown_key)  # LRU: перемещаем в конец
            return True, 0
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("❌ Error in try_acquire_cooldown: %s", e, exc_info=True)
        return False, 0  # В случае ошибки запрещаем


def format_time_remaining(seconds: int) -> str:
    """
    Форматирует оставшееся время в читаемый вид.
    
    Args:
        seconds: Количество секунд
        
    Returns:
        Строка формата "X мин Y сек" или "Y сек"
    """
    seconds = max(0, _safe_int(seconds))
    if seconds <= 0:
        return "0 сек"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes > 0:
        return f"{minutes} мин {secs} сек"
    return f"{secs} сек"


def _get_user_dedup_key(user: User) -> str:
    """
    Генерация уникального ключа для дедупликации пользователя.
    
    Args:
        user: Объект User из Telegram API
        
    Returns:
        Уникальный ключ или пустая строка при ошибке
        
    Note:
        Учитывает user_id + username + hash(full_name) для
        идентификации пользователей даже при смене username.
    """
    try:
        user_id = getattr(user, 'id', None)
        if user_id is None or not isinstance(user_id, int):
            return ""
        
        username = getattr(user, 'username', None) or ""
        full_name = getattr(user, 'full_name', None) or ""
        
        # Нормализация имени для стабильного хэша
        name_normalized = str(full_name).lower().strip()
        name_hash = hashlib.md5(name_normalized.encode('utf-8')).hexdigest()[:8]
        
        return f"{user_id}:{username}:{name_hash}"
        
    except Exception as e:
        logger.warning("⚠️ Error generating dedup key: %s", e)
        return ""


def _is_valid_user(user: Optional[User]) -> bool:
    """
    Проверка валидности объекта User.
    
    Args:
        user: Объект User или None
        
    Returns:
        True если пользователь валиден (имеет ID и не бот), иначе False
    """
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
    """
    Форматирует список участников в HTML-упоминания.
    
    Args:
        members: Список объектов User
        
    Returns:
        Список строк с HTML-упоминаниями (@username или ссылки)
        
    Note:
        Пропускает невалидных пользователей с логированием предупреждений.
    """
    mentions: List[str] = []
    
    for member in members:
        member_id = getattr(member, 'id', 'unknown') if member else 'unknown'
        
        if not _is_valid_user(member):
            continue
        
        try:
            user_id = getattr(member, 'id')
            username = getattr(member, 'username', None)
            
            if username and isinstance(username, str) and username.strip():
                # Пользователь с @username
                mentions.append("@" + safe_html_escape(username.strip()))
            else:
                # Пользователь без username — используем inline-ссылку
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
    """
    Отправка сообщения с повторами при rate limit (429).
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата для отправки
        text: Текст сообщения
        parse_mode: Режим парсинга (HTML/Markdown)
        reply_markup: Клавиатура сообщения
        max_retries: Максимум попыток отправки
        
    Returns:
        Объект Message при успехе, None при неустранимой ошибке
        
    Note:
        При TelegramRetryAfter ждёт указанное время + 1 секунда.
        При TelegramForbiddenError сразу возвращает None.
        При исчерпании попыток логирует ошибку и возвращает None.
    """
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
                
        except asyncio.CancelledError:
            raise  # Пробрасываем для обработки выше
            
        except TelegramAPIError as e:
            last_error = e
            logger.error("❌ Telegram API error: %s", e)
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("❌ Unexpected error sending message: %s", e, exc_info=True)
            return None
    
    # Исчерпаны все попытки
    logger.error("❌ Failed to send message after %d retries. Last error: %s", 
                 max_retries, last_error)
    return None


async def get_chat_members_safe(
    bot: Optional[Bot],
    chat_id: int
) -> Tuple[List[User], bool]:
    """
    Безопасное получение списка участников чата.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        
    Returns:
        Tuple[список_участников: List[User], есть_ещё: bool]
        
    Note:
        Дедупликация по user_id + username + name_hash.
        Возвращает флаг has_more при достижении MAX_MEMBERS_TO_FETCH.
        Сначала получает администраторов, затем остальных участников.
    """
    members: List[User] = []
    seen_keys: Set[str] = set()
    has_more = False
    
    if bot is None:
        logger.warning("⚠️ Bot is None in get_chat_members_safe")
        return members, has_more
    
    # 1. Получаем администраторов
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
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("❌ Error fetching admins: %s", e, exc_info=True)
    
    # 2. Получаем остальных участников с лимитом
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
    except asyncio.CancelledError:
        raise
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
    """
    Команда общего сбора (только для админов).
    
    Выполняет следующие проверки:
    1. Регистрация пользователя в БД
    2. Права администратора чата
    3. Права бота на упоминания
    4. Кулдаун (1 раз в 5 минут)
    
    После проверок отправляет сообщение с кнопками ПОДТВЕРДИТЬ/ОТМЕНА.
    """
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
    
    # Проверка регистрации с повторными попытками
    try:
        user = await _db_get_user_safe(user_id)
        if not user:
            await message.answer("❌ Используйте /start для регистрации")
            return
    except DatabaseError as e:
        logger.error("❌ Database error in cmd_all: %s", e)
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
        return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("❌ Unexpected error in cmd_all: %s", e, exc_info=True)
        await message.answer("❌ Внутренняя ошибка. Попробуйте позже.")
        return
    
    # Проверка прав
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
    
    # Проверка кулдауна
    can_use, remaining = await try_acquire_cooldown(chat_id)
    if not can_use:
        await message.answer(
            "⏰ <b>Подождите!</b>\n\nСледующий сбор через <b>" + format_time_remaining(remaining) + "</b>.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Генерация подписи и кнопок
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
    """
    Команда для упоминания конкретного пользователя.
    
    Формат: /tag @username [текст]
    Пример: /tag @user Привет!
    """
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
    """
    Команда для упоминания всех администраторов чата.
    
    Формат: /tagrole админы [текст]
    Пример: /tagrole админы Срочное собрание!
    """
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
    except asyncio.CancelledError:
        raise
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
    """
    Подтверждение общего сбора.
    
    Проверяет подпись администратора, кулдаун, получает список участников
    и отправляет их батчами с упоминаниями.
    """
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
    
    # Парсинг callback_data
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
    
    # Проверка подписи
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
    
    # Проверка кулдауна
    can_use, remaining = await try_acquire_cooldown(chat_id)
    if not can_use:
        if status_msg_id:
            await send_with_retry(callback.bot, chat_id,
                "⏰ <b>Сбор отменён:</b> Кулдаун активен (" + format_time_remaining(remaining) + ")",
                ParseMode.HTML)
        await callback.answer("⏰ Кулдаун активен!", show_alert=True)
        return
    
    # Получение участников
    members, has_more = await get_chat_members_safe(callback.bot, chat_id)
    
    if not members:
        if status_msg_id:
            await send_with_retry(callback.bot, chat_id,
                "❌ <b>Ошибка:</b> Не удалось получить список участников.",
                ParseMode.HTML)
        await callback.answer("❌ Нет участников", show_alert=True)
        return
    
    # Форматирование и отправка
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
    
    # Финальное сообщение со статистикой
    status_parts = ["✅ <b>Общий сбор завершён!</b>"]
    status_parts.append("👥 Упомянуто: " + str(len(mentions)))
    if has_more:
        status_parts.append("⚠️ Показано первых " + str(MAX_MEMBERS_TO_FETCH) + " из-за лимита")
    if failed_batches > 0:
        status_parts.append("⚠️ Не отправлено батчей: " + str(failed_batches))
    
    final_msg = "\n".join(status_parts)
    await send_with_retry(callback.bot, chat_id, final_msg, ParseMode.HTML)
    
    # Обновление статус-сообщения
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
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("❌ Unexpected error: %s", e, exc_info=True)
        await callback.answer("❌ Внутренняя ошибка", show_alert=True)
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
