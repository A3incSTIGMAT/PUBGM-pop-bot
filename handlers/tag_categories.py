import logging
import sqlite3
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
    """Инициализация таблиц и глобального каталога"""
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
    
    # Добавляем глобальные категории
    for cat in DEFAULT_CATEGORIES:
        cursor.execute("""
            INSERT OR IGNORE INTO tag_categories (slug, name, description, icon_emoji)
            VALUES (?, ?, ?, ?)
        """, (cat["slug"], cat["name"], cat["desc"], cat["icon"]))
    
    conn.commit()
    conn.close()
    logger.info("✅ Таблицы категорий тегов созданы")


async def get_all_categories():
    """Получить все глобальные категории"""
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


async def get_chat_enabled_categories(chat_id: int):
    """Получить список включённых категорий в чате"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT tc.slug, tc.name, tc.description, tc.icon_emoji
        FROM tag_categories tc
        JOIN chat_tag_settings cts ON tc.slug = cts.category_slug
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
    
    conn.close()
    return results


async def get_chat_enabled_slugs(chat_id: int) -> set:
    """Получить set включённых категорий в чате"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT category_slug FROM chat_tag_settings WHERE chat_id = ? AND is_enabled = 1", (chat_id,))
    results = {row[0] for row in cursor.fetchall()}
    conn.close()
    return results


async def toggle_chat_category(chat_id: int, category_slug: str, enabled: bool):
    """Включить/отключить категорию в чате"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO chat_tag_settings (chat_id, category_slug, is_enabled)
        VALUES (?, ?, ?)
    """, (chat_id, category_slug, 1 if enabled else 0))
    conn.commit()
    conn.close()


async def get_user_subscriptions(user_id: int, chat_id: int) -> dict:
    """Получить подписки пользователя в чате"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category_slug, is_subscribed 
        FROM user_tag_subscriptions 
        WHERE user_id = ? AND chat_id = ?
    """, (user_id, chat_id))
    
    results = {row[0]: bool(row[1]) for row in cursor.fetchall()}
    conn.close()
    return results


async def toggle_user_subscription(user_id: int, chat_id: int, category_slug: str, subscribe: bool):
    """Включить/отключить подписку пользователя"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_tag_subscriptions (user_id, chat_id, category_slug, is_subscribed)
        VALUES (?, ?, ?, ?)
    """, (user_id, chat_id, category_slug, 1 if subscribe else 0))
    conn.commit()
    conn.close()


async def collect_subscribed_users(chat_id: int, category_slug: str):
    """Собрать подписанных пользователей на категорию"""
    conn = db._get_connection()
    cursor = conn.cursor()
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
            results.append(f"[{first_name}](tg://user?id={user_id})")
    
    conn.close()
    return results
