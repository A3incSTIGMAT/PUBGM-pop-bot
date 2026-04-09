import sqlite3
import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

# Исправлено имя переменной на DATABASE_PATH (как в config.py)
from config import DATABASE_PATH 

class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        # Инициализируем БД сразу при создании объекта
        self._init_db_sync()
    
    def _init_db_sync(self):
        """Инициализация базы данных (синхронно, только при старте)"""
        # Создаем папку /data если нет
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
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
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER,
                to_id INTEGER,
                amount INTEGER,
                reason TEXT,
                date TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                description TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        
        # Добавляем товары
        self._add_default_shop_items_sync()

    def _add_default_shop_items_sync(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM shop_items")
        if cursor.fetchone()[0] == 0:
            items = [
                ("⭐ VIP 1 месяц", 5000, "Доступ к VIP-комнатам + бонусы"),
                ("🎰 10 билетов на слот", 400, "10 игр в слот-машину"),
                ("💎 1000 монет", 100, "Пополнение баланса"),
                ("🎁 Случайный подарок", 200, "Получи случайную награду")
            ]
            cursor.executemany("INSERT INTO shop_items (name, price, description) VALUES (?, ?, ?)", items)
            conn.commit()
        conn.close()

    # --- Вспомогательная функция для работы с sqlite3 без блокировки бота ---
    async def _run_in_thread(self, func, *args):
        return await asyncio.to_thread(func, *args)

    def _get_connection(self):
        # Добавили timeout, чтобы не было ошибки "database is locked"
        return sqlite3.connect(self.db_path, timeout=10)

    # --- Методы БД ---

    async def get_user(self, user_id: int) -> Optional[Dict]:
        def _get_user():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    "user_id": row[0], "username": row[1], "first_name": row[2],
                    "balance": row[3], "daily_streak": row[4], "last_daily": row[5],
                    "vip_level": row[6], "vip_until": row[7], "wins": row[8],
                    "losses": row[9], "register_date": row[10],
                    "warns": json.loads(row[11]) if row[11] else []
                }
            return None
        return await self._run_in_thread(_get_user)

    async def create_user(self, user_id: int, username: str = None, first_name: str = None, balance: int = 1000):
        def _create_user():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, balance, register_date)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, balance, datetime.now().isoformat()))
            conn.commit()
            conn.close()
        await self._run_in_thread(_create_user)

    async def update_balance(self, user_id: int, delta: int, reason: str = ""):
        def _update_balance():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
            conn.commit()
            conn.close()
            
            if reason:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO transactions (from_id, to_id, amount, reason, date)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, user_id, delta, reason, datetime.now().isoformat()))
                conn.commit()
                conn.close()
        await self._run_in_thread(_update_balance)

    async def get_balance(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        return user["balance"] if user else 0

# Создаём глобальный экземпляр
db = Database()

