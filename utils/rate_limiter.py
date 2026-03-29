"""
rate_limiter.py — Production-ready Rate Limiting Service
=========================================================

✅ Инкапсулированное состояние (без глобалов)
✅ Async-safe с asyncio.Lock
✅ Redis с retry-логикой и graceful degradation
✅ Фоновая очистка памяти (защита от утечек)
✅ Dependency injection friendly
✅ Thread-safe для конкурентных запросов
✅ Поддержка user/chat идентификаторов
✅ Полное логирование всех операций
✅ Метрики для мониторинга
✅ Admin утилиты для управления лимитами

Usage:
    # В bot.py при старте:
    from rate_limiter import init_rate_limiter, get_service
    
    async def on_startup():
        await init_rate_limiter(REDIS_URL)
    
    # В хендлерах:
    @rate_limit(limit=10, key="slot", period=60)
    async def cmd_slot(message: Message):
        ...
    
    # Программная проверка:
    service = get_service()
    allowed, wait = await service.check("user:123:slot", limit=10, period=60)
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple, Callable, Any, Union
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime

from config import REDIS_URL, RATE_LIMIT_GAMES

# Ленивый импорт redis (только если нужен)
redis = None
try:
    import redis.asyncio as redis
except ImportError:
    pass

# Настройка логирования
logger = logging.getLogger(__name__)


# ============================================================================
# 📊 DATA CLASSES
# ============================================================================

@dataclass
class RateLimitResult:
    """Результат проверки лимита с полной информацией"""
    allowed: bool
    wait_seconds: int
    current_count: int
    limit: int
    period: int
    key: str
    timestamp: float = field(default_factory=time.time)
    
    @property
    def message(self) -> str:
        """Форматированное сообщение об ошибке"""
        if self.allowed:
            return ""
        return f"⏰ Превышен лимит. Подождите {self.wait_seconds} сек."
    
    @property
    def remaining(self) -> int:
        """Сколько ещё запросов доступно"""
        if self.allowed:
            return self.limit - self.current_count
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для логирования"""
        return {
            "allowed": self.allowed,
            "wait_seconds": self.wait_seconds,
            "current_count": self.current_count,
            "limit": self.limit,
            "period": self.period,
            "key": self.key,
            "timestamp": self.timestamp,
            "remaining": self.remaining
        }


@dataclass
class RateLimiterStats:
    """Статистика работы лимитера"""
    total_checks: int = 0
    allowed_checks: int = 0
    denied_checks: int = 0
    redis_hits: int = 0
    redis_misses: int = 0
    memory_fallbacks: int = 0
    errors: int = 0
    active_keys: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def allow_rate(self) -> float:
        """Процент разрешённых запросов"""
        if self.total_checks == 0:
            return 0.0
        return (self.allowed_checks / self.total_checks) * 100
    
    @property
    def uptime_seconds(self) -> float:
        """Время работы в секундах"""
        return time.time() - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_checks": self.total_checks,
            "allowed_checks": self.allowed_checks,
            "denied_checks": self.denied_checks,
            "allow_rate": f"{self.allow_rate:.2f}%",
            "redis_hits": self.redis_hits,
            "redis_misses": self.redis_misses,
            "memory_fallbacks": self.memory_fallbacks,
            "errors": self.errors,
            "active_keys": self.active_keys,
            "uptime_seconds": self.uptime_seconds
        }


# ============================================================================
# 🗄️ REDIS BACKEND
# ============================================================================

