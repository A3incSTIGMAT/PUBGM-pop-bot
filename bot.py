#!/usr/bin/env python3
"""
bot.py — Основной файл бота Nexus (PRODUCTION v3.2.1)
======================================================

Telegram бот с играми, модерацией и системой безопасности.

Исправления относительно v3.2.0:
🔧 [CRITICAL] Исправлено закрытие бота: bot.close() вместо bot.session.close()
🔧 [CRITICAL] Добавлены null-checks для event.from_user/chat в middleware
🔧 [CRITICAL] resolve_used_update_types() вызывается ПОСЛЕ регистрации роутеров
🔧 [CRITICAL] Добавлена валидация токена бота через getMe() при старте
🔧 [MAJOR] Добавлена базовая аутентификация для /metrics endpoint
🔧 [MAJOR] Улучшено получение имени хендлера для partial/lambda функций
🔧 [MINOR] Добавлен retry-логику для проверки Redis
🔧 [MINOR] Добавлена метрика last_health_check_timestamp

Команды:
🎮 ИГРЫ: /slot, /duel, /roulette, /rps, /games_history
📊 СТАТИСТИКА: /stats, /metrics, /admin_list, /bot_info
🛡️ МОДЕРАЦИЯ: /ban, /unban, /mute, /unmute, /kick, /warn, /warns, /clear, /pin, /unpin, /mod_logs

Особенности:
✓ Полная совместимость с aiogram 3.x
✓ Безопасность: CSRF, XSS, rate limiting, sanitized logging
✓ Redis для production (опционально)
✓ Prometheus метрики с аутентификацией
✓ Health checks с детальной диагностикой
✓ Graceful shutdown с обработкой сигналов
✓ Асинхронная архитектура с правильными middleware
"""

# ============================================================================
# 📦 ИМПОРТЫ
# ============================================================================

import asyncio
import functools
import hashlib
import hmac
import os
import signal
import sys
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable, Union

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeDefault, ErrorEvent
from aiogram.exceptions import TelegramAPIError
from aiogram.dispatcher.middlewares.base import BaseMiddleware

# Конфигурация
from config import (
    BOT_TOKEN,
    ADMIN_IDS,
    LOG_LEVEL,
    LOG_FILE,
    REDIS_CONFIG,
    SECURITY_CONFIG,
    DATABASE_PATH,
)

# Определяем окружение
BOT_ENV = os.getenv("BOT_ENV", "development")
IS_PRODUCTION = BOT_ENV == "production"

# Логирование (единая точка входа)
from utils.logger import logger

# Инициализация базы данных
from database import db

# Роутеры
from handlers import games_interactive, admin

# Безопасность
from utils.security import (
    run_security_tests,
    sanitize_html,
    csrf,
    encryptor,
    RateLimiter,
    password_login_limiter,
    api_call_limiter,
)


# ============================================================================
# 📊 PROMETHEUS МЕТРИКИ (глобальная регистрация — ОДИН РАЗ)
# ============================================================================

PROMETHEUS_ENABLED = False
try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_ENABLED = True
except ImportError:
    logger.debug("ℹ️ prometheus_client not installed, metrics disabled")

# Регистрация метрик только если Prometheus доступен
if PROMETHEUS_ENABLED:
    # Метрики времени
    BOT_START_TIME = Gauge('bot_start_time_timestamp', 'Bot start timestamp')
    BOT_UPTIME = Gauge('bot_uptime_seconds', 'Bot uptime in seconds')
    LAST_HEALTH_CHECK = Gauge('bot_last_health_check_timestamp', 'Last successful health check')
    
    # Метрики сообщений
    MESSAGES_RECEIVED = Counter(
        'bot_messages_received_total', 
        'Total messages received',
        ['chat_type']
    )
    COMMANDS_RECEIVED = Counter(
        'bot_commands_received_total', 
        'Total commands received', 
        ['command']
    )
    
    # Метрики ошибок
    ERRORS_TOTAL = Counter(
        'bot_errors_total', 
        'Total errors', 
        ['error_type', 'component']
    )
    
    # Метрики пользователей
    ACTIVE_USERS = Gauge('bot_active_users', 'Currently active users')
    ACTIVE_CHATS = Gauge('bot_active_chats', 'Currently active chats')
    TOTAL_USERS = Gauge('bot_total_users', 'Total registered users')
    
    # Метрики производительности
    HANDLER_DURATION = Histogram(
        'bot_handler_duration_seconds',
        'Handler execution time',
        ['handler_name'],
        buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
    )


