"""
Утилиты для работы с категориями тегов (АСИНХРОННАЯ ВЕРСИЯ)
"""

import logging
import asyncio
import hashlib
import time
from datetime import datetime
from database import db

logger = logging.getLogger(__name__)

# Глобальные категории по умолчанию
DEFAULT_CATEGORIES = [
    {"slug": "pubg", "name": "🎮 PUBG Mobile", "desc": "Поиск сквада / ранкед", "icon": "🎮"},
    {"slug": "cs2", "name": "🎮 CS2", "desc": "Поиск напарников", "icon": "🎮"},
    {"slug": "dota", "name": "🎮 Dota 2", "desc": "Собрать пати", "icon": "🎮"},
    {"slug": "mafia", "name": "🎭 Мафия", "desc": "Сбор на партию", "icon": "🎭"},
    {"slug": "video_call", "name": "📞 Видео-звонок", "desc": "Созвон в группе", "icon": "📞"},
    {"slug": "important", "name": "❓ Важный вопрос", "desc": "Нужен совет / помощь", "icon": "❓"},
    {"slug": "giveaway", "name": "🎁 Розыгрыш", "desc": "Конкурсы и ивенты", "icon": "🎁"},
    {"slug": "offtopic", "name": "💬 Флудилка", "desc": "Оффтоп и общение", "icon": "💬"},
    {"slug": "tech", "name": "🔧 Техническое", "desc": "Баги, предложения", "icon": "🔧"},
    {"slug": "urgent", "name": "🆘 Срочно", "desc": "Помощь админам", "icon": "🆘"},
]


async def init_categories():
    """Инициализация таблиц и глобального каталога (АСИНХРОННО)"""
    def _sync_init():
        conn = db._get_connection()
        cursor = conn.cursor()
        
        # Таблица глобальных категорий
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tag_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                icon_emoji TEXT DEFAULT '🔔',
                is_global BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица настроек категорий в чате
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_tag_settings (
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT 0,
                custom_name TEXT,
                cooldown_seconds INTEGER DEFAULT 300,
                PRIMARY KEY (chat_id, category_slug)
            )
        """)
        
        # Таблица подписок пользователей
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
        
        # Добавляем глобальные категории
        for cat in DEFAULT_CATEGORIES:
            cursor.execute("""
                INSERT OR IGNORE INTO tag_categories (slug, name, description, icon_emoji)
                VALUES (?, ?, ?, ?)
            """, (cat["slug"], cat["name"], cat["desc"], cat["icon"]))
        
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_init)
    logger.info("✅ Таблицы категорий тегов созданы")


async def get_all_categories():
    """Получить все глобальные категории"""
    def _sync_get():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT slug, name, description, icon_emoji FROM tag_categories")
        results = []
        for row in cursor.fetchall():
            results.append({
                "slug": row[0],
                "name": row[1],
                "description": row[2],
                "icon": row[3],
            })
        conn.close()
        return results
    
    return await asyncio.to_thread(_sync_get)


async def get_chat_enabled_categories(chat_id: int):
    """Получить список включённых категорий в чате"""
    def _sync_get():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT tc.slug, tc.name, tc.description, tc.icon_emoji
                FROM tag_categories tc
                INNER JOIN chat_tag_settings cts ON tc.slug = cts.category_slug
                WHERE cts.chat_id = ? AND cts.is_enabled = 1
            """, (chat_id,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "slug": row[0],
                    "name": row[1],
                    "description": row[2],
                    "icon": row[3],
                })
            return results
        except Exception as e:
            logger.error(f"Error in get_chat_enabled_categories: {e}")
            return []
        finally:
            conn.close()
    
    return await asyncio.to_thread(_sync_get)


async def get_chat_enabled_slugs(chat_id: int) -> set:
    """Получить set включённых категорий в чате"""
    def _sync_get():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT category_slug FROM chat_tag_settings WHERE chat_id = ? AND is_enabled = 1", 
                (chat_id,)
            )
            results = {row[0] for row in cursor.fetchall()}
            return results
        except Exception as e:
            logger.error(f"Error in get_chat_enabled_slugs: {e}")
            return set()
        finally:
            conn.close()
    
    return await asyncio.to_thread(_sync_get)


async def toggle_chat_category(chat_id: int, category_slug: str, enabled: bool):
    """Включить/отключить категорию в чате"""
    def _sync_toggle():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO chat_tag_settings (chat_id, category_slug, is_enabled)
            VALUES (?, ?, ?)
        """, (chat_id, category_slug, 1 if enabled else 0))
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_toggle)


async def get_user_subscriptions(user_id: int, chat_id: int) -> dict:
    """Получить подписки пользователя в чате"""
    def _sync_get():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT category_slug, is_subscribed 
                FROM user_tag_subscriptions 
                WHERE user_id = ? AND chat_id = ?
            """, (user_id, chat_id))
            results = {row[0]: bool(row[1]) for row in cursor.fetchall()}
            return results
        except Exception as e:
            logger.error(f"Error in get_user_subscriptions: {e}")
            return {}
        finally:
            conn.close()
    
    return await asyncio.to_thread(_sync_get)