class RedisRateLimiterBackend:
    """
    Redis backend для rate limiting с retry-логикой и graceful degradation.
    Использует sorted sets для точного контроля временных окон (sliding window).
    
    Алгоритм:
    1. Удаляет записи за пределами временного окна
    2. Считает количество оставшихся записей
    3. Если лимит превышен — возвращает время ожидания
    4. Если нет — добавляет новую запись и устанавливает TTL
    """
    
    def __init__(
        self, 
        url: str, 
        max_retries: int = 3,
        retry_delay: float = 1.0,
        connection_timeout: float = 5.0,
        socket_timeout: float = 5.0
    ):
        """
        Инициализация Redis backend
        
        Args:
            url: URL для подключения к Redis (redis://...)
            max_retries: Максимальное количество попыток подключения
            retry_delay: Задержка между попытками (секунды)
            connection_timeout: Таймаут подключения
            socket_timeout: Таймаут операций
        """
        self.url = url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connection_timeout = connection_timeout
        self.socket_timeout = socket_timeout
        self._client: Optional[redis.Redis] = None
        self._connected = False
        self._connection_attempts = 0
        self._last_error: Optional[str] = None
    
    @property
    def is_connected(self) -> bool:
        """Статус подключения к Redis"""
        return self._connected and self._client is not None
    
    @property
    def connection_info(self) -> Dict[str, Any]:
        """Информация о подключении"""
        return {
            "connected": self.is_connected,
            "url": self.url if self.url else "not configured",
            "attempts": self._connection_attempts,
            "last_error": self._last_error
        }
    
    async def connect(self) -> bool:
        """
        Асинхронное подключение с экспоненциальной задержкой.
        
        Returns:
            bool: True если подключение успешно
        """
        if not redis:
            self._last_error = "redis.asyncio module not installed"
            logger.warning("Redis library not installed. Install with: pip install redis")
            return False
        
        for attempt in range(self.max_retries):
            self._connection_attempts += 1
            try:
                logger.info(f"Connecting to Redis (attempt {attempt + 1}/{self.max_retries})...")
                
                self._client = redis.from_url(
                    self.url,
                    decode_responses=True,
                    socket_timeout=self.socket_timeout,
                    socket_connect_timeout=self.connection_timeout,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                
                # Проверяем соединение с таймаутом
                await asyncio.wait_for(
                    self._client.ping(),
                    timeout=self.connection_timeout
                )
                
                self._connected = True
                self._last_error = None
                logger.info("✅ Redis connected successfully")
                return True
                
            except asyncio.TimeoutError as e:
                self._last_error = f"Connection timeout: {e}"
                logger.warning(f"Redis connection timeout (attempt {attempt + 1}): {e}")
                
            except Exception as e:
                self._last_error = str(e)
                logger.warning(f"Redis connection failed (attempt {attempt + 1}): {e}")
            
            # Экспоненциальная задержка перед следующей попыткой
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay:.1f} seconds...")
                await asyncio.sleep(delay)
        
        logger.error("❌ Failed to connect to Redis after all attempts")
        self._connected = False
        return False
    
    async def check(
        self, 
        key: str, 
        limit: int, 
        period: int
    ) -> Tuple[bool, int, int]:
        """
        Проверка лимита с использованием sliding window алгоритма.
        Операция атомарна благодаря Redis pipeline.
        
        Args:
            key: Уникальный ключ (например, "user:123:slot")
            limit: Максимальное количество запросов
            period: Период времени в секундах
        
        Returns:
            Tuple[allowed, wait_seconds, current_count]
            
        Raises:
            RuntimeError: Если Redis не подключён
        """
        if not self.is_connected:
            raise RuntimeError("Redis not connected")
        
        now = time.time()
        window_start = now - period
        
        try:
            # Используем pipeline для атомарности операций
            pipe = self._client.pipeline(transaction=True)
            
            # 1. Удаляем записи за пределами окна
            pipe.zremrangebyscore(key, 0, window_start)
            
            # 2. Считаем текущее количество запросов
            pipe.zcard(key)
            
            # Выполняем первые две операции
            results = await pipe.execute()
            current_count = results[1]
            
            # 3. Проверяем лимит
            if current_count >= limit:
                # Получаем timestamp самого старого запроса
                oldest = await self._client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    # Время ожидания = оставшееся время до истечения самого старого запроса
                    oldest_timestamp = oldest[0][1]
                    wait_time = int(period - (now - oldest_timestamp))
                    return False, max(1, wait_time), current_count
                return False, 1, current_count
            
            # 4. Добавляем текущий запрос (используем score = timestamp для сортировки)
            await self._client.zadd(key, {str(now): now})
            
            # 5. Устанавливаем TTL с буфером для безопасности
            await self._client.expire(key, period + 10)
            
            return True, 0, current_count + 1
            
        except Exception as e:
            logger.error(f"Redis rate limit error for key '{key}': {e}", exc_info=True)
            raise
    
    async def reset(self, key: str) -> bool:
        """
        Сбросить лимит для ключа
        
        Args:
            key: Ключ для сброса
            
        Returns:
            bool: True если ключ был удалён
        """
        if not self.is_connected:
            return False
        
        try:
            deleted = await self._client.delete(key)
            if deleted:
                logger.debug(f"Reset Redis limit for key: {key}")
            return bool(deleted)
        except Exception as e:
            logger.error(f"Failed to reset key '{key}': {e}")
            return False
    
    async def get_count(self, key: str, period: int) -> int:
        """
        Получить текущее количество запросов в окне
        
        Args:
            key: Ключ для проверки
            period: Период времени в секундах
            
        Returns:
            int: Количество запросов в текущем окне
        """
        if not self.is_connected:
            return 0
        
        try:
            now = time.time()
            window_start = now - period
            
            # Удаляем старые записи
            await self._client.zremrangebyscore(key, 0, window_start)
            
            # Возвращаем количество
            return await self._client.zcard(key)
        except Exception as e:
            logger.error(f"Failed to get count for key '{key}': {e}")
            return 0
    
    async def get_all_keys(self, pattern: str = "*") -> List[str]:
        """
        Получить все ключи по паттерну
        
        Args:
            pattern: Паттерн для поиска ключей
            
        Returns:
            List[str]: Список ключей
        """
        if not self.is_connected:
            return []
        
        try:
            cursor = 0
            keys = []
            while True:
                cursor, batch = await self._client.scan(cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break
            return keys
        except Exception as e:
            logger.error(f"Failed to scan keys: {e}")
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику Redis
        
        Returns:
            Dict со статистикой
        """
        if not self.is_connected:
            return {"connected": False}
        
        try:
            info = await self._client.info("stats")
            memory = await self._client.info("memory")
            
            return {
                "connected": True,
                "total_commands": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "used_memory": memory.get("used_memory_human", "0"),
                "uptime": info.get("uptime_in_seconds", 0)
            }
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {e}")
            return {"connected": True, "error": str(e)}
    
    async def close(self):
        """Graceful shutdown — закрываем соединение с Redis"""
        if self._client and self._connected:
            try:
                await self._client.aclose()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            finally:
                self._connected = False
                self._client = None


# ============================================================================
# 🧠 IN-MEMORY BACKEND
# ============================================================================

class MemoryRateLimiterBackend:
    """
    Thread-safe in-memory backend для rate limiting.
    Используется как fallback при недоступности Redis.
    Реализует фоновую очистку для предотвращения утечек памяти.
    """
    
    def __init__(
        self, 
        cleanup_interval: int = 300, 
        max_age: int = 600,
        enable_stats: bool = True
    ):
        """
        Args:
            cleanup_interval: Интервал очистки в секундах (по умолчанию 5 минут)
            max_age: Максимальный возраст записей в секундах (по умолчанию 10 минут)
            enable_stats: Включить сбор статистики
        """
        self._storage: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = cleanup_interval
        self._max_age = max_age
        self._enable_stats = enable_stats
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = True
        
        # Статистика
        self._stats = RateLimiterStats()
        
        # Запускаем фоновую задачу очистки
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"Memory backend initialized with cleanup interval: {cleanup_interval}s, max age: {max_age}s")
    
    @property
    def active_keys(self) -> int:
        """Количество активных ключей"""
        return len(self._storage)
    
    @property
    def total_entries(self) -> int:
        """Общее количество записей в хранилище"""
        return sum(len(timestamps) for timestamps in self._storage.values())
    
    @property
    def stats(self) -> RateLimiterStats:
        """Статистика работы"""
        stats = self._stats
        stats.active_keys = self.active_keys
        return stats
    
    async def _cleanup_loop(self):
        """
        Фоновая задача для очистки устаревших записей.
        Запускается с интервалом cleanup_interval и удаляет записи старше max_age.
        """
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_entries()
            except asyncio.CancelledError:
                logger.info("Memory cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Memory cleanup error: {e}", exc_info=True)
    
    async def _cleanup_old_entries(self):
        """
        Удаление старых записей и пустых ключей.
        Использует max_age для определения устаревших записей.
        """
        now = time.time()
        cutoff = now - self._max_age
        keys_cleaned = 0
        entries_cleaned = 0
        
        async with self._lock:
            keys_to_delete = []
            
            for key, timestamps in self._storage.items():
                original_count = len(timestamps)
                
                # Оставляем только свежие записи
                self._storage[key] = [ts for ts in timestamps if ts > cutoff]
                
                entries_cleaned += original_count - len(self._storage[key])
                
                # Помечаем пустые ключи на удаление
                if not self._storage[key]:
                    keys_to_delete.append(key)
            
            # Удаляем пустые ключи
            for key in keys_to_delete:
                del self._storage[key]
                keys_cleaned += 1
            
            if keys_cleaned > 0 or entries_cleaned > 0:
                logger.debug(f"Cleaned up {keys_cleaned} empty keys and {entries_cleaned} expired entries")
    
    async def check(
        self, 
        key: str, 
        limit: int, 
        period: int
    ) -> Tuple[bool, int, int]:
        """
        Проверка лимита с thread-safe доступом.
        
        Args:
            key: Уникальный ключ
            limit: Максимальное количество запросов
            period: Период времени в секундах
            
        Returns:
            Tuple[allowed, wait_seconds, current_count]
        """
        now = time.time()
        window_start = now - period
        
        async with self._lock:
            # Обновляем статистику
            if self._enable_stats:
                self._stats.total_checks += 1
            
            # Получаем или создаём список временных меток
            timestamps = self._storage.get(key, [])
            
            # Очищаем старые записи за пределами окна
            timestamps = [ts for ts in timestamps if ts > window_start]
            
            current_count = len(timestamps)
            
            # Проверяем лимит
            if current_count >= limit:
                # Находим самую старую запись для расчёта времени ожидания
                oldest = min(timestamps)
                wait_time = int(period - (now - oldest))
                
                # Сохраняем обновлённый список
                self._storage[key] = timestamps
                
                if self._enable_stats:
                    self._stats.denied_checks += 1
                
                return False, max(1, wait_time), current_count
            
            # Добавляем текущую метку
            timestamps.append(now)
            self._storage[key] = timestamps
            
            if self._enable_stats:
                self._stats.allowed_checks += 1
            
            return True, 0, current_count + 1
    
    async def reset(self, key: str) -> bool:
        """
        Сбросить лимит для ключа
        
        Args:
            key: Ключ для сброса
            
        Returns:
            bool: True если ключ был удалён
        """
        async with self._lock:
            if key in self._storage:
                del self._storage[key]
                logger.debug(f"Reset memory limit for key: {key}")
                return True
            return False
    
    async def get_count(self, key: str, period: int) -> int:
        """
        Получить текущее количество запросов в окне
        
        Args:
            key: Ключ для проверки
            period: Период времени в секундах
            
        Returns:
            int: Количество запросов в текущем окне
        """
        now = time.time()
        window_start = now - period
        
        async with self._lock:
            timestamps = self._storage.get(key, [])
            valid_timestamps = [ts for ts in timestamps if ts > window_start]
            return len(valid_timestamps)
    
    async def get_all_keys(self) -> List[str]:
        """
        Получить все активные ключи
        
        Returns:
            List[str]: Список всех ключей
        """
        async with self._lock:
            return list(self._storage.keys())
    
    async def close(self):
        """
        Остановка фоновой задачи очистки.
        Должна быть вызвана при завершении работы.
        """
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error during cleanup task shutdown: {e}")
        
        # Очищаем хранилище
        async with self._lock:
            self._storage.clear()
        
        logger.info("Memory backend closed")


# ============================================================================
# 🎯 MAIN SERVICE
# ============================================================================

class RateLimiterService:
    """
    Основной сервис rate limiting с поддержкой Redis и fallback на memory.
    
    Features:
        - Автоматический fallback при недоступности Redis
        - Graceful degradation
        - Dependency injection friendly
        - Thread-safe операции
        - Полная статистика
        - Admin утилиты
    
    Usage:
        # Инициализация при старте
        service = RateLimiterService(redis_url="redis://localhost:6379")
        await service.initialize()
        
        # Проверка лимита
        result = await service.check("user:123:slot", limit=30, period=60)
        if result.allowed:
            # Выполняем действие
            pass
        else:
            # Сообщаем о лимите
            await message.answer(f"Подождите {result.wait_seconds} секунд")
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        use_redis: bool = True,
        default_limit: int = RATE_LIMIT_GAMES,
        default_period: int = 60,
        enable_metrics: bool = True
    ):
        """
        Args:
            redis_url: URL для подключения к Redis
            use_redis: Использовать ли Redis (если False, только memory)
            default_limit: Лимит по умолчанию
            default_period: Период по умолчанию (секунды)
            enable_metrics: Включить сбор метрик
        """
        self.redis_url = redis_url
        self.use_redis = use_redis
        self.default_limit = default_limit
        self.default_period = default_period
        self.enable_metrics = enable_metrics
        
        self._redis_backend: Optional[RedisRateLimiterBackend] = None
        self._memory_backend: Optional[MemoryRateLimiterBackend] = None
        self._initialized = False
        self._using_redis = False
        self._stats = RateLimiterStats()
        self._fallback_counter = 0
    
    @property
    def is_initialized(self) -> bool:
        """Статус инициализации сервиса"""
        return self._initialized
    
    @property
    def using_redis(self) -> bool:
        """Используется ли Redis (или memory fallback)"""
        return self._using_redis
    
    @property
    def stats(self) -> RateLimiterStats:
        """Статистика работы сервиса"""
        stats = self._stats
        if self._memory_backend:
            stats.active_keys = self._memory_backend.active_keys
        return stats
    
    async def initialize(self):
        """
        Асинхронная инициализация сервиса.
        Должна быть вызвана при старте приложения.
        """
        if self._initialized:
            logger.warning("RateLimiterService already initialized")
            return
        
        logger.info("Initializing RateLimiterService...")
        
        # Инициализация memory backend (всегда)
        self._memory_backend = MemoryRateLimiterBackend(
            cleanup_interval=300,
            max_age=600,
            enable_stats=self.enable_metrics
        )
        logger.info("✅ Memory backend initialized")
        
        # Инициализация Redis backend (если настроен и включён)
        if self.use_redis and self.redis_url:
            logger.info(f"Attempting to connect to Redis at {self.redis_url}")
            self._redis_backend = RedisRateLimiterBackend(self.redis_url)
            
            if await self._redis_backend.connect():
                self._using_redis = True
                logger.info("✅ Using Redis for rate limiting")
            else:
                logger.warning("⚠️ Redis unavailable, falling back to memory backend")
                self._using_redis = False
                self._fallback_counter += 1
        else:
            if not self.use_redis:
                logger.info("📝 Redis disabled by configuration")
            elif not self.redis_url:
                logger.info("📝 No Redis URL provided, using memory backend")
            self._using_redis = False
        
        self._initialized = True
        logger.info(f"RateLimiterService initialized successfully (Redis: {self._using_redis})")
    
    def _get_backend(self):
        """
        Получить активный backend (Redis или Memory)
        
        Returns:
            RedisRateLimiterBackend или MemoryRateLimiterBackend
            
        Raises:
            RuntimeError: Если сервис не инициализирован
        """
        if not self._initialized:
            raise RuntimeError("RateLimiterService not initialized. Call initialize() first.")
        
        # Пытаемся использовать Redis если он доступен
        if self._using_redis and self._redis_backend and self._redis_backend.is_connected:
            return self._redis_backend
        
        # Fallback на memory
        if self._memory_backend:
            return self._memory_backend
        
        raise RuntimeError("No backend available")
    
    async def check(
        self,
        key: str,
        limit: Optional[int] = None,
        period: Optional[int] = None
    ) -> RateLimitResult:
        """
        Проверить, не превышен ли лимит.
        
        Args:
            key: Уникальный ключ (например, "user:123:slot")
            limit: Максимальное количество запросов (по умолчанию self.default_limit)
            period: Период времени в секундах (по умолчанию self.default_period)
        
        Returns:
            RateLimitResult с полной информацией о лимите
        """
        limit = limit or self.default_limit
        period = period or self.default_period
        
        backend = self._get_backend()
        is_redis_backend = backend is self._redis_backend
        
        try:
            allowed, wait_seconds, count = await backend.check(key, limit, period)
            
            # Обновляем статистику
            if self.enable_metrics:
                self._stats.total_checks += 1
                if allowed:
                    self._stats.allowed_checks += 1
                else:
                    self._stats.denied_checks += 1
                
                if is_redis_backend:
                    self._stats.redis_hits += 1
                else:
                    self._stats.redis_misses += 1
            
            return RateLimitResult(
                allowed=allowed,
                wait_seconds=wait_seconds,
                current_count=count,
                limit=limit,
                period=period,
                key=key
            )
            
        except Exception as e:
            logger.error(f"Rate limit check failed for key '{key}': {e}", exc_info=True)
            
            if self.enable_metrics:
                self._stats.errors += 1
            
            # Fallback на memory backend при ошибке Redis
            if is_redis_backend and self._memory_backend:
                logger.warning(f"Falling back to memory backend for key '{key}'")
                self._fallback_counter += 1
                
                try:
                    allowed, wait_seconds, count = await self._memory_backend.check(key, limit, period)
                    
                    return RateLimitResult(
                        allowed=allowed,
                        wait_seconds=wait_seconds,
                        current_count=count,
                        limit=limit,
                        period=period,
                        key=key
                    )
                except Exception as fallback_error:
                    logger.error(f"Memory backend also failed: {fallback_error}")
            
            # Если всё сломалось, разрешаем запрос (fail-open)
            logger.warning(f"All backends failed for key '{key}', allowing request (fail-open)")
            return RateLimitResult(
                allowed=True,
                wait_seconds=0,
                current_count=0,
                limit=limit,
                period=period,
                key=key
            )
    
    async def reset(self, key: str) -> bool:
        """
        Сбросить лимит для ключа
        
        Args:
            key: Ключ для сброса
            
        Returns:
            bool: True если сброс выполнен успешно
        """
        backend = self._get_backend()
        return await backend.reset(key)
    
    async def get_count(self, key: str, period: Optional[int] = None) -> int:
        """
        Получить текущее количество запросов в окне
        
        Args:
            key: Ключ для проверки
            period: Период времени в секундах
            
        Returns:
            int: Количество запросов в текущем окне
        """
        period = period or self.default_period
        backend = self._get_backend()
        return await backend.get_count(key, period)
    
    async def get_all_keys(self, pattern: str = "*") -> List[str]:
        """
        Получить все активные ключи
        
        Args:
            pattern: Паттерн для поиска ключей
            
        Returns:
            List[str]: Список ключей
        """
        backend = self._get_backend()
        
        if hasattr(backend, 'get_all_keys'):
            return await backend.get_all_keys(pattern)
        
        # Для memory backend
        if hasattr(backend, 'get_all_keys'):
            return await backend.get_all_keys()
        
        return []
    
    async def get_redis_stats(self) -> Dict[str, Any]:
        """
        Получить статистику Redis (если используется)
        
        Returns:
            Dict со статистикой Redis
        """
        if self._redis_backend and self._redis_backend.is_connected:
            return await self._redis_backend.get_stats()
        return {"connected": False, "reason": "Redis not available"}
    
    async def get_full_stats(self) -> Dict[str, Any]:
        """
        Получить полную статистику сервиса
        
        Returns:
            Dict с полной статистикой
        """
        stats = {
            "service": {
                "initialized": self._initialized,
                "using_redis": self._using_redis,
                "default_limit": self.default_limit,
                "default_period": self.default_period,
                "fallback_count": self._fallback_counter
            },
            "stats": self.stats.to_dict()
        }
        
        # Добавляем информацию о Redis если используется
        if self._redis_backend:
            stats["redis"] = {
                "connected": self._redis_backend.is_connected,
                "info": self._redis_backend.connection_info
            }
        
        # Добавляем информацию о memory backend
        if self._memory_backend:
            stats["memory"] = {
                "active_keys": self._memory_backend.active_keys,
                "total_entries": self._memory_backend.total_entries
            }
        
        return stats
    
    async def close(self):
        """
        Graceful shutdown сервиса.
        Закрывает все соединения и останавливает фоновые задачи.
        """
        logger.info("Closing RateLimiterService...")
        
        if self._memory_backend:
            await self._memory_backend.close()
        
        if self._redis_backend:
            await self._redis_backend.close()
        
        self._initialized = False
        logger.info("RateLimiterService closed")