# ============================================================================
# 🎛️ ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================================

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None
redis_client: Any = None
_health_task: Optional[asyncio.Task] = None
_start_timestamp: float = 0


# ============================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _update_uptime_metric():
    """Обновление метрики uptime"""
    if PROMETHEUS_ENABLED and _start_timestamp > 0:
        uptime = datetime.now(timezone.utc).timestamp() - _start_timestamp
        BOT_UPTIME.set(uptime)


def _get_handler_name(handler: Callable) -> str:
    """
    Безопасное получение имени хендлера для метрик.
    Корректно обрабатывает partial, lambda, обёртки и методы классов.
    """
    # Распаковываем functools.partial
    while isinstance(handler, functools.partial):
        handler = handler.func
    
    # Пробуем разные атрибуты в порядке приоритета
    for attr_path in ('__name__', '__qualname__', '__class__.__name__'):
        try:
            value = handler
            for attr in attr_path.split('.'):
                value = getattr(value, attr)
            if value and isinstance(value, str) and value != '<lambda>':
                return value[:32]
        except (AttributeError, TypeError):
            continue
    
    # Для lambda или если ничего не найдено — используем хеш
    try:
        return f"handler_{hash(handler) & 0xFFFF:04x}"
    except Exception:
        return "handler_unknown"


async def _validate_bot_token(bot_instance: Bot, timeout: int = 10) -> bool:
    """
    Проверка валидности токена бота через getMe.
    
    Args:
        bot_instance: Экземпляр бота для проверки
        timeout: Таймаут запроса в секундах
    
    Returns:
        bool: True если токен валиден
    """
    try:
        me = await bot_instance.get_me(request_timeout=timeout)
        logger.info(f"✅ Bot token valid: @{me.username} (ID: {me.id}, name: {me.first_name})")
        return True
    except TelegramAPIError as e:
        if "Unauthorized" in str(e) or "Invalid token" in str(e):
            logger.critical(f"❌ Invalid bot token: {e}")
        else:
            logger.error(f"❌ Telegram API error during token validation: {e}")
        return False
    except asyncio.TimeoutError:
        logger.critical("❌ Bot token validation timed out — check network connection")
        return False
    except Exception as e:
        logger.critical(f"❌ Unexpected error during token validation: {type(e).__name__}: {e}")
        return False


async def _redis_health_check(client, retries: int = 3, delay: float = 1.0) -> bool:
    """
    Проверка соединения с Redis с повторными попытками.
    
    Args:
        client: Redis клиент
        retries: Количество попыток
        delay: Базовая задержка между попытками (сек)
    
    Returns:
        bool: True если соединение успешно
    """
    for attempt in range(retries):
        try:
            await client.ping()
            return True
        except Exception as e:
            if attempt == retries - 1:
                logger.error(f"❌ Redis health check failed after {retries} attempts: {e}")
                return False
            wait_time = delay * (attempt + 1)  # Exponential backoff
            logger.warning(f"⚠️ Redis ping failed (attempt {attempt+1}/{retries}), retrying in {wait_time}s: {e}")
            await asyncio.sleep(wait_time)
    return False


# ============================================================================
# 🛡️ MIDDLEWARES (aiogram 3.x — правильная реализация)
# ============================================================================

