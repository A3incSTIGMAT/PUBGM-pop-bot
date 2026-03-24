"""
Антиспам модуль для NEXUS бота.
Содержит функции для защиты от флуда, спама и нежелательного контента.
"""

import time
import asyncio
import re
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# Хранилища
user_messages: Dict[int, List[float]] = defaultdict(list)
user_commands: Dict[int, Dict[str, float]] = defaultdict(dict)
user_warnings: Dict[int, int] = defaultdict(int)
temp_bans: Dict[int, float] = {}

# Настройки
SPAM_LIMIT = 5
SPAM_WINDOW = 10
WARNINGS_BEFORE_MUTE = 3

COMMAND_RATE_LIMITS = {
    "daily": {"limit": 1, "window": 86400},
    "gift": {"limit": 10, "window": 3600},
    "roulette": {"limit": 20, "window": 3600},
    "rps": {"limit": 30, "window": 3600},
    "duel": {"limit": 10, "window": 3600},
    "balance": {"limit": 60, "window": 3600},
    "stats": {"limit": 60, "window": 3600},
    "top": {"limit": 30, "window": 3600},
    "default": {"limit": 30, "window": 60}
}

# Запрещенные слова для фильтрации (мат)
FORBIDDEN_WORDS = [
    "хуй", "пизда", "бля", "еба", "пидор", "мудак",
    "сука", "залупа", "говно", "долбаеб", "хер", "нах"
]

# ========== ОСНОВНЫЕ ФУНКЦИИ АНТИСПАМА ==========

def is_spam(user_id: int) -> Tuple[bool, int]:
    """
    Проверяет, спамит ли пользователь.
    Возвращает (True/False, количество сообщений за окно)
    """
    now = time.time()
    messages = [t for t in user_messages[user_id] if now - t < SPAM_WINDOW]
    messages.append(now)
    user_messages[user_id] = messages
    return len(messages) > SPAM_LIMIT, len(messages)

def is_rate_limited(user_id: int, command: str) -> Tuple[bool, int]:
    """
    Проверяет rate limiting для команды.
    Возвращает (True/False, секунды до следующего разрешения)
    """
    limits = COMMAND_RATE_LIMITS.get(command, COMMAND_RATE_LIMITS["default"])
    limit = limits["limit"]
    window = limits["window"]
    
    cmd_history = user_commands[user_id]
    last_execution = cmd_history.get(command, 0)
    now = time.time()
    
    if last_execution == 0:
        cmd_history[command] = now
        return False, 0
    
    time_since_last = now - last_execution
    
    if time_since_last < window / limit:
        wait_time = int((window / limit) - time_since_last)
        return True, wait_time
    
    cmd_history[command] = now
    return False, 0

def is_temp_banned(user_id: int) -> Tuple[bool, int]:
    """
    Проверяет временный бан.
    Возвращает (True/False, секунды до разбана)
    """
    if user_id not in temp_bans:
        return False, 0
    
    ban_until = temp_bans[user_id]
    now = time.time()
    
    if now > ban_until:
        del temp_bans[user_id]
        return False, 0
    
    return True, int(ban_until - now)

def add_temp_ban(user_id: int, duration_seconds: int = 300):
    """Добавляет временный бан"""
    temp_bans[user_id] = time.time() + duration_seconds

def add_warning(user_id: int, reason: str = "спам") -> int:
    """Добавляет предупреждение"""
    user_warnings[user_id] += 1
    return user_warnings[user_id]

def reset_warnings(user_id: int):
    """Сбрасывает предупреждения"""
    if user_id in user_warnings:
        del user_warnings[user_id]

def get_warnings(user_id: int) -> int:
    """Получает количество предупреждений"""
    return user_warnings.get(user_id, 0)

def should_mute(user_id: int) -> bool:
    """Проверяет, нужно ли замутить пользователя"""
    return user_warnings.get(user_id, 0) >= WARNINGS_BEFORE_MUTE

# ========== ФИЛЬТРАЦИЯ КОНТЕНТА ==========

def contains_forbidden_words(text: str, forbidden_words: List[str] = None) -> bool:
    """
    Проверяет, содержит ли текст запрещенные слова.
    """
    if forbidden_words is None:
        forbidden_words = FORBIDDEN_WORDS
    
    if not forbidden_words:
        return False
    
    text_lower = text.lower()
    for word in forbidden_words:
        if word in text_lower:
            return True
    return False

def contains_links(text: str) -> bool:
    """
    Проверяет, содержит ли текст ссылки.
    """
    url_pattern = r'https?://\S+|www\.\S+|t\.me/\S+'
    return bool(re.search(url_pattern, text))

def contains_phone(text: str) -> bool:
    """
    Проверяет, содержит ли текст номер телефона.
    """
    phone_pattern = r'\+?\d[\d\-\(\)\s]{8,}\d'
    return bool(re.search(phone_pattern, text))

def contains_email(text: str) -> bool:
    """
    Проверяет, содержит ли текст email.
    """
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return bool(re.search(email_pattern, text))

def censor_text(text: str, forbidden_words: List[str] = None) -> str:
    """
    Заменяет запрещенные слова звездочками.
    """
    if forbidden_words is None:
        forbidden_words = FORBIDDEN_WORDS
    
    result = text
    for word in forbidden_words:
        result = re.sub(rf'\b{word}\b', '*' * len(word), result, flags=re.IGNORECASE)
    return result

# ========== СТАТИСТИКА ==========

def get_spam_stats() -> Dict[str, int]:
    """Получает статистику антиспама"""
    return {
        "active_users": len(user_messages),
        "warned_users": len(user_warnings),
        "temp_banned": len(temp_bans),
        "total_warnings": sum(user_warnings.values())
    }

def get_rate_limit_info(user_id: int, command: str) -> Dict[str, any]:
    """Информация о rate limiting"""
    limits = COMMAND_RATE_LIMITS.get(command, COMMAND_RATE_LIMITS["default"])
    cmd_history = user_commands[user_id]
    last_execution = cmd_history.get(command, 0)
    
    if last_execution == 0:
        return {"remaining": limits["limit"], "reset": 0}
    
    now = time.time()
    time_since_last = now - last_execution
    window = limits["window"]
    limit = limits["limit"]
    
    remaining = max(0, limit - int(time_since_last / (window / limit)))
    reset_time = int((window / limit) - time_since_last) if remaining == 0 else 0
    
    return {"remaining": remaining, "reset": reset_time}

# ========== ОЧИСТКА ==========

async def cleanup_old_data():
    """Очищает старые данные антиспама"""
    while True:
        await asyncio.sleep(3600)
        now = time.time()
        
        # Очищаем старые сообщения
        for user_id in list(user_messages.keys()):
            messages = [t for t in user_messages[user_id] if now - t < 3600]
            if messages:
                user_messages[user_id] = messages
            else:
                del user_messages[user_id]
        
        # Очищаем старые временные баны
        for user_id in list(temp_bans.keys()):
            if now > temp_bans[user_id]:
                del temp_bans[user_id]