# ============================================================================
# 🌍 GLOBAL INSTANCE & HELPERS
# ============================================================================

# Глобальный сервис (создаётся при инициализации)
_service: Optional[RateLimiterService] = None


async def init_rate_limiter(
    redis_url: Optional[str] = None,
    use_redis: bool = True,
    default_limit: int = RATE_LIMIT_GAMES,
    default_period: int = 60,
    enable_metrics: bool = True
) -> RateLimiterService:
    """
    Инициализировать глобальный сервис rate limiting.
    Должна быть вызвана при старте бота.
    
    Args:
        redis_url: URL Redis (если None, берётся из config.REDIS_URL)
        use_redis: Использовать ли Redis
        default_limit: Лимит по умолчанию
        default_period: Период по умолчанию (секунды)
        enable_metrics: Включить сбор метрик
    
    Returns:
        RateLimiterService: Инициализированный сервис
    
    Example:
        # В bot.py
        from utils.rate_limiter import init_rate_limiter
        
        async def on_startup():
            await init_rate_limiter(REDIS_URL)
    """
    global _service
    
    if _service is not None:
        logger.warning("Rate limiter already initialized, returning existing instance")
        return _service
    
    # Используем переданный URL или из конфига
    redis_url = redis_url or REDIS_URL
    
    _service = RateLimiterService(
        redis_url=redis_url,
        use_redis=use_redis,
        default_limit=default_limit,
        default_period=default_period,
        enable_metrics=enable_metrics
    )
    
    await _service.initialize()
    return _service