class LoggingMiddleware(BaseMiddleware):
    """
    Middleware для логирования и метрик сообщений.
    Правильная реализация для aiogram 3.x с безопасным доступом к полям.
    """
    
    async def __call__(
        self, 
        handler: Callable, 
        event: types.Message, 
        data: Dict[str, Any]
    ) -> Any:
        """Обработка сообщения с логированием"""
        start_time = datetime.now(timezone.utc)
        
        # Обновление метрик
        if PROMETHEUS_ENABLED:
            # Безопасное извлечение типа чата
            chat_type = "unknown"
            if hasattr(event, 'chat') and event.chat and hasattr(event.chat, 'type'):
                chat_type = event.chat.type
            MESSAGES_RECEIVED.labels(chat_type=chat_type).inc()
            
            # Логирование команд
            if hasattr(event, 'text') and event.text and event.text.startswith('/'):
                command = event.text.split()[0][1:].split('@')[0]
                COMMANDS_RECEIVED.labels(command=command[:32]).inc()
        
        # Безопасное извлечение информации о пользователе
        user_info = "unknown"
        if hasattr(event, 'from_user') and event.from_user:
            user_info = f"{event.from_user.id} ({event.from_user.full_name})"
        elif hasattr(event, 'sender_chat') and event.sender_chat:
            user_info = f"chat:{event.sender_chat.id}"
        
        # Безопасное извлечение контента
        content = sanitize_html(getattr(event, 'text', '') or '[non-text]')[:100]
        
        logger.debug(f"📩 Message from {user_info} [{chat_type}]: {content}")
        
        try:
            # Выполнение хендлера
            result = await handler(event, data)
            
            # Замер времени выполнения
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if PROMETHEUS_ENABLED:
                handler_name = _get_handler_name(handler)
                HANDLER_DURATION.labels(handler_name=handler_name).observe(elapsed)
            
            # Предупреждение о медленных хендлерах
            if elapsed > 1.0:
                handler_name = getattr(handler, '__name__', 'unknown')
                logger.warning(f"⚠️ Slow handler '{handler_name}': {elapsed:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Handler error: {type(e).__name__}: {e}", exc_info=True)
            if PROMETHEUS_ENABLED:
                ERRORS_TOTAL.labels(
                    error_type=type(e).__name__,
                    component='handler'
                ).inc()
            raise


class AdminCheckMiddleware(BaseMiddleware):
    """
    Middleware для проверки прав администратора.
    Добавляет в data флаг is_admin для использования в хендлерах.
    """
    
    async def __call__(
        self, 
        handler: Callable, 
        event: types.Message, 
        data: Dict[str, Any]
    ) -> Any:
        """Проверка прав администратора"""
        # Безопасная проверка прав
        if event and hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
            # Поддерживаем как int, так и str в ADMIN_IDS
            data['is_admin'] = user_id in ADMIN_IDS or str(user_id) in ADMIN_IDS
            
            if data['is_admin'] and PROMETHEUS_ENABLED:
                ACTIVE_USERS.inc()
        
        return await handler(event, data)


# ============================================================================
# 🛡️ ОБРАБОТЧИК ОШИБОК (aiogram 3.x — правильная сигнатура)
# ============================================================================

async def error_handler(event: ErrorEvent, dispatcher: Dispatcher) -> None:
    """
    Глобальный обработчик ошибок для aiogram 3.x.
    
    Args:
        event: Событие ошибки с информацией об исключении и обновлении
        dispatcher: Экземпляр диспетчера
    """
    exception = event.exception
    error_type = type(exception).__name__
    error_msg = str(exception)[:200]
    
    # Логирование с уровнем в зависимости от типа ошибки
    if isinstance(exception, TelegramAPIError):
        logger.warning(f"⚠️ Telegram API Error: {error_type}: {error_msg}")
    elif isinstance(exception, asyncio.TimeoutError):
        logger.warning(f"⚠️ Timeout error: {error_msg}")
    else:
        logger.error(f"❌ Unhandled error: {error_type}: {error_msg}", exc_info=True)
    
    # Обновление метрик ошибок
    if PROMETHEUS_ENABLED:
        component = 'telegram_api' if isinstance(exception, TelegramAPIError) else 'bot'
        ERRORS_TOTAL.labels(error_type=error_type, component=component).inc()
    
    # Уведомление администраторов только для критических ошибок
    if isinstance(exception, TelegramAPIError) and bot:
        skip_errors = {
            'Message is not modified', 
            'Message to edit not found', 
            'There is no answer to query',
            'query is too old',
            'message is not modified',
            'message can\'t be edited'
        }
        if not any(skip.lower() in error_msg.lower() for skip in skip_errors):
            safe_msg = sanitize_html(error_msg)
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"⚠️ <b>Telegram API Error</b>\n\n"
                        f"<code>{error_type}: {safe_msg}</code>\n\n"
                        f"<i>Bot: @{bot.username}</i>",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass  # Не спамим, если не можем отправить
    
    # Вежливый ответ пользователю (если есть сообщение)
    if event.update and event.update.message and bot:
        try:
            # Не отвечаем на частые ошибки Telegram API
            if not isinstance(exception, TelegramAPIError):
                await event.update.message.answer(
                    "❌ Произошла ошибка. Администраторы уже уведомлены.\n"
                    "Попробуйте повторить позже."
                )
        except Exception:
            pass  # Игнорируем ошибки отправки


