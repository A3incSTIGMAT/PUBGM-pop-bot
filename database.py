#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАЙЛ: database.py
ВЕРСИЯ: 3.6.4-final
ОПИСАНИЕ: Асинхронная база данных NEXUS Bot — добавлен update_xo_stats
СОВМЕСТИМОСТЬ: Python 3.9+ / aiogram 3.x
"""

import asyncio
import logging
import os
import random
import re
import shutil
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, TypedDict, FrozenSet

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

MAX_RETRIES = 5
RETRY_DELAY_BASE = 0.1
CACHE_TTL_BALANCE = 60
CACHE_TTL_STATS = 300
CACHE_TTL_PROFILE = 600
DB_BUSY_TIMEOUT = 10000
POOL_MAX_CONNECTIONS = 5
POOL_QUEUE_TIMEOUT = 30
CACHE_SHARDS = 8
CACHE_MAX_SIZE_PER_SHARD = 500
SLOW_QUERY_THRESHOLD = 1.0
COMMIT_EVERY = 100
MAX_ABOUT_LENGTH = 500
MAX_TAG_LENGTH = 20
MIN_TAG_LENGTH = 2
MAX_USERNAME_LENGTH = 32
MIN_USERNAME_LENGTH = 3
MAX_FIRST_NAME_LENGTH = 50
CONNECTION_MAX_IDLE = 300

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,32}$')
NAME_PATTERN = re.compile(r'^[а-яА-Яa-zA-Z\s\-]{1,50}$')


# ==================== ИСКЛЮЧЕНИЯ ====================

class DatabaseError(Exception):
    """Базовое исключение для всех ошибок базы данных."""
    pass


class UserNotFoundError(DatabaseError):
    """Пользователь не найден."""
    pass


class InsufficientFundsError(DatabaseError):
    """Недостаточно средств для выполнения операции."""
    pass


class MigrationError(DatabaseError):
    """Критическая ошибка при выполнении миграции."""
    pass


class ValidationError(DatabaseError):
    """Ошибка валидации входных параметров."""
    pass


class ConnectionPoolExhaustedError(DatabaseError):
    """Пул соединений исчерпан."""
    pass


# ==================== ФУНКЦИИ ВАЛИДАЦИИ ====================

def validate_user_id(user_id: Any) -> int:
    """Валидация user_id: должен быть положительным целым числом."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValidationError(
            "user_id must be a positive integer, got " +
            type(user_id).__name__ + ": " + str(user_id)
        )
    return user_id


def validate_username(username: Optional[str]) -> Optional[str]:
    """Валидация username: длина 3-32, только буквы/цифры/подчёркивание."""
    if username is None:
        return None
    username = username.lstrip('@').strip()
    if not username:
        return None
    if len(username) < MIN_USERNAME_LENGTH or len(username) > MAX_USERNAME_LENGTH:
        raise ValidationError(
            "Username must be " + str(MIN_USERNAME_LENGTH) + "-" +
            str(MAX_USERNAME_LENGTH) + " chars"
        )
    if not USERNAME_PATTERN.match(username):
        raise ValidationError("Username must contain only letters, numbers and underscore")
    return username


def validate_first_name(name: Optional[str]) -> Optional[str]:
    """Валидация имени: длина 1-50, только буквы/пробелы/дефис."""
    if name is None:
        return None
    name = name.strip()
    if not name:
        return None
    if len(name) > MAX_FIRST_NAME_LENGTH:
        raise ValidationError(
            "Name must be <= " + str(MAX_FIRST_NAME_LENGTH) + " chars"
        )
    if not NAME_PATTERN.match(name):
        raise ValidationError("Name must contain only letters, spaces and hyphens")
    return name


# ==================== МЕТРИКИ ====================

class DatabaseMetrics:
    """Сбор метрик производительности базы данных."""
    
    def __init__(self) -> None:
        self.query_count: int = 0
        self.total_query_time: float = 0.0
        self.retry_count: int = 0
        self.cache_hits: Dict[str, int] = {"balance": 0, "stats": 0, "profile": 0}
        self.cache_misses: Dict[str, int] = {"balance": 0, "stats": 0, "profile": 0}
        self.connection_creations: int = 0
        self.transaction_count: int = 0
        self.error_count: int = 0
        self.slow_query_count: int = 0
        self.pool_wait_time: float = 0.0
        self.pool_wait_count: int = 0
    
    @property
    def avg_query_time_ms(self) -> float:
        if self.query_count == 0:
            return 0.0
        return (self.total_query_time / self.query_count) * 1000
    
    @property
    def cache_hit_rate(self) -> float:
        total_hits = sum(self.cache_hits.values())
        total_misses = sum(self.cache_misses.values())
        total = total_hits + total_misses
        if total == 0:
            return 0.0
        return (total_hits / total) * 100
    
    @property
    def avg_pool_wait_ms(self) -> float:
        if self.pool_wait_count == 0:
            return 0.0
        return (self.pool_wait_time / self.pool_wait_count) * 1000
    
    def record_cache_hit(self, cache_type: str) -> None:
        if cache_type in self.cache_hits:
            self.cache_hits[cache_type] += 1
    
    def record_cache_miss(self, cache_type: str) -> None:
        if cache_type in self.cache_misses:
            self.cache_misses[cache_type] += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_count": self.query_count,
            "avg_query_time_ms": round(self.avg_query_time_ms, 2),
            "retry_count": self.retry_count,
            "cache_hits_by_type": self.cache_hits,
            "cache_misses_by_type": self.cache_misses,
            "cache_hit_rate": round(self.cache_hit_rate, 1),
            "connection_creations": self.connection_creations,
            "active_connections_estimate": min(self.connection_creations, POOL_MAX_CONNECTIONS),
            "avg_pool_wait_ms": round(self.avg_pool_wait_ms, 2),
            "transaction_count": self.transaction_count,
            "error_count": self.error_count,
            "slow_query_count": self.slow_query_count,
        }


# ==================== TYPED DICT ====================

class UserDict(TypedDict, total=False):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    balance: int
    daily_streak: int
    last_daily: Optional[str]
    vip_level: int
    vip_until: Optional[str]
    wins: int
    losses: int
    register_date: Optional[str]
    warns: str
    xp: int
    rank: int


class UserStatsDict(TypedDict, total=False):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    balance: int
    daily_streak: int
    vip_level: int
    xp: int
    rank: int
    messages_total: int
    messages_today: int
    total_voice: int
    total_stickers: int
    total_gifs: int
    total_photos: int
    total_videos: int
    days_active: int
    current_streak: int
    games_played: int
    wins: int
    losses: int
    draws: int
    wins_vs_bot: int
    losses_vs_bot: int
    calculated_rank: int


class TransferResultDict(TypedDict):
    success: bool
    error: Optional[str]
    new_from_balance: Optional[int]
    new_to_balance: Optional[int]


class RelationshipResultDict(TypedDict):
    success: bool
    error: Optional[str]
    relationship_id: Optional[int]


class HealthCheckDict(TypedDict):
    status: str
    latency_ms: Optional[float]
    error: Optional[str]
    metrics: Optional[Dict[str, Any]]
    pool: Optional[Dict[str, Any]]


# ==================== SQL-ЗАПРОСЫ ====================

