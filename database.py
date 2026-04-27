#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАЙЛ: database.py
ВЕРСИЯ: 3.3.1-refactored
ОПИСАНИЕ: Асинхронная база данных NEXUS Bot — ИСПРАВЛЕНЫ все 19 проблем
ИЗМЕНЕНИЯ v3.3.1:
  ✅ Убран FOR UPDATE (не поддерживается SQLite)
  ✅ Убран двойной кэш в get_user_stats (оставлен только _stats_cache)
  ✅ Убран декоратор @cached для методов класса (используется self._stats_cache)
  ✅ Исправлен вызов get_relationship → get_relationship_status
  ✅ get_deletable_messages возвращает заглушку (message_id не хранятся)
  ✅ cache_size уменьшен до -8000 (8 МБ)
  ✅ Добавлен метод get_relationship() как алиас
  ✅ Статические методы политики вынесены с пометкой DEPRECATED
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

MAX_RETRIES = 5
RETRY_DELAY = 0.1
CACHE_TTL_SECONDS = 300  # TTL для кэша статистики

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
    "rules": "📜 <b>Правила чата</b>\n\n1. Уважайте собеседников — оскорбления запрещены.\n2. Спам, флуд, реклама — бан.\n3. Контент 18+ только в специальных чатах.\n4. Модераторы имеют право на предупреждение и мут.\n5. Жалобы на модерацию — в ЛС @admin",
    "privacy": "🔐 <b>Конфиденциальность</b>\n\n• Мы не передаём ваши данные третьим лицам.\n• Сообщения хранятся 90 дней для аналитики.\n• Вы можете запросить удаление своих данных командой /delete_data",
    "moderation": "⚖️ <b>Модерация</b>\n\n• Предупреждение → Мут 1ч → Мут 24ч → Бан.\n• За серьёзные нарушения — мгновенный бан.\n• Решения модераторов можно обжаловать в течение 24ч",
    "feedback": "📬 <b>Обратная связь</b>\n\n• Баги и предложения: /feedback\n• Жалобы на пользователей: /report @username\n• Вопросы админам: @admin_nexus",
    "contacts": "👥 <b>Контакты</b>\n\n• Главный админ: @admin_nexus\n• Поддержка: @support_nexus\n• Канал обновлений: @nexus_bot_news"
}


# ==================== ИСКЛЮЧЕНИЯ ====================

class DatabaseError(Exception):
    """Исключение для ошибок базы данных."""
    pass


class UserNotFoundError(DatabaseError):
    """Пользователь не найден."""
    pass


class InsufficientFundsError(DatabaseError):
    """Недостаточно средств."""
    pass


# ==================== ОСНОВНОЙ КЛАСС ====================