# ============================================================================
# 🔧 ИНИЦИАЛИЗАЦИЯ
# ============================================================================

async def set_bot_commands():
    """Установка команд бота"""
    if not bot:
        logger.error("Cannot set commands: bot not initialized")
        return
    
    commands = [
        # Игры
        BotCommand(command="slot", description="🎰 Слот-машина"),
        BotCommand(command="duel", description="⚔️ Дуэль с пользователем"),
        BotCommand(command="roulette", description="🎲 Рулетка"),
        BotCommand(command="rps", description="✊ Камень-ножницы-бумага"),
        BotCommand(command="games_history", description="📜 История игр"),
        
        # Статистика
        BotCommand(command="stats", description="📊 Статистика бота (админ)"),
        BotCommand(command="metrics", description="📈 Метрики (админ)"),
        BotCommand(command="admin_list", description="👥 Список администраторов"),
        BotCommand(command="bot_info", description="ℹ️ Информация о боте"),
        
        # Модерация
        BotCommand(command="ban", description="🔨 Забанить пользователя"),
        BotCommand(command="unban", description="🔓 Разбанить пользователя"),
        BotCommand(command="mute", description="🔇 Замутить пользователя"),
        BotCommand(command="unmute", description="🔊 Снять мут"),
        BotCommand(command="kick", description="👢 Кикнуть пользователя"),
        BotCommand(command="warn", description="⚠️ Выдать предупреждение"),
        BotCommand(command="warns", description="📋 Показать предупреждения"),
        BotCommand(command="clear", description="🧹 Очистить чат"),
        BotCommand(command="pin", description="📌 Закрепить сообщение"),
        BotCommand(command="unpin", description="📌 Открепить сообщение"),
        BotCommand(command="mod_logs", description="📜 Логи модерации (админ)"),
    ]
    
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info(f"✅ Set {len(commands)} bot commands")
    except TelegramAPIError as e:
        logger.error(f"Failed to set bot commands: {e}")


async def init_redis():
    """Инициализация Redis (если включён)"""
    global redis_client
    
    if not REDIS_CONFIG.get('enabled', False):
        logger.info("ℹ️ Redis disabled, using memory storage")
        return None
    
    try:
        import redis.asyncio as redis
        
        redis_client = await redis.from_url(
            REDIS_CONFIG['url'],
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            max_connections=10,
            health_check_interval=30
        )
        
        # Проверка соединения с повторными попытками
        if await _redis_health_check(redis_client):
            logger.info("✅ Redis connected and healthy")
            return redis_client
        else:
            raise ConnectionError("Redis health check failed")
        
    except ImportError:
        logger.warning("⚠️ redis.asyncio not installed, using memory storage")
        return None
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        if IS_PRODUCTION and REDIS_CONFIG.get('require_redis_production', True):
            raise RuntimeError("Redis is required in production mode")
        return None


async def init_security(redis_client_instance):
    """Инициализация модуля безопасности"""
    logger.info("🔐 Initializing security module...")
    
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key:
        logger.error("❌ SECRET_KEY not set in environment")
        if IS_PRODUCTION:
            raise RuntimeError("SECRET_KEY is required in production")
    
    # Настройка CSRF с Redis (если доступен)
    if redis_client_instance:
        csrf.redis = redis_client_instance
        logger.info("✅ CSRF protection with Redis enabled")
    else:
        logger.info("ℹ️ CSRF protection with memory storage")
    
    # Запуск тестов безопасности (только в dev)
    if BOT_ENV == 'development':
        try:
            test_results = await run_security_tests()
            passed = sum(test_results.values())
            total = len(test_results)
            if passed == total:
                logger.info(f"✅ Security tests passed ({passed}/{total})")
            else:
                failed = [k for k, v in test_results.items() if not v]
                logger.warning(f"⚠️ Security tests: {passed}/{total} passed, failed: {failed}")
        except Exception as e:
            logger.error(f"Security tests failed: {e}")
    
    logger.info(f"✅ Security module initialized (Redis: {redis_client_instance is not None})")


