"""
Rate limiter для игр и команд
Поддерживает Redis (если настроен) и in-memory режим
"""

import asyncio
import time
from typing import Dict, Optional, Callable, Any
from functools import wraps
from collections import defaultdict

from config import REDIS_URL, RATE_LIMIT_GAMES
from utils.logger import logger

# In-memory storage для rate limiting
_in_memory_storage: Dict[str, list] = defaultdict(list)

# Redis client (если доступен)
_redis_client = None

try:
    if REDIS_URL:
        import redis.asyncio as redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("✅ Redis connected for rate limiting")
    else:
        logger.info("🔄 Using in-memory rate limiting")
except Exception as e:
    logger.warning(f"⚠️ Redis not available, using in-memory: {e}")


class RateLimiter:
    """Rate limiter для команд"""
    
    def __init__(self, limit: int = 30, period: int = 60):
        """
        Args:
            limit: максимальное количество запросов
            period: период времени в секундах
        """
        self.limit = limit
        self.period = period
    
    async def check(self, key: str) -> tuple[bool, int]:
        """
        Проверить, не превышен ли лимит
        
        Returns:
            (is_allowed, seconds_to_wait)
        """
        if _redis_client:
            return await self._check_redis(key)
        else:
            return self._check_memory(key)
    
    async def _check_redis(self, key: str) -> tuple[bool, int]:
        """Redis-based rate limiting"""
        try:
            now = time.time()
            window_start = now - self.period
            
            # Remove old entries
            await _redis_client.zremrangebyscore(key, 0, window_start)
            
            # Count requests in current window
            count = await _redis_client.zcard(key)
            
            if count >= self.limit:
                # Get oldest timestamp to calculate wait time
                oldest = await _redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    wait_time = int(self.period - (now - oldest[0][1]))
                    return False, max(1, wait_time)
                return False, 1
            
            # Add current request
            await _redis_client.zadd(key, {str(now): now})
            await _redis_client.expire(key, self.period)
            
            return True, 0
            
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            # Fallback to in-memory
            return self._check_memory(key)
    
    def _check_memory(self, key: str) -> tuple[bool, int]:
        """In-memory rate limiting"""
        now = time.time()
        window_start = now - self.period
        
        # Clean old entries
        _in_memory_storage[key] = [
            ts for ts in _in_memory_storage[key] 
            if ts > window_start
        ]
        
        if len(_in_memory_storage[key]) >= self.limit:
            oldest = min(_in_memory_storage[key])
            wait_time = int(self.period - (now - oldest))
            return False, max(1, wait_time)
        
        _in_memory_storage[key].append(now)
        return True, 0


# Глобальные лимитеры для разных типов команд
_command_limiters: Dict[str, RateLimiter] = {}


def get_limiter(command: str, limit: int = None) -> RateLimiter:
    """Получить или создать лимитер для команды"""
    limit = limit or RATE_LIMIT_GAMES
    key = f"{command}:{limit}"
    
    if key not in _command_limiters:
        _command_limiters[key] = RateLimiter(limit=limit, period=60)
    
    return _command_limiters[key]


def rate_limit(limit: int = None, key: str = None, period: int = 60):
    """
    Декоратор для ограничения частоты вызовов команд
    
    Args:
        limit: максимальное количество вызовов за период
        key: ключ для лимитера (если None, используется имя функции)
        period: период времени в секундах (по умолчанию 60)
    
    Usage:
        @rate_limit(limit=30, key="slot")
        async def cmd_slot(message: Message):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(message, *args, **kwargs):
            # Определяем ключ для лимитера
            user_id = message.from_user.id
            limiter_key = f"{key or func.__name__}:{user_id}"
            
            # Создаем лимитер
            limiter = RateLimiter(limit=limit or RATE_LIMIT_GAMES, period=period)
            
            # Проверяем лимит
            is_allowed, wait_time = await limiter.check(limiter_key)
            
            if not is_allowed:
                # Превышен лимит
                await message.answer(
                    f"⚠️ *Превышен лимит команд!*\n\n"
                    f"Вы можете использовать эту команду не более {limit or RATE_LIMIT_GAMES} раз в минуту.\n"
                    f"Подождите *{wait_time} секунд* перед следующим вызовом.\n\n"
                    f"🎮 Попробуйте другие игры: /slot, /duel, /roulette, /rps",
                    parse_mode="Markdown"
                )
                return
            
            # Вызываем оригинальную функцию
            return await func(message, *args, **kwargs)
        
        return wrapper
    return decorator


class GameRateLimiter:
    """Класс для лимитирования игр с разными параметрами"""
    
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
    
    async def check(self, user_id: int, game_type: str, limit: int = None) -> tuple[bool, int]:
        """Проверить лимит для конкретной игры"""
        limit = limit or RATE_LIMIT_GAMES
        key = f"game:{game_type}:{user_id}"
        
        if key not in self._limiters:
            self._limiters[key] = RateLimiter(limit=limit, period=60)
        
        return await self._limiters[key].check(key)
    
    async def reset(self, user_id: int, game_type: str):
        """Сбросить лимиты для пользователя (административная функция)"""
        key = f"game:{game_type}:{user_id}"
        
        if _redis_client:
            await _redis_client.delete(key)
        else:
            if key in _in_memory_storage:
                del _in_memory_storage[key]
        
        if key in self._limiters:
            del self._limiters[key]


# Глобальный экземпляр
game_rate_limiter = GameRateLimiter()


async def check_game_limit(user_id: int, game_type: str, limit: int = None) -> tuple[bool, int]:
    """Удобная функция для проверки лимита игр"""
    return await game_rate_limiter.check(user_id, game_type, limit)


async def reset_game_limit(user_id: int, game_type: str):
    """Сбросить лимит игр для пользователя"""
    await game_rate_limiter.reset(user_id, game_type)


# ========== Admin functions ==========

async def get_user_limits(user_id: int) -> Dict[str, int]:
    """Получить текущие лимиты пользователя (admin)"""
    limits = {}
    game_types = ["slot", "duel", "roulette", "rps"]
    
    for game_type in game_types:
        key = f"game:{game_type}:{user_id}"
        
        if _redis_client:
            count = await _redis_client.zcard(key)
            limits[game_type] = count
        else:
            limits[game_type] = len(_in_memory_storage.get(key, []))
    
    return limits


async def clear_user_limits(user_id: int):
    """Очистить все лимиты пользователя (admin)"""
    game_types = ["slot", "duel", "roulette", "rps"]
    
    for game_type in game_types:
        await reset_game_limit(user_id, game_type)
    
    logger.info(f"Cleared all limits for user {user_id}")
