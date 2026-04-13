"""
Модуль управления категориями тегов
База данных, глобальный каталог, работа с подписками
"""

import asyncio
import hashlib
import logging
import re
import sqlite3
import time
from typing import List, Dict, Optional
from datetime import datetime

from database import db

logger = logging.getLogger(__name__)

# Глобальные категории по умолчанию
DEFAULT_CATEGORIES = [
    {"slug": "pubg", "name": "🎮 PUBG Mobile", "desc": "Поиск команды для ранкеда", "icon": "🎮"},
    {"slug": "cs2", "name": "🎮 CS2", "desc": "Поиск напарников для матчмейкинга", "icon": "🎮"},
    {"slug": "dota", "name": "🎮 Dota 2", "desc": "Собрать пати для каток", "icon": "🎮"},
    {"slug": "mafia", "name": "🎭 Мафия", "desc": "Сбор на партию в Мафию", "icon": "🎭"},
    {"slug": "video_call", "name": "📞 Видео-звонок", "desc": "Созвон в группе", "icon": "📞"},
    {"slug": "important", "name": "❓ Важный вопрос", "desc": "Нужен совет / помощь", "icon": "❓"},
    {"slug": "giveaway", "name": "🎁 Розыгрыш", "desc": "Конкурсы и ивенты", "icon": "🎁"},
    {"slug": "offtopic", "name": "💬 Флудилка", "desc": "Оффтоп и общение", "icon": "💬"},
    {"slug": "tech", "name": "🔧 Техническое", "desc": "Баги, предложения по боту", "icon": "🔧"},
    {"slug": "urgent", "name": "🆘 Срочно", "desc": "Помощь администраторов", "icon": "🆘"},
]

# Настройки
MAX_MENTIONS_PER_MESSAGE = 35  # Безопасный лимит для Telegram


async def _exec_db_sync(query: str, params: tuple = (), fetch: bool = False):
    """Безопасное выполнение синхронного запроса к БД в отдельном потоке"""
    def _run():
        conn = db._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")  # Улучшает конкурентный доступ
        conn.execute("PRAGMA busy_timeout=5000")  # Ждёт 5 сек при блокировке
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if fetch:
                result = cursor.fetchall() if cursor.description else None
            else:
                result = cursor.rowcount
            conn.commit()
            return result
        except sqlite3.Error as e:
            logger.error(f"DB error: {e} | Query: {query} | Params: {params}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    return await asyncio.to_thread(_run)


async def init_categories():
    """Инициализация глобального каталога категорий (вызывать ОДИН раз при старте)"""
    try:
        # Создаём таблицы
        await _exec_db_sync("""
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
        
        await _exec_db_sync("""
            CREATE TABLE IF NOT EXISTS chat_tag_settings (
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT 1,
                custom_name TEXT,
                cooldown_seconds INTEGER DEFAULT 300,
                max_uses_per_day INTEGER DEFAULT 10,
                PRIMARY KEY (chat_id, category_slug)
            )
        """)
        
        await _exec_db_sync("""
            CREATE TABLE IF NOT EXISTS user_tag_subscriptions (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_subscribed BOOLEAN DEFAULT 1,
                quiet_start INTEGER DEFAULT 23,
                quiet_end INTEGER DEFAULT 8,
                last_notified TIMESTAMP,
                notified_count_today INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id, category_slug)
            )
        """)
        
        await _exec_db_sync("""
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
        
        await _exec_db_sync("""
            CREATE TABLE IF NOT EXISTS tag_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                triggered_by BIGINT NOT NULL,
                mentioned_count INTEGER,
                delivered_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Добавляем глобальные категории (идемпотентно)
        for cat in DEFAULT_CATEGORIES:
            await _exec_db_sync("""
                INSERT OR IGNORE INTO tag_categories (slug, name, description, icon_emoji)
                VALUES (?, ?, ?, ?)
            """, (cat["slug"], cat["name"], cat["desc"], cat["icon"]))
            
    except Exception as e:
        logger.error(f"Failed to init categories: {e}")
        raise


async def get_chat_enabled_categories(chat_id: int) -> List[Dict]:
    """Получить активные категории для чата"""
    try:
        # Сначала получаем включённые глобальные категории
        global_cats = await _exec_db_sync("""
            SELECT tc.slug, tc.name, tc.description, tc.icon_emoji,
                   cts.custom_name, cts.cooldown_seconds, cts.max_uses_per_day
            FROM tag_categories tc
            LEFT JOIN chat_tag_settings cts 
                ON tc.slug = cts.category_slug AND cts.chat_id = ?
            WHERE cts.chat_id IS NULL  -- нет настройки = включено по умолчанию
               OR cts.is_enabled = 1   -- явно включено
            ORDER BY tc.name
        """, (chat_id,), fetch=True) or []
        
        # Затем кастомные категории чата
        custom_cats = await _exec_db_sync("""
            SELECT slug, name, description, icon_emoji, name, 300, 10
            FROM chat_custom_categories
            WHERE chat_id = ?
            ORDER BY name
        """, (chat_id,), fetch=True) or []
        
        # Объединяем и форматируем
        results = []
        for row in global_cats + custom_cats:
            results.append({
                "slug": row[0],
                "name": row[4] or row[1],  # кастомное имя или глобальное
                "description": row[2],
                "icon": row[3],
                "cooldown": row[5] or 300,
                "max_per_day": row[6] or 10
            })
        return results
        
    except Exception as e:
        logger.error(f"Failed to get categories for chat {chat_id}: {e}")
        return []


async def get_user_subscriptions(user_id: int, chat_id: int) -> Dict[str, bool]:
    """Получить подписки пользователя на категории в чате"""
    try:
        rows = await _exec_db_sync("""
            SELECT category_slug, is_subscribed 
            FROM user_tag_subscriptions 
            WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id), fetch=True) or []
        return {row[0]: bool(row[1]) for row in rows}
    except Exception as e:
        logger.error(f"Failed to get subscriptions for user {user_id}: {e}")
        return {}