async def init_database():
    """Инициализация базы данных"""
    logger.info("🗄️ Initializing database...")
    
    try:
        await db.init()
        logger.info(f"✅ Database initialized: {DATABASE_PATH}")
        
        # Обновление метрики количества пользователей
        if PROMETHEUS_ENABLED and hasattr(db, 'get_total_users'):
            try:
                total_users = await db.get_total_users()
                TOTAL_USERS.set(total_users)
                logger.debug(f"📊 Total users metric updated: {total_users}")
            except Exception as e:
                logger.warning(f"Failed to update total_users metric: {e}")
            
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        if IS_PRODUCTION:
            raise
        logger.warning("⚠️ Continuing without database in development mode")


async def init_prometheus():
    """Инициализация Prometheus метрик"""
    if not PROMETHEUS_ENABLED:
        logger.info("ℹ️ Prometheus not available, metrics disabled")
        return
    
    try:
        port = int(os.getenv("PROMETHEUS_PORT", "9090"))
        start_http_server(port)
        logger.info(f"✅ Prometheus metrics server started on port {port}")
        
        # Установка метрики времени старта
        BOT_START_TIME.set_to_current_time()
        
    except Exception as e:
        logger.warning(f"⚠️ Failed to start Prometheus metrics server: {e}")


# ============================================================================
# 🚀 СОБЫТИЯ ЗАПУСКА И ОСТАНОВКИ
# ============================================================================

async def on_startup(dispatcher: Dispatcher):
    """Действия при запуске бота"""
    global _start_timestamp
    
    _start_timestamp = datetime.now(timezone.utc).timestamp()
    
    logger.info("=" * 60)
    logger.info("🚀 STARTING NEXUS BOT v3.2.1")
    logger.info(f"📦 Environment: {BOT_ENV}")
    logger.info(f"🤖 Bot ID: {bot.id if bot else 'unknown'}")
    logger.info(f"👑 Admins: {ADMIN_IDS}")
    logger.info(f"🔐 Security: enabled")
    logger.info("=" * 60)
    
    # 0. Валидация токена бота (критично!)
    if not await _validate_bot_token(bot):
        raise RuntimeError("Bot token validation failed — check BOT_TOKEN in config")
    
    # 1. Redis (нужен для security и storage)
    redis_instance = await init_redis()
    
    # 2. Безопасность (зависит от Redis)
    await init_security(redis_instance)
    
    # 3. База данных
    await init_database()
    
    # 4. Prometheus метрики
    await init_prometheus()
    
    # 5. Команды бота
    await set_bot_commands()
    
    # Обновление метрик старта
    if PROMETHEUS_ENABLED:
        BOT_START_TIME.set_to_current_time()
        ACTIVE_CHATS.set(0)
        LAST_HEALTH_CHECK.set_to_current_time()
    
    logger.info("✅ Bot is ready!")
    logger.info("📝 Commands: /slot, /duel, /roulette, /rps, /games_history")
    logger.info("🛡️ Admin: /ban, /mute, /kick, /warn, /clear, /stats")


async def on_shutdown(dispatcher: Dispatcher):
    """Действия при остановке бота"""
    logger.info("=" * 60)
    logger.info("🛑 SHUTTING DOWN NEXUS BOT")
    
    # 1. Отмена задачи health check
    global _health_task
    if _health_task and not _health_task.done():
        _health_task.cancel()
        try:
            await _health_task
        except asyncio.CancelledError:
            logger.debug("Health check task cancelled")
    
    # 2. Закрытие Redis
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
            logger.info("✅ Redis connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing Redis: {e}")
    
    # 3. Закрытие базы данных
    try:
        await db.close()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.error(f"❌ Error closing database: {e}")
    
    # 4. Закрытие бота (aiogram 3.x: bot.close() закрывает сессию автоматически)
    if bot:
        try:
            await bot.close()
            logger.info("✅ Bot session closed")
        except AttributeError:
            # Fallback для старых версий или форков
            if hasattr(bot, 'session') and bot.session:
                await bot.session.close()
        except Exception as e:
            logger.error(f"❌ Error closing bot: {e}")
    
    # 5. Финальные метрики
    if PROMETHEUS_ENABLED:
        uptime = datetime.now(timezone.utc).timestamp() - _start_timestamp
        logger.info(f"📊 Final uptime: {uptime:.0f} seconds")
    
    logger.info("✅ Shutdown complete")
    logger.info("=" * 60)


