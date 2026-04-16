import sqlite3
import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Optional, List, Any

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
        """Синхронное получение соединения с БД"""
        return sqlite3.connect(self.db_path)
    
    async def _get_connection_async(self):
        """Асинхронное получение соединения с БД (через thread)"""
        return await asyncio.to_thread(self._get_connection)
    
    async def init(self):
        """Асинхронная инициализация"""
        await asyncio.to_thread(self._init_db)
        return self
    
    async def close(self):
        """Закрытие соединения (ничего не делаем, sqlite3 сам управляет)"""
        pass
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ==========
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя (АСИНХРОННО)"""
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        
        return await asyncio.to_thread(_sync_get)
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Найти пользователя по username"""
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        
        return await asyncio.to_thread(_sync_get)
    
    async def create_user(self, user_id: int, username: str = None, first_name: str = None, balance: int = 1000):
        """Создать пользователя (АСИНХРОННО)"""
        def _sync_create():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, balance, register_date, warns)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name, balance, datetime.now().isoformat(), '[]'))
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_create)
    
    async def user_exists(self, user_id: int) -> bool:
        """Проверить существование пользователя"""
        user = await self.get_user(user_id)
        return user is not None
    
    async def update_balance(self, user_id: int, delta: int, reason: str = ""):
        """Обновить баланс (АТОМАРНАЯ ТРАНЗАКЦИЯ)"""
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                # Обновляем баланс
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
                
                # Записываем транзакцию если есть причина
                if reason:
                    cursor.execute("""
                        INSERT INTO transactions (from_id, to_id, amount, reason, date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, user_id, abs(delta), reason, datetime.now().isoformat()))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        await asyncio.to_thread(_sync_update)
    
    async def transfer_coins(self, from_id: int, to_username: str, amount: int, reason: str = "transfer") -> bool:
        """Перевод монет между пользователями по username"""
        # Сначала найдём получателя
        target = await self.get_user_by_username(to_username)
        if not target:
            return False
        
        to_id = target["user_id"]
        
        if from_id == to_id:
            raise ValueError("Нельзя перевести самому себе")
        
        def _sync_transfer():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                # Проверяем баланс отправителя
                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (from_id,))
                row = cursor.fetchone()
                if not row or row[0] < amount:
                    raise ValueError("Недостаточно средств")
                
                # Списываем с отправителя
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, from_id))
                
                # Зачисляем получателю
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, to_id))
                
                # Записываем транзакцию
                cursor.execute("""
                    INSERT INTO transactions (from_id, to_id, amount, reason, date)
                    VALUES (?, ?, ?, ?, ?)
                """, (from_id, to_id, amount, reason, datetime.now().isoformat()))
                
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        return await asyncio.to_thread(_sync_transfer)
    
    async def get_balance(self, user_id: int) -> int:
        """Получить баланс пользователя"""
        user = await self.get_user(user_id)
        return user["balance"] if user else 0
    
    async def save_profile(self, user_id: int, full_name: str, age: int, city: str, timezone: str, about: str):
        """Сохранить анкету пользователя"""
        def _sync_save():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("SELECT created_at FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            created_at = row[0] if row else now
            
            cursor.execute("""
                INSERT OR REPLACE INTO user_profiles 
                (user_id, full_name, age, city, timezone, about, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, full_name, age, city, timezone, about, created_at, now))
            
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_save)
    
    async def get_profile(self, user_id: int) -> Optional[Dict]:
        """Получить анкету пользователя"""
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        
        return await asyncio.to_thread(_sync_get)
    
    async def update_daily_streak(self, user_id: int, streak: int):
        """Обновить стрик ежедневного бонуса"""
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET daily_streak = ?, last_daily = ? 
                WHERE user_id = ?
            """, (streak, datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_update)
    
    async def get_top_users(self, limit: int = 10) -> List[Dict]:
        """Получить топ пользователей по балансу"""
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, balance, vip_level 
                FROM users 
                ORDER BY balance DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        
        return await asyncio.to_thread(_sync_get)
    
    async def get_top_donors(self, limit: int = 10) -> List[Dict]:
        """Получить топ донатеров"""
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.user_id, u.username, u.first_name, d.total_donated, d.donor_rank
                FROM donors d
                JOIN users u ON d.user_id = u.user_id
                ORDER BY d.total_donated DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        
        return await asyncio.to_thread(_sync_get)
    
    async def update_donor_stats(self, user_id: int, amount_rub: int):
        """Обновить статистику донатера"""
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Определяем ранг донатера
            cursor.execute("SELECT total_donated FROM donors WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            current_total = row[0] if row else 0
            new_total = current_total + amount_rub
            
            donor_rank = "💎 Поддерживающий"
            if new_total >= 5000:
                donor_rank = "👑 Легендарный спонсор"
            elif new_total >= 2000:
                donor_rank = "💫 Золотой спонсор"
            elif new_total >= 500:
                donor_rank = "⭐ Серебряный спонсор"
            elif new_total >= 100:
                donor_rank = "🔰 Бронзовый спонсор"
            
            cursor.execute("""
                INSERT INTO donors (user_id, total_donated, last_donate, donor_rank)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    total_donated = total_donated + ?,
                    last_donate = CURRENT_TIMESTAMP,
                    donor_rank = ?
            """, (user_id, amount_rub, donor_rank, amount_rub, donor_rank))
            
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_update)
    
    async def add_warn(self, user_id: int, warn_text: str):
        """Добавить предупреждение пользователю"""
        user = await self.get_user(user_id)
        if user:
            warns = user.get('warns', [])
            if isinstance(warns, str):
                try:
                    warns = json.loads(warns)
                except:
                    warns = []
            
            warns.append({
                'text': warn_text,
                'date': datetime.now().isoformat()
            })
            
            def _sync_update():
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET warns = ? WHERE user_id = ?", 
                             (json.dumps(warns), user_id))
                conn.commit()
                conn.close()
            
            await asyncio.to_thread(_sync_update)
    
    async def get_user_warns(self, user_id: int) -> List[Dict]:
        """Получить предупреждения пользователя"""
        user = await self.get_user(user_id)
        if user:
            warns = user.get('warns', [])
            if isinstance(warns, str):
                try:
                    return json.loads(warns)
                except:
                    return []
            return warns
        return []
    
    async def clear_warns(self, user_id: int):
        """Очистить предупреждения пользователя"""
        def _sync_clear():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET warns = '[]' WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_clear)


# Глобальный экземпляр базы данных
db = Database()