async def is_user_subscribed(user_id: int, chat_id: int, category_slug: str) -> bool:
    """Проверить, подписан ли пользователь на категорию (НОВЫЙ МЕТОД)"""
    def _sync_check():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT is_subscribed 
                FROM user_tag_subscriptions 
                WHERE user_id = ? AND chat_id = ? AND category_slug = ?
            """, (user_id, chat_id, category_slug))
            row = cursor.fetchone()
            
            if row:
                return bool(row[0])
            else:
                # Если записи нет — по умолчанию подписан (для обратной совместимости)
                return True
        except Exception as e:
            logger.error(f"Error in is_user_subscribed: {e}")
            return True
        finally:
            conn.close()
    
    return await asyncio.to_thread(_sync_check)


async def toggle_user_subscription(user_id: int, chat_id: int, category_slug: str, subscribe: bool):
    """Включить/отключить подписку пользователя"""
    def _sync_toggle():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_tag_subscriptions (user_id, chat_id, category_slug, is_subscribed)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, category_slug, 1 if subscribe else 0))
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_toggle)


async def collect_subscribed_users(chat_id: int, category_slug: str):
    """Собрать подписанных пользователей на категорию"""
    def _sync_collect():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT u.user_id, u.username, u.first_name
                FROM user_tag_subscriptions uts
                JOIN users u ON u.user_id = uts.user_id
                WHERE uts.chat_id = ? AND uts.category_slug = ? AND uts.is_subscribed = 1
            """, (chat_id, category_slug))
            
            results = []
            for row in cursor.fetchall():
                user_id, username, first_name = row
                if username:
                    results.append(f"@{username}")
                else:
                    safe_name = first_name.replace('<', '&lt;').replace('>', '&gt;') if first_name else "Пользователь"
                    results.append(f'<a href="tg://user?id={user_id}">{safe_name}</a>')
            return results
        except Exception as e:
            logger.error(f"Error in collect_subscribed_users: {e}")
            return []
        finally:
            conn.close()
    
    return await asyncio.to_thread(_sync_collect)


async def collect_all_users_except_unsubscribed(chat_id: int, category_slug: str = None):
    """
    Собрать ВСЕХ пользователей, КРОМЕ тех, кто ЯВНО отписался от категории.
    Если category_slug не указан — собирает всех (общий сбор).
    """
    def _sync_collect():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            if category_slug:
                # Исключаем пользователей, которые явно отписались от этой категории
                cursor.execute("""
                    SELECT u.user_id, u.username, u.first_name
                    FROM users u
                    WHERE u.user_id NOT IN (
                        SELECT user_id FROM user_tag_subscriptions 
                        WHERE chat_id = ? AND category_slug = ? AND is_subscribed = 0
                    )
                """, (chat_id, category_slug))
            else:
                # Все пользователи
                cursor.execute("SELECT user_id, username, first_name FROM users")
            
            results = []
            for row in cursor.fetchall():
                user_id, username, first_name = row
                if username:
                    results.append(f"@{username}")
                else:
                    safe_name = first_name.replace('<', '&lt;').replace('>', '&gt;') if first_name else "Пользователь"
                    results.append(f'<a href="tg://user?id={user_id}">{safe_name}</a>')
            return results
        except Exception as e:
            logger.error(f"Error in collect_all_users_except_unsubscribed: {e}")
            return []
        finally:
            conn.close()
    
    return await asyncio.to_thread(_sync_collect)


async def add_custom_category(chat_id: int, name: str, created_by: int) -> str:
    """Добавить кастомную категорию в чат"""
    slug = f"custom_{hashlib.md5(f'{chat_id}_{time.time()}'.encode()).hexdigest()[:8]}"
    
    def _sync_add():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_custom_categories (chat_id, slug, name, created_by)
            VALUES (?, ?, ?, ?)
        """, (chat_id, slug, name, created_by))
        cursor.execute("""
            INSERT OR REPLACE INTO chat_tag_settings (chat_id, category_slug, is_enabled)
            VALUES (?, ?, 1)
        """, (chat_id, slug))
        conn.commit()
        conn.close()
        return slug
    
    return await asyncio.to_thread(_sync_add)


async def delete_custom_category(chat_id: int, slug: str):
    """Удалить кастомную категорию"""
    def _sync_delete():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_custom_categories WHERE chat_id = ? AND slug = ?", (chat_id, slug))
        cursor.execute("DELETE FROM chat_tag_settings WHERE chat_id = ? AND category_slug = ?", (chat_id, slug))
        cursor.execute("DELETE FROM user_tag_subscriptions WHERE chat_id = ? AND category_slug = ?", (chat_id, slug))
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_delete)


async def log_tag_usage(chat_id: int, category_slug: str, triggered_by: int, mentioned_count: int):
    """Записать в лог вызов тега"""
    def _sync_log():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tag_usage_log (chat_id, category_slug, triggered_by, mentioned_count)
            VALUES (?, ?, ?, ?)
        """, (chat_id, category_slug, triggered_by, mentioned_count))
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_sync_log)