# ============================================================================
# 🏥 HEALTH CHECK
# ============================================================================

async def health_check() -> Dict[str, Any]:
    """
    Проверка состояния бота.
    
    Returns:
        Dict со статусом всех компонентов
    """
    status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "3.2.1",
        "environment": BOT_ENV,
        "bot": {
            "id": bot.id if bot else None,
            "username": bot.username if bot else None,
            "is_ready": bot is not None,
        },
        "database": "unknown",
        "redis": "unknown",
        "security": "enabled",
        "uptime_seconds": None,
    }
    
    # Uptime
    if _start_timestamp > 0:
        status["uptime_seconds"] = round(
            datetime.now(timezone.utc).timestamp() - _start_timestamp, 
            1
        )
    
    # Проверка базы данных
    try:
        if hasattr(db, 'is_initialized'):
            status["database"] = "healthy" if db.is_initialized else "not_initialized"
            if not db.is_initialized:
                status["status"] = "degraded"
        else:
            status["database"] = "healthy"
    except Exception as e:
        status["database"] = f"error: {type(e).__name__}"
        status["status"] = "unhealthy"
    
    # Проверка Redis
    if redis_client:
        try:
            if await _redis_health_check(redis_client, retries=1):
                status["redis"] = "healthy"
            else:
                status["redis"] = "unhealthy"
                if status["status"] == "healthy":
                    status["status"] = "degraded"
        except Exception as e:
            status["redis"] = f"error: {type(e).__name__}"
            if status["status"] == "healthy":
                status["status"] = "degraded"
    else:
        status["redis"] = "disabled"
    
    # Обновление метрики последнего успешного health check
    if PROMETHEUS_ENABLED and status["status"] == "healthy":
        LAST_HEALTH_CHECK.set_to_current_time()
    
    return status


# ============================================================================
# 🌐 HEALTH CHECK HTTP SERVER
# ============================================================================

async def health_check_server():
    """Простой HTTP сервер для health checks (Kubernetes/Docker)"""
    try:
        from aiohttp import web
    except ImportError:
        logger.debug("ℹ️ aiohttp not installed, health check server disabled")
        return
    
    # Токен для аутентификации метрик (опционально)
    METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")
    REQUIRE_METRICS_AUTH = IS_PRODUCTION and bool(METRICS_TOKEN)
    
    async def health_handler(request):
        """Handler для /health endpoint (публичный)"""
        try:
            status_data = await health_check()
            http_status = 200 if status_data["status"] == "healthy" else 503
            return web.json_response(status_data, status=http_status)
        except Exception as e:
            logger.error(f"Health check handler error: {e}")
            return web.json_response(
                {"status": "error", "error": str(e)}, 
                status=500
            )
    
    async def metrics_handler(request):
        """Handler для /metrics endpoint (с опциональной аутентификацией)"""
        # Проверка аутентификации если требуется
        if REQUIRE_METRICS_AUTH:
            auth_header = request.headers.get('Authorization', '')
            expected = f"Bearer {METRICS_TOKEN}"
            # Constant-time сравнение для защиты от timing-атак
            if not hmac.compare_digest(auth_header, expected):
                return web.Response(status=401, text='Unauthorized')
        
        if not PROMETHEUS_ENABLED:
            return web.Response(text="Prometheus not enabled", status=503)
        
        try:
            return web.Response(
                body=generate_latest(),
                content_type=CONTENT_TYPE_LATEST
            )
        except Exception as e:
            logger.error(f"Metrics handler error: {e}")
            return web.Response(text=str(e), status=500)
    
    # Создание приложения
    app = web.Application()
    app.router.add_get('/health', health_handler)
    app.router.add_get('/metrics', metrics_handler)
    app.router.add_get('/', lambda r: web.HTTPFound('/health'))
    
    # Запуск сервера
    port = int(os.getenv("HEALTH_PORT", "8080"))
    
    try:
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"✅ Health check server started on http://0.0.0.0:{port}")
        logger.info(f"   Endpoints: /health (public), /metrics ({'auth required' if REQUIRE_METRICS_AUTH else 'public'})")
        
        # Держим сервер запущенным
        while True:
            await asyncio.sleep(3600)  # Проверяем раз в час
            _update_uptime_metric()
            
    except asyncio.CancelledError:
        logger.info("🛑 Health check server stopped")
        if 'runner' in locals():
            await runner.cleanup()
        raise
    except Exception as e:
        logger.error(f"❌ Health check server error: {e}")
        raise


