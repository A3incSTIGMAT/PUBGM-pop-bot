"""
Логирование для NEXUS бота с защитой от переполнения.
"""

import logging
import time
import asyncio
from datetime import datetime
from typing import Optional
from enum import Enum
from collections import deque

# Настройка основного логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("NEXUS")

class LogType(Enum):
    """Типы логов"""
    INFO = "ℹ️"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    ADMIN = "🛡️"
    GAME = "🎮"
    ECONOMY = "💰"
    USER = "👤"
    ATTACK = "🔥"

class Logger:
    """Класс для логирования действий с защитой от флуда логов"""
    
    def __init__(self, name: str = "NEXUS", max_logs_per_minute: int = 100):
        self.logger = logging.getLogger(name)
        self.max_logs_per_minute = max_logs_per_minute
        self.log_timestamps: deque = deque(maxlen=max_logs_per_minute)
        self.attack_mode = False
    
    def _can_log(self) -> bool:
        """Проверяет, не превышен ли лимит логов"""
        now = time.time()
        while self.log_timestamps and now - self.log_timestamps[0] > 60:
            self.log_timestamps.popleft()
        
        if len(self.log_timestamps) >= self.max_logs_per_minute:
            if not self.attack_mode:
                self.logger.warning("⚠️ Превышен лимит логов! Возможна атака.")
                self.attack_mode = True
            return False
        
        self.log_timestamps.append(now)
        if self.attack_mode and len(self.log_timestamps) < self.max_logs_per_minute * 0.5:
            self.attack_mode = False
        return True
    
    def _log(self, level: int, message: str, log_type: LogType = LogType.INFO):
        """Внутренний метод логирования"""
        if not self._can_log() and level < logging.WARNING:
            return
        
        formatted = f"{log_type.value} {message}"
        self.logger.log(level, formatted)
    
    def info(self, message: str):
        self._log(logging.INFO, message, LogType.INFO)
    
    def success(self, message: str):
        self._log(logging.INFO, message, LogType.SUCCESS)
    
    def error(self, message: str):
        self._log(logging.ERROR, message, LogType.ERROR)
    
    def warning(self, message: str):
        self._log(logging.WARNING, message, LogType.WARNING)
    
    def attack(self, message: str):
        self._log(logging.WARNING, message, LogType.ATTACK)
    
    def admin(self, message: str):
        """Логирование действий администраторов"""
        self._log(logging.INFO, message, LogType.ADMIN)
    
    def game(self, message: str):
        """Логирование игровых действий"""
        self._log(logging.INFO, message, LogType.GAME)
    
    def economy(self, message: str):
        """Логирование экономических действий"""
        self._log(logging.INFO, message, LogType.ECONOMY)
    
    def user(self, message: str):
        """Логирование действий пользователей"""
        self._log(logging.INFO, message, LogType.USER)
    
    def admin_action(self, admin_name: str, action: str, target: Optional[str] = None):
        if target:
            msg = f"{admin_name} ➜ {action} ➜ {target}"
        else:
            msg = f"{admin_name} ➜ {action}"
        self.admin(msg)
    
    def game_action(self, user_name: str, game: str, result: str, amount: Optional[int] = None):
        if amount:
            msg = f"{user_name} ➜ {game} ➜ {result} ➜ {amount} NCoin"
        else:
            msg = f"{user_name} ➜ {game} ➜ {result}"
        self.game(msg)
    
    def economy_action(self, user_name: str, action: str, amount: int, target: Optional[str] = None):
        if target:
            msg = f"{user_name} ➜ {action} {amount} NCoin ➜ {target}"
        else:
            msg = f"{user_name} ➜ {action} {amount} NCoin"
        self.economy(msg)
    
    def user_action(self, user_name: str, command: str):
        self.user(f"{user_name} ➜ {command}")
    
    def command_stats(self, command: str, user_id: int, duration_ms: float):
        if duration_ms > 1000:
            self.warning(f"{command} by {user_id} SLOW: {duration_ms:.2f}ms")

# Глобальный экземпляр логгера
nexus_logger = Logger()

# Удобные функции для быстрого доступа
def log_info(message: str):
    nexus_logger.info(message)

def log_success(message: str):
    nexus_logger.success(message)

def log_error(message: str):
    nexus_logger.error(message)

def log_warning(message: str):
    nexus_logger.warning(message)

def log_attack(message: str):
    nexus_logger.attack(message)

def log_admin(admin_name: str, action: str, target: Optional[str] = None):
    """Логирование действий администратора"""
    nexus_logger.admin_action(admin_name, action, target)

def log_game(user_name: str, game: str, result: str, amount: Optional[int] = None):
    nexus_logger.game_action(user_name, game, result, amount)

def log_economy(user_name: str, action: str, amount: int, target: Optional[str] = None):
    nexus_logger.economy_action(user_name, action, amount, target)

def log_user(user_name: str, command: str):
    nexus_logger.user_action(user_name, command)

def measure_time(func):
    """Декоратор для измерения времени выполнения"""
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        duration = (time.time() - start) * 1000
        if hasattr(args[0], 'from_user') and hasattr(args[0].from_user, 'full_name'):
            nexus_logger.command_stats(func.__name__, args[0].from_user.id, duration)
        return result
    return wrapper

def get_logs_summary() -> dict:
    return {
        "status": "active",
        "attack_mode": nexus_logger.attack_mode,
        "logger": "NEXUS",
        "timestamp": datetime.now().isoformat()
    }