class SQL_QUERIES:
    """Контейнер для всех SQL-запросов."""
    
    GET_USER = "SELECT * FROM users WHERE user_id = ?"
    GET_USER_BY_USERNAME = "SELECT * FROM users WHERE username = ?"
    GET_USER_BALANCE = "SELECT balance FROM users WHERE user_id = ?"
    USER_EXISTS = "SELECT 1 FROM users WHERE user_id = ? LIMIT 1"
    
    INSERT_USER = (
        "INSERT OR IGNORE INTO users "
        "(user_id, username, first_name, balance, register_date, warns, xp, rank) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    INSERT_PROFILE = (
        "INSERT OR IGNORE INTO user_profiles (user_id, created_at, updated_at) "
        "VALUES (?, ?, ?)"
    )
    INSERT_STATS = (
        "INSERT OR IGNORE INTO user_stats (user_id, register_date, last_active) "
        "VALUES (?, ?, ?)"
    )
    INSERT_ECONOMY = (
        "INSERT OR IGNORE INTO user_economy_stats (user_id, max_balance) "
        "VALUES (?, ?)"
    )
    INSERT_XO_STATS = "INSERT OR IGNORE INTO xo_stats (user_id) VALUES (?)"
    
    UPDATE_BALANCE = "UPDATE users SET balance = balance + ? WHERE user_id = ?"
    UPDATE_MAX_BALANCE = (
        "UPDATE user_economy_stats "
        "SET max_balance = MAX(COALESCE(max_balance, 0), "
        "(SELECT balance FROM users WHERE user_id = ?)), "
        "total_earned = COALESCE(total_earned, 0) + ? "
        "WHERE user_id = ?"
    )
    UPDATE_TOTAL_SPENT = (
        "UPDATE user_economy_stats "
        "SET total_spent = COALESCE(total_spent, 0) + ? "
        "WHERE user_id = ?"
    )
    INSERT_TRANSACTION = (
        "INSERT INTO transactions (from_id, to_id, amount, reason, date) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    
    BEGIN_IMMEDIATE = "BEGIN IMMEDIATE"
    
    GET_PROFILE = "SELECT * FROM user_profiles WHERE user_id = ?"
    GET_PROFILE_CREATED = "SELECT created_at FROM user_profiles WHERE user_id = ?"
    UPSERT_PROFILE = (
        "INSERT OR REPLACE INTO user_profiles "
        "(user_id, full_name, age, city, timezone, about, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    
    UPDATE_RANK = "UPDATE users SET rank = ? WHERE user_id = ?"
    ADD_XP = "UPDATE users SET xp = COALESCE(xp, 0) + ? WHERE user_id = ?"
    
    GET_USER_STATS = (
        "SELECT u.user_id, u.username, u.first_name, "
        "COALESCE(u.balance, 0) as balance, "
        "COALESCE(u.daily_streak, 0) as daily_streak, "
        "COALESCE(u.vip_level, 0) as vip_level, "
        "COALESCE(u.xp, 0) as xp, "
        "COALESCE(u.rank, 1) as rank, "
        "COALESCE(s.messages_total, 0) as messages_total, "
        "COALESCE(s.messages_today, 0) as messages_today, "
        "COALESCE(s.total_voice, 0) as total_voice, "
        "COALESCE(s.total_stickers, 0) as total_stickers, "
        "COALESCE(s.total_gifs, 0) as total_gifs, "
        "COALESCE(s.total_photos, 0) as total_photos, "
        "COALESCE(s.total_videos, 0) as total_videos, "
        "COALESCE(s.days_active, 0) as days_active, "
        "COALESCE(s.current_streak, 0) as current_streak, "
        "COALESCE(x.games_played, 0) as games_played, "
        "COALESCE(x.wins, 0) as wins, "
        "COALESCE(x.losses, 0) as losses, "
        "COALESCE(x.draws, 0) as draws, "
        "COALESCE(x.wins_vs_bot, 0) as wins_vs_bot, "
        "COALESCE(x.losses_vs_bot, 0) as losses_vs_bot "
        "FROM users u "
        "LEFT JOIN user_stats s ON u.user_id = s.user_id "
        "LEFT JOIN xo_stats x ON u.user_id = x.user_id "
        "WHERE u.user_id = ?"
    )
    
    TRACK_ACTIVITY_TEMPLATE = (
        "INSERT INTO user_activity_log (user_id, chat_id, date, {column}) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, chat_id, date) "
        "DO UPDATE SET {column} = {column} + ?"
    )
    UPDATE_MESSAGE_STATS = (
        "UPDATE user_stats "
        "SET messages_total = COALESCE(messages_total, 0) + 1, "
        "messages_today = COALESCE(messages_today, 0) + 1, "
        "last_message_date = ?, last_active = ? "
        "WHERE user_id = ?"
    )
    UPDATE_ACTIVITY_STATS_TEMPLATE = (
        "UPDATE user_stats SET {column} = COALESCE({column}, 0) + ?, "
        "last_active = ? WHERE user_id = ?"
    )
    
    TRACK_WORD = (
        "INSERT INTO chat_word_stats (chat_id, date, word, count) "
        "VALUES (?, ?, ?, 1) "
        "ON CONFLICT(chat_id, date, word) "
        "DO UPDATE SET count = count + 1"
    )
    
    GET_TOP_USERS = (
        "SELECT u.user_id, u.username, u.first_name, u.balance, u.xp, u.rank, "
        "COALESCE(s.messages_total, 0) as messages_total, "
        "COALESCE(x.wins, 0) as wins, "
        "COALESCE(s.days_active, 0) as days_active "
        "FROM users u "
        "LEFT JOIN user_stats s ON u.user_id = s.user_id "
        "LEFT JOIN xo_stats x ON u.user_id = x.user_id "
        "WHERE u.balance >= 0 ORDER BY {order_clause} LIMIT ?"
    )
    
    GET_CHAT_TOP_BALANCE = (
        "SELECT u.user_id, u.username, u.first_name, u.balance, u.vip_level "
        "FROM users u "
        "INNER JOIN (SELECT DISTINCT user_id FROM user_activity_log "
        "WHERE chat_id = ? AND date >= date('now', '-30 days')) a "
        "ON u.user_id = a.user_id "
        "WHERE u.balance > 0 ORDER BY u.balance DESC LIMIT ?"
    )
    
    GET_CHAT_TOP_XO = (
        "SELECT u.user_id, u.username, u.first_name, "
        "COALESCE(x.wins, 0) as wins, "
        "COALESCE(x.games_played, 0) as games_played, "
        "CASE WHEN COALESCE(x.games_played, 0) > 0 "
        "THEN ROUND(COALESCE(x.wins, 0) * 100.0 / x.games_played, 1) "
        "ELSE 0 END as win_rate "
        "FROM xo_stats x "
        "INNER JOIN users u ON x.user_id = u.user_id "
        "INNER JOIN (SELECT DISTINCT user_id FROM user_activity_log "
        "WHERE chat_id = ? AND date >= date('now', '-30 days')) a "
        "ON x.user_id = a.user_id "
        "WHERE COALESCE(x.games_played, 0) >= 1 "
        "ORDER BY x.wins DESC, win_rate DESC LIMIT ?"
    )
    
    GET_CHAT_TOP_MESSAGES = (
        "SELECT ual.user_id, u.first_name, u.username, "
        "SUM(ual.messages) as messages_total, "
        "COUNT(DISTINCT ual.date) as active_days "
        "FROM user_activity_log ual "
        "LEFT JOIN users u ON ual.user_id = u.user_id "
        "WHERE ual.chat_id = ? AND ual.date >= date('now', '-30 days') "
        "GROUP BY ual.user_id "
        "HAVING messages_total > 0 "
        "ORDER BY messages_total DESC LIMIT ?"
    )
    
    GET_RELATIONSHIP = (
        "SELECT * FROM relationships "
        "WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)) "
        "AND type = ? AND status IN ('pending', 'active') "
        "ORDER BY created_at DESC LIMIT 1"
    )
    INSERT_RELATIONSHIP = (
        "INSERT INTO relationships (user1_id, user2_id, type, status, created_at) "
        "VALUES (?, ?, ?, 'pending', ?)"
    )
    GET_RELATIONSHIP_BY_ID = (
        "SELECT user1_id, user2_id, status FROM relationships WHERE id = ?"
    )
    CONFIRM_RELATIONSHIP = (
        "UPDATE relationships SET status = 'active', confirmed_by_user2 = 1 "
        "WHERE id = ? AND status = 'pending'"
    )
    GET_RELATIONSHIP_STATUS = (
        "SELECT r.*, "
        "u1.username as user1_username, u1.first_name as user1_name, "
        "u2.username as user2_username, u2.first_name as user2_name "
        "FROM relationships r "
        "LEFT JOIN users u1 ON r.user1_id = u1.user_id "
        "LEFT JOIN users u2 ON r.user2_id = u2.user_id "
        "WHERE (r.user1_id = ? OR r.user2_id = ?) "
        "AND r.type = ? AND r.status IN ('pending', 'active') "
        "ORDER BY r.created_at DESC LIMIT 1"
    )
    GET_USER_RELATIONSHIPS = (
        "SELECT r.*, "
        "CASE WHEN r.user1_id = ? THEN u2.username ELSE u1.username END as partner_username, "
        "CASE WHEN r.user1_id = ? THEN u2.first_name ELSE u1.first_name END as partner_name, "
        "CASE WHEN r.user1_id = ? THEN r.user2_id ELSE r.user1_id END as partner_id "
        "FROM relationships r "
        "LEFT JOIN users u1 ON r.user1_id = u1.user_id "
        "LEFT JOIN users u2 ON r.user2_id = u2.user_id "
        "WHERE (r.user1_id = ? OR r.user2_id = ?) "
        "AND r.status IN ('pending', 'active') "
        "ORDER BY r.created_at DESC"
    )
    END_RELATIONSHIP = (
        "UPDATE relationships SET status = 'ended', ended_at = CURRENT_TIMESTAMP "
        "WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)) "
        "AND type = ? AND status = 'active'"
    )
    
    ADD_USER_TAG = "INSERT OR IGNORE INTO user_tags (user_id, tag_name) VALUES (?, ?)"
    REMOVE_USER_TAG = "DELETE FROM user_tags WHERE user_id = ? AND tag_name = ?"
    GET_USER_TAGS = "SELECT tag_name FROM user_tags WHERE user_id = ? ORDER BY tag_name"
    SEARCH_USERS_BY_TAG = (
        "SELECT u.user_id, u.username, u.first_name, u.balance "
        "FROM user_tags t JOIN users u ON t.user_id = u.user_id "
        "WHERE t.tag_name = ? ORDER BY u.balance DESC LIMIT ?"
    )
    
    CREATE_TICKET = (
        "INSERT INTO feedback_tickets (user_id, message, status, created_at) "
        "VALUES (?, ?, 'open', CURRENT_TIMESTAMP)"
    )
    GET_USER_TICKETS = (
        "SELECT id, message, status, created_at, answered_at, admin_response "
        "FROM feedback_tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT ?"
    )
    UPDATE_TICKET_CLOSED = (
        "UPDATE feedback_tickets SET status = ?, admin_response = ?, answered_at = ? "
        "WHERE id = ?"
    )
    UPDATE_TICKET_STATUS = "UPDATE feedback_tickets SET status = ? WHERE id = ?"
    GET_PENDING_TICKETS = (
        "SELECT t.id, t.message, t.created_at, u.username, u.first_name "
        "FROM feedback_tickets t JOIN users u ON t.user_id = u.user_id "
        "WHERE t.status = 'open' ORDER BY t.created_at ASC LIMIT ?"
    )
    
    INSERT_ADMIN_LOG = (
        "INSERT INTO admin_logs (admin_id, action, chat_id, target_user_id, details) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    GET_ADMIN_LOGS_BY_ADMIN = (
        "SELECT * FROM admin_logs WHERE admin_id = ? ORDER BY created_at DESC LIMIT ?"
    )
    GET_ALL_ADMIN_LOGS = "SELECT * FROM admin_logs ORDER BY created_at DESC LIMIT ?"
    
    GET_DAILY_SUMMARY = "SELECT * FROM chat_daily_summary WHERE chat_id = ? AND date = ?"
    SAVE_DAILY_SUMMARY = (
        "INSERT OR REPLACE INTO chat_daily_summary "
        "(chat_id, date, total_messages, active_users, top_words, top_users) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    GET_TOP_WORDS = (
        "SELECT word, count FROM chat_word_stats "
        "WHERE chat_id = ? AND date = ? ORDER BY count DESC LIMIT ?"
    )
    
    GET_DELETABLE_MESSAGES = (
        "SELECT user_id, date, messages, voice, stickers, gifs, photos, videos "
        "FROM user_activity_log "
        "WHERE chat_id = ? AND date >= ? ORDER BY date DESC, messages DESC LIMIT ?"
    )
    GET_CUSTOM_RP = "SELECT user_id, action_text FROM custom_rp WHERE command = ? LIMIT 1"
    SHOP_ITEMS_COUNT = "SELECT COUNT(*) as cnt FROM shop_items"
    INSERT_SHOP_ITEM = "INSERT INTO shop_items (name, price, description) VALUES (?, ?, ?)"
    TAG_CATEGORIES_COUNT = "SELECT COUNT(*) as cnt FROM tag_categories"
    INSERT_TAG_CATEGORY = (
        "INSERT OR IGNORE INTO tag_categories (slug, name, description, icon_emoji) "
        "VALUES (?, ?, ?, ?)"
    )
    GET_ACTIVE_USERS = (
        "SELECT DISTINCT user_id FROM user_activity_log "
        "WHERE date >= date('now', '-1 days') LIMIT 100"
    )
    PRAGMA_TABLE_INFO = "PRAGMA table_info({table})"
    ALTER_TABLE = "ALTER TABLE {table} ADD COLUMN {column} {definition}"
    TABLE_EXISTS = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
    GET_MIGRATION_VERSION = (
        "SELECT version FROM _migrations ORDER BY version DESC LIMIT 1"
    )
    INSERT_MIGRATION = "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)"
    DELETE_MIGRATION = "DELETE FROM _migrations WHERE version = ?"
    
    BATCH_UPDATE_RANKS = "UPDATE users SET rank = ? WHERE user_id = ?"
    BATCH_UPDATE_STREAKS = (
        "UPDATE user_stats SET current_streak = 0 "
        "WHERE last_active < ? AND current_streak > 0"
    )
    
    # XO Stats update queries
    UPDATE_XO_WIN = (
        "UPDATE xo_stats SET games_played = COALESCE(games_played, 0) + 1, "
        "wins = COALESCE(wins, 0) + 1, "
        "total_bet = COALESCE(total_bet, 0) + ?, "
        "total_won = COALESCE(total_won, 0) + ?, "
        "current_win_streak = COALESCE(current_win_streak, 0) + 1, "
        "max_win_streak = MAX(COALESCE(max_win_streak, 0), "
        "COALESCE(current_win_streak, 0) + 1) "
        "WHERE user_id = ?"
    )
    UPDATE_XO_LOSS = (
        "UPDATE xo_stats SET games_played = COALESCE(games_played, 0) + 1, "
        "losses = COALESCE(losses, 0) + 1, "
        "total_bet = COALESCE(total_bet, 0) + ?, "
        "current_win_streak = 0 "
        "WHERE user_id = ?"
    )
    UPDATE_XO_DRAW = (
        "UPDATE xo_stats SET games_played = COALESCE(games_played, 0) + 1, "
        "draws = COALESCE(draws, 0) + 1, "
        "total_bet = COALESCE(total_bet, 0) + ?, "
        "current_win_streak = 0 "
        "WHERE user_id = ?"
    )
    UPDATE_XO_WIN_VS_BOT = (
        "UPDATE xo_stats SET games_played = COALESCE(games_played, 0) + 1, "
        "wins_vs_bot = COALESCE(wins_vs_bot, 0) + 1, "
        "wins = COALESCE(wins, 0) + 1, "
        "total_bet = COALESCE(total_bet, 0) + ?, "
        "total_won = COALESCE(total_won, 0) + ? "
        "WHERE user_id = ?"
    )
    UPDATE_XO_LOSS_VS_BOT = (
        "UPDATE xo_stats SET games_played = COALESCE(games_played, 0) + 1, "
        "losses_vs_bot = COALESCE(losses_vs_bot, 0) + 1, "
        "losses = COALESCE(losses, 0) + 1, "
        "total_bet = COALESCE(total_bet, 0) + ? "
        "WHERE user_id = ?"
    )


# ==================== ВАЛИДАЦИЯ ====================

ACTIVITY_COLUMN_MAP: Dict[str, str] = {
    "message": "messages", "voice": "voice", "sticker": "stickers",
    "gif": "gifs", "photo": "photos", "video": "videos",
    "xo_game": "xo_games", "game": "games_played",
}

STAT_COLUMN_MAP: Dict[str, str] = {
    "voice": "total_voice", "sticker": "total_stickers",
    "gif": "total_gifs", "photo": "total_photos", "video": "total_videos",
}

VALID_ACTIVITY_COLUMNS: FrozenSet[str] = frozenset(ACTIVITY_COLUMN_MAP.values())
VALID_STAT_COLUMNS: FrozenSet[str] = frozenset(STAT_COLUMN_MAP.values())
VALID_ORDER_COLUMNS: FrozenSet[str] = frozenset({
    "balance", "xp", "rank", "messages", "wins", "activity"
})

DEFAULT_CATEGORIES = [
    ("pubg", "🎮 PUBG Mobile", "Поиск сквада / ранкед", "🎮"),
    ("cs2", "🎮 CS2", "Поиск напарников", "🎮"),
    ("dota", "🎮 Dota 2", "Собрать пати", "🎮"),
    ("mafia", "🎭 Мафия", "Сбор на партию", "🎭"),
    ("video_call", "📞 Видео-звонок", "Созвон в группе", "📞"),
    ("important", "❓ Важный вопрос", "Нужен совет / помощь", "❓"),
    ("giveaway", "🎁 Розыгрыш", "Конкурсы и ивенты", "🎁"),
    ("offtopic", "💬 Флудилка", "Оффтоп и общение", "💬"),
    ("tech", "🔧 Техническое", "Баги, предложения", "🔧"),
    ("urgent", "🆘 Срочно", "Помощь админам", "🆘"),
]

DEFAULT_SHOP_ITEMS = [
    ("⭐ VIP 1 месяц", 5000, "Доступ к VIP-комнатам + бонусы"),
    ("💎 1000 монет", 100, "Пополнение баланса"),
    ("🎁 Случайный подарок", 200, "Получи случайную награду"),
]

DEFAULT_POLICY_TEXT = {
    "rules": "📜 <b>Правила чата</b>\n\n1. Уважайте собеседников.\n2. Спам, флуд, реклама — бан.\n3. Контент 18+ только в специальных чатах.\n4. Модераторы имеют право на мут.\n5. Жалобы на модерацию — в ЛС @admin",
    "privacy": "🔐 <b>Конфиденциальность</b>\n\n• Мы не передаём ваши данные третьим лицам.\n• Сообщения хранятся 90 дней.\n• Вы можете запросить удаление: /delete_data",
    "moderation": "⚖️ <b>Модерация</b>\n\n• Предупреждение → Мут 1ч → Мут 24ч → Бан.\n• Решения модераторов можно обжаловать в течение 24ч",
    "feedback": "📬 <b>Обратная связь</b>\n\n• Баги и предложения: /feedback\n• Жалобы на пользователей: /report @username",
    "contacts": "👥 <b>Контакты</b>\n\n• Главный админ: @admin_nexus\n• Поддержка: @support_nexus"
}


# ==================== LRU-КЭШ ====================

class LRUCacheShard:
    """Шард LRU-кэша с ограничением размера."""
    
    def __init__(self, max_size: int = CACHE_MAX_SIZE_PER_SHARD) -> None:
        self._cache: OrderedDict[str, Tuple[Any, float, int]] = OrderedDict()
        self._lock = asyncio.Lock()
        self.max_size = max_size
    
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._cache:
                value, timestamp, ttl = self._cache[key]
                if time.time() - timestamp < ttl:
                    self._cache.move_to_end(key)
                    return value
                del self._cache[key]
        return None
    
    async def set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            self._cache.pop(key, None)
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            self._cache[key] = (value, time.time(), ttl)
    
    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear_pattern(self, pattern: str) -> None:
        async with self._lock:
            keys = [k for k in self._cache if pattern in k]
            for k in keys:
                del self._cache[k]
    
    async def clear_all(self) -> None:
        async with self._lock:
            self._cache.clear()
    
    @property
    def size(self) -> int:
        return len(self._cache)


class ShardedLRUCache:
    """Сегментированный LRU-кэш."""
    
    def __init__(self, num_shards: int = CACHE_SHARDS) -> None:
        self._shards = [LRUCacheShard() for _ in range(num_shards)]
    
    def _get_shard(self, key: str) -> LRUCacheShard:
        return self._shards[abs(hash(key)) % len(self._shards)]
    
    async def get(self, key: str) -> Optional[Any]:
        return await self._get_shard(key).get(key)
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        await self._get_shard(key).set(key, value, ttl)
    
    async def delete(self, key: str) -> None:
        await self._get_shard(key).delete(key)
    
    async def clear_pattern(self, pattern: str) -> None:
        for shard in self._shards:
            await shard.clear_pattern(pattern)
    
    async def clear_all(self) -> None:
        for shard in self._shards:
            await shard.clear_all()
    
    @property
    def total_size(self) -> int:
        return sum(shard.size for shard in self._shards)


# ==================== ПУЛ СОЕДИНЕНИЙ ====================

class ConnectionPool:
    """Пул соединений с мониторингом и таймаутами."""
    
    def __init__(self, db_path: str, max_connections: int = POOL_MAX_CONNECTIONS) -> None:
        self.db_path = db_path
        self.max_connections = max_connections
        self._semaphore = asyncio.Semaphore(max_connections)
        self._created_count = 0
        self._active_count = 0
        self._wait_count = 0
        self._total_wait_time = 0.0
        self._closed = False
    
    async def get_connection(self) -> aiosqlite.Connection:
        if self._closed:
            raise DatabaseError("Connection pool is closed")
        
        wait_start = time.time()
        
        try:
            acquired = await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=POOL_QUEUE_TIMEOUT
            )
            if not acquired:
                raise ConnectionPoolExhaustedError("Connection pool exhausted")
        except asyncio.TimeoutError:
            raise ConnectionPoolExhaustedError(
                "Connection pool timeout after " + str(POOL_QUEUE_TIMEOUT) + "s"
            )
        
        wait_time = time.time() - wait_start
        self._wait_count += 1
        self._total_wait_time += wait_time
        
        if wait_time > 1.0:
            logger.warning(
                "Pool wait: %.2fs (active: %s/%s)",
                wait_time, self._active_count, self.max_connections
            )
        
        self._active_count += 1
        
        try:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA busy_timeout = " + str(DB_BUSY_TIMEOUT))
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute("PRAGMA cache_size = -8000")
            
            original_close = conn.close
            
            async def tracked_close() -> None:
                self._active_count = max(0, self._active_count - 1)
                if not self._closed:
                    self._semaphore.release()
                await original_close()
            
            conn.close = tracked_close  # type: ignore
            self._created_count += 1
            return conn
            
        except Exception:
            self._active_count = max(0, self._active_count - 1)
            if not self._closed:
                self._semaphore.release()
            raise
    
    async def close(self) -> None:
        self._closed = True
        for _ in range(self.max_connections):
            self._semaphore.release()
        logger.info("Connection pool closed")
    
    @property
    def created_connections(self) -> int:
        return self._created_count
    
    @property
    def active_connections(self) -> int:
        return self._active_count
    
    @property
    def avg_wait_time_ms(self) -> float:
        if self._wait_count == 0:
            return 0.0
        return (self._total_wait_time / self._wait_count) * 1000
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "max_connections": self.max_connections,
            "active_connections": self.active_connections,
            "total_created": self.created_connections,
            "avg_wait_time_ms": round(self.avg_wait_time_ms, 2),
            "total_waits": self._wait_count,
            "is_closed": self._closed,
        }