async def toggle_user_subscription(user_id: int, chat_id: int, category_slug: str, subscribe: bool):
    """Включить/отключить подписку пользователя на категорию"""
    # Валидация slug
    if not re.match(r'^[a-z0-9_]+$', category_slug):
        raise ValueError(f"Invalid category slug: {category_slug}")
    
    try:
        await _exec_db_sync("""
            INSERT OR REPLACE INTO user_tag_subscriptions 
            (user_id, chat_id, category_slug, is_subscribed)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, category_slug, 1 if subscribe else 0))
    except Exception as e:
        logger.error(f"Failed to toggle subscription: {e}")
        raise


async def toggle_chat_category(chat_id: int, category_slug: str, enabled: bool):
    """Включить/отключить категорию в чате"""
    if not re.match(r'^[a-z0-9_]+$', category_slug):
        raise ValueError(f"Invalid category slug: {category_slug}")
    
    try:
        await _exec_db_sync("""
            INSERT OR REPLACE INTO chat_tag_settings 
            (chat_id, category_slug, is_enabled)
            VALUES (?, ?, ?)
        """, (chat_id, category_slug, 1 if enabled else 0))
    except Exception as e:
        logger.error(f"Failed to toggle category {category_slug} in chat {chat_id}: {e}")
        raise


async def add_custom_category(chat_id: int, name: str, created_by: int) -> str:
    """Добавить кастомную категорию в чат"""
    # Генерируем уникальный slug
    slug = f"custom_{hashlib.md5(f'{chat_id}_{time.time()}'.encode()).hexdigest()[:8]}"
    
    try:
        # Добавляем кастомную категорию
        await _exec_db_sync("""
            INSERT INTO chat_custom_categories (chat_id, slug, name, created_by)
            VALUES (?, ?, ?, ?)
        """, (chat_id, slug, name.strip(), created_by))
        
        # Автоматически включаем её
        await _exec_db_sync("""
            INSERT OR REPLACE INTO chat_tag_settings (chat_id, category_slug, is_enabled)
            VALUES (?, ?, 1)
        """, (chat_id, slug))
        
        return slug
    except Exception as e:
        logger.error(f"Failed to add custom category: {e}")
        raise


async def delete_custom_category(chat_id: int, slug: str):
    """Удалить кастомную категорию и все связанные данные"""
    if not slug.startswith("custom_"):
        raise ValueError("Can only delete custom categories")
    
    try:
        # Удаляем в правильном порядке из-за потенциальных внешних ключей
        await _exec_db_sync("""
            DELETE FROM user_tag_subscriptions WHERE chat_id = ? AND category_slug = ?
        """, (chat_id, slug))
        
        await _exec_db_sync("""
            DELETE FROM chat_tag_settings WHERE chat_id = ? AND category_slug = ?
        """, (chat_id, slug))
        
        await _exec_db_sync("""
            DELETE FROM chat_custom_categories WHERE chat_id = ? AND slug = ?
        """, (chat_id, slug))
        
    except Exception as e:
        logger.error(f"Failed to delete custom category {slug}: {e}")
        raise


async def collect_subscribed_users(chat_id: int, category_slug: str, limit: int = MAX_MENTIONS_PER_MESSAGE) -> List[str]:
    """Собрать пользователей, подписанных на категорию (с форматированием для Telegram)"""
    if not re.match(r'^[a-z0-9_]+$', category_slug):
        raise ValueError(f"Invalid category slug: {category_slug}")
    
    try:
        rows = await _exec_db_sync("""
            SELECT u.user_id, u.username, u.first_name
            FROM user_tag_subscriptions uts
            JOIN users u ON u.user_id = uts.user_id
            WHERE uts.chat_id = ? 
              AND uts.category_slug = ? 
              AND uts.is_subscribed = 1
            LIMIT ?
        """, (chat_id, category_slug, limit), fetch=True) or []
        
        results = []
        for user_id, username, first_name in rows:
            if username:
                results.append(f"@{username}")
            else:
                # Формат для упоминания без username (работает в Telegram)
                results.append(f"[{first_name or 'Пользователь'}](tg://user?id={user_id})")
        
        return results
    except Exception as e:
        logger.error(f"Failed to collect users for category {category_slug}: {e}")
        return []


async def log_tag_usage(chat_id: int, category_slug: str, triggered_by: int, mentioned_count: int, delivered_count: Optional[int] = None):
    """Записать в лог вызов тега"""
    if delivered_count is None:
        delivered_count = mentioned_count
    
    try:
        await _exec_db_sync("""
            INSERT INTO tag_usage_log (chat_id, category_slug, triggered_by, mentioned_count, delivered_count)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, category_slug, triggered_by, mentioned_count, delivered_count))
    except Exception as e:
        # Логирование не должно ломать основную функциональность
        logger.error(f"Failed to log tag usage: {e}")