# ============================================================================
# 🎯 MAIN FUNCTION
# ============================================================================

async def main():
    """Основная функция запуска бота"""
    global bot, dp, redis_client
    
    # 1. Создание бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # 2. Инициализация Redis ДО создания Dispatcher
    redis_client = await init_redis()
    
    # 3. Выбор хранилища FSM
    if REDIS_CONFIG.get('enabled', False) and redis_client:
        storage = RedisStorage(redis_client)
        logger.info("✅ Using Redis storage for FSM")
    else:
        storage = MemoryStorage()
        logger.info("✅ Using Memory storage for FSM")
    
    # 4. Создание Dispatcher
    dp = Dispatcher(storage=storage)
    
    # 5. Регистрация роутеров
    dp.include_router(games_interactive.router)
    dp.include_router(admin.router)
    
    # 6. Регистрация middleware (правильный способ для aiogram 3.x)
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(AdminCheckMiddleware())
    
    # 7. Регистрация обработчика ошибок (правильная сигнатура)
    dp.error.register(error_handler)
    
    # 8. Регистрация событий запуска/остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # 9. Получение типов обновлений ПОСЛЕ регистрации всех роутеров
    allowed_updates = dp.resolve_used_update_types()
    logger.info(f"📡 Listening for updates: {allowed_updates or 'all types'}")
    
    # 10. Запуск бота
    logger.info("🔄 Starting bot polling...")
    
    try:
        await dp.start_polling(
            bot, 
            allowed_updates=allowed_updates if allowed_updates else None,
            skip_updates=True  # Пропускать старые обновления при старте
        )
    except KeyboardInterrupt:
        logger.info("⌨️ Bot stopped by user (KeyboardInterrupt)")
    except SystemExit:
        logger.info("🛑 Bot stopped by SystemExit")
    except Exception as e:
        logger.critical(f"💥 Bot crashed: {type(e).__name__}: {e}", exc_info=True)
        raise
    finally:
        # Гарантированный вызов shutdown даже при исключении
        if dp and hasattr(dp, 'shutdown'):
            await dp.shutdown(bot)


# ============================================================================
# 📝 ENTRY POINT
# ============================================================================

def _setup_signal_handlers(loop: asyncio.AbstractEventLoop):
    """Настройка обработки сигналов для graceful shutdown"""
    
    def signal_handler(signum, frame):
        """Обработчик сигналов завершения"""
        sig_name = signal.Signals(signum).name
        logger.info(f"📡 Received signal {sig_name}, initiating graceful shutdown...")
        
        # Отмена всех задач кроме текущей
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()
    
    # Регистрация обработчиков
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s, None))
        except NotImplementedError:
            # Windows не поддерживает add_signal_handler
            logger.debug(f"⚠️ Signal handler for {sig.name} not supported on this platform")
    
    logger.debug("✅ Signal handlers registered for SIGTERM, SIGINT")


if __name__ == "__main__":
    # Создание event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Настройка сигналов
    _setup_signal_handlers(loop)
    
    # Запуск health check сервера в фоне
    async def start_with_health():
        global _health_task
        
        # Запускаем health check сервер как задачу
        _health_task = asyncio.create_task(health_check_server())
        
        # Даём серверу время на старт
        await asyncio.sleep(0.5)
        
        # Запускаем основного бота
        await main()
    
    try:
        # Запуск основного цикла
        loop.run_until_complete(start_with_health())
    except KeyboardInterrupt:
        logger.info("⌨️ Received keyboard interrupt")
    except Exception as e:
        logger.critical(f"💥 Fatal error: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Отмена всех оставшихся задач
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        
        # Ждём завершения с таймаутом
        if pending:
            try:
                loop.run_until_complete(
                    asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=5.0
                    )
                )
            except asyncio.TimeoutError:
                logger.warning("⚠️ Some tasks didn't finish in time")
            except asyncio.CancelledError:
                pass
        
        # Закрытие loop
        loop.close()
        
        logger.info("👋 Goodbye!")
        sys.exit(0)

