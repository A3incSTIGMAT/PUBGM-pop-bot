#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: utils/rate_limiter.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Rate limiting для команд с защитой от memory leak
# ============================================

import asyncio
import time
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Any
from functools import wraps

from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode

# ==================== КОНСТАНТЫ ====================

CLEANUP_INTERVAL = 300  # Очистка каждые 5 минут
MAX_ENTRIES_PER_KEY = 1000  # Максимум записей на ключ

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

_rate_limits: Dict[str, List[float]] = defaultdict(list)
_cleanup_task: Optional[asyncio.Task] = None
_lock = asyncio.Lock()


# ==================== ФОНОВАЯ ОЧИСТКА ====================

async def _cleanup_expired_entries() -> None:
    """Периодическая очистка устаревших записей."""
    global _rate_limits
    
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        
        async with _lock:
            now = time.time()
            keys_to_delete = []
            
            for key, timestamps in _rate_limits.items():
                # Очищаем старые записи
                cleaned = [t for t in timestamps if now - t < 3600]  # Храним максимум час
                
                if not cleaned:
                    keys_to_delete.append(key)
                else:
                    _rate_limits[key] = cleaned
            
            for key in keys_to_delete:
                del _rate_limits[key]


def start_cleanup_task() -> None:
    """Запускает фоновую очистку (вызвать при старте бота)."""
    global _cleanup_task
    if _cleanup_task is None:
        _cleanup_task = asyncio.create_task(_cleanup_expired_entries())


async def stop_cleanup_task() -> None:
    """Останавливает фоновую очистку (вызвать при остановке)."""
    global _cleanup_task
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None


# ==================== ДЕКОРАТОР ====================

def rate_limit(
    limit: int = 5,
    period: int = 60,
    key: Optional[str] = None,
    silent: bool = False
) -> Callable:
    """
    Декоратор для ограничения частоты вызовов.
    
    Args:
        limit: Максимальное количество вызовов
        period: Период в секундах
        key: Ключ для группировки (по умолчанию имя функции + user_id)
        silent: Если True, не отправлять сообщение о лимите
    
    Example:
        @rate_limit(limit=3, period=60)  # 3 раза в минуту
        async def cmd_daily(message: Message):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: Message | CallbackQuery, *args: Any, **kwargs: Any) -> Any:
            # Определяем user_id
            if isinstance(event, Message):
                if event.from_user is None:
                    return await func(event, *args, **kwargs)
                user_id = event.from_user.id
            elif isinstance(event, CallbackQuery):
                if event.from_user is None:
                    return await func(event, *args, **kwargs)
                user_id = event.from_user.id
            else:
                return await func(event, *args, **kwargs)
            
            # Формируем ключ
            limiter_key = f"{key or func.__name__}:{user_id}"
            now = time.time()
            
            async with _lock:
                # Очищаем старые записи
                _rate_limits[limiter_key] = [
                    t for t in _rate_limits[limiter_key] 
                    if t > now - period
                ]
                
                # Проверяем лимит
                if len(_rate_limits[limiter_key]) >= limit:
                    if not silent:
                        wait_time = int(period - (now - _rate_limits[limiter_key][0]))
                        wait_text = _format_wait_time(wait_time)
                        
                        if isinstance(event, Message):
                            await event.answer(
                                f"⏰ <b>Лимит запросов!</b>\n\n"
                                f"Подождите <b>{wait_text}</b> перед следующим использованием.",
                                parse_mode=ParseMode.HTML
                            )
                        elif isinstance(event, CallbackQuery):
                            await event.answer(
                                f"⏰ Подождите {wait_text}",
                                show_alert=True
                            )
                    return None
                
                # Добавляем запись
                _rate_limits[limiter_key].append(now)
                
                # Ограничиваем размер списка
                if len(_rate_limits[limiter_key]) > MAX_ENTRIES_PER_KEY:
                    _rate_limits[limiter_key] = _rate_limits[limiter_key][-MAX_ENTRIES_PER_KEY:]
            
            return await func(event, *args, **kwargs)
        
        return wrapper
    return decorator


# ==================== КЛАСС ДЛЯ РУЧНОГО УПРАВЛЕНИЯ ====================

class RateLimiter:
    """
    Класс для ручного управления rate limiting.
    Используется когда декоратор не подходит.
    """
    
    def __init__(self, limit: int = 5, period: int = 60):
        self.limit = limit
        self.period = period
        self._storage: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check(self, key: str) -> tuple[bool, int]:
        """
        Проверяет, можно ли выполнить действие.
        
        Args:
            key: Ключ для проверки
            
        Returns:
            (разрешено, время_ожидания_в_секундах)
        """
        async with self._lock:
            now = time.time()
            
            # Очистка старых записей
            self._storage[key] = [
                t for t in self._storage[key] 
                if t > now - self.period
            ]
            
            if len(self._storage[key]) >= self.limit:
                wait_time = int(self.period - (now - self._storage[key][0]))
                return False, max(0, wait_time)
            
            self._storage[key].append(now)
            return True, 0
    
    async def reset(self, key: str) -> None:
        """Сбросить лимит для ключа."""
        async with self._lock:
            self._storage.pop(key, None)
    
    async def get_remaining(self, key: str) -> int:
        """Получить оставшееся количество запросов."""
        async with self._lock:
            now = time.time()
            self._storage[key] = [
                t for t in self._storage[key] 
                if t > now - self.period
            ]
            return max(0, self.limit - len(self._storage[key]))


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def _format_wait_time(seconds: int) -> str:
    """Форматирует время ожидания."""
    if seconds <= 0:
        return "1 сек"
    if seconds < 60:
        return f"{seconds} сек"
    minutes = seconds // 60
    secs = seconds % 60
    if secs == 0:
        return f"{minutes} мин"
    return f"{minutes} мин {secs} сек"


# ==================== ПРЕДУСТАНОВЛЕННЫЕ ЛИМИТЕРЫ ====================

# Для часто используемых команд
daily_limiter = RateLimiter(limit=1, period=10)  # /daily — раз в 10 сек
transfer_limiter = RateLimiter(limit=5, period=60)  # /transfer — 5 раз в минуту
game_limiter = RateLimiter(limit=10, period=60)  # Игры — 10 раз в минуту