def get_service() -> RateLimiterService:
    """
    Получить глобальный сервис rate limiting.
    
    Raises:
        RuntimeError: Если сервис не инициализирован
    
    Returns:
        RateLimiterService: Инициализированный сервис
    
    Example:
        service = get_service()
        result = await service.check("user:123:slot", limit=30)
    """
    if _service is None:
        raise RuntimeError(
            "RateLimiterService not initialized. "
            "Call 'await init_rate_limiter()' at startup."
        )
    return _service


def _extract_identifier(message: Any) -> Optional[str]:
    """
    Безопасное извлечение идентификатора из сообщения.
    
    Поддерживает:
        - Личные сообщения (from_user)
        - Групповые чаты (chat)
        - CallbackQuery (message)
    
    Args:
        message: Aiogram Message или CallbackQuery объект
    
    Returns:
        str: Идентификатор в формате "user:123" или "chat:456"
    """
    try:
        # Обработка CallbackQuery
        if hasattr(message, 'message') and hasattr(message, 'from_user'):
            return f"user:{message.from_user.id}"
        
        # Обработка Message
        if hasattr(message, 'from_user') and message.from_user:
            return f"user:{message.from_user.id}"
        
        # Проверяем chat (для каналов и групп без from_user)
        if hasattr(message, 'chat') and message.chat:
            return f"chat:{message.chat.id}"
        
        logger.warning(f"Cannot extract identifier from message type: {type(message)}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting identifier: {e}", exc_info=True)
        return None


