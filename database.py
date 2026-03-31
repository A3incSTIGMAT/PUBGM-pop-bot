"""
database.py — Асинхронная работа с SQLite
"""

import aiosqlite
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import DATABASE_PATH


class Database:
    """Асинхронный менеджер базы данных"""

    def __init__(self):
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def init(self):
        """Инициализация БД и создание таблиц"""
        if self._initialized:
            return

        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        self._db = await aiosqlite.connect(DATABASE_PATH)
        await self._create_tables()
        self._initialized = True

    async def _create_tables(self):
        """Создание всех таблиц"""
        # Таблица пользователей
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance INTEGER DEFAULT 0,
                total_games INTEGER DEFAULT 0,
                total_wins INTEGER DEFAULT 0,
                total_bets INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                is_vip BOOLEAN DEFAULT 0,
                vip_expires TEXT,
                last_daily TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица истории игр
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS games_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                game_type TEXT,
                bet INTEGER,
                result TEXT,
                win_amount INTEGER DEFAULT 0,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Таблица предупреждений
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS user_warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                admin_id INTEGER,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица заявок на пополнение
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount_rub INTEGER,
                amount_ncoin INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT
            )
        ''')

        await self._db.commit()

    # ==================== ПОЛЬЗОВАТЕЛИ ====================

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя"""
        async with self._db.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def create_user(self, user_id: int, username: str = None, full_name: str = None):
        """Создать пользователя"""
        await self._db.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, full_name))
        await self._db.commit()

    async def update_activity(self, user_id: int):
        """Обновить время активности"""
        await self._db.execute(
            'UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?',
            (user_id,)
        )
        await self._db.commit()

    # ==================== БАЛАНС ====================

    async def get_balance(self, user_id: int) -> int:
        """Получить баланс"""
        async with self._db.execute(
            'SELECT balance FROM users WHERE user_id = ?', (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def add_balance(self, user_id: int, amount: int, description: str = ""):
        """Добавить средства"""
        await self._db.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
            (amount, user_id)
        )
        await self._db.commit()

    async def subtract_balance(self, user_id: int, amount: int, description: str = "") -> bool:
        """Списать средства"""
        cursor = await self._db.execute(
            'UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?',
            (amount, user_id, amount)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # ==================== ИГРЫ ====================

    async def add_game_history(self, user_id: int, game_type: str, bet: int,
                               result: str, win_amount: int = 0, details: dict = None):
        """Добавить запись в историю игр"""
        details_json = json.dumps(details) if details else None

        await self._db.execute('''
            INSERT INTO games_history (user_id, game_type, bet, result, win_amount, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, game_type, bet, result, win_amount, details_json))

        # Обновляем статистику
        await self._db.execute('''
            UPDATE users SET
                total_games = total_games + 1,
                total_bets = total_bets + ?,
                total_won = total_won + ?,
                last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (bet, win_amount, user_id))

        if result == 'win':
            await self._db.execute(
                'UPDATE users SET total_wins = total_wins + 1 WHERE user_id = ?',
                (user_id,)
            )

        await self._db.commit()

    async def get_game_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить историю игр"""
        async with self._db.execute('''
            SELECT * FROM games_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ==================== ПРЕДУПРЕЖДЕНИЯ ====================

    async def add_warn(self, chat_id: int, user_id: int, admin_id: int, reason: str) -> int:
        """Добавить предупреждение"""
        await self._db.execute('''
            INSERT INTO user_warns (chat_id, user_id, admin_id, reason)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, user_id, admin_id, reason))
        await self._db.commit()

        async with self._db.execute('''
            SELECT COUNT(*) FROM user_warns WHERE chat_id = ? AND user_id = ?
        ''', (chat_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_warns(self, chat_id: int, user_id: int) -> List[Dict]:
        """Получить предупреждения"""
        async with self._db.execute('''
            SELECT reason, admin_id, timestamp FROM user_warns
            WHERE chat_id = ? AND user_id = ?
            ORDER BY timestamp DESC
        ''', (chat_id, user_id)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_warns(self, chat_id: int, user_id: int):
        """Очистить предупреждения"""
        await self._db.execute(
            'DELETE FROM user_warns WHERE chat_id = ? AND user_id = ?',
            (chat_id, user_id)
        )
        await self._db.commit()

    # ==================== СТАТИСТИКА ====================

    async def get_total_users(self) -> int:
        """Общее количество пользователей"""
        async with self._db.execute('SELECT COUNT(*) FROM users') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_total_games(self) -> int:
        """Общее количество игр"""
        async with self._db.execute('SELECT COUNT(*) FROM games_history') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_total_bets(self) -> int:
        """Общая сумма ставок"""
        async with self._db.execute('SELECT SUM(bet) FROM games_history') as cursor:
            row = await cursor.fetchone()
            return row[0] if row[0] else 0

    async def get_total_wins(self) -> int:
        """Общая сумма выигрышей"""
        async with self._db.execute(
            'SELECT SUM(win_amount) FROM games_history WHERE result = "win"'
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row[0] else 0

    # ==================== ЗАКРЫТИЕ ====================

    async def close(self):
        """Закрыть соединение"""
        if self._db:
            await self._db.close()
            self._initialized = False


# Глобальный экземпляр
db = Database()
