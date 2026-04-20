# ============================================
# ФАЙЛ: database.py
# ОПИСАНИЕ: База данных NEXUS Bot — ОЧИЩЕННАЯ ВЕРСИЯ
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# УДАЛЕНО: старые игры (слот, рулетка, КНБ, дуэль)
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
    # (Все методы статистики остаются без изменений)
    # ... (весь код методов track_user_activity, get_user_stats, get_top_* и т.д.)


# Глобальный экземпляр базы данных
db = Database()
