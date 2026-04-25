#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАЙЛ: database.py
ВЕРСИЯ: 3.2.1-final
ОПИСАНИЕ: Асинхронная база данных NEXUS Bot — ИСПРАВЛЕН UNIQUE В relationships
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

MAX_RETRIES = 5
RETRY_DELAY = 0.1

ALLOWED_ACTIVITY_TYPES = frozenset({
    "message", "voice", "sticker", "gif", "photo", "video", "xo_game"
})

VALID_ACTIVITY_COLUMNS = frozenset({
    "messages", "voice", "stickers", "gifs", "photos", "videos", "xo_games"
})

STOP_WORDS = frozenset({
    'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то',
    'все', 'она', 'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же', 'вы', 'за',
    'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще',
    'нет', 'о', 'из', 'ему', 'теперь', 'когда', 'даже', 'ну', 'вдруг', 'ли',
    'если', 'уже', 'или', 'ни', 'быть', 'был', 'него', 'до', 'вас', 'нибудь',
    'опять', 'уж', 'вам', 'ведь', 'там', 'потом', 'себя', 'ничего', 'ей',
    'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней', 'для', 'мы', 'тебя',
    'их', 'чем', 'была', 'сам', 'чтоб', 'без', 'будто', 'чего', 'раз', 'тоже',
    'себе', 'под', 'будет', 'тогда', 'кто', 'этот', 'того', 'потому',
    'этого', 'какой', 'совсем', 'ним', 'здесь', 'этом', 'один', 'почти',
    'мой', 'тем', 'чтобы', 'нее', 'сейчас', 'были', 'куда', 'зачем', 'всех',
    'можно', 'при', 'наконец', 'два', 'об', 'другой', 'хоть', 'после', 'над',
    'больше', 'тот', 'через', 'эти', 'нас', 'про', 'всего', 'них', 'какая',
    'много', 'разве', 'три', 'эту', 'моя', 'впрочем', 'хорошо', 'свою',
    'этой', 'перед', 'иногда', 'лучше', 'чуть', 'нельзя', 'такой', 'им',
    'более', 'всегда', 'конечно', 'всю', 'между', 'это', 'просто', 'очень'
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


# ==================== ИСКЛЮЧЕНИЕ ====================

class DatabaseError(Exception):
    """Исключение для ошибок базы данных."""
    pass


# ==================== ОСНОВНОЙ КЛАСС ====================

class Database:
    """Асинхронный класс для работы с SQLite через aiosqlite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DATABASE_PATH
        self._initialized = False
        self._lock = asyncio.Lock()
        logger.info(f"Database instance created with path: {self.db_path}")

    # ==================== ВНУТРЕННИЕ МЕТОДЫ ====================

    async def _execute_with_retry(
        self,
        query: str,
        params: tuple = (),
        fetch_one: bool = False,
        fetch_all: bool = False
    ) -> Any:
        """Выполняет SQL-запрос с повторными попытками при блокировке."""
        if not self.db_path:
            raise DatabaseError("Database path is not set")

        for attempt in range(MAX_RETRIES):
            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    conn.row_factory = aiosqlite.Row
                    await conn.execute("PRAGMA busy_timeout = 5000")
                    await conn.execute("PRAGMA journal_mode = WAL")
                    await conn.execute("PRAGMA synchronous = NORMAL")
                    await conn.execute("PRAGMA cache_size = -20000")
                    
                    cursor = await conn.execute(query, params)
                    
                    # Автокоммит для не-fetch запросов
                    if not fetch_one and not fetch_all:
                        await conn.commit()
                    
                    if fetch_one:
                        row = await cursor.fetchone()
                        return dict(row) if row else None
                    elif fetch_all:
                        rows = await cursor.fetchall()
                        return [dict(r) for r in rows] if rows else []
                    else:
                        return cursor.rowcount
                        
            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"Database locked, retry {attempt + 1}/{MAX_RETRIES} after {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"DB operational error: {e}")
                raise DatabaseError(f"Database error: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected DB error: {e}")
                raise DatabaseError(f"Unexpected error: {e}") from e
        
        return None

    async def _execute_transaction(self, queries: List[Tuple[str, tuple]]) -> bool:
        """Выполняет несколько запросов в одной транзакции."""
        if not self.db_path:
            raise DatabaseError("Database path is not set")
        
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA busy_timeout = 5000")
                
                try:
                    await conn.execute("BEGIN")
                    
                    for query, params in queries:
                        await conn.execute(query, params)
                    
                    await conn.commit()
                    return True
                    
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"Transaction failed: {e}")
                    raise DatabaseError(f"Transaction failed: {e}") from e

    # ==================== ИНИЦИАЛИЗАЦИЯ ====================

    async def initialize(self) -> None:
        """Асинхронная инициализация БД."""
        async with self._lock:
            if self._initialized:
                return
            
            if self.db_path:
                db_dir = os.path.dirname(self.db_path)
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)
            
            await self._create_tables()
            await self._run_migrations()
            await self._create_indexes()
            await self._add_default_data()
            
            self._initialized = True
            logger.info("✅ Database initialized successfully")

    async def _create_tables(self) -> None:
        """Создание всех таблиц."""
        tables = [
            # users
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance INTEGER DEFAULT 1000,
                daily_streak INTEGER DEFAULT 0,
                last_daily TEXT,
                vip_level INTEGER DEFAULT 0,
                vip_until TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                register_date TEXT,
                warns TEXT DEFAULT '[]'
            )
            """,
            # transactions
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER,
                to_id INTEGER,
                amount INTEGER,
                reason TEXT,
                date TEXT
            )
            """,
            # shop_items
            """
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                description TEXT
            )
            """,
            # user_profiles
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                age INTEGER,
                city TEXT,
                timezone TEXT,
                about TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """,
            # user_stats
            """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                messages_total INTEGER DEFAULT 0,
                messages_today INTEGER DEFAULT 0,
                messages_week INTEGER DEFAULT 0,
                messages_month INTEGER DEFAULT 0,
                last_message_date TEXT,
                register_date TEXT,
                last_active TEXT,
                total_voice INTEGER DEFAULT 0,
                total_stickers INTEGER DEFAULT 0,
                total_gifs INTEGER DEFAULT 0,
                total_photos INTEGER DEFAULT 0,
                total_videos INTEGER DEFAULT 0,
                days_active INTEGER DEFAULT 0,
                current_streak INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0,
                last_streak_update TEXT
            )
            """,
            # user_activity_log
            """
            CREATE TABLE IF NOT EXISTS user_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id BIGINT NOT NULL,
                date TEXT NOT NULL,
                messages INTEGER DEFAULT 0,
                voice INTEGER DEFAULT 0,
                stickers INTEGER DEFAULT 0,
                gifs INTEGER DEFAULT 0,
                photos INTEGER DEFAULT 0,
                videos INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                xo_games INTEGER DEFAULT 0,
                UNIQUE(user_id, chat_id, date)
            )
            """,
            # xo_stats
            """
            CREATE TABLE IF NOT EXISTS xo_stats (
                user_id INTEGER PRIMARY KEY,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                wins_vs_bot INTEGER DEFAULT 0,
                losses_vs_bot INTEGER DEFAULT 0,
                total_bet INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                max_win_streak INTEGER DEFAULT 0,
                current_win_streak INTEGER DEFAULT 0
            )
            """,
            # user_economy_stats
            """
            CREATE TABLE IF NOT EXISTS user_economy_stats (
                user_id INTEGER PRIMARY KEY,
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                total_transferred INTEGER DEFAULT 0,
                total_received INTEGER DEFAULT 0,
                total_donated_rub INTEGER DEFAULT 0,
                total_donated_coins INTEGER DEFAULT 0,
                max_balance INTEGER DEFAULT 0,
                daily_claims INTEGER DEFAULT 0,
                vip_purchases INTEGER DEFAULT 0
            )
            """,
            # chat_daily_summary
            """
            CREATE TABLE IF NOT EXISTS chat_daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                date TEXT NOT NULL,
                total_messages INTEGER DEFAULT 0,
                active_users INTEGER DEFAULT 0,
                top_words TEXT,
                top_users TEXT,
                rp_actions INTEGER DEFAULT 0,
                xo_games INTEGER DEFAULT 0,
                UNIQUE(chat_id, date)
            )
            """,
            # chat_word_stats
            """
            CREATE TABLE IF NOT EXISTS chat_word_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                date TEXT NOT NULL,
                word TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                UNIQUE(chat_id, date, word)
            )
            """,
            # custom_rp
            """
            CREATE TABLE IF NOT EXISTS custom_rp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                command TEXT NOT NULL,
                action_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, command)
            )
            """,
            # tag_categories
            """
            CREATE TABLE IF NOT EXISTS tag_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                icon_emoji TEXT DEFAULT '🔔',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # chat_tag_settings
            """
            CREATE TABLE IF NOT EXISTS chat_tag_settings (
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT 0,
                PRIMARY KEY (chat_id, category_slug)
            )
            """,
            # user_tag_subscriptions
            """
            CREATE TABLE IF NOT EXISTS user_tag_subscriptions (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_subscribed BOOLEAN DEFAULT 1,
                PRIMARY KEY (user_id, chat_id, category_slug)
            )
            """,
            # chat_rating
            """
            CREATE TABLE IF NOT EXISTS chat_rating (
                chat_id BIGINT PRIMARY KEY,
                chat_title TEXT,
                activity_points INTEGER DEFAULT 0,
                members_count INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                messages_count INTEGER DEFAULT 0,
                week_activity INTEGER DEFAULT 0,
                month_activity INTEGER DEFAULT 0,
                owner_id INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # chat_rewards
            """
            CREATE TABLE IF NOT EXISTS chat_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                reward_type TEXT,
                reward_amount INTEGER,
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # donors
            """
            CREATE TABLE IF NOT EXISTS donors (
                user_id INTEGER PRIMARY KEY,
                total_donated INTEGER DEFAULT 0,
                last_donate TIMESTAMP,
                donor_rank TEXT DEFAULT '💎 Поддерживающий'
            )
            """,
            # ref_links
            """
            CREATE TABLE IF NOT EXISTS ref_links (
                user_id INTEGER,
                chat_id INTEGER,
                ref_code TEXT UNIQUE,
                invited_count INTEGER DEFAULT 0,
                earned_coins INTEGER DEFAULT 0,
                created_at TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
            """,
            # ref_invites
            """
            CREATE TABLE IF NOT EXISTS ref_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                chat_id INTEGER,
                invited_at TEXT
            )
            """,
            # relationships — ИСПРАВЛЕН UNIQUE
            """
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                UNIQUE(user1_id, user2_id, type)
            )
            """,
            # groups
            """
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                group_name TEXT NOT NULL,
                group_leader INTEGER NOT NULL,
                member_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # group_members
            """
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER,
                user_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, user_id)
            )
            """,
        ]
        
        for sql in tables:
            await self._execute_with_retry(sql)
        
        logger.info(f"Created {len(tables)} tables")

    async def _create_indexes(self) -> None:
        """Создание индексов для оптимизации."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_activity_log_user_chat_date ON user_activity_log(user_id, chat_id, date);",
            "CREATE INDEX IF NOT EXISTS idx_chat_words_chat_date ON chat_word_stats(chat_id, date);",
            "CREATE INDEX IF NOT EXISTS idx_transactions_from_id ON transactions(from_id);",
            "CREATE INDEX IF NOT EXISTS idx_transactions_to_id ON transactions(to_id);",
            "CREATE INDEX IF NOT EXISTS idx_custom_rp_command ON custom_rp(command);",
            "CREATE INDEX IF NOT EXISTS idx_custom_rp_user_id ON custom_rp(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);",
            "CREATE INDEX IF NOT EXISTS idx_user_stats_last_active ON user_stats(last_active);",
            "CREATE INDEX IF NOT EXISTS idx_relationships_users ON relationships(user1_id, user2_id);",
        ]
        
        for sql in indexes:
            try:
                await self._execute_with_retry(sql)
            except Exception as e:
                logger.warning(f"Failed to create index: {e}")

    async def _run_migrations(self) -> None:
        """Автоматическое добавление недостающих колонок."""
        migrations = {
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
            "user_activity_log": {
                "chat_id": "BIGINT NOT NULL DEFAULT 0",
            },
            "chat_rating": {
                "owner_id": "INTEGER",
            }
        }

        for table, columns in migrations.items():
            try:
                rows = await self._execute_with_retry(
                    f"PRAGMA table_info({table})",
                    fetch_all=True
                )
                existing = {row["name"] for row in rows} if rows else set()
                
                for col_name, col_def in columns.items():
                    if col_name not in existing:
                        try:
                            await self._execute_with_retry(
                                f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
                            )
                            logger.info(f"✅ Added column {col_name} to {table}")
                        except Exception as e:
                            logger.warning(f"Could not add column {col_name} to {table}: {e}")
            except Exception as e:
                logger.warning(f"Could not check migrations for {table}: {e}")

    async def _add_default_data(self) -> None:
        """Добавление данных по умолчанию."""
        # Shop items
        row = await self._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM shop_items",
            fetch_one=True
        )
        if row and row.get("cnt", 0) == 0:
            queries = []
            for name, price, desc in DEFAULT_SHOP_ITEMS:
                queries.append((
                    "INSERT INTO shop_items (name, price, description) VALUES (?, ?, ?)",
                    (name, price, desc)
                ))
            await self._execute_transaction(queries)
            logger.info("Added default shop items")

        # Tag categories
        row = await self._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM tag_categories",
            fetch_one=True
        )
        if row and row.get("cnt", 0) == 0:
            queries = []
            for slug, name, desc, icon in DEFAULT_CATEGORIES:
                queries.append((
                    """INSERT OR IGNORE INTO tag_categories 
                       (slug, name, description, icon_emoji) VALUES (?, ?, ?, ?)""",
                    (slug, name, desc, icon)
                ))
            await self._execute_transaction(queries)
            logger.info("Added default tag categories")

    # ==================== ОСНОВНЫЕ МЕТОДЫ ====================

    async def get_user(self, user_id: int) -> Optional[Dict]:
        if user_id is None: return None
        return await self._execute_with_retry(
            "SELECT * FROM users WHERE user_id = ?", (user_id,), fetch_one=True
        )

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        if not username: return None
        username = username.lstrip('@')
        return await self._execute_with_retry(
            "SELECT * FROM users WHERE username = ?", (username,), fetch_one=True
        )

    async def create_user(self, user_id: int, username: Optional[str] = None,
                          first_name: Optional[str] = None, balance: int = 1000) -> None:
        if user_id is None: return
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        balance = balance if balance is not None else 1000

        queries = [
            ("""INSERT OR IGNORE INTO users (user_id, username, first_name, balance, register_date, warns)
                VALUES (?, ?, ?, ?, ?, ?)""", (user_id, username, first_name, balance, now, '[]')),
            ("""INSERT OR IGNORE INTO user_stats (user_id, register_date, last_active) VALUES (?, ?, ?)""",
             (user_id, today, now)),
            ("""INSERT OR IGNORE INTO user_economy_stats (user_id, max_balance) VALUES (?, ?)""",
             (user_id, balance)),
            ("""INSERT OR IGNORE INTO xo_stats (user_id) VALUES (?)""", (user_id,)),
        ]
        await self._execute_transaction(queries)
        logger.info(f"Created user {user_id}")

    async def user_exists(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return user is not None

    async def get_balance(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        return user.get("balance", 0) if user else 0

    async def update_balance(self, user_id: int, delta: int, reason: str = "") -> None:
        if user_id is None or delta is None: return
        
        queries = [
            ("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id)),
            ("""UPDATE user_economy_stats SET max_balance = MAX(COALESCE(max_balance, 0), 
                (SELECT balance FROM users WHERE user_id = ?)),
                total_earned = COALESCE(total_earned, 0) + ? WHERE user_id = ?""",
             (user_id, max(0, delta), user_id)),
        ]
        if delta < 0:
            queries.append(("""UPDATE user_economy_stats SET total_spent = COALESCE(total_spent, 0) + ?
                               WHERE user_id = ?""", (abs(delta), user_id)))
        if reason:
            queries.append(("""INSERT INTO transactions (from_id, to_id, amount, reason, date)
                               VALUES (?, ?, ?, ?, ?)""",
                           (user_id, user_id, abs(delta), reason, datetime.now().isoformat())))
        await self._execute_transaction(queries)

    async def transfer_coins(self, from_id: int, to_username: str, amount: int,
                             reason: str = "transfer") -> bool:
        if from_id is None or not to_username or amount is None or amount <= 0: return False
        target = await self.get_user_by_username(to_username)
        if not target: return False
        to_id = target.get("user_id")
        if to_id is None or from_id == to_id: return False
        
        result = await self._execute_with_retry(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, from_id, amount))
        if result == 0: return False
        
        queries = [
            ("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, to_id)),
            ("""INSERT INTO transactions (from_id, to_id, amount, reason, date)
                VALUES (?, ?, ?, ?, ?)""", (from_id, to_id, amount, reason, datetime.now().isoformat())),
            ("UPDATE user_economy_stats SET total_transferred = COALESCE(total_transferred, 0) + ? WHERE user_id = ?",
             (amount, from_id)),
            ("UPDATE user_economy_stats SET total_received = COALESCE(total_received, 0) + ? WHERE user_id = ?",
             (amount, to_id)),
        ]
        await self._execute_transaction(queries)
        logger.info(f"Transfer: {from_id} -> {to_id} ({amount} coins)")
        return True

    async def save_profile(self, user_id: int, full_name: str, age: int, city: str,
                           timezone: str, about: str) -> None:
        if user_id is None: return
        now = datetime.now().isoformat()
        row = await self._execute_with_retry(
            "SELECT created_at FROM user_profiles WHERE user_id = ?", (user_id,), fetch_one=True)
        created_at = row["created_at"] if row and row.get("created_at") else now
        await self._execute_with_retry(
            """INSERT OR REPLACE INTO user_profiles (user_id, full_name, age, city, timezone, about, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, full_name or "", age or 0, city or "", timezone or "", about or "", created_at, now))

    async def get_profile(self, user_id: int) -> Optional[Dict]:
        if user_id is None: return None
        return await self._execute_with_retry(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,), fetch_one=True)

    async def update_daily_streak(self, user_id: int, streak: int) -> None:
        if user_id is None: return
        await self._execute_with_retry(
            "UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
            (streak or 0, datetime.now().isoformat(), user_id))

    async def claim_daily_bonus(self, user_id: int, bonus_amount: int, streak: int,
                                today_str: str, reason: str = "Ежедневный бонус") -> Dict:
        if user_id is None or bonus_amount is None: return {'new_balance': 0, 'success': False}
        row = await self._execute_with_retry(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
        if not row: return {'new_balance': 0, 'success': False}
        old_balance = row["balance"] or 0
        new_balance = old_balance + bonus_amount
        
        queries = [
            ("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id)),
            ("UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?", (streak or 0, today_str, user_id)),
            ("""INSERT INTO transactions (from_id, to_id, amount, reason, date)
                VALUES (?, ?, ?, ?, ?)""", (user_id, user_id, bonus_amount, reason, datetime.now().isoformat())),
            ("""UPDATE user_economy_stats SET daily_claims = COALESCE(daily_claims, 0) + 1,
                total_earned = COALESCE(total_earned, 0) + ? WHERE user_id = ?""", (bonus_amount, user_id)),
        ]
        await self._execute_transaction(queries)
        return {'new_balance': new_balance, 'success': True}

    async def get_top_users(self, limit: int = 10) -> List[Dict]:
        limit = limit if limit is not None else 10
        return await self._execute_with_retry(
            """SELECT user_id, username, first_name, balance, vip_level 
               FROM users WHERE balance > 0 ORDER BY balance DESC LIMIT ?""",
            (limit,), fetch_all=True) or []

    async def get_top_balance(self, limit: int = 10) -> List[Dict]:
        return await self.get_top_users(limit)

    async def get_top_donors(self, limit: int = 10) -> List[Dict]:
        limit = limit if limit is not None else 10
        return await self._execute_with_retry(
            """SELECT d.user_id, u.username, u.first_name, d.total_donated, d.donor_rank
               FROM donors d LEFT JOIN users u ON d.user_id = u.user_id
               WHERE d.total_donated > 0 ORDER BY d.total_donated DESC LIMIT ?""",
            (limit,), fetch_all=True) or []

    async def update_donor_stats(self, user_id: int, amount_rub: int) -> None:
        if user_id is None or amount_rub is None: return
        row = await self._execute_with_retry(
            "SELECT total_donated FROM donors WHERE user_id = ?", (user_id,), fetch_one=True)
        current_total = row["total_donated"] if row and row.get("total_donated") else 0
        new_total = current_total + amount_rub
        
        if new_total >= 5000: donor_rank = "👑 Легендарный спонсор"
        elif new_total >= 2000: donor_rank = "💫 Золотой спонсор"
        elif new_total >= 500: donor_rank = "⭐ Серебряный спонсор"
        elif new_total >= 100: donor_rank = "🔰 Бронзовый спонсор"
        else: donor_rank = "💎 Поддерживающий"
        
        await self._execute_with_retry(
            """INSERT INTO donors (user_id, total_donated, last_donate, donor_rank)
               VALUES (?, ?, CURRENT_TIMESTAMP, ?)
               ON CONFLICT(user_id) DO UPDATE SET total_donated = total_donated + ?,
               last_donate = CURRENT_TIMESTAMP, donor_rank = ?""",
            (user_id, amount_rub, donor_rank, amount_rub, donor_rank))

    async def add_warn(self, user_id: int, warn_text: str) -> None:
        if user_id is None: return
        user = await self.get_user(user_id)
        if user:
            warns = user.get('warns', [])
            if isinstance(warns, str):
                try: warns = json.loads(warns)
                except json.JSONDecodeError: warns = []
            warns.append({'text': warn_text or "", 'date': datetime.now().isoformat()})
            await self._execute_with_retry("UPDATE users SET warns = ? WHERE user_id = ?", (json.dumps(warns), user_id))

    async def get_user_warns(self, user_id: int) -> List[Dict]:
        if user_id is None: return []
        user = await self.get_user(user_id)
        if user:
            warns = user.get('warns', [])
            if isinstance(warns, str):
                try: return json.loads(warns)
                except json.JSONDecodeError: return []
            return warns
        return []

    async def clear_warns(self, user_id: int) -> None:
        if user_id is None: return
        await self._execute_with_retry("UPDATE users SET warns = '[]' WHERE user_id = ?", (user_id,))

    # ==================== СТАТИСТИКА ====================

    async def track_user_activity(self, user_id: int, chat_id: int, activity_type: str, value: int = 1) -> None:
        if user_id is None or chat_id is None or activity_type not in ALLOWED_ACTIVITY_TYPES: return
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat()
        value = value if value is not None else 1

        col_map = {"message": "messages", "voice": "voice", "sticker": "stickers", "gif": "gifs",
                    "photo": "photos", "video": "videos", "xo_game": "xo_games"}
        col = col_map.get(activity_type, "messages")
        if col not in VALID_ACTIVITY_COLUMNS: return
        
        queries = [("INSERT OR IGNORE INTO user_stats (user_id, register_date) VALUES (?, ?)", (user_id, today))]
        
        if activity_type == "message":
            queries.append(("""UPDATE user_stats SET messages_total = COALESCE(messages_total, 0) + ?,
                messages_today = COALESCE(messages_today, 0) + ?, messages_week = COALESCE(messages_week, 0) + ?,
                messages_month = COALESCE(messages_month, 0) + ?, last_message_date = ?, last_active = ?
                WHERE user_id = ?""", (value, value, value, value, today, now, user_id)))
        elif activity_type in ("voice", "sticker", "gif", "photo", "video"):
            queries.append((f"""UPDATE user_stats SET total_{activity_type}s = COALESCE(total_{activity_type}s, 0) + ?,
                last_active = ? WHERE user_id = ?""", (value, now, user_id)))
        else:
            queries.append(("UPDATE user_stats SET last_active = ? WHERE user_id = ?", (now, user_id)))
        
        queries.append((f"""INSERT INTO user_activity_log (user_id, chat_id, date, {col}) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id, date) DO UPDATE SET {col} = COALESCE({col}, 0) + ?""",
            (user_id, chat_id, today, value, value)))
        await self._execute_transaction(queries)

    async def update_user_streaks(self, user_id: Optional[int] = None) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if user_id is not None:
            rows = await self._execute_with_retry(
                """SELECT user_id, last_message_date, days_active, current_streak, max_streak 
                   FROM user_stats WHERE user_id = ?""", (user_id,), fetch_all=True)
        else:
            rows = await self._execute_with_retry(
                """SELECT user_id, last_message_date, days_active, current_streak, max_streak 
                   FROM user_stats WHERE last_message_date IS NOT NULL""", fetch_all=True)
        if not rows: return
        
        queries = []
        for row in rows:
            uid, last_date = row["user_id"], row["last_message_date"]
            days_active, current_streak, max_streak = row["days_active"] or 0, row["current_streak"] or 0, row["max_streak"] or 0
            if last_date == today: continue
            new_days = days_active + 1
            new_streak = current_streak + 1 if last_date == yesterday else 1
            new_max = max(max_streak, new_streak)
            queries.append(("""UPDATE user_stats SET days_active = ?, current_streak = ?, max_streak = ?,
                last_streak_update = ? WHERE user_id = ?""", (new_days, new_streak, new_max, today, uid)))
        if queries: await self._execute_transaction(queries)

    async def get_user_stats(self, user_id: int) -> Optional[Dict]:
        if user_id is None: return None
        result = await self._execute_with_retry(
            """SELECT s.user_id, COALESCE(s.messages_total,0) as messages_total,
                COALESCE(s.messages_today,0) as messages_today, COALESCE(s.messages_week,0) as messages_week,
                COALESCE(s.messages_month,0) as messages_month, s.last_message_date, s.register_date, s.last_active,
                COALESCE(s.total_voice,0) as total_voice, COALESCE(s.total_stickers,0) as total_stickers,
                COALESCE(s.total_gifs,0) as total_gifs, COALESCE(s.total_photos,0) as total_photos,
                COALESCE(s.total_videos,0) as total_videos, COALESCE(s.days_active,0) as days_active,
                COALESCE(s.current_streak,0) as current_streak, COALESCE(s.max_streak,0) as max_streak,
                COALESCE(e.total_earned,0) as total_earned, COALESCE(e.total_spent,0) as total_spent,
                COALESCE(e.total_transferred,0) as total_transferred, COALESCE(e.total_received,0) as total_received,
                COALESCE(e.total_donated_rub,0) as total_donated_rub, COALESCE(e.total_donated_coins,0) as total_donated_coins,
                COALESCE(e.max_balance,0) as max_balance, COALESCE(e.daily_claims,0) as daily_claims,
                COALESCE(x.games_played,0) as games_played, COALESCE(x.wins,0) as wins,
                COALESCE(x.losses,0) as losses, COALESCE(x.draws,0) as draws,
                COALESCE(x.wins_vs_bot,0) as wins_vs_bot, COALESCE(x.losses_vs_bot,0) as losses_vs_bot,
                COALESCE(x.total_bet,0) as total_bet, COALESCE(x.total_won,0) as total_won,
                COALESCE(x.max_win_streak,0) as max_win_streak, COALESCE(x.current_win_streak,0) as current_win_streak,
                COALESCE(u.balance,0) as balance, COALESCE(u.daily_streak,0) as daily_streak,
                COALESCE(u.vip_level,0) as vip_level, u.register_date as user_register_date
               FROM user_stats s LEFT JOIN user_economy_stats e ON s.user_id = e.user_id
               LEFT JOIN xo_stats x ON s.user_id = x.user_id LEFT JOIN users u ON s.user_id = u.user_id
               WHERE s.user_id = ?""", (user_id,), fetch_one=True)
        return result or {'messages_total':0,'wins':0,'games_played':0,'balance':0,'daily_streak':0,'vip_level':0}

    async def get_top_messages(self, limit: int = 10) -> List[Dict]:
        limit = limit if limit is not None else 10
        return await self._execute_with_retry(
            """SELECT u.user_id, u.username, u.first_name, COALESCE(s.messages_total,0) as messages_total
               FROM user_stats s JOIN users u ON s.user_id = u.user_id
               WHERE COALESCE(s.messages_total,0) > 0 ORDER BY s.messages_total DESC LIMIT ?""",
            (limit,), fetch_all=True) or []

    async def get_top_xo(self, limit: int = 10) -> List[Dict]:
        limit = limit if limit is not None else 10
        return await self._execute_with_retry(
            """SELECT u.user_id, u.username, u.first_name, COALESCE(x.wins,0) as wins,
               COALESCE(x.games_played,0) as games_played
               FROM xo_stats x JOIN users u ON x.user_id = u.user_id
               WHERE COALESCE(x.games_played,0) >= 3 ORDER BY x.wins DESC LIMIT ?""",
            (limit,), fetch_all=True) or []

    async def get_top_activity(self, limit: int = 10) -> List[Dict]:
        limit = limit if limit is not None else 10
        return await self._execute_with_retry(
            """SELECT u.user_id, u.username, u.first_name, COALESCE(s.days_active,0) as days_active,
               COALESCE(s.current_streak,0) as current_streak, COALESCE(s.max_streak,0) as max_streak
               FROM user_stats s JOIN users u ON s.user_id = u.user_id
               WHERE COALESCE(s.days_active,0) > 0 ORDER BY s.days_active DESC, s.current_streak DESC LIMIT ?""",
            (limit,), fetch_all=True) or []

    async def get_top_daily_streak(self, limit: int = 10) -> List[Dict]:
        limit = limit if limit is not None else 10
        return await self._execute_with_retry(
            """SELECT user_id, username, first_name, COALESCE(daily_streak,0) as daily_streak
               FROM users WHERE COALESCE(daily_streak,0) > 0 ORDER BY daily_streak DESC LIMIT ?""",
            (limit,), fetch_all=True) or []

    async def update_xo_stats(self, user_id: int, result_type: str, bet: int = 0, won: int = 0) -> None:
        if user_id is None or user_id == "bot": return
        bet = bet if bet is not None else 0
        won = won if won is not None else 0
        
        queries = [
            ("INSERT OR IGNORE INTO xo_stats (user_id) VALUES (?)", (user_id,)),
            ("UPDATE xo_stats SET games_played = COALESCE(games_played,0) + 1 WHERE user_id = ?", (user_id,)),
        ]
        if result_type == "win":
            queries.append(("UPDATE xo_stats SET wins = COALESCE(wins,0) + 1, current_win_streak = COALESCE(current_win_streak,0) + 1 WHERE user_id = ?", (user_id,)))
        elif result_type == "loss":
            queries.append(("UPDATE xo_stats SET losses = COALESCE(losses,0) + 1, current_win_streak = 0 WHERE user_id = ?", (user_id,)))
        elif result_type == "draw":
            queries.append(("UPDATE xo_stats SET draws = COALESCE(draws,0) + 1, current_win_streak = 0 WHERE user_id = ?", (user_id,)))
        elif result_type == "loss_vs_bot":
            queries.append(("UPDATE xo_stats SET losses_vs_bot = COALESCE(losses_vs_bot,0) + 1, current_win_streak = 0 WHERE user_id = ?", (user_id,)))
        elif result_type == "win_vs_bot":
            queries.append(("UPDATE xo_stats SET wins_vs_bot = COALESCE(wins_vs_bot,0) + 1, current_win_streak = COALESCE(current_win_streak,0) + 1 WHERE user_id = ?", (user_id,)))
        if bet > 0: queries.append(("UPDATE xo_stats SET total_bet = COALESCE(total_bet,0) + ? WHERE user_id = ?", (bet, user_id)))
        if won > 0: queries.append(("UPDATE xo_stats SET total_won = COALESCE(total_won,0) + ? WHERE user_id = ?", (won, user_id)))
        queries.append(("UPDATE xo_stats SET max_win_streak = MAX(COALESCE(max_win_streak,0), COALESCE(current_win_streak,0)) WHERE user_id = ?", (user_id,)))
        await self._execute_transaction(queries)

    # ==================== АНАЛИЗ ЧАТА ====================

    async def log_chat_message(self, chat_id: int, user_id: int, text: str) -> None:
        if chat_id is None or user_id is None or not text or len(text) < 3: return
        today = datetime.now().strftime("%Y-%m-%d")
        words = re.findall(r'[а-яА-Яa-zA-Z]{3,}', text.lower())
        for word in words:
            if word in STOP_WORDS: continue
            await self._execute_with_retry(
                """INSERT INTO chat_word_stats (chat_id, date, word, count) VALUES (?, ?, ?, 1)
                   ON CONFLICT(chat_id, date, word) DO UPDATE SET count = count + 1""",
                (chat_id, today, word))

    async def get_chat_daily_stats(self, chat_id: int) -> Dict:
        if chat_id is None: return {'unique_users': 0, 'total_messages': 0}
        today = datetime.now().strftime("%Y-%m-%d")
        row = await self._execute_with_retry(
            """SELECT COUNT(DISTINCT user_id) as unique_users, COALESCE(SUM(messages),0) as total_messages
               FROM user_activity_log WHERE chat_id = ? AND date = ?""",
            (chat_id, today), fetch_one=True)
        if row: return {'unique_users': row.get('unique_users',0) or 0, 'total_messages': row.get('total_messages',0) or 0}
        return {'unique_users': 0, 'total_messages': 0}

    async def get_chat_top_words(self, chat_id: int, limit: int = 10) -> List[Tuple[str, int]]:
        if chat_id is None: return []
        today = datetime.now().strftime("%Y-%m-%d")
        limit = limit if limit is not None else 10
        rows = await self._execute_with_retry(
            "SELECT word, count FROM chat_word_stats WHERE chat_id = ? AND date = ? ORDER BY count DESC LIMIT ?",
            (chat_id, today, limit), fetch_all=True)
        return [(r["word"], r["count"]) for r in rows] if rows else []

    async def get_chat_active_users(self, chat_id: int, limit: int = 5) -> List[Dict]:
        if chat_id is None: return []
        today = datetime.now().strftime("%Y-%m-%d")
        limit = limit if limit is not None else 5
        return await self._execute_with_retry(
            """SELECT ual.user_id, u.first_name, ual.messages as message_count
               FROM user_activity_log ual LEFT JOIN users u ON ual.user_id = u.user_id
               WHERE ual.chat_id = ? AND ual.date = ? ORDER BY ual.messages DESC LIMIT ?""",
            (chat_id, today, limit), fetch_all=True) or []

    async def get_chat_top_balance(self, chat_id: int, limit: int = 3) -> List[Dict]:
        if chat_id is None: return []
        return await self.get_top_balance(limit if limit else 3)

    async def get_chat_top_xo(self, chat_id: int, limit: int = 3) -> List[Dict]:
        if chat_id is None: return []
        return await self.get_top_xo(limit if limit else 3)

    async def get_chat_top_messages(self, chat_id: int, limit: int = 3) -> List[Dict]:
        if chat_id is None: return []
        limit = limit if limit is not None else 3
        return await self._execute_with_retry(
            """SELECT ual.user_id, u.first_name, u.username, SUM(ual.messages) as messages_total
               FROM user_activity_log ual LEFT JOIN users u ON ual.user_id = u.user_id
               WHERE ual.chat_id = ? GROUP BY ual.user_id ORDER BY messages_total DESC LIMIT ?""",
            (chat_id, limit), fetch_all=True) or []

    async def get_total_users(self) -> int:
        row = await self._execute_with_retry("SELECT COUNT(*) as cnt FROM users", fetch_one=True)
        return row.get("cnt", 0) if row else 0

    async def get_total_messages_count(self) -> int:
        row = await self._execute_with_retry("SELECT COALESCE(SUM(messages_total),0) as cnt FROM user_stats", fetch_one=True)
        return row.get("cnt", 0) if row else 0

    async def get_chat_members_count(self, chat_id: int) -> int:
        if chat_id is None: return 0
        row = await self._execute_with_retry(
            "SELECT COUNT(*) as cnt FROM group_members gm JOIN groups g ON gm.group_id = g.id WHERE g.chat_id = ?",
            (chat_id,), fetch_one=True)
        return row.get("cnt", 0) if row else 0

    async def get_all_chats_with_bot(self) -> List[int]:
        rows = await self._execute_with_retry("SELECT DISTINCT chat_id FROM chat_word_stats", fetch_all=True)
        return [r["chat_id"] for r in rows] if rows else []

    # ==================== ОЧИСТКА ====================

    async def cleanup_old_activity_logs(self, days: int = 90) -> None:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        queries = [("DELETE FROM user_activity_log WHERE date < ?", (cutoff,)),
                   ("DELETE FROM chat_word_stats WHERE date < ?", (cutoff,))]
        await self._execute_transaction(queries)

    async def reset_daily_counters(self) -> None:
        await self._execute_with_retry("UPDATE user_stats SET messages_today = 0")

    async def reset_weekly_counters(self) -> None:
        await self._execute_with_retry("UPDATE user_stats SET messages_week = 0")

    async def reset_monthly_counters(self) -> None:
        await self._execute_with_retry("UPDATE user_stats SET messages_month = 0")

    async def cleanup_bot_from_all_tables(self, bot_id: int) -> None:
        if bot_id is None: return
        tables_with_user_id = ['users','user_stats','user_economy_stats','xo_stats','user_profiles','custom_rp',
                               'user_activity_log','user_tag_subscriptions','ref_links','donors']
        special_tables = {'transactions': ("from_id = ? OR to_id = ?", (bot_id, bot_id)),
                          'relationships': ("user1_id = ? OR user2_id = ?", (bot_id, bot_id)),
                          'ref_invites': ("inviter_id = ? OR invited_id = ?", (bot_id, bot_id)),
                          'group_members': ("user_id = ?", (bot_id,))}
        queries = []
        for table in tables_with_user_id:
            queries.append((f"DELETE FROM {table} WHERE user_id = ?", (bot_id,)))
        for table, (condition, params) in special_tables.items():
            queries.append((f"DELETE FROM {table} WHERE {condition}", params))
        try: await self._execute_transaction(queries)
        except DatabaseError as e: logger.warning(f"Failed to clean bot data: {e}")

    # ==================== КАСТОМНЫЕ РП ====================

    async def count_custom_rp(self, user_id: int) -> int:
        if user_id is None: return 0
        row = await self._execute_with_retry("SELECT COUNT(*) as cnt FROM custom_rp WHERE user_id = ?", (user_id,), fetch_one=True)
        return row.get("cnt", 0) if row else 0

    async def check_custom_rp_exists(self, user_id: int, command: str) -> bool:
        if user_id is None or not command: return False
        row = await self._execute_with_retry("SELECT 1 FROM custom_rp WHERE user_id = ? AND command = ?", (user_id, command), fetch_one=True)
        return row is not None

    async def add_custom_rp(self, user_id: int, command: str, action_text: str) -> None:
        if user_id is None or not command or not action_text: return
        await self._execute_with_retry("INSERT INTO custom_rp (user_id, command, action_text) VALUES (?, ?, ?)",
                                       (user_id, command, action_text))

    async def delete_custom_rp(self, user_id: int, command: str) -> bool:
        if user_id is None or not command: return False
        result = await self._execute_with_retry("DELETE FROM custom_rp WHERE user_id = ? AND command = ?", (user_id, command))
        return result > 0

    async def get_custom_rp(self, user_id: int) -> Dict[str, str]:
        if user_id is None: return {}
        rows = await self._execute_with_retry("SELECT command, action_text FROM custom_rp WHERE user_id = ?", (user_id,), fetch_all=True)
        return {r["command"]: r["action_text"] for r in rows} if rows else {}

    async def get_all_custom_rp(self, limit: int = 1000, offset: int = 0) -> Dict[int, Dict[str, str]]:
        limit = limit if limit is not None else 1000
        rows = await self._execute_with_retry(
            "SELECT user_id, command, action_text FROM custom_rp ORDER BY user_id LIMIT ? OFFSET ?",
            (limit, offset), fetch_all=True)
        result: Dict[int, Dict[str, str]] = {}
        for row in (rows or []):
            uid = row["user_id"]
            if uid not in result: result[uid] = {}
            result[uid][row["command"]] = row["action_text"]
        return result

    # ==================== ОТНОШЕНИЯ ====================

    async def create_relationship(self, user1_id: int, user2_id: int, rel_type: str) -> bool:
        if user1_id is None or user2_id is None or not rel_type: return False
        try:
            await self._execute_with_retry(
                "INSERT OR IGNORE INTO relationships (user1_id, user2_id, type) VALUES (?, ?, ?)",
                (user1_id, user2_id, rel_type))
            return True
        except Exception as e:
            logger.error(f"Create relationship error: {e}")
            return False

    async def get_relationship(self, user1_id: int, user2_id: int, rel_type: str) -> Optional[Dict]:
        if user1_id is None or user2_id is None or not rel_type: return None
        return await self._execute_with_retry(
            """SELECT * FROM relationships WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))
               AND type = ? AND status = 'active'""",
            (user1_id, user2_id, user2_id, user1_id, rel_type), fetch_one=True)

    async def get_relationship_status(self, user_id: int, rel_type: str = "marriage") -> Optional[Dict]:
        if user_id is None: return None
        return await self._execute_with_retry(
            """SELECT * FROM relationships WHERE (user1_id = ? OR user2_id = ?) AND type = ? AND status = 'active'
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, user_id, rel_type), fetch_one=True)

    async def end_relationship(self, user1_id: int, user2_id: int, rel_type: str) -> bool:
        if user1_id is None or user2_id is None or not rel_type: return False
        result = await self._execute_with_retry(
            """UPDATE relationships SET status = 'ended', ended_at = CURRENT_TIMESTAMP
               WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))
               AND type = ? AND status = 'active'""",
            (user1_id, user2_id, user2_id, user1_id, rel_type))
        return result > 0

    async def get_marriage_partner(self, user_id: int) -> Optional[int]:
        rel = await self.get_relationship_status(user_id, "marriage")
        if not rel: return None
        return rel["user2_id"] if rel["user1_id"] == user_id else rel["user1_id"]

    # ==================== ГРУППЫ ====================

    async def create_group(self, chat_id: int, group_name: str, leader_id: int) -> Optional[int]:
        if chat_id is None or not group_name or leader_id is None: return None
        try:
            result = await self._execute_with_retry(
                "INSERT INTO groups (chat_id, group_name, group_leader, member_count) VALUES (?, ?, ?, 1)",
                (chat_id, group_name, leader_id))
            if result > 0:
                row = await self._execute_with_retry(
                    "SELECT id FROM groups WHERE chat_id = ? AND group_name = ?", (chat_id, group_name), fetch_one=True)
                if row:
                    await self._execute_with_retry("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
                                                   (row["id"], leader_id))
                    return row["id"]
            return None
        except Exception as e:
            logger.error(f"Create group error: {e}")
            return None

    async def join_group(self, group_id: int, user_id: int) -> bool:
        if group_id is None or user_id is None: return False
        try:
            await self._execute_with_retry("INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
                                           (group_id, user_id))
            await self._execute_with_retry("UPDATE groups SET member_count = member_count + 1 WHERE id = ?", (group_id,))
            return True
        except Exception as e:
            logger.error(f"Join group error: {e}")
            return False

    async def leave_group(self, group_id: int, user_id: int) -> bool:
        if group_id is None or user_id is None: return False
        try:
            group = await self._execute_with_retry("SELECT group_leader FROM groups WHERE id = ?", (group_id,), fetch_one=True)
            if group and group["group_leader"] == user_id: return False
            result = await self._execute_with_retry("DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
                                                    (group_id, user_id))
            if result > 0:
                await self._execute_with_retry("UPDATE groups SET member_count = MAX(member_count - 1, 0) WHERE id = ?", (group_id,))
            return result > 0
        except Exception as e:
            logger.error(f"Leave group error: {e}")
            return False

    async def get_user_groups(self, user_id: int) -> List[Dict]:
        if user_id is None: return []
        return await self._execute_with_retry(
            "SELECT g.* FROM groups g JOIN group_members gm ON g.id = gm.group_id WHERE gm.user_id = ?",
            (user_id,), fetch_all=True) or []

    async def get_group_members(self, group_id: int) -> List[Dict]:
        if group_id is None: return []
        return await self._execute_with_retry(
            """SELECT u.user_id, u.username, u.first_name FROM group_members gm
               LEFT JOIN users u ON gm.user_id = u.user_id WHERE gm.group_id = ?""",
            (group_id,), fetch_all=True) or []

    async def delete_group(self, group_id: int) -> bool:
        if group_id is None: return False
        try:
            await self._execute_with_retry("DELETE FROM group_members WHERE group_id = ?", (group_id,))
            result = await self._execute_with_retry("DELETE FROM groups WHERE id = ?", (group_id,))
            return result > 0
        except Exception as e:
            logger.error(f"Delete group error: {e}")
            return False

    # ==================== ЗАКРЫТИЕ ====================

    async def close(self) -> None:
        logger.info("Database connection closed (no-op for aiosqlite)")


# ==================== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ====================

db = Database()
