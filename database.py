# ============================================
# ФАЙЛ: database.py
# ОПИСАНИЕ: База данных NEXUS Bot — ПОЛНАЯ ВЕРСИЯ СО ВСЕМИ МЕТОДАМИ
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# ВКЛЮЧАЕТ: get_user_stats, get_top_*, update_xo_stats, claim_daily_bonus
# ============================================

import sqlite3
import os
import json
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

from config import DATABASE_PATH


class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных"""
        if not self.db_path:
            return
            
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # ==================== ОСНОВНЫЕ ТАБЛИЦЫ ====================
        
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
        
        # ==================== ТАБЛИЦЫ СТАТИСТИКИ ====================
        
        cursor.execute("""
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
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                messages INTEGER DEFAULT 0,
                voice INTEGER DEFAULT 0,
                stickers INTEGER DEFAULT 0,
                gifs INTEGER DEFAULT 0,
                photos INTEGER DEFAULT 0,
                videos INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                xo_games INTEGER DEFAULT 0,
                UNIQUE(user_id, date)
            )
        """)
        
        cursor.execute("""
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
        """)
        
        cursor.execute("""
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
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_tops_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                top_type TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                position INTEGER,
                value INTEGER,
                updated_at TEXT,
                UNIQUE(top_type, user_id)
            )
        """)
        
        # ==================== ТАБЛИЦЫ ДЛЯ АНАЛИЗА ЧАТА ====================
        
        cursor.execute("""
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
                hugs INTEGER DEFAULT 0,
                kisses INTEGER DEFAULT 0,
                kicks INTEGER DEFAULT 0,
                generated_summary TEXT,
                UNIQUE(chat_id, date)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_word_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                date TEXT NOT NULL,
                word TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                UNIQUE(chat_id, date, word)
            )
        """)
        
        # ==================== ОСТАЛЬНЫЕ ТАБЛИЦЫ ====================
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS donors (
                user_id INTEGER PRIMARY KEY,
                total_donated INTEGER DEFAULT 0,
                last_donate TIMESTAMP,
                donor_rank TEXT DEFAULT '💎 Поддерживающий'
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_rating (
                user_id INTEGER PRIMARY KEY,
                total_xp INTEGER DEFAULT 0,
                rating_position INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                reward_type TEXT,
                reward_amount INTEGER,
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER,
                user_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, user_id)
            )
        """)
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ref_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                ref_link TEXT,
                bonus_amount INTEGER DEFAULT 100,
                created_at TEXT
            )
        """)
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ref_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                chat_id INTEGER,
                invited_at TEXT
            )
        """)
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_tag_settings (
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT 0,
                PRIMARY KEY (chat_id, category_slug)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tag_subscriptions (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_subscribed BOOLEAN DEFAULT 1,
                PRIMARY KEY (user_id, chat_id, category_slug)
            )
        """)
        
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
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM shop_items")
        if cursor.fetchone()[0] == 0:
            items = [
                ("⭐ VIP 1 месяц", 5000, "Доступ к VIP-комнатам + бонусы"),
                ("💎 1000 монет", 100, "Пополнение баланса"),
                ("🎁 Случайный подарок", 200, "Получи случайную награду")
            ]
            cursor.executemany("INSERT INTO shop_items (name, price, description) VALUES (?, ?, ?)", items)
            conn.commit()
        conn.close()
    
    def _add_default_tag_categories(self):
        if not self.db_path:
            return
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
        if not self.db_path:
            return None
        return sqlite3.connect(self.db_path)
    
    async def _get_connection_async(self):
        return await asyncio.to_thread(self._get_connection)
    
    async def init(self):
        if self.db_path:
            await asyncio.to_thread(self._init_db)
        return self
    
    async def close(self):
        pass
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ==========
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        if user_id is None or not self.db_path:
            return None
            
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
        if username is None or not self.db_path:
            return None
            
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
        if user_id is None or not self.db_path:
            return
            
        def _sync_create():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            today = datetime.now().strftime("%Y-%m-%d")
            
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, balance, register_date, warns)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name, balance if balance is not None else 1000, now, '[]'))
            
            cursor.execute("""
                INSERT OR IGNORE INTO user_stats (user_id, register_date, last_active)
                VALUES (?, ?, ?)
            """, (user_id, today, now))
            
            cursor.execute("""
                INSERT OR IGNORE INTO user_economy_stats (user_id, max_balance)
                VALUES (?, ?)
            """, (user_id, balance if balance is not None else 1000))
            
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_create)
    
    async def user_exists(self, user_id: int) -> bool:
        if user_id is None:
            return False
        user = await self.get_user(user_id)
        return user is not None
    
    async def update_balance(self, user_id: int, delta: int, reason: str = ""):
        if user_id is None or delta is None or not self.db_path:
            return
            
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
                
                if reason:
                    cursor.execute("""
                        INSERT INTO transactions (from_id, to_id, amount, reason, date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, user_id, abs(delta), reason, datetime.now().isoformat()))
                
                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    new_balance = row[0]
                    cursor.execute("""
                        UPDATE user_economy_stats 
                        SET max_balance = MAX(COALESCE(max_balance, 0), ?),
                            total_earned = COALESCE(total_earned, 0) + ? 
                        WHERE user_id = ?
                    """, (new_balance, max(0, delta), user_id))
                    
                    if delta < 0:
                        cursor.execute("""
                            UPDATE user_economy_stats 
                            SET total_spent = COALESCE(total_spent, 0) + ? 
                            WHERE user_id = ?
                        """, (abs(delta), user_id))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        await asyncio.to_thread(_sync_update)
    
    async def transfer_coins(self, from_id: int, to_username: str, amount: int, reason: str = "transfer") -> bool:
        if from_id is None or to_username is None or amount is None or not self.db_path:
            return False
            
        target = await self.get_user_by_username(to_username)
        if not target:
            return False
        
        to_id = target.get("user_id")
        if to_id is None:
            return False
        
        if from_id == to_id:
            raise ValueError("Нельзя перевести самому себе")
        
        def _sync_transfer():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (from_id,))
                row = cursor.fetchone()
                if not row or row[0] is None or row[0] < amount:
                    raise ValueError("Недостаточно средств")
                
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, from_id))
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, to_id))
                
                cursor.execute("""
                    INSERT INTO transactions (from_id, to_id, amount, reason, date)
                    VALUES (?, ?, ?, ?, ?)
                """, (from_id, to_id, amount, reason, datetime.now().isoformat()))
                
                cursor.execute("""
                    UPDATE user_economy_stats 
                    SET total_transferred = COALESCE(total_transferred, 0) + ? 
                    WHERE user_id = ?
                """, (amount, from_id))
                
                cursor.execute("""
                    UPDATE user_economy_stats 
                    SET total_received = COALESCE(total_received, 0) + ? 
                    WHERE user_id = ?
                """, (amount, to_id))
                
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        return await asyncio.to_thread(_sync_transfer)
    
    async def get_balance(self, user_id: int) -> int:
        if user_id is None:
            return 0
        user = await self.get_user(user_id)
        return user.get("balance", 0) if user else 0
    
    async def save_profile(self, user_id: int, full_name: str, age: int, city: str, timezone: str, about: str):
        if user_id is None:
            return
            
        def _sync_save():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("SELECT created_at FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            created_at = row[0] if row and row[0] is not None else now
            
            cursor.execute("""
                INSERT OR REPLACE INTO user_profiles 
                (user_id, full_name, age, city, timezone, about, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, full_name or "", age or 0, city or "", timezone or "", about or "", created_at, now))
            
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_save)
    
    async def get_profile(self, user_id: int) -> Optional[Dict]:
        if user_id is None:
            return None
            
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
        if user_id is None:
            return
            
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET daily_streak = ?, last_daily = ? 
                WHERE user_id = ?
            """, (streak or 0, datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_update)
    
    async def get_top_users(self, limit: int = 10) -> List[Dict]:
        if limit is None:
            limit = 10
        if not self.db_path:
            return []
            
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, balance, vip_level 
                FROM users 
                WHERE balance > 0
                ORDER BY balance DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows] if rows else []
        
        return await asyncio.to_thread(_sync_get)
    
    async def get_top_donors(self, limit: int = 10) -> List[Dict]:
        if limit is None:
            limit = 10
        if not self.db_path:
            return []
            
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.user_id, u.username, u.first_name, d.total_donated, d.donor_rank
                FROM donors d
                JOIN users u ON d.user_id = u.user_id
                WHERE d.total_donated > 0
                ORDER BY d.total_donated DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows] if rows else []
        
        return await asyncio.to_thread(_sync_get)
    
    async def update_donor_stats(self, user_id: int, amount_rub: int):
        if user_id is None or amount_rub is None:
            return
            
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT total_donated FROM donors WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            current_total = row[0] if row and row[0] is not None else 0
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
        if user_id is None:
            return
            
        user = await self.get_user(user_id)
        if user:
            warns = user.get('warns', [])
            if isinstance(warns, str):
                try:
                    warns = json.loads(warns)
                except:
                    warns = []
            
            warns.append({
                'text': warn_text or "",
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
        if user_id is None:
            return []
            
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
        if user_id is None:
            return
            
        def _sync_clear():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET warns = '[]' WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_clear)

    async def claim_daily_bonus(self, user_id: int, bonus_amount: int, streak: int, today_str: str, reason: str = "Ежедневный бонус") -> dict:
        if user_id is None or bonus_amount is None:
            return {'new_balance': 0, 'success': False}
            
        def _sync_claim():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"User {user_id} not found")
                
                old_balance = row[0] if row[0] is not None else 0
                new_balance = old_balance + bonus_amount
                
                cursor.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (new_balance, user_id)
                )
                
                cursor.execute(
                    "UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
                    (streak or 0, today_str, user_id)
                )
                
                cursor.execute("""
                    INSERT INTO transactions (from_id, to_id, amount, reason, date)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, user_id, bonus_amount, reason, datetime.now().isoformat()))
                
                cursor.execute("""
                    UPDATE user_economy_stats 
                    SET daily_claims = COALESCE(daily_claims, 0) + 1,
                        total_earned = COALESCE(total_earned, 0) + ? 
                    WHERE user_id = ?
                """, (bonus_amount, user_id))
                
                conn.commit()
                return {'new_balance': new_balance, 'success': True}
                
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        return await asyncio.to_thread(_sync_claim)

    # ==================== МЕТОДЫ СТАТИСТИКИ ====================

    async def track_user_activity(self, user_id: int, activity_type: str, value: int = 1):
        if user_id is None or activity_type is None:
            return
            
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat()
        value = value if value is not None else 1
        
        def _sync_track():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                cursor.execute("""
                    INSERT OR IGNORE INTO user_stats (user_id, register_date)
                    VALUES (?, ?)
                """, (user_id, today))
                
                if activity_type == "message":
                    cursor.execute("""
                        UPDATE user_stats SET 
                            messages_total = COALESCE(messages_total, 0) + ?,
                            messages_today = COALESCE(messages_today, 0) + ?,
                            messages_week = COALESCE(messages_week, 0) + ?,
                            messages_month = COALESCE(messages_month, 0) + ?,
                            last_message_date = ?,
                            last_active = ?
                        WHERE user_id = ?
                    """, (value, value, value, value, today, now, user_id))
                elif activity_type in ["voice", "sticker", "gif", "photo", "video"]:
                    col = f"total_{activity_type}s"
                    cursor.execute(f"""
                        UPDATE user_stats SET 
                            {col} = COALESCE({col}, 0) + ?,
                            last_active = ?
                        WHERE user_id = ?
                    """, (value, now, user_id))
                elif activity_type == "xo_game":
                    cursor.execute("""
                        UPDATE user_stats SET last_active = ? WHERE user_id = ?
                    """, (now, user_id))
                
                if activity_type == "message":
                    cursor.execute("""
                        INSERT INTO user_activity_log (user_id, date, messages)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id, date) DO UPDATE SET
                            messages = COALESCE(messages, 0) + ?
                    """, (user_id, today, value, value))
                elif activity_type in ["voice", "sticker", "gif", "photo", "video"]:
                    col = activity_type + "s"
                    cursor.execute(f"""
                        INSERT INTO user_activity_log (user_id, date, {col})
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id, date) DO UPDATE SET
                            {col} = COALESCE({col}, 0) + ?
                    """, (user_id, today, value, value))
                elif activity_type == "xo_game":
                    cursor.execute("""
                        INSERT INTO user_activity_log (user_id, date, xo_games)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id, date) DO UPDATE SET
                            xo_games = COALESCE(xo_games, 0) + ?
                    """, (user_id, today, value, value))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        await asyncio.to_thread(_sync_track)

    async def update_user_streaks(self, user_id: int = None):
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                if user_id is not None:
                    cursor.execute("""
                        SELECT user_id, last_message_date, days_active, current_streak, max_streak 
                        FROM user_stats WHERE user_id = ?
                    """, (user_id,))
                else:
                    cursor.execute("""
                        SELECT user_id, last_message_date, days_active, current_streak, max_streak 
                        FROM user_stats WHERE last_message_date IS NOT NULL
                    """)
                
                rows = cursor.fetchall()
                
                for row in rows:
                    uid, last_date, days_active, current_streak, max_streak = row
                    
                    if last_date == today:
                        continue
                    
                    new_days = (days_active or 0) + 1
                    new_streak = (current_streak or 0) + 1 if last_date == yesterday else 1
                    new_max = max(max_streak or 0, new_streak)
                    
                    cursor.execute("""
                        UPDATE user_stats SET 
                            days_active = ?,
                            current_streak = ?,
                            max_streak = ?,
                            last_streak_update = ?
                        WHERE user_id = ?
                    """, (new_days, new_streak, new_max, today, uid))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        await asyncio.to_thread(_sync_update)

    async def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Получить полную статистику пользователя"""
        if user_id is None or not self.db_path:
            return None
            
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    s.user_id,
                    COALESCE(s.messages_total, 0) as messages_total,
                    COALESCE(s.messages_today, 0) as messages_today,
                    COALESCE(s.messages_week, 0) as messages_week,
                    COALESCE(s.messages_month, 0) as messages_month,
                    s.last_message_date,
                    s.register_date,
                    s.last_active,
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
                    COALESCE(x.current_win_streak, 0) as current_win_streak,
                    COALESCE(u.balance, 0) as balance,
                    COALESCE(u.daily_streak, 0) as daily_streak,
                    COALESCE(u.vip_level, 0) as vip_level,
                    u.register_date as user_register_date
                FROM user_stats s
                LEFT JOIN user_economy_stats e ON s.user_id = e.user_id
                LEFT JOIN xo_stats x ON s.user_id = x.user_id
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        
        return await asyncio.to_thread(_sync_get)

    async def get_top_messages(self, limit: int = 10) -> List[Dict]:
        """Топ по сообщениям"""
        if limit is None:
            limit = 10
        if not self.db_path:
            return []
            
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id, u.username, u.first_name, COALESCE(s.messages_total, 0) as messages_total
                FROM user_stats s
                JOIN users u ON s.user_id = u.user_id
                WHERE COALESCE(s.messages_total, 0) > 0
                ORDER BY s.messages_total DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows] if rows else []
        
        return await asyncio.to_thread(_sync_get)

    async def get_top_balance(self, limit: int = 10) -> List[Dict]:
        """Топ по балансу"""
        return await self.get_top_users(limit)

    async def get_top_xo(self, limit: int = 10) -> List[Dict]:
        """Топ по победам в крестиках-ноликах"""
        if limit is None:
            limit = 10
        if not self.db_path:
            return []
            
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id, u.username, u.first_name, 
                       COALESCE(x.wins, 0) as wins, 
                       COALESCE(x.games_played, 0) as games_played
                FROM xo_stats x
                JOIN users u ON x.user_id = u.user_id
                WHERE COALESCE(x.games_played, 0) >= 3
                ORDER BY x.wins DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows] if rows else []
        
        return await asyncio.to_thread(_sync_get)

    async def get_top_activity(self, limit: int = 10) -> List[Dict]:
        """Топ по дням активности"""
        if limit is None:
            limit = 10
        if not self.db_path:
            return []
            
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id, u.username, u.first_name, 
                       COALESCE(s.days_active, 0) as days_active, 
                       COALESCE(s.current_streak, 0) as current_streak, 
                       COALESCE(s.max_streak, 0) as max_streak
                FROM user_stats s
                JOIN users u ON s.user_id = u.user_id
                WHERE COALESCE(s.days_active, 0) > 0
                ORDER BY s.days_active DESC, s.current_streak DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows] if rows else []
        
        return await asyncio.to_thread(_sync_get)

    async def get_top_daily_streak(self, limit: int = 10) -> List[Dict]:
        """Топ по стрику daily"""
        if limit is None:
            limit = 10
        if not self.db_path:
            return []
            
        def _sync_get():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, COALESCE(daily_streak, 0) as daily_streak
                FROM users
                WHERE COALESCE(daily_streak, 0) > 0
                ORDER BY daily_streak DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows] if rows else []
        
        return await asyncio.to_thread(_sync_get)

    async def update_xo_stats(self, user_id: int, result_type: str, bet: int = 0, won: int = 0):
        """Обновить статистику крестиков-ноликов"""
        if user_id == "bot" or user_id is None:
            return
            
        bet = bet if bet is not None else 0
        won = won if won is not None else 0
        
        def _sync_update():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                cursor.execute("INSERT OR IGNORE INTO xo_stats (user_id) VALUES (?)", (user_id,))
                cursor.execute("UPDATE xo_stats SET games_played = COALESCE(games_played, 0) + 1 WHERE user_id = ?", (user_id,))
                
                if result_type == "win":
                    cursor.execute("UPDATE xo_stats SET wins = COALESCE(wins, 0) + 1, current_win_streak = COALESCE(current_win_streak, 0) + 1 WHERE user_id = ?", (user_id,))
                elif result_type == "loss":
                    cursor.execute("UPDATE xo_stats SET losses = COALESCE(losses, 0) + 1, current_win_streak = 0 WHERE user_id = ?", (user_id,))
                elif result_type == "draw":
                    cursor.execute("UPDATE xo_stats SET draws = COALESCE(draws, 0) + 1, current_win_streak = 0 WHERE user_id = ?", (user_id,))
                elif result_type == "loss_vs_bot":
                    cursor.execute("UPDATE xo_stats SET losses_vs_bot = COALESCE(losses_vs_bot, 0) + 1, current_win_streak = 0 WHERE user_id = ?", (user_id,))
                elif result_type == "win_vs_bot":
                    cursor.execute("UPDATE xo_stats SET wins_vs_bot = COALESCE(wins_vs_bot, 0) + 1, current_win_streak = COALESCE(current_win_streak, 0) + 1 WHERE user_id = ?", (user_id,))
                
                if bet > 0:
                    cursor.execute("UPDATE xo_stats SET total_bet = COALESCE(total_bet, 0) + ? WHERE user_id = ?", (bet, user_id))
                if won > 0:
                    cursor.execute("UPDATE xo_stats SET total_won = COALESCE(total_won, 0) + ? WHERE user_id = ?", (won, user_id))
                
                cursor.execute("""
                    UPDATE xo_stats SET max_win_streak = MAX(COALESCE(max_win_streak, 0), COALESCE(current_win_streak, 0))
                    WHERE user_id = ?
                """, (user_id,))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        await asyncio.to_thread(_sync_update)

    # ==================== МЕТОДЫ ДЛЯ АНАЛИЗА ЧАТА ====================
    
    STOP_WORDS = {
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
    }
    
    TOPIC_KEYWORDS = {
        "крестики-нолики": ["крестики", "нолики", "xo", "tic", "tac", "победа", "ничья", "выиграл", "проиграл"],
        "бот": ["бот", "nexus", "нексус", "команда", "функция", "баг", "фича", "обновление"],
        "игры": ["игра", "играть", "слот", "рулетка", "ставка", "казино"],
        "общение": ["привет", "как дела", "что делаешь", "чем занимаешься"],
        "флуд": ["хаха", "ахах", "лол", "кек", "ор", "ору"],
    }
    
    async def log_chat_message(self, chat_id: int, user_id: int, text: str):
        """Логирование сообщения для анализа тем"""
        if chat_id is None or user_id is None or text is None or not self.db_path:
            return
        
        if len(text) < 3:
            return
            
        today = datetime.now().strftime("%Y-%m-%d")
        
        def _sync_log():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                words = re.findall(r'[а-яА-Яa-zA-Z]{3,}', text.lower())
                
                for word in words:
                    if word in self.STOP_WORDS:
                        continue
                        
                    cursor.execute("""
                        INSERT INTO chat_word_stats (chat_id, date, word, count)
                        VALUES (?, ?, ?, 1)
                        ON CONFLICT(chat_id, date, word) DO UPDATE SET
                            count = count + 1
                    """, (chat_id, today, word))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
            finally:
                conn.close()
        
        await asyncio.to_thread(_sync_log)
    
    async def cleanup_old_activity_logs(self, days: int = 90):
        """Очистка старых логов активности"""
        if days is None:
            days = 90
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        def _sync_cleanup():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_activity_log WHERE date < ?", (cutoff,))
            cursor.execute("DELETE FROM chat_word_stats WHERE date < ?", (cutoff,))
            
            cursor.execute("""
                UPDATE user_stats SET 
                    messages_today = 0,
                    messages_week = 0,
                    messages_month = 0
            """)
            
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_cleanup)

    async def reset_daily_counters(self):
        """Сброс дневных счётчиков"""
        def _sync_reset():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_stats SET messages_today = 0")
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_reset)

    async def reset_weekly_counters(self):
        """Сброс недельных счётчиков"""
        def _sync_reset():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_stats SET messages_week = 0")
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_reset)

    async def reset_monthly_counters(self):
        """Сброс месячных счётчиков"""
        def _sync_reset():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_stats SET messages_month = 0")
            conn.commit()
            conn.close()
        
        await asyncio.to_thread(_sync_reset)


# Глобальный экземпляр базы данных
db = Database()