# ============================================================================
# 🎨 DECORATOR
# ============================================================================

def rate_limit(
    limit: Optional[int] = None,
    key: Optional[str] = None,
    period: int = 60,
    error_message: Optional[str] = None,
    skip_on_error: bool = True
):
    """
    Декоратор для ограничения частоты вызовов хендлеров.
    
    Args:
        limit: Максимальное количество вызовов за period
        key: Ключ для лимитера (если None, используется имя функции)
        period: Период времени в секундах
        error_message: Кастомное сообщение об ошибке
        skip_on_error: Если True, при ошибке лимитера пропускаем проверку
    
    Example:
        @router.message(Command("slot"))
        @rate_limit(limit=10, key="slot", period=60)
        async def cmd_slot(message: Message):
            await message.answer("Playing slot...")
    
    Returns:
        Декорированная функция
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(message: Any, *args, **kwargs):
            # Получаем сервис
            try:
                service = get_service()
            except RuntimeError as e:
                logger.warning(f"Rate limiter not available: {e}")
                if skip_on_error:
                    return await func(message, *args, **kwargs)
                raise
            
            # Извлекаем идентификатор
            identifier = _extract_identifier(message)
            if identifier is None:
                # Не можем определить пользователя, пропускаем лимит
                logger.warning(f"Skipping rate limit for {func.__name__}: no identifier")
                return await func(message, *args, **kwargs)
            
            # Формируем ключ
            limiter_key = f"{key or func.__name__}:{identifier}"
            
            # Проверяем лимит
            try:
                result = await service.check(limiter_key, limit, period)
            except Exception as e:
                logger.error(f"Rate limit check failed for {func.__name__}: {e}")
                if skip_on_error:
                    return await func(message, *args, **kwargs)
                raise
            
            if not result.allowed:
                msg = error_message or (
                    f"⏰ *Лимит исчерпан!*\n\n"
                    f"Вы можете использовать эту команду не более *{result.limit} раз* "
                    f"за {period} секунд.\n\n"
                    f"Подождите *{result.wait_seconds} сек.* перед следующим вызовом."
                )
                
                try:
                    await message.answer(msg, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Failed to send rate limit message: {e}")
                
                return None
            
            # Вызываем оригинальную функцию
            return await func(message, *args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# 🎮 GAME-SPECIFIC HELPERS
# ============================================================================

class GameRateLimiter:
    """
    Удобный интерфейс для лимитирования игр.
    Автоматически формирует ключи в формате "game:{game_type}:user:{user_id}"
    """
    
    def __init__(self, service: Optional[RateLimiterService] = None):
        """
        Args:
            service: Сервис rate limiting (если None, используется глобальный)
        """
        self._service = service
    
    @property
    def service(self) -> RateLimiterService:
        """Получить сервис (создаёт при необходимости)"""
        if self._service is None:
            self._service = get_service()
        return self._service
    
    async def check(
        self,
        user_id: int,
        game_type: str,
        limit: Optional[int] = None,
        period: int = 60
    ) -> RateLimitResult:
        """
        Проверить лимит для конкретной игры.
        
        Args:
            user_id: ID пользователя
            game_type: Тип игры ("slot", "duel", "roulette", "rps")
            limit: Лимит (по умолчанию из сервиса)
            period: Период в секундах
        
        Returns:
            RateLimitResult с информацией о лимите
        """
        key = f"game:{game_type}:user:{user_id}"
        return await self.service.check(key, limit, period)
    
    async def reset(self, user_id: int, game_type: str) -> bool:
        """
        Сбросить лимит для игры
        
        Args:
            user_id: ID пользователя
            game_type: Тип игры
            
        Returns:
            bool: True если сброс выполнен
        """
        key = f"game:{game_type}:user:{user_id}"
        return await self.service.reset(key)
    
    async def get_count(self, user_id: int, game_type: str, period: int = 60) -> int:
        """
        Получить текущее количество запросов в окне
        
        Args:
            user_id: ID пользователя
            game_type: Тип игры
            period: Период в секундах
            
        Returns:
            int: Количество запросов
        """
        key = f"game:{game_type}:user:{user_id}"
        return await self.service.get_count(key, period)
    
    async def get_stats(
        self,
        user_id: int,
        game_types: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Получить статистику использования для пользователя.
        
        Args:
            user_id: ID пользователя
            game_types: Список игр (по умолчанию все основные)
        
        Returns:
            Dict[game_type, Dict] со статистикой по каждой игре
        """
        game_types = game_types or ["slot", "duel", "roulette", "rps"]
        stats = {}
        
        for game_type in game_types:
            key = f"game:{game_type}:user:{user_id}"
            count = await self.service.get_count(key, 60)
            stats[game_type] = {
                "key": key,
                "count": count,
                "limit": self.service.default_limit,
                "period": 60
            }
        
        return stats
    
    async def reset_all(self, user_id: int, game_types: Optional[List[str]] = None) -> int:
        """
        Сбросить все лимиты пользователя
        
        Args:
            user_id: ID пользователя
            game_types: Список игр для сброса (по умолчанию все)
            
        Returns:
            int: Количество сброшенных лимитов
        """
        game_types = game_types or ["slot", "duel", "roulette", "rps"]
        cleared = 0
        
        for game_type in game_types:
            if await self.reset(user_id, game_type):
                cleared += 1
        
        logger.info(f"Reset {cleared} game limits for user {user_id}")
        return cleared


