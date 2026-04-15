import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, Optional

from config import DATABASE_PATH

class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # ==================== ОСНОВНЫЕ ТАБЛИЦЫ ====================
        
        # Таблица пользователей
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
        
        # Таблица транзакций
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
        
        # Таблица магазина
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                description TEXT
            )
        """)
        
        # Таблица для анкет пользователей
        cursor.execute("""
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
        """)
        
        # ==================== НОВЫЕ ТАБЛИЦЫ ====================
        
        # Таблица рангов пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_ranks (
                user_id INTEGER PRIMARY KEY,
                rank_level INTEGER DEFAULT 0,
                rank_name TEXT DEFAULT '🌱 Дерево',
                rank_xp INTEGER DEFAULT 0,
                rank_bonus INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица донатеров
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS donors (
                user_id INTEGER PRIMARY KEY,
                total_donated INTEGER DEFAULT 0,
                last_donate TIMESTAMP,
                donor_rank TEXT DEFAULT '💎 Поддерживающий'
            )
        """)
        
        # Таблица глобального рейтинга
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_rating (
                user_id INTEGER PRIMARY KEY,
                total_xp INTEGER DEFAULT 0,
                rating_position INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица активности чатов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_rating (
                chat_id BIGINT PRIMARY KEY,
                chat_title TEXT,
                activity_points INTEGER DEFAULT 0,
                members_count INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                messages_count INTEGER DEFAULT 0,
                week_activity INTEGER DEFAULT 0,
                month_activity INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица наград чатов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                reward_type TEXT,
                reward_amount INTEGER,
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица личной статистики игр
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_game_stats (
                user_id INTEGER PRIMARY KEY,
                total_games INTEGER DEFAULT 0,
                total_wins INTEGER DEFAULT 0,
                total_coins INTEGER DEFAULT 0,
                slot_played INTEGER DEFAULT 0,
                roulette_played INTEGER DEFAULT 0,
                rps_played INTEGER DEFAULT 0,
                duel_played INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица отношений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user1_id, user2_id, type)
            )
        """)
        
        # Таблица групп
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                group_name TEXT NOT NULL,
                group_leader INTEGER NOT NULL,
                member_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица участников групп
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER,
                user_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, user_id)
            )
        """)
        
        # Таблица кастомных РП команд
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_rp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                command TEXT NOT NULL,
                action_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, command)
            )
        """)
        
        # Таблица реферальных достижений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ref_milestones (
                user_id INTEGER,
                chat_id INTEGER,
                milestone INTEGER,
                awarded BOOLEAN DEFAULT 0,
                awarded_at TIMESTAMP,
                PRIMARY KEY (user_id, chat_id, milestone)
            )
        """)
        
        # Таблица реферальных настроек чатов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ref_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                ref_link TEXT,
                bonus_amount INTEGER DEFAULT 100,
                created_at TEXT
            )
        """)
        
        # Таблица реферальных ссылок пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ref_links (
                user_id INTEGER,
                chat_id INTEGER,
                ref_code TEXT UNIQUE,
                invited_count INTEGER DEFAULT 0,
                earned_coins INTEGER DEFAULT 0,
                created_at TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        # Таблица реферальных приглашений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ref_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                chat_id INTEGER,
                invited_at TEXT
            )
        """)
        
        # Таблица тегов (глобальный каталог)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tag_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                icon_emoji TEXT DEFAULT '🔔',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица настроек категорий в чате
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_tag_settings (
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT 0,
                PRIMARY KEY (chat_id, category_slug)
            )
        """)
        
        # Таблица подписок пользователей на теги
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tag_subscriptions (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_subscribed BOOLEAN DEFAULT 1,
                PRIMARY KEY (user_id, chat_id, category_slug)
            )
        """)
        
        # Таблица кастомных категорий чата
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                icon_emoji TEXT DEFAULT '📌',
                created_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, slug)
            )
        """)
        
        # Таблица логов вызовов тегов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tag_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                triggered_by BIGINT NOT NULL,
                mentioned_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        
        self._add_default_shop_items()
        self._add_default_tag_categories()
    
    def _add_default_shop_items(self):
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
    
    def _add_default_tag_categories(self):
        """Добавление глобальных категорий тегов"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
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
        
        for slug, name, desc, icon in DEFAULT_CATEGORIES:
            cursor.execute("""
                INSERT OR IGNORE INTO tag_categories (slug, name, description, icon_emoji)
                VALUES (?, ?, ?, ?)
            """, (slug, name, desc, icon))
        
        conn.commit()
        conn.close()
    
    # ========== МЕТОДЫ ДЛЯ СОВМЕСТИМОСТИ ==========
    
    def _get_connection(self):
        """Получить соединение с БД"""
        return sqlite3.connect(self.db_path)
    
    async def init(self):
        """Асинхронная инициализация"""
        self._init_db()
        return self
    
    async def close(self):
        """Закрытие соединения"""
        pass
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ==========
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "user_id": row[0],
                "username": row[1],
                "first_name": row[2],
                "balance": row[3],
                "daily_streak": row[4],
                "last_daily": row[5],
                "vip_level": row[6],
                "vip_until": row[7],
                "wins": row[8],
                "losses": row[9],
                "register_date": row[10],
                "warns": json.loads(row[11]) if row[11] else []
            }
        return None
    
    async def create_user(self, user_id: int, username: str = None, first_name: str = None, balance: int = 1000):
        """Создать пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, balance, register_date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, first_name, balance, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    async def update_balance(self, user_id: int, delta: int, reason: str = ""):
        """Обновить баланс"""
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
    
    async def get_balance(self, user_id: int) -> int:
        """Получить баланс"""
        user = await self.get_user(user_id)
        return user["balance"] if user else 0
    
    async def save_profile(self, user_id: int, full_name: str, age: int, city: str, timezone: str, about: str):
        """Сохранить анкету пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_profiles 
            (user_id, full_name, age, city, timezone, about, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM user_profiles WHERE user_id = ?), ?), ?)
        """, (user_id, full_name, age, city, timezone, about, user_id, datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    async def get_profile(self, user_id: int) -> Optional[Dict]:
        """Получить анкету пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "full_name": row[1],
                "age": row[2],
                "city": row[3],
                "timezone": row[4],
                "about": row[5],
                "created_at": row[6],
                "updated_at": row[7]
            }
        return None

db = Database()