# ==================== КОНТЕКСТНЫЙ МЕНЕДЖЕР ====================

class AsyncConnectionContext:
    """Асинхронный контекстный менеджер для соединений."""
    
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool
        self.conn: Optional[aiosqlite.Connection] = None
    
    async def __aenter__(self) -> aiosqlite.Connection:
        self.conn = await self.pool.get_connection()
        return self.conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.conn:
            try:
                await self.conn.close()
            except Exception as e:
                logger.error("Error closing connection: %s", e)
            finally:
                self.conn = None


# ==================== ОСНОВНОЙ КЛАСС ====================

class Database:
    """Асинхронный класс для работы с SQLite через aiosqlite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DATABASE_PATH
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._cache = ShardedLRUCache()
        self._pool: Optional[ConnectionPool] = None
        self.metrics = DatabaseMetrics()

    # ==================== СОЕДИНЕНИЕ ====================

    async def _get_pool(self) -> ConnectionPool:
        if self._pool is None:
            self._pool = ConnectionPool(self.db_path)
        return self._pool

    async def connection_context(self) -> AsyncConnectionContext:
        pool = await self._get_pool()
        return AsyncConnectionContext(pool)

    # ==================== КЭШ ====================

    async def _cache_get(self, key: str, cache_type: str) -> Optional[Any]:
        value = await self._cache.get(key)
        if value is not None:
            self.metrics.record_cache_hit(cache_type)
        else:
            self.metrics.record_cache_miss(cache_type)
        return value

    async def _cache_set(self, key: str, value: Any, cache_type: str) -> None:
        ttls = {
            "balance": CACHE_TTL_BALANCE,
            "stats": CACHE_TTL_STATS,
            "profile": CACHE_TTL_PROFILE
        }
        ttl = ttls.get(cache_type, CACHE_TTL_STATS)
        await self._cache.set(key, value, ttl)

    async def _invalidate_stats_cache(self, user_id: Optional[int] = None) -> None:
        if user_id is None:
            await self._cache.clear_pattern("user_stats:")
            await self._cache.clear_pattern("balance:")
            await self._cache.clear_pattern("profile:")
        else:
            await self._cache.delete("user_stats:" + str(user_id))
            await self._cache.delete("balance:" + str(user_id))
            await self._cache.delete("profile:" + str(user_id))

    # ==================== ВНУТРЕННИЕ МЕТОДЫ ====================

    async def _execute_with_retry(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = False
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]], int]]:
        if not self.db_path:
            raise DatabaseError("Database path is not set")
        if params is None:
            params = ()
        
        last_error: Optional[Exception] = None
        
        for attempt in range(MAX_RETRIES):
            try:
                start = time.time()
                pool = await self._get_pool()
                async with AsyncConnectionContext(pool) as conn:
                    cursor = await conn.execute(query, params)
                    
                    if commit:
                        await conn.commit()
                    
                    result = None
                    if fetch_one:
                        row = await cursor.fetchone()
                        result = dict(row) if row else None
                    elif fetch_all:
                        rows = await cursor.fetchall()
                        result = [dict(r) for r in rows] if rows else []
                    else:
                        result = cursor.rowcount
                    
                    duration = time.time() - start
                    self.metrics.query_count += 1
                    self.metrics.total_query_time += duration
                    
                    if duration > SLOW_QUERY_THRESHOLD:
                        self.metrics.slow_query_count += 1
                        qp = query[:100].replace('\n', ' ')
                        logger.warning("Slow query (%.2fs): %s...", duration, qp)
                    
                    return result
                    
            except aiosqlite.OperationalError as e:
                last_error = e
                if "database is locked" in str(e).lower() and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY_BASE * (2 ** attempt) + random.uniform(0, 0.1)
                    self.metrics.retry_count += 1
                    logger.warning(
                        "Database locked, retry %s/%s after %.2fs",
                        attempt + 1, MAX_RETRIES, wait_time
                    )
                    await asyncio.sleep(wait_time)
                    continue
                self.metrics.error_count += 1
                logger.error("DB operational error: %s", e)
                raise DatabaseError("Database error: " + str(e)) from e
            except Exception as e:
                last_error = e
                self.metrics.error_count += 1
                logger.error("Unexpected DB error: %s", e)
                raise DatabaseError("Unexpected error: " + str(e)) from e
        
        self.metrics.error_count += 1
        raise DatabaseError(
            "Max retries exceeded. Last error: " + str(last_error)
        )

    async def _insert_get_id(self, query: str, params: tuple) -> Optional[int]:
        pool = await self._get_pool()
        async with AsyncConnectionContext(pool) as conn:
            cursor = await conn.execute(query, params)
            row_id = cursor.lastrowid
            await conn.commit()
            return row_id

    async def _execute_transaction(
        self, queries: List[Tuple[str, tuple]], use_immediate: bool = True
    ) -> bool:
        if not self.db_path:
            raise DatabaseError("Database path is not set")
        
        pool = await self._get_pool()
        async with AsyncConnectionContext(pool) as conn:
            try:
                await conn.execute(
                    SQL_QUERIES.BEGIN_IMMEDIATE if use_immediate else "BEGIN"
                )
                for query, params in queries:
                    await conn.execute(query, params)
                await conn.commit()
                self.metrics.transaction_count += 1
                await self._invalidate_stats_cache()
                return True
            except Exception as e:
                await conn.rollback()
                self.metrics.error_count += 1
                logger.error("Transaction failed: %s", e)
                raise DatabaseError("Transaction failed: " + str(e)) from e

    async def _execute_batch(
        self, query_template: str, batch_params: List[tuple], atomic: bool = False
    ) -> int:
        processed = 0
        pool = await self._get_pool()
        async with AsyncConnectionContext(pool) as conn:
            try:
                if atomic:
                    await conn.execute("BEGIN")
                for i, params in enumerate(batch_params):
                    await conn.execute(query_template, params)
                    processed += 1
                    if not atomic and (i + 1) % COMMIT_EVERY == 0:
                        await conn.commit()
                if atomic:
                    await conn.commit()
                return processed
            except Exception as e:
                if atomic:
                    await conn.rollback()
                    logger.error("Batch operation rolled back: %s", e)
                raise

    async def _table_exists(self, table_name: str) -> bool:
        result = await self._execute_with_retry(
            SQL_QUERIES.TABLE_EXISTS, (table_name,), fetch_one=True
        )
        return result is not None

    # ==================== БЭКАП ====================

    async def _backup_database(self) -> Optional[str]:
        if not self.db_path or not os.path.exists(self.db_path):
            return None
        backup_path = (
            self.db_path + ".backup-" +
            datetime.now().strftime('%Y%m%d-%H%M%S')
        )
        try:
            shutil.copy2(self.db_path, backup_path)
            logger.info("Backup: %s", backup_path)
            return backup_path
        except Exception as e:
            logger.error("Backup failed: %s", e)
            return None

    # ==================== ИНИЦИАЛИЗАЦИЯ ====================

    async def initialize(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            
            if self.db_path:
                db_dir = os.path.dirname(self.db_path)
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)
            
            await self._create_tables()
            await self._backup_database()
            await self._run_migrations()
            await self._create_indexes()
            await self._add_default_data()
            
            self._initialized = True
            logger.info("✅ Database initialized")

    async def _create_tables(self) -> None:
        tables = [
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "version INTEGER PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
            "CREATE TABLE IF NOT EXISTS users ("
            "user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, "
            "balance INTEGER DEFAULT 1000 CHECK(balance >= 0), "
            "daily_streak INTEGER DEFAULT 0, last_daily TEXT, "
            "vip_level INTEGER DEFAULT 0, vip_until TEXT, "
            "wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, "
            "register_date TEXT, warns TEXT DEFAULT '[]', "
            "xp INTEGER DEFAULT 0, rank INTEGER DEFAULT 1"
            ")",
            "CREATE TABLE IF NOT EXISTS transactions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "from_id INTEGER, to_id INTEGER, amount INTEGER, reason TEXT, date TEXT, "
            "FOREIGN KEY (from_id) REFERENCES users(user_id), "
            "FOREIGN KEY (to_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS shop_items ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT, price INTEGER, description TEXT"
            ")",
            "CREATE TABLE IF NOT EXISTS user_profiles ("
            "user_id INTEGER PRIMARY KEY, "
            "full_name TEXT, age INTEGER, city TEXT, timezone TEXT, about TEXT, "
            "created_at TEXT, updated_at TEXT, "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS user_stats ("
            "user_id INTEGER PRIMARY KEY, "
            "messages_total INTEGER DEFAULT 0, messages_today INTEGER DEFAULT 0, "
            "messages_week INTEGER DEFAULT 0, messages_month INTEGER DEFAULT 0, "
            "last_message_date TEXT, register_date TEXT, last_active TEXT, "
            "total_voice INTEGER DEFAULT 0, total_stickers INTEGER DEFAULT 0, "
            "total_gifs INTEGER DEFAULT 0, total_photos INTEGER DEFAULT 0, "
            "total_videos INTEGER DEFAULT 0, days_active INTEGER DEFAULT 0, "
            "current_streak INTEGER DEFAULT 0, max_streak INTEGER DEFAULT 0, "
            "last_streak_update TEXT, "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS user_activity_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, chat_id BIGINT NOT NULL, date TEXT NOT NULL, "
            "messages INTEGER DEFAULT 0, voice INTEGER DEFAULT 0, "
            "stickers INTEGER DEFAULT 0, gifs INTEGER DEFAULT 0, "
            "photos INTEGER DEFAULT 0, videos INTEGER DEFAULT 0, "
            "games_played INTEGER DEFAULT 0, xo_games INTEGER DEFAULT 0, "
            "UNIQUE(user_id, chat_id, date), "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS xo_stats ("
            "user_id INTEGER PRIMARY KEY, "
            "games_played INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, "
            "losses INTEGER DEFAULT 0, draws INTEGER DEFAULT 0, "
            "wins_vs_bot INTEGER DEFAULT 0, losses_vs_bot INTEGER DEFAULT 0, "
            "total_bet INTEGER DEFAULT 0, total_won INTEGER DEFAULT 0, "
            "max_win_streak INTEGER DEFAULT 0, current_win_streak INTEGER DEFAULT 0, "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS user_economy_stats ("
            "user_id INTEGER PRIMARY KEY, "
            "total_earned INTEGER DEFAULT 0, total_spent INTEGER DEFAULT 0, "
            "total_transferred INTEGER DEFAULT 0, total_received INTEGER DEFAULT 0, "
            "total_donated_rub INTEGER DEFAULT 0, total_donated_coins INTEGER DEFAULT 0, "
            "max_balance INTEGER DEFAULT 0, daily_claims INTEGER DEFAULT 0, "
            "vip_purchases INTEGER DEFAULT 0, "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS chat_daily_summary ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "chat_id BIGINT NOT NULL, date TEXT NOT NULL, "
            "total_messages INTEGER DEFAULT 0, active_users INTEGER DEFAULT 0, "
            "top_words TEXT, top_users TEXT, "
            "rp_actions INTEGER DEFAULT 0, xo_games INTEGER DEFAULT 0, "
            "UNIQUE(chat_id, date)"
            ")",
            "CREATE TABLE IF NOT EXISTS chat_word_stats ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "chat_id BIGINT NOT NULL, date TEXT NOT NULL, "
            "word TEXT NOT NULL, count INTEGER DEFAULT 1, "
            "UNIQUE(chat_id, date, word)"
            ")",
            "CREATE TABLE IF NOT EXISTS custom_rp ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, command TEXT NOT NULL, "
            "action_text TEXT NOT NULL, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE(user_id, command), "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS tag_categories ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, "
            "description TEXT, icon_emoji TEXT DEFAULT '🔔', "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
            "CREATE TABLE IF NOT EXISTS chat_tag_settings ("
            "chat_id BIGINT NOT NULL, category_slug TEXT NOT NULL, "
            "is_enabled BOOLEAN DEFAULT 0, "
            "PRIMARY KEY (chat_id, category_slug)"
            ")",
            "CREATE TABLE IF NOT EXISTS user_tag_subscriptions ("
            "user_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, "
            "category_slug TEXT NOT NULL, is_subscribed BOOLEAN DEFAULT 1, "
            "PRIMARY KEY (user_id, chat_id, category_slug)"
            ")",
            "CREATE TABLE IF NOT EXISTS chat_rating ("
            "chat_id BIGINT PRIMARY KEY, chat_title TEXT, "
            "activity_points INTEGER DEFAULT 0, members_count INTEGER DEFAULT 0, "
            "games_played INTEGER DEFAULT 0, messages_count INTEGER DEFAULT 0, "
            "week_activity INTEGER DEFAULT 0, month_activity INTEGER DEFAULT 0, "
            "owner_id INTEGER, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
            "CREATE TABLE IF NOT EXISTS chat_rewards ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "chat_id BIGINT NOT NULL, reward_type TEXT, "
            "reward_amount INTEGER, awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
            "CREATE TABLE IF NOT EXISTS donors ("
            "user_id INTEGER PRIMARY KEY, "
            "total_donated INTEGER DEFAULT 0, last_donate TIMESTAMP, "
            "donor_rank TEXT DEFAULT '💎 Поддерживающий', "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS ref_links ("
            "user_id INTEGER, chat_id INTEGER, ref_code TEXT UNIQUE, "
            "invited_count INTEGER DEFAULT 0, earned_coins INTEGER DEFAULT 0, "
            "created_at TEXT, PRIMARY KEY (user_id, chat_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS ref_invites ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "inviter_id INTEGER, invited_id INTEGER, chat_id INTEGER, invited_at TEXT"
            ")",
            "CREATE TABLE IF NOT EXISTS relationships ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user1_id INTEGER NOT NULL, user2_id INTEGER NOT NULL, "
            "type TEXT NOT NULL, status TEXT DEFAULT 'pending', "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "ended_at TIMESTAMP, confirmed_by_user2 BOOLEAN DEFAULT 0, "
            "UNIQUE(user1_id, user2_id, type)"
            ")",
            "CREATE TABLE IF NOT EXISTS groups ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "chat_id BIGINT NOT NULL, group_name TEXT NOT NULL, "
            "group_leader INTEGER NOT NULL, member_count INTEGER DEFAULT 1, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
            "CREATE TABLE IF NOT EXISTS group_members ("
            "group_id INTEGER, user_id INTEGER, "
            "joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (group_id, user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS feedback_tickets ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, message TEXT NOT NULL, "
            "status TEXT DEFAULT 'open', "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "answered_at TIMESTAMP, admin_response TEXT, "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS user_tags ("
            "user_id INTEGER NOT NULL, tag_name TEXT NOT NULL, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (user_id, tag_name), "
            "FOREIGN KEY (user_id) REFERENCES users(user_id)"
            ")",
            "CREATE TABLE IF NOT EXISTS admin_logs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "admin_id INTEGER NOT NULL, action TEXT NOT NULL, "
            "chat_id BIGINT, target_user_id INTEGER, details TEXT, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
        ]
        for sql in tables:
            await self._execute_with_retry(sql)
        logger.info("Created %s tables", len(tables))

    async def _create_indexes(self) -> None:
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_activity_log_user_chat_date "
            "ON user_activity_log(user_id, chat_id, date);",
            "CREATE INDEX IF NOT EXISTS idx_activity_log_chat_date "
            "ON user_activity_log(chat_id, date);",
            "CREATE INDEX IF NOT EXISTS idx_activity_log_date "
            "ON user_activity_log(date);",
            "CREATE INDEX IF NOT EXISTS idx_chat_words_chat_date "
            "ON chat_word_stats(chat_id, date);",
            "CREATE INDEX IF NOT EXISTS idx_transactions_from_id "
            "ON transactions(from_id);",
            "CREATE INDEX IF NOT EXISTS idx_transactions_to_id "
            "ON transactions(to_id);",
            "CREATE INDEX IF NOT EXISTS idx_transactions_date "
            "ON transactions(date);",
            "CREATE INDEX IF NOT EXISTS idx_custom_rp_command "
            "ON custom_rp(command);",
            "CREATE INDEX IF NOT EXISTS idx_custom_rp_user_id "
            "ON custom_rp(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_users_username "
            "ON users(username);",
            "CREATE INDEX IF NOT EXISTS idx_users_rank "
            "ON users(rank DESC);",
            "CREATE INDEX IF NOT EXISTS idx_users_balance "
            "ON users(balance DESC);",
            "CREATE INDEX IF NOT EXISTS idx_users_xp "
            "ON users(xp DESC);",
            "CREATE INDEX IF NOT EXISTS idx_user_stats_last_active "
            "ON user_stats(last_active);",
            "CREATE INDEX IF NOT EXISTS idx_user_stats_messages "
            "ON user_stats(messages_total DESC);",
            "CREATE INDEX IF NOT EXISTS idx_relationships_users "
            "ON relationships(user1_id, user2_id);",
            "CREATE INDEX IF NOT EXISTS idx_relationships_status "
            "ON relationships(status);",
            "CREATE INDEX IF NOT EXISTS idx_feedback_status "
            "ON feedback_tickets(status);",
            "CREATE INDEX IF NOT EXISTS idx_feedback_user "
            "ON feedback_tickets(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_xo_wins "
            "ON xo_stats(wins DESC);",
        ]
        
        critical_errors = []
        for sql in indexes:
            try:
                await self._execute_with_retry(sql)
            except Exception as e:
                error_msg = "Index creation failed: " + sql[:80] + "... — " + str(e)
                logger.error(error_msg)
                critical_errors.append(error_msg)
        
        if critical_errors:
            raise MigrationError(
                "Failed to create " + str(len(critical_errors)) +
                " indexes: " + "; ".join(critical_errors[:3])
            )
        
        logger.info("Created %s indexes", len(indexes))

    async def _run_migrations(self) -> None:
        await self._execute_with_retry(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "version INTEGER PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        
        row = await self._execute_with_retry(
            SQL_QUERIES.GET_MIGRATION_VERSION, fetch_one=True
        )
        current_version = row["version"] if row else 0
        
        migrations = {
            1: {
                "users": {"xp": "INTEGER DEFAULT 0", "rank": "INTEGER DEFAULT 1"},
                "xo_stats": {
                    "total_bet": "INTEGER DEFAULT 0",
                    "total_won": "INTEGER DEFAULT 0",
                    "max_win_streak": "INTEGER DEFAULT 0",
                    "current_win_streak": "INTEGER DEFAULT 0",
                },
                "user_economy_stats": {
                    "total_earned": "INTEGER DEFAULT 0",
                    "total_spent": "INTEGER DEFAULT 0",
                    "total_transferred": "INTEGER DEFAULT 0",
                    "total_received": "INTEGER DEFAULT 0",
                    "total_donated_rub": "INTEGER DEFAULT 0",
                    "total_donated_coins": "INTEGER DEFAULT 0",
                    "max_balance": "INTEGER DEFAULT 0",
                    "daily_claims": "INTEGER DEFAULT 0",
                    "vip_purchases": "INTEGER DEFAULT 0",
                },
                "user_stats": {
                    "total_voice": "INTEGER DEFAULT 0",
                    "total_stickers": "INTEGER DEFAULT 0",
                    "total_gifs": "INTEGER DEFAULT 0",
                    "total_photos": "INTEGER DEFAULT 0",
                    "total_videos": "INTEGER DEFAULT 0",
                    "days_active": "INTEGER DEFAULT 0",
                    "current_streak": "INTEGER DEFAULT 0",
                    "max_streak": "INTEGER DEFAULT 0",
                    "last_streak_update": "TEXT",
                },
                "user_activity_log": {"chat_id": "BIGINT NOT NULL DEFAULT 0"},
                "chat_rating": {"owner_id": "INTEGER"},
                "relationships": {
                    "status": "TEXT DEFAULT 'pending'",
                    "confirmed_by_user2": "BOOLEAN DEFAULT 0",
                }
            }
        }
        
        for version in range(current_version + 1, max(migrations.keys()) + 1):
            if version not in migrations:
                continue
            
            logger.info("Migration v%s...", version)
            critical_errors = []
            applied_tables = []
            
            for table, cols in migrations[version].items():
                if not await self._table_exists(table):
                    critical_errors.append("Table '" + table + "' not found")
                    continue
                
                try:
                    rows = await self._execute_with_retry(
                        SQL_QUERIES.PRAGMA_TABLE_INFO.format(table=table),
                        fetch_all=True
                    )
                    if rows is None:
                        critical_errors.append(
                            "Schema query failed for '" + table + "'"
                        )
                        continue
                    
                    existing = {row["name"] for row in rows}
                    
                    for col_name, col_def in cols.items():
                        if col_name not in existing:
                            await self._execute_with_retry(
                                SQL_QUERIES.ALTER_TABLE.format(
                                    table=table, column=col_name, definition=col_def
                                )
                            )
                            logger.info("✅ Added %s to %s", col_name, table)
                            applied_tables.append(table)
                except DatabaseError as e:
                    critical_errors.append("Table '" + table + "': " + str(e))
            
            if critical_errors:
                for table in applied_tables:
                    logger.warning(
                        "Rollback: migration v%s failed, changes to %s may remain",
                        version, table
                    )
                raise MigrationError(
                    "v" + str(version) + ": " + "; ".join(critical_errors)
                )
            
            await self._insert_get_id(
                SQL_QUERIES.INSERT_MIGRATION,
                (version, datetime.now().isoformat())
            )
            logger.info("✅ Migration v%s applied", version)

    async def _add_default_data(self) -> None:
        row = await self._execute_with_retry(
            SQL_QUERIES.SHOP_ITEMS_COUNT, fetch_one=True
        )
        if row and row.get("cnt", 0) == 0:
            queries = [
                (SQL_QUERIES.INSERT_SHOP_ITEM, (n, p, d))
                for n, p, d in DEFAULT_SHOP_ITEMS
            ]
            await self._execute_transaction(queries)
        
        row = await self._execute_with_retry(
            SQL_QUERIES.TAG_CATEGORIES_COUNT, fetch_one=True
        )
        if row and row.get("cnt", 0) == 0:
            queries = [
                (SQL_QUERIES.INSERT_TAG_CATEGORY, (s, n, d, i))
                for s, n, d, i in DEFAULT_CATEGORIES
            ]
            await self._execute_transaction(queries)

    # ==================== ОСНОВНЫЕ МЕТОДЫ ====================

    async def get_user(self, user_id: int) -> Optional[UserDict]:
        validate_user_id(user_id)
        return await self._execute_with_retry(
            SQL_QUERIES.GET_USER, (user_id,), fetch_one=True
        )

    async def get_user_by_username(self, username: str) -> Optional[UserDict]:
        username = validate_username(username)
        if not username:
            return None
        return await self._execute_with_retry(
            SQL_QUERIES.GET_USER_BY_USERNAME, (username,), fetch_one=True
        )

    async def get_user_by_id_or_username(self, identifier: str) -> Optional[UserDict]:
        if not identifier:
            return None
        try:
            uid = int(identifier)
            if uid > 0:
                return await self.get_user(uid)
        except (ValueError, TypeError):
            pass
        return await self.get_user_by_username(identifier)

    async def create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        balance: int = 1000
    ) -> bool:
        validate_user_id(user_id)
        username = validate_username(username)
        first_name = validate_first_name(first_name)
        if balance < 0:
            raise ValidationError("balance must be >= 0")
        if await self.user_exists(user_id):
            return False
        
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        
        queries = [
            (SQL_QUERIES.INSERT_USER,
             (user_id, username, first_name, balance, now, '[]', 0, 1)),
            (SQL_QUERIES.INSERT_PROFILE, (user_id, now, now)),
            (SQL_QUERIES.INSERT_STATS, (user_id, today, now)),
            (SQL_QUERIES.INSERT_ECONOMY, (user_id, balance)),
            (SQL_QUERIES.INSERT_XO_STATS, (user_id,)),
        ]
        await self._execute_transaction(queries)
        logger.info("✅ Created user %s", user_id)
        return True

    async def user_exists(self, user_id: int) -> bool:
        validate_user_id(user_id)
        result = await self._execute_with_retry(
            SQL_QUERIES.USER_EXISTS, (user_id,), fetch_one=True
        )
        return result is not None

    async def get_balance(self, user_id: int) -> int:
        validate_user_id(user_id)
        
        cache_key = "balance:" + str(user_id)
        cached = await self._cache_get(cache_key, "balance")
        if cached is not None:
            return cached
        
        if not await self.user_exists(user_id):
            return 0
        
        user = await self.get_user(user_id)
        balance = user.get("balance", 0) if user else 0
        await self._cache_set(cache_key, balance, "balance")
        return balance

    async def update_balance(self, user_id: int, delta: int, reason: str = "") -> bool:
        validate_user_id(user_id)
        if delta is None:
            return False
        
        if delta < 0:
            current = await self.get_balance(user_id)
            if current + delta < 0:
                raise InsufficientFundsError(
                    "Insufficient funds: balance=" + str(current) +
                    ", delta=" + str(delta)
                )
        
        now = datetime.now().isoformat()
        queries = [
            (SQL_QUERIES.UPDATE_BALANCE, (delta, user_id)),
            (SQL_QUERIES.UPDATE_MAX_BALANCE,
             (user_id, max(0, delta), user_id)),
        ]
        if delta < 0:
            queries.append(
                (SQL_QUERIES.UPDATE_TOTAL_SPENT, (abs(delta), user_id))
            )
        if reason:
            queries.append(
                (SQL_QUERIES.INSERT_TRANSACTION,
                 (user_id, user_id, abs(delta), reason, now))
            )
        
        success = await self._execute_transaction(queries)
        if success:
            await self._invalidate_stats_cache(user_id)
        return success

    async def transfer_coins(
        self,
        from_id: int,
        to_username: str,
        amount: int,
        reason: str = "transfer"
    ) -> TransferResultDict:
        validate_user_id(from_id)
        
        result: TransferResultDict = {
            'success': False,
            'error': None,
            'new_from_balance': None,
            'new_to_balance': None
        }
        
        to_username = validate_username(to_username)
        if not to_username:
            result['error'] = "Invalid username"
            return result
        if not amount or amount <= 0:
            result['error'] = "Amount must be > 0"
            return result
        
        target = await self.get_user_by_username(to_username)
        if not target:
            result['error'] = "User @" + to_username + " not found"
            return result
        
        to_id = target.get("user_id")
        if not to_id or from_id == to_id:
            result['error'] = "Cannot transfer to self"
            return result
        
        pool = await self._get_pool()
        async with AsyncConnectionContext(pool) as conn:
            try:
                await conn.execute(SQL_QUERIES.BEGIN_IMMEDIATE)
                
                cursor = await conn.execute(
                    SQL_QUERIES.GET_USER_BALANCE, (from_id,)
                )
                row = await cursor.fetchone()
                if not row or row["balance"] < amount:
                    await conn.rollback()
                    result['error'] = "Insufficient funds"
                    return result
                
                await conn.execute(
                    SQL_QUERIES.UPDATE_BALANCE, (-amount, from_id)
                )
                await conn.execute(
                    SQL_QUERIES.UPDATE_BALANCE, (amount, to_id)
                )
                
                now = datetime.now().isoformat()
                await conn.execute(
                    SQL_QUERIES.INSERT_TRANSACTION,
                    (from_id, to_id, amount, reason, now)
                )
                
                await conn.execute(
                    "UPDATE user_economy_stats "
                    "SET total_transferred = COALESCE(total_transferred, 0) + ? "
                    "WHERE user_id = ?",
                    (amount, from_id)
                )
                await conn.execute(
                    "UPDATE user_economy_stats "
                    "SET total_received = COALESCE(total_received, 0) + ? "
                    "WHERE user_id = ?",
                    (amount, to_id)
                )
                
                await conn.commit()
                
                await self._invalidate_stats_cache(from_id)
                await self._invalidate_stats_cache(to_id)
                
                from_bal = await conn.execute(
                    SQL_QUERIES.GET_USER_BALANCE, (from_id,)
                )
                to_bal = await conn.execute(
                    SQL_QUERIES.GET_USER_BALANCE, (to_id,)
                )
                from_row = await from_bal.fetchone()
                to_row = await to_bal.fetchone()
                
                result.update({
                    'success': True,
                    'new_from_balance': (
                        from_row["balance"] if from_row else None
                    ),
                    'new_to_balance': (
                        to_row["balance"] if to_row else None
                    )
                })
                return result
                
            except Exception as e:
                await conn.rollback()
                result['error'] = str(e)
                logger.error("Transfer failed: %s", e)
                return result
            finally:
                self.metrics.transaction_count += 1

    # ==================== ПРОФИЛИ ====================

    async def save_profile(
        self,
        user_id: int,
        full_name: str,
        age: int,
        city: str,
        timezone: str,
        about: str
    ) -> bool:
        validate_user_id(user_id)
        if age is not None and (age < 0 or age > 120):
            raise ValidationError("Age must be 0-120")
        if about and len(about) > MAX_ABOUT_LENGTH:
            raise ValidationError(
                "About must be <= " + str(MAX_ABOUT_LENGTH) + " chars"
            )
        
        now = datetime.now().isoformat()
        row = await self._execute_with_retry(
            SQL_QUERIES.GET_PROFILE_CREATED, (user_id,), fetch_one=True
        )
        created_at = row["created_at"] if row and row.get("created_at") else now
        
        success = await self._execute_with_retry(
            SQL_QUERIES.UPSERT_PROFILE,
            (user_id, full_name or "", age or 0, city or "",
             timezone or "", about or "", created_at, now),
            commit=True
        )
        if success:
            await self._invalidate_stats_cache(user_id)
        return bool(success)

    async def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        validate_user_id(user_id)
        
        cache_key = "profile:" + str(user_id)
        cached = await self._cache_get(cache_key, "profile")
        if cached is not None:
            return cached
        
        result = await self._execute_with_retry(
            SQL_QUERIES.GET_PROFILE, (user_id,), fetch_one=True
        )
        if result:
            await self._cache_set(cache_key, result, "profile")
        return result

    # ==================== РАНГИ ====================

    @staticmethod
    def calculate_rank(
        xp: int, messages: int, xo_wins: int, days_active: int
    ) -> int:
        """
        Formula: Score = XP + messages*2 + xo_wins*10 + days_active*5
        Rank = (Score // 100) + 1, clamped to [1, 100]
        """
        score = (
            (xp or 0) +
            (messages or 0) * 2 +
            (xo_wins or 0) * 10 +
            (days_active or 0) * 5
        )
        return min(max((score // 100) + 1, 1), 100)

    async def recalculate_user_rank(self, user_id: int) -> Optional[int]:
        validate_user_id(user_id)
        
        stats = await self.get_user_stats(user_id)
        if not stats:
            return None
        
        new_rank = self.calculate_rank(
            xp=stats.get('xp', 0),
            messages=stats.get('messages_total', 0),
            xo_wins=stats.get('wins', 0),
            days_active=stats.get('days_active', 0)
        )
        
        await self._execute_with_retry(
            SQL_QUERIES.UPDATE_RANK, (new_rank, user_id), commit=True
        )
        return new_rank

    async def get_user_rank(self, user_id: int) -> Optional[Dict[str, Any]]:
        validate_user_id(user_id)
        
        user = await self.get_user(user_id)
        if not user:
            return None
        
        stats = await self.get_user_stats(user_id) or {}
        cr = user.get('rank', 1)
        calc = self.calculate_rank(
            xp=stats.get('xp', 0),
            messages=stats.get('messages_total', 0),
            xo_wins=stats.get('wins', 0),
            days_active=stats.get('days_active', 0)
        )
        
        return {
            'user_id': user_id,
            'username': user.get('username'),
            'current_rank': cr,
            'calculated_rank': calc,
            'xp': stats.get('xp', 0),
            'messages': stats.get('messages_total', 0),
            'xo_wins': stats.get('wins', 0),
            'days_active': stats.get('days_active', 0),
            'needs_recalc': cr != calc
        }

    async def add_xp(
        self, user_id: int, xp_amount: int, reason: str = "activity"
    ) -> bool:
        validate_user_id(user_id)
        if xp_amount is None or xp_amount <= 0:
            return False
        
        success = await self._execute_with_retry(
            SQL_QUERIES.ADD_XP, (xp_amount, user_id), commit=True
        )
        if success:
            await self.recalculate_user_rank(user_id)
        return bool(success)

    # ==================== XO STATS ====================

    async def update_xo_stats(
        self, user_id: int, result: str, bet: int, won: int
    ) -> bool:
        """
        Обновление статистики крестиков-ноликов.
        
        Args:
            user_id: ID игрока
            result: Тип результата (win, loss, draw, win_vs_bot, loss_vs_bot)
            bet: Сумма ставки
            won: Сумма выигрыша
        
        Returns:
            True если обновление успешно
        """
        if user_id is None:
            return False
        
        result_map = {
            "win": SQL_QUERIES.UPDATE_XO_WIN,
            "loss": SQL_QUERIES.UPDATE_XO_LOSS,
            "draw": SQL_QUERIES.UPDATE_XO_DRAW,
            "win_vs_bot": SQL_QUERIES.UPDATE_XO_WIN_VS_BOT,
            "loss_vs_bot": SQL_QUERIES.UPDATE_XO_LOSS_VS_BOT,
        }
        
        query = result_map.get(result)
        if not query:
            logger.warning("Unknown XO result type: %s", result)
            return False
        
        try:
            if result in ("win", "win_vs_bot"):
                await self._execute_with_retry(
                    query, (bet, won, user_id), commit=True
                )
            elif result in ("loss", "draw", "loss_vs_bot"):
                await self._execute_with_retry(
                    query, (bet, user_id), commit=True
                )
            
            await self._invalidate_stats_cache(user_id)
            return True
        except DatabaseError as e:
            logger.error(
                "XO stats update failed for user %s: %s", user_id, e
            )
            return False

    # ==================== ТРЕКИНГ ====================

    async def track_user_activity(
        self,
        user_id: int,
        chat_id: int,
        activity_type: str,
        value: int = 1
    ) -> bool:
        if user_id is None or chat_id is None or not activity_type:
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        column = ACTIVITY_COLUMN_MAP.get(activity_type)
        
        if column not in VALID_ACTIVITY_COLUMNS:
            return False
        
        try:
            query = SQL_QUERIES.TRACK_ACTIVITY_TEMPLATE.format(column=column)
            await self._execute_with_retry(
                query, (user_id, chat_id, today, value, value), commit=True
            )
            
            if activity_type == "message":
                await self._execute_with_retry(
                    SQL_QUERIES.UPDATE_MESSAGE_STATS,
                    (today, datetime.now().isoformat(), user_id),
                    commit=True
                )
            else:
                stat_col = STAT_COLUMN_MAP.get(activity_type)
                if stat_col in VALID_STAT_COLUMNS:
                    stat_query = (
                        SQL_QUERIES.UPDATE_ACTIVITY_STATS_TEMPLATE
                        .format(column=stat_col)
                    )
                    await self._execute_with_retry(
                        stat_query,
                        (value, datetime.now().isoformat(), user_id),
                        commit=True
                    )
            
            return True
        except Exception as e:
            logger.error("Activity tracking failed: %s", e)
            return False

    async def track_word(self, chat_id: int, word: str) -> bool:
        if chat_id is None or not word or len(word.strip()) < 3:
            return False
        
        await self._execute_with_retry(
            SQL_QUERIES.TRACK_WORD,
            (chat_id, datetime.now().strftime("%Y-%m-%d"), word.lower().strip()),
            commit=True
        )
        return True

    # ==================== СТАТИСТИКА ====================

    async def get_user_stats(self, user_id: int) -> Optional[UserStatsDict]:
        validate_user_id(user_id)
        
        cache_key = "user_stats:" + str(user_id)
        cached = await self._cache_get(cache_key, "stats")
        if cached is not None:
            return cached
        
        result = await self._execute_with_retry(
            SQL_QUERIES.GET_USER_STATS, (user_id,), fetch_one=True
        )
        
        if result:
            result['calculated_rank'] = self.calculate_rank(
                xp=result.get('xp', 0),
                messages=result.get('messages_total', 0),
                xo_wins=result.get('wins', 0),
                days_active=result.get('days_active', 0)
            )
            await self._cache_set(cache_key, result, "stats")
            return result
        
        user = await self.get_user(user_id)
        if user:
            default: UserStatsDict = {
                'user_id': user_id,
                'username': user.get('username'),
                'first_name': user.get('first_name'),
                'balance': user.get('balance', 0),
                'daily_streak': user.get('daily_streak', 0),
                'vip_level': user.get('vip_level', 0),
                'xp': 0,
                'rank': 1,
                'messages_total': 0,
                'messages_today': 0,
                'wins': 0,
                'games_played': 0,
                'days_active': 0,
                'current_streak': 0,
                'calculated_rank': 1
            }
            await self._cache_set(cache_key, default, "stats")
            return default
        
        return None

    # ==================== ТОПЫ ====================

    async def get_top_users(
        self, limit: int = 10, order_by: str = "balance"
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(100, limit or 10))
        if order_by not in VALID_ORDER_COLUMNS:
            order_by = "balance"
        
        order_map = {
            "balance": "u.balance DESC",
            "xp": "u.xp DESC",
            "rank": "u.rank ASC",
            "messages": "COALESCE(s.messages_total, 0) DESC",
            "wins": "COALESCE(x.wins, 0) DESC",
            "activity": "COALESCE(s.days_active, 0) DESC"
        }
        
        order_clause = order_map.get(order_by, order_map["balance"])
        query = SQL_QUERIES.GET_TOP_USERS.format(order_clause=order_clause)
        
        return await self._execute_with_retry(
            query, (limit,), fetch_all=True
        ) or []

    async def get_chat_top_balance(
        self, chat_id: int, limit: int = 3
    ) -> List[Dict[str, Any]]:
        if chat_id is None:
            return []
        limit = max(1, min(20, limit or 3))
        return await self._execute_with_retry(
            SQL_QUERIES.GET_CHAT_TOP_BALANCE, (chat_id, limit), fetch_all=True
        ) or []

    async def get_chat_top_xo(
        self, chat_id: int, limit: int = 3
    ) -> List[Dict[str, Any]]:
        if chat_id is None:
            return []
        limit = max(1, min(20, limit or 3))
        return await self._execute_with_retry(
            SQL_QUERIES.GET_CHAT_TOP_XO, (chat_id, limit), fetch_all=True
        ) or []

    async def get_chat_top_messages(
        self, chat_id: int, limit: int = 3
    ) -> List[Dict[str, Any]]:
        if chat_id is None:
            return []
        limit = max(1, min(20, limit or 3))
        return await self._execute_with_retry(
            SQL_QUERIES.GET_CHAT_TOP_MESSAGES, (chat_id, limit), fetch_all=True
        ) or []

    # ==================== ОТНОШЕНИЯ ====================

    async def get_relationship(
        self, u1: int, u2: int, rt: str
    ) -> Optional[Dict[str, Any]]:
        if not u1 or not u2 or not rt:
            return None
        return await self._execute_with_retry(
            SQL_QUERIES.GET_RELATIONSHIP,
            (u1, u2, u2, u1, rt),
            fetch_one=True
        )

    async def propose_relationship(
        self, pid: int, tid: int, rt: str
    ) -> RelationshipResultDict:
        result: RelationshipResultDict = {
            'success': False, 'error': None, 'relationship_id': None
        }
        
        if not all([pid, tid, rt]):
            result['error'] = "Invalid parameters"
            return result
        if pid == tid:
            result['error'] = "Self relationship"
            return result
        
        ex = await self.get_relationship(pid, tid, rt)
        if ex:
            result['error'] = "Already " + ex.get('status', 'exists')
            result['relationship_id'] = ex.get('id')
            return result
        
        rid = await self._insert_get_id(
            SQL_QUERIES.INSERT_RELATIONSHIP,
            (pid, tid, rt, datetime.now().isoformat())
        )
        
        if rid:
            result.update({'success': True, 'relationship_id': rid})
        return result

    async def confirm_relationship(
        self, rid: int, cid: int, allow_either: bool = False
    ) -> bool:
        if not rid or not cid:
            return False
        
        rel = await self._execute_with_retry(
            SQL_QUERIES.GET_RELATIONSHIP_BY_ID, (rid,), fetch_one=True
        )
        if not rel or rel['status'] != 'pending':
            return False
        
        if allow_either:
            if cid not in (rel['user1_id'], rel['user2_id']):
                return False
        else:
            if rel['user2_id'] != cid:
                return False
        
        return bool(await self._execute_with_retry(
            SQL_QUERIES.CONFIRM_RELATIONSHIP, (rid,), commit=True
        ))

    async def get_relationship_status(
        self, uid: int, rt: str = "marriage"
    ) -> Optional[Dict[str, Any]]:
        if not uid:
            return None
        
        rel = await self._execute_with_retry(
            SQL_QUERIES.GET_RELATIONSHIP_STATUS,
            (uid, uid, rt),
            fetch_one=True
        )
        if not rel:
            return None
        
        is_u1 = rel['user1_id'] == uid
        pid = rel['user2_id'] if is_u1 else rel['user1_id']
        pname = (rel['user2_name'] if is_u1 else rel['user1_name']) or str(pid)
        
        return {
            'id': rel['id'],
            'partner_id': pid,
            'partner_name': pname,
            'type': rel['type'],
            'status': rel['status'],
            'is_initiator': is_u1,
            'can_cancel': rel['status'] == 'pending' and is_u1
        }

    async def end_relationship(
        self, uid: int, pid: int, rt: str
    ) -> bool:
        if not uid or not pid or not rt:
            return False
        return bool(await self._execute_with_retry(
            SQL_QUERIES.END_RELATIONSHIP,
            (uid, pid, pid, uid, rt),
            commit=True
        ))

    # ==================== ТЕГИ ====================

    async def add_user_tag(self, user_id: int, tag_name: str) -> bool:
        validate_user_id(user_id)
        if not tag_name:
            raise ValidationError("tag_name is required")
        
        tag_name = tag_name.strip().lower()
        if len(tag_name) < MIN_TAG_LENGTH or len(tag_name) > MAX_TAG_LENGTH:
            raise ValidationError(
                "Tag must be " + str(MIN_TAG_LENGTH) + "-" +
                str(MAX_TAG_LENGTH) + " chars"
            )
        
        return bool(await self._execute_with_retry(
            SQL_QUERIES.ADD_USER_TAG, (user_id, tag_name), commit=True
        ))

    async def remove_user_tag(self, user_id: int, tag_name: str) -> bool:
        validate_user_id(user_id)
        if not tag_name:
            return False
        return bool(await self._execute_with_retry(
            SQL_QUERIES.REMOVE_USER_TAG,
            (user_id, tag_name.strip().lower()),
            commit=True
        ))

    async def get_user_tags(self, user_id: int) -> List[str]:
        validate_user_id(user_id)
        rows = await self._execute_with_retry(
            SQL_QUERIES.GET_USER_TAGS, (user_id,), fetch_all=True
        )
        return [r["tag_name"] for r in rows] if rows else []

    async def search_users_by_tag(
        self, tag_name: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        if not tag_name:
            return []
        tag_name = tag_name.strip().lower()
        limit = max(1, min(50, limit))
        return await self._execute_with_retry(
            SQL_QUERIES.SEARCH_USERS_BY_TAG, (tag_name, limit), fetch_all=True
        ) or []

    # ==================== FEEDBACK ====================

    async def create_feedback_ticket(
        self, user_id: int, message: str
    ) -> Optional[int]:
        validate_user_id(user_id)
        if not message or len(message) < 10:
            return None
        return await self._execute_with_retry(
            SQL_QUERIES.CREATE_TICKET, (user_id, message.strip())
        )

    async def get_user_tickets(
        self, user_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        validate_user_id(user_id)
        return await self._execute_with_retry(
            SQL_QUERIES.GET_USER_TICKETS, (user_id, limit), fetch_all=True
        ) or []

    async def update_ticket(
        self,
        ticket_id: int,
        status: str,
        admin_response: Optional[str] = None
    ) -> bool:
        if not ticket_id or status not in ('open', 'closed', 'in_progress'):
            return False
        
        if admin_response and status == 'closed':
            return bool(await self._execute_with_retry(
                SQL_QUERIES.UPDATE_TICKET_CLOSED,
                (status, admin_response, datetime.now().isoformat(), ticket_id),
                commit=True
            ))
        
        return bool(await self._execute_with_retry(
            SQL_QUERIES.UPDATE_TICKET_STATUS,
            (status, ticket_id),
            commit=True
        ))

    async def get_pending_feedback(self, limit: int = 20) -> List[Dict[str, Any]]:
        return await self._execute_with_retry(
            SQL_QUERIES.GET_PENDING_TICKETS, (limit,), fetch_all=True
        ) or []

    # ==================== ПОЛИТИКА ====================

    @staticmethod
    def get_policy_section(section: str) -> str:
        return DEFAULT_POLICY_TEXT.get(section, "Раздел не найден.")

    @staticmethod
    def get_all_policy_sections() -> List[Dict[str, str]]:
        return [
            {"key": "rules", "title": "📜 Правила", "emoji": "📜"},
            {"key": "privacy", "title": "🔐 Конфиденциальность", "emoji": "🔐"},
            {"key": "moderation", "title": "⚖️ Модерация", "emoji": "⚖️"},
            {"key": "feedback", "title": "📬 Обратная связь", "emoji": "📬"},
            {"key": "contacts", "title": "👥 Контакты", "emoji": "👥"},
        ]

    # ==================== HEALTH & METRICS ====================

    async def health_check(self) -> HealthCheckDict:
        result: HealthCheckDict = {
            "status": "unknown",
            "latency_ms": None,
            "error": None,
            "metrics": None,
            "pool": None
        }
        
        if not self.db_path:
            result.update({"status": "unhealthy", "error": "DB path not set"})
            return result
        
        try:
            start = time.time()
            await self._execute_with_retry("SELECT 1", fetch_one=True)
            latency = (time.time() - start) * 1000
            
            pool_stats = self._pool.get_stats() if self._pool else {}
            
            result.update({
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "metrics": self.metrics.to_dict(),
                "pool": pool_stats
            })
            return result
        except Exception as e:
            pool_stats = self._pool.get_stats() if self._pool else {}
            result.update({
                "status": "unhealthy",
                "error": str(e),
                "metrics": self.metrics.to_dict(),
                "pool": pool_stats
            })
            return result

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics.to_dict()

    # ==================== ПРОЧЕЕ ====================

    async def get_custom_rp_action(
        self, command: str
    ) -> Optional[Tuple[int, str]]:
        if not command:
            return None
        result = await self._execute_with_retry(
            SQL_QUERIES.GET_CUSTOM_RP, (command.lower(),), fetch_one=True
        )
        return (result["user_id"], result["action_text"]) if result else None

    async def get_parser_triggers(self, chat_id: int) -> Dict[str, List[str]]:
        return {
            "greetings": ["привет", "здравствуй", "хай", "ку"],
            "farewells": ["пока", "до свидания", "чао"],
            "thanks": ["спасибо", "благодарю", "мерси"],
        }

    async def get_deletable_messages(
        self, chat_id: int, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if not chat_id:
            return []
        cutoff = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d")
        limit = max(1, min(100, limit))
        return await self._execute_with_retry(
            SQL_QUERIES.GET_DELETABLE_MESSAGES,
            (chat_id, cutoff, limit),
            fetch_all=True
        ) or []

    async def log_admin_action(
        self,
        admin_id: int,
        action: str,
        chat_id: Optional[int] = None,
        target_user_id: Optional[int] = None,
        details: Optional[str] = None
    ) -> None:
        try:
            await self._execute_with_retry(
                SQL_QUERIES.INSERT_ADMIN_LOG,
                (admin_id, action, chat_id, target_user_id, details),
                commit=True
            )
        except Exception as e:
            logger.error("Admin log failed: %s", e)

    async def get_admin_logs(
        self, limit: int = 50, admin_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(200, limit))
        if admin_id:
            return await self._execute_with_retry(
                SQL_QUERIES.GET_ADMIN_LOGS_BY_ADMIN,
                (admin_id, limit),
                fetch_all=True
            ) or []
        return await self._execute_with_retry(
            SQL_QUERIES.GET_ALL_ADMIN_LOGS, (limit,), fetch_all=True
        ) or []

    async def get_chat_daily_summary(
        self, chat_id: int, date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not chat_id:
            return None
        if date is None:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return await self._execute_with_retry(
            SQL_QUERIES.GET_DAILY_SUMMARY, (chat_id, date), fetch_one=True
        )

    async def save_daily_summary(
        self,
        chat_id: int,
        date: str,
        total_messages: int,
        active_users: int,
        top_words_json: str,
        top_users_json: str
    ) -> bool:
        if not chat_id or not date:
            return False
        return bool(await self._execute_with_retry(
            SQL_QUERIES.SAVE_DAILY_SUMMARY,
            (chat_id, date, total_messages, active_users,
             top_words_json, top_users_json),
            commit=True
        ))

    async def get_top_words(
        self, chat_id: int, date: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        if not chat_id:
            return []
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return await self._execute_with_retry(
            SQL_QUERIES.GET_TOP_WORDS, (chat_id, date, limit), fetch_all=True
        ) or []

    async def get_active_users_for_rank_update(self) -> List[int]:
        rows = await self._execute_with_retry(
            SQL_QUERIES.GET_ACTIVE_USERS, fetch_all=True
        )
        return [r["user_id"] for r in rows] if rows else []

    async def rollback_migration(self, version: int) -> bool:
        logger.warning(
            "Rollback metadata only for v%s. "
            "Schema changes require manual revert or backup restore.",
            version
        )
        await self._execute_with_retry(
            SQL_QUERIES.DELETE_MIGRATION, (version,), commit=True
        )
        return True

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Connection pool closed")
        
        await self._cache.clear_all()
        logger.info("Cache cleared")
        logger.info("Database resources closed")


# ==================== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ====================

db = Database()