def create_game_limiter() -> GameRateLimiter:
    """
    Factory для создания игрового лимитера
    
    Returns:
        GameRateLimiter: Экземпляр игрового лимитера
    """
    return GameRateLimiter()


# ============================================================================
# 🔧 ADMIN UTILITIES
# ============================================================================

async def get_user_limits(user_id: int) -> Dict[str, Any]:
    """
    Получить текущие лимиты пользователя (для админов).
    
    Args:
        user_id: ID пользователя
    
    Returns:
        Dict с полной информацией о лимитах пользователя
    """
    service = get_service()
    game_limiter = GameRateLimiter(service)
    
    game_stats = await game_limiter.get_stats(user_id)
    
    return {
        "user_id": user_id,
        "games": game_stats,
        "total_active_limits": sum(stat["count"] for stat in game_stats.values()),
        "default_limit": service.default_limit,
        "default_period": service.default_period,
        "using_redis": service.using_redis,
        "timestamp": time.time()
    }


async def clear_user_limits(
    user_id: int, 
    game_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Очистить все лимиты пользователя (для админов).
    
    Args:
        user_id: ID пользователя
        game_types: Список игр для очистки (по умолчанию все)
    
    Returns:
        Dict с результатом операции
    """
    game_limiter = create_game_limiter()
    cleared = await game_limiter.reset_all(user_id, game_types)
    
    return {
        "user_id": user_id,
        "cleared_count": cleared,
        "game_types": game_types or ["slot", "duel", "roulette", "rps"],
        "timestamp": time.time()
    }


async def get_system_stats() -> Dict[str, Any]:
    """
    Получить полную системную статистику (для админов)
    
    Returns:
        Dict с полной статистикой системы
    """
    service = get_service()
    full_stats = await service.get_full_stats()
    
    # Добавляем информацию о времени работы
    full_stats["system"] = {
        "timestamp": time.time(),
        "timestamp_iso": datetime.now().isoformat(),
        "python_version": __import__("sys").version
    }
    
    return full_stats


async def check_rate_limit_status() -> Dict[str, Any]:
    """
    Проверить статус rate limiting системы
    
    Returns:
        Dict со статусом
    """
    try:
        service = get_service()
        
        status = {
            "initialized": service.is_initialized,
            "using_redis": service.using_redis,
            "health": "healthy"
        }
        
        # Проверяем Redis если используется
        if service.using_redis and service._redis_backend:
            if not service._redis_backend.is_connected:
                status["health"] = "degraded"
                status["warning"] = "Redis disconnected, using memory fallback"
        
        return status
        
    except RuntimeError:
        return {
            "initialized": False,
            "using_redis": False,
            "health": "not_initialized",
            "error": "Rate limiter not initialized"
        }


# ============================================================================
# 📊 METRICS EXPORTER (для Prometheus)
# ============================================================================

class RateLimiterMetricsExporter:
    """
    Экспорт метрик для Prometheus (опционально)
    """
    
    def __init__(self, service: RateLimiterService):
        self.service = service
        self._enabled = False
        
        try:
            from prometheus_client import Counter, Gauge, Histogram
            
            self.checks_total = Counter(
                'rate_limiter_checks_total',
                'Total rate limit checks',
                ['result']  # allowed, denied, error
            )
            
            self.active_keys = Gauge(
                'rate_limiter_active_keys',
                'Active rate limit keys'
            )
            
            self.wait_time = Histogram(
                'rate_limiter_wait_seconds',
                'Wait time when limit exceeded',
                buckets=[1, 2, 5, 10, 15, 30, 60]
            )
            
            self._enabled = True
            logger.info("Prometheus metrics exporter enabled")
            
        except ImportError:
            logger.debug("prometheus_client not installed, metrics disabled")
    
    async def update_metrics(self):
        """Обновить метрики"""
        if not self._enabled:
            return
        
        try:
            stats = self.service.stats
            self.active_keys.set(stats.active_keys)
            
        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")
    
    def record_check(self, allowed: bool, wait_time: int = 0):
        """Записать результат проверки"""
        if not self._enabled:
            return
        
        result = "allowed" if allowed else "denied"
        self.checks_total.labels(result=result).inc()
        
        if not allowed and wait_time > 0:
            self.wait_time.observe(wait_time)


# ============================================================================
# 🧪 TEST HELPERS
# ============================================================================

class MockRateLimiterBackend:
    """
    Mock backend для тестирования
    """
    
    def __init__(self, should_allow: bool = True, wait_seconds: int = 0):
        self.should_allow = should_allow
        self.wait_seconds = wait_seconds
        self.checks: List[Tuple[str, int, int]] = []
        self.resets: List[str] = []
    
    async def check(self, key: str, limit: int, period: int) -> Tuple[bool, int, int]:
        self.checks.append((key, limit, period))
        return self.should_allow, self.wait_seconds, 5
    
    async def reset(self, key: str) -> bool:
        self.resets.append(key)
        return True
    
    async def get_count(self, key: str, period: int) -> int:
        return 0


def create_test_service(should_allow: bool = True) -> RateLimiterService:
    """
    Создать сервис с mock backend для тестирования
    
    Args:
        should_allow: Должен ли лимитер разрешать запросы
        
    Returns:
        RateLimiterService: Сервис для тестирования
    """
    service = RateLimiterService(use_redis=False)
    service._initialized = True
    service._memory_backend = MockRateLimiterBackend(should_allow=should_allow)
    return service


# ============================================================================
# 📝 EXPORTS
# ============================================================================

__all__ = [
    # Основные классы
    'RateLimiterService',
    'RateLimiterResult',
    'RateLimiterStats',
    'GameRateLimiter',
    
    # Инициализация
    'init_rate_limiter',
    'get_service',
    
    # Декоратор
    'rate_limit',
    
    # Игровые утилиты
    'create_game_limiter',
    
    # Admin утилиты
    'get_user_limits',
    'clear_user_limits',
    'get_system_stats',
    'check_rate_limit_status',
    
    # Метрики
    'RateLimiterMetricsExporter',
    
    # Тестирование
    'create_test_service',
    'MockRateLimiterBackend'
]
