"""
Модели данных для NEXUS бота.
Содержит dataclass для работы с пользователями, чатами и подарками.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class User:
    """Модель пользователя"""
    user_id: int
    chat_id: int
    username: Optional[str] = None
    balance: int = 0
    total_messages: int = 0
    is_vip: bool = False
    vip_until: Optional[int] = None
    birthday: Optional[str] = None
    reputation: int = 0
    
    @property
    def is_vip_active(self) -> bool:
        """Проверка, активен ли VIP"""
        if not self.is_vip or not self.vip_until:
            return False
        import time
        return time.time() < self.vip_until
    
    @property
    def display_name(self) -> str:
        """Отображаемое имя пользователя"""
        if self.username:
            return f"@{self.username}"
        return f"User_{self.user_id}"

@dataclass
class Chat:
    """Модель чата"""
    chat_id: int
    chat_name: Optional[str] = None
    welcome_message: Optional[str] = None
    log_channel_id: Optional[int] = None
    language: str = "ru"

@dataclass
class Gift:
    """Модель подарка"""
    id: int
    from_user: int
    to_user: int
    chat_id: int
    gift_type: str
    amount: int
    created_at: datetime

@dataclass
class GameStats:
    """Модель статистики игр"""
    user_id: int
    chat_id: int
    game_name: str
    wins: int = 0
    losses: int = 0
    total_played: int = 0
    
    @property
    def winrate(self) -> float:
        """Процент побед"""
        if self.total_played == 0:
            return 0.0
        return (self.wins / self.total_played) * 100

@dataclass
class Captcha:
    """Модель капчи"""
    user_id: int
    chat_id: int
    answer: int
    created_at: datetime

@dataclass
class Birthday:
    """Модель дня рождения"""
    user_id: int
    chat_id: int
    birthday: str
    created_at: datetime

@dataclass
class Report:
    """Модель анонимной жалобы"""
    id: int
    chat_id: int
    reporter_id: int
    target_id: int
    reason: str
    status: str
    created_at: datetime