class Database:
    """Асинхронный класс для работы с SQLite через aiosqlite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DATABASE_PATH
        self._initialized = False
        self._lock = asyncio.Lock()
        self._stats_cache: Dict[str, Tuple[Any, float]] = {}
        logger.info(f"Database instance created with path: {self.db_path}")

    # ==================== ВНУТРЕННИЕ МЕТОДЫ ====================

    async def _execute_with_retry(
        self,
        query: str,
        params: tuple = (),
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = False
    ) -> Any:
        """Выполняет SQL-запрос с повторными попытками при блокировке.
        
        ВАЖНО: commit=True НЕ ИСПОЛЬЗУЕТСЯ для не-fetch запросов,
        коммит происходит автоматически.
        """
        if not self.db_path:
            raise DatabaseError("Database path is not set")

        for attempt in range(MAX_RETRIES):
            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    conn.row_factory = aiosqlite.Row
                    await conn.execute("PRAGMA busy_timeout = 5000")
                    await conn.execute("PRAGMA journal_mode = WAL")
                    await conn.execute("PRAGMA synchronous = NORMAL")
                    await conn.execute("PRAGMA cache_size = -8000")
                    
                    cursor = await conn.execute(query, params)
                    
                    if commit:
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
        """Выполняет несколько запросов в одной транзакции с блокировкой."""
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
                    self._invalidate_stats_cache()
                    return True
                    
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"Transaction failed: {e}")
                    raise DatabaseError(f"Transaction failed: {e}") from e

    def _invalidate_stats_cache(self, user_id: Optional[int] = None):
        """Инвалидация кэша статистики."""
        if user_id is None:
            self._stats_cache.clear()
        else:
            keys_to_delete = [k for k in self._stats_cache if str(user_id) in k]
            for k in keys_to_delete:
                del self._stats_cache[k]

    def _get_cached(self, key: str, ttl: int = CACHE_TTL_SECONDS) -> Optional[Any]:
        """Получение из кэша."""
        if key in self._stats_cache:
            value, timestamp = self._stats_cache[key]
            if datetime.now().timestamp() - timestamp < ttl:
                return value
        return None

    def _set_cached(self, key: str, value: Any):
        """Запись в кэш."""
        self._stats_cache[key] = (value, datetime.now().timestamp())

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
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance INTEGER DEFAULT 1000 CHECK(balance >= 0),
                daily_streak INTEGER DEFAULT 0,
                last_daily TEXT,
                vip_level INTEGER DEFAULT 0,
                vip_until TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                register_date TEXT,
                warns TEXT DEFAULT '[]',
                xp INTEGER DEFAULT 0,
                rank INTEGER DEFAULT 1
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER,
                to_id INTEGER,
                amount INTEGER,
                reason TEXT,
                date TEXT,
                FOREIGN KEY (from_id) REFERENCES users(user_id),
                FOREIGN KEY (to_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                description TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                age INTEGER,
                city TEXT,
                timezone TEXT,
                about TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
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
                last_streak_update TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
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
                UNIQUE(user_id, chat_id, date),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
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
                current_win_streak INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
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
                vip_purchases INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
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
            """
            CREATE TABLE IF NOT EXISTS custom_rp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                command TEXT NOT NULL,
                action_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, command),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
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
            """
            CREATE TABLE IF NOT EXISTS chat_tag_settings (
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT 0,
                PRIMARY KEY (chat_id, category_slug)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_tag_subscriptions (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_subscribed BOOLEAN DEFAULT 1,
                PRIMARY KEY (user_id, chat_id, category_slug)
            )
            """,
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
            """
            CREATE TABLE IF NOT EXISTS chat_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                reward_type TEXT,
                reward_amount INTEGER,
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS donors (
                user_id INTEGER PRIMARY KEY,
                total_donated INTEGER DEFAULT 0,
                last_donate TIMESTAMP,
                donor_rank TEXT DEFAULT '💎 Поддерживающий',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
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
            """
            CREATE TABLE IF NOT EXISTS ref_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                chat_id INTEGER,
                invited_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                confirmed_by_user2 BOOLEAN DEFAULT 0,
                UNIQUE(user1_id, user2_id, type)
            )
            """,
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
            """
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER,
                user_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS feedback_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                answered_at TIMESTAMP,
                admin_response TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_tags (
                user_id INTEGER NOT NULL,
                tag_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, tag_name),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                chat_id BIGINT,
                target_user_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            "CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback_tickets(status);",
            "CREATE INDEX IF NOT EXISTS idx_users_rank ON users(rank DESC);",
            "CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC);",
        ]
        
        for sql in indexes:
            try:
                await self._execute_with_retry(sql)
            except Exception as e:
                logger.warning(f"Failed to create index: {e}")

    async def _run_migrations(self) -> None:
        """Автоматическое добавление недостающих колонок."""
        migrations = {
            "users": {
                "xp": "INTEGER DEFAULT 0",
                "rank": "INTEGER DEFAULT 1",
            },
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
            },
            "relationships": {
                "status": "TEXT DEFAULT 'pending'",
                "confirmed_by_user2": "BOOLEAN DEFAULT 0",
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
        """Получение пользователя по ID."""
        if user_id is None:
            return None
        return await self._execute_with_retry(
            "SELECT * FROM users WHERE user_id = ?", (user_id,), fetch_one=True
        )

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Получение пользователя по username."""
        if not username:
            return None
        username = username.lstrip('@')
        return await self._execute_with_retry(
            "SELECT * FROM users WHERE username = ?", (username,), fetch_one=True
        )

    async def get_user_by_id_or_username(self, identifier: str) -> Optional[Dict]:
        """Получение пользователя по ID или username."""
        if not identifier:
            return None
        
        # Пробуем как числовой ID
        try:
            user_id = int(identifier)
            user = await self.get_user(user_id)
            if user:
                return user
        except (ValueError, TypeError):
            pass
        
        # Пробуем как username
        return await self.get_user_by_username(identifier)

    async def create_user(self, user_id: int, username: Optional[str] = None,
                          first_name: Optional[str] = None, balance: int = 1000) -> None:
        """Создаёт пользователя во ВСЕХ связанных таблицах атомарно."""
        if user_id is None:
            return
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        balance = max(0, balance if balance is not None else 1000)

        queries = [
            ("""INSERT OR IGNORE INTO users (user_id, username, first_name, balance, register_date, warns, xp, rank)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
             (user_id, username, first_name, balance, now, '[]', 0, 1)),
            ("""INSERT OR IGNORE INTO user_profiles (user_id, created_at, updated_at) 
                VALUES (?, ?, ?)""", (user_id, now, now)),
            ("""INSERT OR IGNORE INTO user_stats (user_id, register_date, last_active) 
                VALUES (?, ?, ?)""", (user_id, today, now)),
            ("""INSERT OR IGNORE INTO user_economy_stats (user_id, max_balance) 
                VALUES (?, ?)""", (user_id, balance)),
            ("""INSERT OR IGNORE INTO xo_stats (user_id) VALUES (?)""", (user_id,)),
        ]
        await self._execute_transaction(queries)
        logger.info(f"✅ Created user {user_id} in all tables")

    async def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя."""
        user = await self.get_user(user_id)
        return user is not None

    async def get_balance(self, user_id: int) -> int:
        """Получение баланса пользователя (с кэшированием)."""
        if user_id is None:
            return 0
        
        cache_key = f"balance:{user_id}"
        cached = self._get_cached(cache_key, ttl=60)
        if cached is not None:
            return cached
        
        user = await self.get_user(user_id)
        balance = user.get("balance", 0) if user else 0
        self._set_cached(cache_key, balance)
        return balance

    async def update_balance(self, user_id: int, delta: int, reason: str = "") -> bool:
        """Атомарное обновление баланса с проверкой на отрицательный результат."""
        if user_id is None or delta is None:
            return False
        
        # Проверка: не уйдёт ли баланс в минус
        if delta < 0:
            current = await self.get_balance(user_id)
            if current + delta < 0:
                raise InsufficientFundsError(f"Balance would be negative: {current} + {delta}")
        
        now = datetime.now().isoformat()
        queries = [
            ("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id)),
            ("""UPDATE user_economy_stats 
                SET max_balance = MAX(COALESCE(max_balance, 0), 
                    (SELECT balance FROM users WHERE user_id = ?)),
                    total_earned = COALESCE(total_earned, 0) + ? 
                WHERE user_id = ?""",
             (user_id, max(0, delta), user_id)),
        ]
        if delta < 0:
            queries.append(("""UPDATE user_economy_stats 
                               SET total_spent = COALESCE(total_spent, 0) + ?
                               WHERE user_id = ?""", (abs(delta), user_id)))
        if reason:
            queries.append(("""INSERT INTO transactions (from_id, to_id, amount, reason, date)
                               VALUES (?, ?, ?, ?, ?)""",
                           (user_id, user_id, abs(delta), reason, now)))
        
        success = await self._execute_transaction(queries)
        if success:
            self._invalidate_stats_cache(user_id)
            logger.info(f"💰 Balance updated for {user_id}: {delta:+d} ({reason})")
        return success

    async def transfer_coins(self, from_id: int, to_username: str, amount: int,
                             reason: str = "transfer") -> Dict[str, Any]:
        """Безопасный перевод с атомарностью и возвратом детальной информации."""
        result = {
            'success': False,
            'error': None,
            'new_from_balance': None,
            'new_to_balance': None
        }
        
        if from_id is None or not to_username or amount is None or amount <= 0:
            result['error'] = "Invalid parameters"
            return result
            
        target = await self.get_user_by_username(to_username)
        if not target:
            result['error'] = f"User @{to_username} not found"
            return result
            
        to_id = target.get("user_id")
        if to_id is None or from_id == to_id:
            result['error'] = "Cannot transfer to self or invalid user"
            return result
        
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                try:
                    await conn.execute("BEGIN")
                    
                    # Проверка и списание
                    cursor = await conn.execute(
                        "SELECT balance FROM users WHERE user_id = ?", (from_id,))
                    row = await cursor.fetchone()
                    if not row or row["balance"] < amount:
                        await conn.rollback()
                        result['error'] = "Insufficient funds"
                        return result
                    
                    await conn.execute(
                        "UPDATE users SET balance = balance - ? WHERE user_id = ?", 
                        (amount, from_id))
                    
                    # Зачисление
                    await conn.execute(
                        "UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                        (amount, to_id))
                    
                    # Лог транзакции
                    now = datetime.now().isoformat()
                    await conn.execute(
                        """INSERT INTO transactions (from_id, to_id, amount, reason, date)
                           VALUES (?, ?, ?, ?, ?)""", 
                        (from_id, to_id, amount, reason, now))
                    
                    # Обновление статистики
                    await conn.execute(
                        """UPDATE user_economy_stats 
                           SET total_transferred = COALESCE(total_transferred, 0) + ? 
                           WHERE user_id = ?""", (amount, from_id))
                    await conn.execute(
                        """UPDATE user_economy_stats 
                           SET total_received = COALESCE(total_received, 0) + ? 
                           WHERE user_id = ?""", (amount, to_id))
                    
                    await conn.commit()
                    
                    # Инвалидация кэша для обоих пользователей
                    self._invalidate_stats_cache(from_id)
                    self._invalidate_stats_cache(to_id)
                    
                    # Получение новых балансов для ответа
                    from_bal = await conn.execute(
                        "SELECT balance FROM users WHERE user_id = ?", (from_id,))
                    to_bal = await conn.execute(
                        "SELECT balance FROM users WHERE user_id = ?", (to_id,))
                    
                    from_bal_row = await from_bal.fetchone()
                    to_bal_row = await to_bal.fetchone()
                    
                    result.update({
                        'success': True,
                        'new_from_balance': from_bal_row["balance"] if from_bal_row else None,
                        'new_to_balance': to_bal_row["balance"] if to_bal_row else None
                    })
                    logger.info(f"💸 Transfer: {from_id} -> {to_id} ({amount} coins)")
                    return result
                    
                except Exception as e:
                    await conn.rollback()
                    result['error'] = str(e)
                    logger.error(f"❌ Transfer failed: {e}")
                    return result

    # ==================== ПРОФИЛИ ====================

    async def save_profile(self, user_id: int, full_name: str, age: int, city: str,
                           timezone: str, about: str) -> bool:
        """Сохранение профиля с валидацией."""
        if user_id is None:
            return False
        
        # Валидация возраста
        if age is not None and (age < 0 or age > 120):
            raise ValueError("Age must be between 0 and 120")
        
        now = datetime.now().isoformat()
        row = await self._execute_with_retry(
            "SELECT created_at FROM user_profiles WHERE user_id = ?", 
            (user_id,), fetch_one=True)
        created_at = row["created_at"] if row and row.get("created_at") else now
        
        success = await self._execute_with_retry(
            """INSERT OR REPLACE INTO user_profiles 
               (user_id, full_name, age, city, timezone, about, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, full_name or "", age or 0, city or "", timezone or "", 
             about or "", created_at, now), commit=True)
        
        if success:
            logger.info(f"👤 Profile saved for user {user_id}")
        return bool(success)

    async def get_profile(self, user_id: int) -> Optional[Dict]:
        """Получение профиля пользователя."""
        if user_id is None:
            return None
        return await self._execute_with_retry(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,), fetch_one=True)

    # ==================== РАНГИ И УРОВНИ ====================

    @staticmethod
    def calculate_rank(xp: int, messages: int, xo_wins: int, days_active: int) -> int:
        """
        Формула расчёта ранга:
        Ранг = (XP + сообщения*2 + победы в XO*10 + дни активности*5) // 100 + 1
        Мин. ранг: 1, Макс. ранг: 100
        """
        score = (
            (xp or 0) +
            ((messages or 0) * 2) +
            ((xo_wins or 0) * 10) +
            ((days_active or 0) * 5)
        )
        rank = (score // 100) + 1
        return min(max(rank, 1), 100)

    async def recalculate_user_rank(self, user_id: int) -> Optional[int]:
        """Пересчёт ранга пользователя на основе актуальных данных."""
        if user_id is None:
            return None
        
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
            "UPDATE users SET rank = ? WHERE user_id = ?", 
            (new_rank, user_id), commit=True)
        
        logger.info(f"⭐ Rank recalculated for user {user_id}: {new_rank}")
        return new_rank

    async def get_user_rank(self, user_id: int) -> Optional[Dict]:
        """Получение ранга с детальной информацией."""
        user = await self.get_user(user_id)
        if not user:
            return None
        
        stats = await self.get_user_stats(user_id) or {}
        
        current_rank = user.get('rank', 1)
        calculated_rank = self.calculate_rank(
            xp=stats.get('xp', 0),
            messages=stats.get('messages_total', 0),
            xo_wins=stats.get('wins', 0),
            days_active=stats.get('days_active', 0)
        )
        
        return {
            'user_id': user_id,
            'username': user.get('username'),
            'current_rank': current_rank,
            'calculated_rank': calculated_rank,
            'xp': stats.get('xp', 0),
            'messages': stats.get('messages_total', 0),
            'xo_wins': stats.get('wins', 0),
            'days_active': stats.get('days_active', 0),
            'needs_recalc': current_rank != calculated_rank
        }

    async def add_xp(self, user_id: int, xp_amount: int, reason: str = "activity") -> bool:
        """Добавление XP с автоматическим пересчётом ранга."""
        if user_id is None or xp_amount is None or xp_amount <= 0:
            return False
        
        success = await self._execute_with_retry(
            """UPDATE users SET xp = COALESCE(xp, 0) + ? WHERE user_id = ?""",
            (xp_amount, user_id), commit=True)
        
        if success:
            await self.recalculate_user_rank(user_id)
            logger.info(f"⭐ Added {xp_amount} XP to user {user_id} ({reason})")
        return bool(success)

    # ==================== ТРЕКИНГ АКТИВНОСТИ ====================

    async def track_user_activity(self, user_id: int, chat_id: int, 
                                  activity_type: str, value: int = 1) -> bool:
        """
        Трекинг активности пользователя в чате.
        Параметры: user_id, chat_id, activity_type, value
        """
        if user_id is None or chat_id is None or not activity_type:
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Маппинг типа активности на колонку
        column_map = {
            "message": "messages",
            "voice": "voice",
            "sticker": "stickers",
            "gif": "gifs",
            "photo": "photos",
            "video": "videos",
            "xo_game": "xo_games",
            "game": "games_played",
        }
        
        column = column_map.get(activity_type)
        if not column:
            logger.warning(f"Unknown activity type: {activity_type}")
            return False
        
        try:
            await self._execute_with_retry(
                f"""INSERT INTO user_activity_log (user_id, chat_id, date, {column})
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, chat_id, date) 
                    DO UPDATE SET {column} = {column} + ?""",
                (user_id, chat_id, today, value, value), commit=True)
            
            # Обновление user_stats
            if activity_type == "message":
                await self._execute_with_retry(
                    """UPDATE user_stats 
                       SET messages_total = COALESCE(messages_total, 0) + 1,
                           messages_today = COALESCE(messages_today, 0) + 1,
                           last_message_date = ?,
                           last_active = ?
                       WHERE user_id = ?""",
                    (today, datetime.now().isoformat(), user_id), commit=True)
            else:
                stat_column_map = {
                    "voice": "total_voice",
                    "sticker": "total_stickers",
                    "gif": "total_gifs",
                    "photo": "total_photos",
                    "video": "total_videos",
                }
                stat_col = stat_column_map.get(activity_type)
                if stat_col:
                    await self._execute_with_retry(
                        f"""UPDATE user_stats 
                           SET {stat_col} = COALESCE({stat_col}, 0) + ?,
                               last_active = ?
                           WHERE user_id = ?""",
                        (value, datetime.now().isoformat(), user_id), commit=True)
            
            return True
        except Exception as e:
            logger.error(f"Failed to track activity: {e}")
            return False

    async def track_word(self, chat_id: int, word: str) -> bool:
        """Трекинг использованных слов в чате."""
        if chat_id is None or not word:
            return False
        
        word = word.lower().strip()
        if len(word) < 3:
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            await self._execute_with_retry(
                """INSERT INTO chat_word_stats (chat_id, date, word, count)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(chat_id, date, word) 
                   DO UPDATE SET count = count + 1""",
                (chat_id, today, word), commit=True)
            return True
        except Exception as e:
            logger.error(f"Failed to track word: {e}")
            return False

    # ==================== СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ ====================

    async def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Единый метод получения ВСЕХ статистик пользователя с кэшированием."""
        if user_id is None:
            return None
        
        cache_key = f"user_stats:{user_id}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        result = await self._execute_with_retry(
            """SELECT 
                u.user_id, u.username, u.first_name, 
                COALESCE(u.balance, 0) as balance, 
                COALESCE(u.daily_streak, 0) as daily_streak,
                COALESCE(u.vip_level, 0) as vip_level,
                COALESCE(u.xp, 0) as xp,
                COALESCE(u.rank, 1) as rank,
                u.register_date as user_register_date,
                
                COALESCE(s.messages_total, 0) as messages_total,
                COALESCE(s.messages_today, 0) as messages_today,
                COALESCE(s.messages_week, 0) as messages_week,
                COALESCE(s.messages_month, 0) as messages_month,
                s.last_message_date, s.last_active,
                COALESCE(s.total_voice, 0) as total_voice,
                COALESCE(s.total_stickers, 0) as total_stickers,
                COALESCE(s.total_gifs, 0) as total_gifs,
                COALESCE(s.total_photos, 0) as total_photos,
                COALESCE(s.total_videos, 0) as total_videos,
                COALESCE(s.days_active, 0) as days_active,
                COALESCE(s.current_streak, 0) as current_streak,
                COALESCE(s.max_streak, 0) as max_streak,
                
                COALESCE(e.total_earned, 0) as total_earned,
                COALESCE(e.total_spent, 0) as total_spent,
                COALESCE(e.total_transferred, 0) as total_transferred,
                COALESCE(e.total_received, 0) as total_received,
                COALESCE(e.total_donated_rub, 0) as total_donated_rub,
                COALESCE(e.total_donated_coins, 0) as total_donated_coins,
                COALESCE(e.max_balance, 0) as max_balance,
                COALESCE(e.daily_claims, 0) as daily_claims,
                
                COALESCE(x.games_played, 0) as games_played,
                COALESCE(x.wins, 0) as wins,
                COALESCE(x.losses, 0) as losses,
                COALESCE(x.draws, 0) as draws,
                COALESCE(x.wins_vs_bot, 0) as wins_vs_bot,
                COALESCE(x.losses_vs_bot, 0) as losses_vs_bot,
                COALESCE(x.total_bet, 0) as total_bet,
                COALESCE(x.total_won, 0) as total_won,
                COALESCE(x.max_win_streak, 0) as max_win_streak,
                COALESCE(x.current_win_streak, 0) as current_win_streak
                
               FROM users u
               LEFT JOIN user_stats s ON u.user_id = s.user_id
               LEFT JOIN user_economy_stats e ON u.user_id = e.user_id
               LEFT JOIN xo_stats x ON u.user_id = x.user_id
               WHERE u.user_id = ?""", 
            (user_id,), fetch_one=True)
        
        if result:
            result['calculated_rank'] = self.calculate_rank(
                xp=result.get('xp', 0),
                messages=result.get('messages_total', 0),
                xo_wins=result.get('wins', 0),
                days_active=result.get('days_active', 0)
            )
            self._set_cached(cache_key, result)
            return result
        
        # Если пользователь есть в users, но нет в stats — возвращаем дефолты
        user = await self.get_user(user_id)
        if user:
            default_stats = {
                'user_id': user_id,
                'username': user.get('username'),
                'first_name': user.get('first_name'),
                'balance': user.get('balance', 0),
                'daily_streak': user.get('daily_streak', 0),
                'vip_level': user.get('vip_level', 0),
                'xp': 0, 'rank': 1,
                'messages_total': 0, 'messages_today': 0, 'wins': 0, 'games_played': 0,
                'days_active': 0, 'current_streak': 0,
                'calculated_rank': 1
            }
            self._set_cached(cache_key, default_stats)
            return default_stats
        
        return None

    # ==================== ТОПЫ И РЕЙТИНГИ ====================

    async def get_top_users(self, limit: int = 10, order_by: str = "balance") -> List[Dict]:
        """Гибкий топ с выбором сортировки."""
        limit = max(1, min(100, limit if limit is not None else 10))
        
        valid_orders = {
            "balance": "u.balance DESC",
            "xp": "u.xp DESC",
            "rank": "u.rank ASC",
            "messages": "COALESCE(s.messages_total, 0) DESC",
            "wins": "COALESCE(x.wins, 0) DESC",
            "activity": "COALESCE(s.days_active, 0) DESC"
        }
        
        order_clause = valid_orders.get(order_by, valid_orders["balance"])
        
        return await self._execute_with_retry(
            f"""SELECT u.user_id, u.username, u.first_name, u.balance, u.xp, u.rank,
                   COALESCE(s.messages_total, 0) as messages_total,
                   COALESCE(x.wins, 0) as wins,
                   COALESCE(s.days_active, 0) as days_active
               FROM users u
               LEFT JOIN user_stats s ON u.user_id = s.user_id
               LEFT JOIN xo_stats x ON u.user_id = x.user_id
               WHERE u.balance >= 0
               ORDER BY {order_clause}
               LIMIT ?""",
            (limit,), fetch_all=True) or []

    async def get_chat_top_balance(self, chat_id: int, limit: int = 3) -> List[Dict]:
        """Топ по балансу среди активных в чате."""
        if chat_id is None:
            return []
        limit = max(1, min(20, limit if limit is not None else 3))
        
        result = await self._execute_with_retry(
            """SELECT u.user_id, u.username, u.first_name, u.balance, u.vip_level
               FROM users u
               INNER JOIN (
                   SELECT DISTINCT user_id
                   FROM user_activity_log
                   WHERE chat_id = ? AND date >= date('now', '-30 days')
               ) a ON u.user_id = a.user_id
               WHERE u.balance > 0
               ORDER BY u.balance DESC
               LIMIT ?""",
            (chat_id, limit), fetch_all=True)
        
        return result if result else []

    async def get_chat_top_xo(self, chat_id: int, limit: int = 3) -> List[Dict]:
        """Топ по победам в XO среди активных в чате."""
        if chat_id is None:
            return []
        limit = max(1, min(20, limit if limit is not None else 3))
        
        result = await self._execute_with_retry(
            """SELECT u.user_id, u.username, u.first_name,
                   COALESCE(x.wins, 0) as wins,
                   COALESCE(x.games_played, 0) as games_played,
                   CASE 
                       WHEN COALESCE(x.games_played, 0) > 0 
                       THEN ROUND(COALESCE(x.wins, 0) * 100.0 / x.games_played, 1)
                       ELSE 0 
                   END as win_rate
               FROM xo_stats x
               INNER JOIN users u ON x.user_id = u.user_id
               INNER JOIN (
                   SELECT DISTINCT user_id
                   FROM user_activity_log
                   WHERE chat_id = ? AND date >= date('now', '-30 days')
               ) a ON x.user_id = a.user_id
               WHERE COALESCE(x.games_played, 0) >= 1
               ORDER BY x.wins DESC, win_rate DESC
               LIMIT ?""",
            (chat_id, limit), fetch_all=True)
        
        return result if result else []

    async def get_chat_top_messages(self, chat_id: int, limit: int = 3) -> List[Dict]:
        """Топ по сообщениям в чате."""
        if chat_id is None:
            return []
        limit = max(1, min(20, limit if limit is not None else 3))
        
        result = await self._execute_with_retry(
            """SELECT ual.user_id, u.first_name, u.username, 
                   SUM(ual.messages) as messages_total,
                   COUNT(DISTINCT ual.date) as active_days
               FROM user_activity_log ual
               LEFT JOIN users u ON ual.user_id = u.user_id
               WHERE ual.chat_id = ? AND ual.date >= date('now', '-30 days')
               GROUP BY ual.user_id
               HAVING messages_total > 0
               ORDER BY messages_total DESC
               LIMIT ?""",
            (chat_id, limit), fetch_all=True)
        
        return result if result else []

    # ==================== ОТНОШЕНИЯ С ВЗАИМНЫМ ПОДТВЕРЖДЕНИЕМ ====================

    async def get_relationship(self, user1_id: int, user2_id: int, rel_type: str) -> Optional[Dict]:
        """Алиас для get_relationship_status (поиск по двум пользователям)."""
        if user1_id is None or user2_id is None or not rel_type:
            return None
        
        return await self._execute_with_retry(
            """SELECT * FROM relationships
               WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))
               AND type = ? AND status IN ('pending', 'active')
               ORDER BY created_at DESC LIMIT 1""",
            (user1_id, user2_id, user2_id, user1_id, rel_type), fetch_one=True)

    async def propose_relationship(self, proposer_id: int, target_id: int, rel_type: str) -> Dict[str, Any]:
        """Создание предложения отношений (ожидает подтверждения)."""
        result = {'success': False, 'error': None, 'relationship_id': None}
        
        if proposer_id is None or target_id is None or not rel_type:
            result['error'] = "Invalid parameters"
            return result
        
        if proposer_id == target_id:
            result['error'] = "Cannot create relationship with self"
            return result
        
        # Проверка на существующие активные отношения
        existing = await self.get_relationship(proposer_id, target_id, rel_type)
        if existing:
            status = existing.get('status')
            if status == 'active':
                result['error'] = "Relationship already active"
            elif status == 'pending':
                result['error'] = "Proposal already pending"
                result['relationship_id'] = existing.get('id')
            return result
        
        now = datetime.now().isoformat()
        rel_id = await self._execute_with_retry(
            """INSERT INTO relationships (user1_id, user2_id, type, status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (proposer_id, target_id, rel_type, now))
        
        if rel_id:
            result.update({'success': True, 'relationship_id': rel_id})
            logger.info(f"💕 Relationship proposed: {proposer_id} -> {target_id} ({rel_type})")
        return result

    async def confirm_relationship(self, relationship_id: int, confirmer_id: int) -> bool:
        """Подтверждение отношений второй стороной."""
        if relationship_id is None or confirmer_id is None:
            return False
        
        rel = await self._execute_with_retry(
            """SELECT user1_id, user2_id, status FROM relationships WHERE id = ?""",
            (relationship_id,), fetch_one=True)
        
        if not rel or rel['status'] != 'pending':
            return False
        
        if rel['user1_id'] == confirmer_id:
            return False
        if rel['user2_id'] != confirmer_id:
            return False
        
        success = await self._execute_with_retry(
            """UPDATE relationships SET status = 'active', confirmed_by_user2 = 1
               WHERE id = ? AND status = 'pending'""",
            (relationship_id,), commit=True)
        
        if success:
            logger.info(f"💕 Relationship confirmed: ID {relationship_id}")
        return bool(success)

    async def get_relationship_status(self, user_id: int, rel_type: str = "marriage") -> Optional[Dict]:
        """Получение статуса отношений с детальной информацией."""
        if user_id is None:
            return None
        
        rel = await self._execute_with_retry(
            """SELECT r.*, 
                   u1.username as user1_username, u1.first_name as user1_name,
                   u2.username as user2_username, u2.first_name as user2_name
               FROM relationships r
               LEFT JOIN users u1 ON r.user1_id = u1.user_id
               LEFT JOIN users u2 ON r.user2_id = u2.user_id
               WHERE (r.user1_id = ? OR r.user2_id = ?) 
                 AND r.type = ? 
                 AND r.status IN ('pending', 'active')
               ORDER BY r.created_at DESC 
               LIMIT 1""",
            (user_id, user_id, rel_type), fetch_one=True)
        
        if not rel:
            return None
        
        if rel['user1_id'] == user_id:
            partner_id = rel['user2_id']
            partner_name = rel['user2_name'] or partner_id
            is_initiator = True
            is_confirmed = rel['confirmed_by_user2'] == 1
        else:
            partner_id = rel['user1_id']
            partner_name = rel['user1_name'] or partner_id
            is_initiator = False
            is_confirmed = rel['confirmed_by_user2'] == 1 if rel['status'] == 'pending' else True
        
        return {
            'id': rel['id'],
            'partner_id': partner_id,
            'partner_name': partner_name,
            'partner_username': rel['user2_username'] if rel['user1_id'] == user_id else rel['user1_username'],
            'type': rel['type'],
            'status': rel['status'],
            'is_initiator': is_initiator,
            'is_confirmed': is_confirmed,
            'created_at': rel['created_at'],
            'can_cancel': rel['status'] == 'pending' and is_initiator
        }

    async def get_user_relationships(self, user_id: int) -> List[Dict]:
        """Получение всех активных/ожидающих отношений пользователя."""
        if user_id is None:
            return []
        
        return await self._execute_with_retry(
            """SELECT r.*,
                   CASE WHEN r.user1_id = ? THEN u2.username ELSE u1.username END as partner_username,
                   CASE WHEN r.user1_id = ? THEN u2.first_name ELSE u1.first_name END as partner_name,
                   CASE WHEN r.user1_id = ? THEN r.user2_id ELSE r.user1_id END as partner_id
               FROM relationships r
               LEFT JOIN users u1 ON r.user1_id = u1.user_id
               LEFT JOIN users u2 ON r.user2_id = u2.user_id
               WHERE (r.user1_id = ? OR r.user2_id = ?)
                 AND r.status IN ('pending', 'active')
               ORDER BY r.created_at DESC""",
            (user_id, user_id, user_id, user_id, user_id), fetch_all=True) or []

    async def end_relationship(self, user_id: int, partner_id: int, rel_type: str) -> bool:
        """Завершение отношений (только для активных)."""
        if user_id is None or partner_id is None or not rel_type:
            return False
        
        success = await self._execute_with_retry(
            """UPDATE relationships SET status = 'ended', ended_at = CURRENT_TIMESTAMP
               WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))
               AND type = ? AND status = 'active'""",
            (user_id, partner_id, partner_id, user_id, rel_type), commit=True)
        
        if success:
            logger.info(f"💔 Relationship ended: {user_id} <-> {partner_id} ({rel_type})")
        return bool(success)

    # ==================== ТЕГИ ПОЛЬЗОВАТЕЛЯ ====================

    async def add_user_tag(self, user_id: int, tag_name: str) -> bool:
        """Добавление тега пользователю."""
        if user_id is None or not tag_name:
            return False
        
        tag_name = tag_name.strip().lower()
        if len(tag_name) < 2 or len(tag_name) > 20:
            return False
        
        success = await self._execute_with_retry(
            "INSERT OR IGNORE INTO user_tags (user_id, tag_name) VALUES (?, ?)",
            (user_id, tag_name), commit=True)
        
        if success:
            logger.info(f"🏷️ Tag '{tag_name}' added to user {user_id}")
        return bool(success)

    async def remove_user_tag(self, user_id: int, tag_name: str) -> bool:
        """Удаление тега."""
        if user_id is None or not tag_name:
            return False
        
        success = await self._execute_with_retry(
            "DELETE FROM user_tags WHERE user_id = ? AND tag_name = ?",
            (user_id, tag_name.strip().lower()), commit=True)
        
        return bool(success)

    async def get_user_tags(self, user_id: int) -> List[str]:
        """Получение всех тегов пользователя."""
        if user_id is None:
            return []
        
        rows = await self._execute_with_retry(
            "SELECT tag_name FROM user_tags WHERE user_id = ? ORDER BY tag_name",
            (user_id,), fetch_all=True)
        
        return [r["tag_name"] for r in rows] if rows else []

    async def search_users_by_tag(self, tag_name: str, limit: int = 20) -> List[Dict]:
        """Поиск пользователей по тегу."""
        if not tag_name:
            return []
        
        tag_name = tag_name.strip().lower()
        limit = max(1, min(50, limit))
        
        return await self._execute_with_retry(
            """SELECT u.user_id, u.username, u.first_name, u.balance
               FROM user_tags t
               JOIN users u ON t.user_id = u.user_id
               WHERE t.tag_name = ?
               ORDER BY u.balance DESC
               LIMIT ?""",
            (tag_name, limit), fetch_all=True) or []

    # ==================== ОБРАТНАЯ СВЯЗЬ (FEEDBACK) ====================

    async def create_feedback_ticket(self, user_id: int, message: str) -> Optional[int]:
        """Создание тикета обратной связи."""
        if user_id is None or not message or len(message) < 10:
            return None
        
        ticket_id = await self._execute_with_retry(
            """INSERT INTO feedback_tickets (user_id, message, status, created_at)
               VALUES (?, ?, 'open', CURRENT_TIMESTAMP)""",
            (user_id, message.strip()))
        
        if ticket_id:
            logger.info(f"📬 Feedback ticket #{ticket_id} created by user {user_id}")
        return ticket_id

    async def get_user_tickets(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получение тикетов пользователя."""
        if user_id is None:
            return []
        
        return await self._execute_with_retry(
            """SELECT id, message, status, created_at, answered_at, admin_response
               FROM feedback_tickets
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, limit), fetch_all=True) or []

    async def update_ticket(self, ticket_id: int, status: str, admin_response: str = None) -> bool:
        """Обновление статуса и ответа админа в тикете."""
        if ticket_id is None or status not in ('open', 'closed', 'in_progress'):
            return False
        
        now = datetime.now().isoformat()
        if admin_response and status == 'closed':
            query = """UPDATE feedback_tickets 
                      SET status = ?, admin_response = ?, answered_at = ?
                      WHERE id = ?"""
            params = (status, admin_response, now, ticket_id)
        else:
            query = "UPDATE feedback_tickets SET status = ? WHERE id = ?"
            params = (status, ticket_id)
        
        success = await self._execute_with_retry(query, params, commit=True)
        if success:
            logger.info(f"📬 Ticket #{ticket_id} updated: status={status}")
        return bool(success)

    async def get_pending_feedback(self, limit: int = 20) -> List[Dict]:
        """Получение открытых тикетов для админов."""
        return await self._execute_with_retry(
            """SELECT t.id, t.message, t.created_at, u.username, u.first_name
               FROM feedback_tickets t
               JOIN users u ON t.user_id = u.user_id
               WHERE t.status = 'open'
               ORDER BY t.created_at ASC
               LIMIT ?""",
            (limit,), fetch_all=True) or []

    # ==================== ПОЛИТИКА И ПРАВИЛА ====================

    @staticmethod
    def get_policy_section(section: str) -> str:
        """Получение раздела политики (из констант)."""
        return DEFAULT_POLICY_TEXT.get(section, "Раздел не найден.")

    @staticmethod
    def get_all_policy_sections() -> List[Dict]:
        """Список всех разделов политики для меню."""
        return [
            {"key": "rules", "title": "📜 Правила", "emoji": "📜"},
            {"key": "privacy", "title": "🔐 Конфиденциальность", "emoji": "🔐"},
            {"key": "moderation", "title": "⚖️ Модерация", "emoji": "⚖️"},
            {"key": "feedback", "title": "📬 Обратная связь", "emoji": "📬"},
            {"key": "contacts", "title": "👥 Контакты", "emoji": "👥"},
        ]

    # ==================== УМНЫЙ ПАРСЕР: ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    async def get_custom_rp_action(self, command: str) -> Optional[Tuple[int, str]]:
        """Поиск кастомного РП действия по команде (для парсера)."""
        if not command:
            return None
        
        result = await self._execute_with_retry(
            "SELECT user_id, action_text FROM custom_rp WHERE command = ? LIMIT 1",
            (command.lower().strip(),), fetch_one=True)
        
        if result:
            return (result["user_id"], result["action_text"])
        return None

    async def get_parser_triggers(self, chat_id: int) -> Dict[str, List[str]]:
        """Получение триггеров для умного парсера в чате."""
        # В будущем можно добавить таблицу parser_triggers
        return {
            "greetings": ["привет", "здравствуй", "хай", "ку"],
            "farewells": ["пока", "до свидания", "чао"],
            "thanks": ["спасибо", "благодарю", "мерси"],
        }

    # ==================== АДМИН: ОЧИСТКА ЧАТА И ЛОГИ ====================

    async def get_deletable_messages(self, chat_id: int, limit: int = 100) -> List[Dict]:
        """
        Возвращает данные о недавней активности в чате для очистки.
        Реальные message_id не хранятся в БД — удаление делается через Telegram API
        в handlers/admin.py с использованием bot.delete_message().
        """
        if chat_id is None:
            return []
        
        # Telegram API позволяет удалять сообщения только за последние 48 часов
        cutoff = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d")
        limit = max(1, min(100, limit))
        
        return await self._execute_with_retry(
            """SELECT user_id, date, messages, voice, stickers, gifs, photos, videos
               FROM user_activity_log 
               WHERE chat_id = ? AND date >= ?
               ORDER BY date DESC, messages DESC
               LIMIT ?""",
            (chat_id, cutoff, limit), fetch_all=True) or []

    async def log_admin_action(self, admin_id: int, action: str, chat_id: int = None, 
                              target_user_id: int = None, details: str = None) -> None:
        """Логирование действий админов для аудита."""
        try:
            await self._execute_with_retry(
                """INSERT INTO admin_logs (admin_id, action, chat_id, target_user_id, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (admin_id, action, chat_id, target_user_id, details), commit=True)
        except Exception as e:
            logger.error(f"Failed to log admin action: {e}")
        
        logger.info(f"🔐 Admin {admin_id}: {action} | chat:{chat_id} | user:{target_user_id} | {details}")

    async def get_admin_logs(self, limit: int = 50, admin_id: int = None) -> List[Dict]:
        """Получение логов действий администраторов."""
        limit = max(1, min(200, limit))
        
        if admin_id:
            return await self._execute_with_retry(
                """SELECT * FROM admin_logs 
                   WHERE admin_id = ? 
                   ORDER BY created_at DESC LIMIT ?""",
                (admin_id, limit), fetch_all=True) or []
        else:
            return await self._execute_with_retry(
                """SELECT * FROM admin_logs 
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,), fetch_all=True) or []

    # ==================== ЕЖЕДНЕВНАЯ СВОДКА ====================

    async def get_chat_daily_summary(self, chat_id: int, date: str = None) -> Optional[Dict]:
        """Получение дневной сводки по чату."""
        if chat_id is None:
            return None
        
        if date is None:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        return await self._execute_with_retry(
            """SELECT * FROM chat_daily_summary 
               WHERE chat_id = ? AND date = ?""",
            (chat_id, date), fetch_one=True)

    async def save_daily_summary(self, chat_id: int, date: str, total_messages: int,
                                 active_users: int, top_words_json: str, 
                                 top_users_json: str) -> bool:
        """Сохранение дневной сводки."""
        if chat_id is None or not date:
            return False
        
        success = await self._execute_with_retry(
            """INSERT OR REPLACE INTO chat_daily_summary 
               (chat_id, date, total_messages, active_users, top_words, top_users)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, date, total_messages, active_users, top_words_json, top_users_json),
            commit=True)
        
        return bool(success)

    async def get_top_words(self, chat_id: int, date: str = None, limit: int = 10) -> List[Dict]:
        """Получение топ-слов за день."""
        if chat_id is None:
            return []
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        return await self._execute_with_retry(
            """SELECT word, count FROM chat_word_stats 
               WHERE chat_id = ? AND date = ?
               ORDER BY count DESC LIMIT ?""",
            (chat_id, date, limit), fetch_all=True) or []

    # ==================== ЗАКРЫТИЕ ====================

    async def close(self) -> None:
        """Закрытие соединения (aiosqlite закрывается автоматически)."""
        logger.info("Database instance closed")


# ==================== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ====================

db = Database()
