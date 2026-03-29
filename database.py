"""
database.py — Асинхронная работа с SQLite базой данных
"""

import aiosqlite
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from config import DATABASE_PATH

class Database:
    """Асинхронный менеджер базы данных"""
    
    def __init__(self):
        self._db: Optional[aiosqlite.Connection] = None
        self.is_initialized = False
    
    async def init(self):
        """Инициализация базы данных и создание таблиц"""
        if self.is_initialized:
            return
        
        # Создаём директорию если нужно
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        
        self._db = await aiosqlite.connect(DATABASE_PATH)
        
        # Создание таблиц
        await self._create_tables()
        
        self.is_initialized = True
    
    async def _create_tables(self):
        """Создание всех необходимых таблиц"""
        
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
                banned_at TEXT,
                ban_reason TEXT,
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
        
        # Таблица транзакций
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                description TEXT,
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
        
        # Таблица логов модерации
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                admin_id INTEGER,
                admin_name TEXT,
                admin_username TEXT,
                target_id INTEGER,
                target_name TEXT,
                target_username TEXT,
                chat_id INTEGER,
                reason TEXT,
                duration_seconds INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индексы для производительности
        await self._db.execute('CREATE INDEX IF NOT EXISTS idx_games_user ON games_history(user_id)')
        await self._db.execute('CREATE INDEX IF NOT EXISTS idx_games_date ON games_history(created_at)')
        await self._db.execute('CREATE INDEX IF NOT EXISTS idx_warns_user ON user_warns(user_id)')
        await self._db.execute('CREATE INDEX IF NOT EXISTS idx_mod_logs_target ON moderation_logs(target_id)')
        
        await self._db.commit()
    
    # ========== ПОЛЬЗОВАТЕЛИ ==========
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя по ID"""
        async with self._db.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    async def create_user(self, user_id: int, username: str = None, full_name: str = None) -> bool:
        """Создать нового пользователя"""
        try:
            await self._db.execute('''
                INSERT INTO users (user_id, username, full_name, balance)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, full_name, 0))
            await self._db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False
    
    async def get_balance(self, user_id: int) -> int:
        """Получить баланс пользователя"""
        async with self._db.execute(
            'SELECT balance FROM users WHERE user_id = ?', (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return 0
    
    async def add_balance(self, user_id: int, amount: int, description: str = "") -> bool:
        """Добавить средства на баланс"""
        try:
            await self._db.execute('''
                UPDATE users SET balance = balance + ? WHERE user_id = ?
            ''', (amount, user_id))
            await self._db.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, 'add', ?)
            ''', (user_id, amount, description))
            await self._db.commit()
            return True
        except Exception:
            return False
    
    async def subtract_balance(self, user_id: int, amount: int, description: str = "") -> bool:
        """Списать средства с баланса"""
        try:
            result = await self._db.execute('''
                UPDATE users SET balance = balance - ? 
                WHERE user_id = ? AND balance >= ?
            ''', (amount, user_id, amount))
            if result.rowcount == 0:
                return False
            
            await self._db.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, 'subtract', ?)
            ''', (user_id, amount, description))
            await self._db.commit()
            return True
        except Exception:
            return False
    
    # ========== ИСТОРИЯ ИГР ==========
    
    async def add_game_history(self, user_id: int, game_type: str, bet: int, 
                                result: str, win_amount: int = 0, details: dict = None):
        """Добавить запись в историю игр"""
        import json
        details_json = json.dumps(details) if details else None
        
        await self._db.execute('''
            INSERT INTO games_history (user_id, game_type, bet, result, win_amount, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, game_type, bet, result, win_amount, details_json))
        
        # Обновляем статистику пользователя
        await self._db.execute('''
            UPDATE users 
            SET total_games = total_games + 1,
                total_bets = total_bets + ?,
                total_won = total_won + ?,
                last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (bet, win_amount, user_id))
        
        if result == 'win':
            await self._db.execute('''
                UPDATE users SET total_wins = total_wins + 1 WHERE user_id = ?
            ''', (user_id,))
        
        await self._db.commit()
    
    async def get_game_history(self, user_id: int, limit: int = 20, offset: int = 0) -> List[Dict]:
        """Получить историю игр пользователя"""
        async with self._db.execute('''
            SELECT * FROM games_history 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (user_id, limit, offset)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ========== СТАТИСТИКА ==========
    
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
        async with self._db.execute('SELECT SUM(win_amount) FROM games_history WHERE result = "win"') as cursor:
            row = await cursor.fetchone()
            return row[0] if row[0] else 0
    
    async def get_active_users_today(self) -> int:
        """Количество активных пользователей сегодня"""
        async with self._db.execute('''
            SELECT COUNT(DISTINCT user_id) FROM games_history 
            WHERE DATE(created_at) = DATE('now')
        ''') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    # ========== ПРЕДУПРЕЖДЕНИЯ ==========
    
    async def add_warn(self, chat_id: int, user_id: int, admin_id: int, reason: str) -> int:
        """Добавить предупреждение и вернуть общее количество"""
        await self._db.execute('''
            INSERT INTO user_warns (chat_id, user_id, admin_id, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (chat_id, user_id, admin_id, reason, datetime.now().isoformat()))
        await self._db.commit()
        
        async with self._db.execute('''
            SELECT COUNT(*) FROM user_warns 
            WHERE chat_id = ? AND user_id = ?
        ''', (chat_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def get_user_warns(self, chat_id: int, user_id: int) -> List[Dict]:
        """Получить предупреждения пользователя"""
        async with self._db.execute('''
            SELECT w.*, u.full_name as admin_name
            FROM user_warns w
            LEFT JOIN users u ON w.admin_id = u.user_id
            WHERE w.chat_id = ? AND w.user_id = ?
            ORDER BY w.timestamp DESC
        ''', (chat_id, user_id)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def delete_warn(self, warn_id: int, chat_id: int) -> bool:
        """Удалить предупреждение"""
        result = await self._db.execute('''
            DELETE FROM user_warns WHERE id = ? AND chat_id = ?
        ''', (warn_id, chat_id))
        await self._db.commit()
        return result.rowcount > 0
    
    # ========== ЛОГИ МОДЕРАЦИИ ==========
    
    async def log_moderation_action(self, action: dict):
        """Логирование действия модерации"""
        await self._db.execute('''
            INSERT INTO moderation_logs 
            (action, admin_id, admin_name, admin_username, target_id, target_name, 
             target_username, chat_id, reason, duration_seconds, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            action['action'], action['admin_id'], action['admin_name'], 
            action.get('admin_username'), action['target_id'], action['target_name'],
            action.get('target_username'), action['chat_id'], action['reason'],
            action.get('duration_seconds'), action['timestamp']
        ))
        await self._db.commit()
    
    async def get_moderation_logs(self, chat_id: int, limit: int = 50) -> List[Dict]:
        """Получить логи модерации"""
        async with self._db.execute('''
            SELECT * FROM moderation_logs 
            WHERE chat_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (chat_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ========== БАН ==========
    
    async def ban_user(self, user_id: int, admin_id: int, reason: str) -> bool:
        """Забанить пользователя"""
        await self._db.execute('''
            UPDATE users 
            SET is_banned = 1, banned_at = ?, ban_reason = ?
            WHERE user_id = ?
        ''', (datetime.now().isoformat(), reason, user_id))
        await self._db.commit()
        
        await self.log_moderation_action({
            'action': 'ban',
            'admin_id': admin_id,
            'admin_name': '',
            'target_id': user_id,
            'target_name': '',
            'chat_id': 0,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })
        return True
    
    async def unban_user(self, user_id: int) -> bool:
        """Разбанить пользователя"""
        await self._db.execute('''
            UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?
        ''', (user_id,))
        await self._db.commit()
        return True
    
    # ========== ЗАКРЫТИЕ ==========
    
    async def close(self):
        """Закрыть соединение с базой данных"""
        if self._db:
            await self._db.close()
            self.is_initialized = False

# Глобальный экземпляр
db = Database()
