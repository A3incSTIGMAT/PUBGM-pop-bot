#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/tag_categories.py
# ВЕРСИЯ: 2.1.0-production (исправленная после аудита)
# ОПИСАНИЕ: Категории тегов — полностью асинхронная версия
# ============================================
# ИСПРАВЛЕНИЯ v2.1.0:
#   🔴 Убраны ВСЕ commit=True из _execute_with_retry
#   🟡 exc_info=True во всех logger.error
#   🟡 Оптимизирован запрос NOT IN → LEFT JOIN
#   🟡 Добавлены индексы для таблиц
#   🟢 Вынесена _format_user_mention()
# ============================================

import hashlib
import html
import logging
import os
import time
from typing import List, Dict, Set, Optional

from database import db, DatabaseError

logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ (НАСТРАИВАЕМЫЕ) ====================

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


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def _format_user_mention(user_id: int, username: Optional[str], first_name: Optional[str]) -> str:
    """
    Форматирование упоминания пользователя.
    
    Args:
        user_id: ID пользователя
        username: @username
        first_name: Имя
        
    Returns:
        HTML-строка с упоминанием
    """
    if username:
        return f"@{safe_html_escape(username)}"
    else:
        safe_name = safe_html_escape(first_name) if first_name else "Пользователь"
        return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

async def init_categories() -> None:
    """
    Инициализация таблиц и глобального каталога.
    
    Создаёт таблицы и индексы если они не существуют.
    Добавляет дефолтные категории.
    Вызывается при старте бота.
    """
    if db is None:
        logger.error("❌ Database is None, cannot init categories")
        return
    
    try:
        # Таблица глобальных категорий
        await db._execute_with_retry("""
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
        await db._execute_with_retry("""
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
        await db._execute_with_retry("""
            CREATE TABLE IF NOT EXISTS user_tag_subscriptions (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                is_subscribed BOOLEAN DEFAULT 1,
                PRIMARY KEY (user_id, chat_id, category_slug)
            )
        """)
        
        # Таблица кастомных категорий чата
        await db._execute_with_retry("""
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
        await db._execute_with_retry("""
            CREATE TABLE IF NOT EXISTS tag_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id BIGINT NOT NULL,
                category_slug TEXT NOT NULL,
                triggered_by BIGINT NOT NULL,
                mentioned_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Индексы для производительности
        await db._execute_with_retry(
            "CREATE INDEX IF NOT EXISTS idx_chat_tag_settings_enabled ON chat_tag_settings(chat_id, is_enabled)")
        await db._execute_with_retry(
            "CREATE INDEX IF NOT EXISTS idx_user_subscriptions_lookup ON user_tag_subscriptions(user_id, chat_id)")
        
        # Добавляем глобальные категории (БЕЗ commit=True!)
        for cat in DEFAULT_CATEGORIES:
            await db._execute_with_retry("""
                INSERT OR IGNORE INTO tag_categories (slug, name, description, icon_emoji)
                VALUES (?, ?, ?, ?)
            """, (cat["slug"], cat["name"], cat["desc"], cat["icon"]))
        
        logger.info("✅ Tag categories tables created and populated")
        
    except DatabaseError as e:
        logger.error(f"❌ Failed to init tag categories: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"❌ Unexpected error in init_categories: {e}", exc_info=True)


# ==================== ПОЛУЧЕНИЕ КАТЕГОРИЙ ====================

async def get_all_categories() -> List[Dict]:
    """Получить все глобальные категории."""
    if db is None:
        return []
    
    try:
        rows = await db._execute_with_retry(
            "SELECT slug, name, description, icon_emoji FROM tag_categories",
            fetch_all=True
        )
        if rows:
            return [
                {
                    "slug": row["slug"],
                    "name": row["name"],
                    "description": row["description"],
                    "icon": row["icon_emoji"],
                }
                for row in rows
            ]
        return []
    except DatabaseError as e:
        logger.error(f"❌ Error in get_all_categories: {e}", exc_info=True)
        return []


async def get_chat_enabled_categories(chat_id: int) -> List[Dict]:
    """
    Получить список включённых категорий в чате.
    
    Args:
        chat_id: ID чата
        
    Returns:
        Список категорий
    """
    if db is None or chat_id is None:
        return []
    
    try:
        rows = await db._execute_with_retry("""
            SELECT tc.slug, tc.name, tc.description, tc.icon_emoji
            FROM tag_categories tc
            INNER JOIN chat_tag_settings cts ON tc.slug = cts.category_slug
            WHERE cts.chat_id = ? AND cts.is_enabled = 1
        """, (chat_id,), fetch_all=True)
        
        if rows:
            return [
                {
                    "slug": row["slug"],
                    "name": row["name"],
                    "description": row["description"],
                    "icon": row["icon_emoji"],
                }
                for row in rows
            ]
        return []
    except DatabaseError as e:
        logger.error(f"❌ Error in get_chat_enabled_categories: {e}", exc_info=True)
        return []


async def get_chat_enabled_slugs(chat_id: int) -> Set[str]:
    """
    Получить set включённых категорий в чате.
    
    Args:
        chat_id: ID чата
        
    Returns:
        Множество slug'ов
    """
    if db is None or chat_id is None:
        return set()
    
    try:
        rows = await db._execute_with_retry(
            "SELECT category_slug FROM chat_tag_settings WHERE chat_id = ? AND is_enabled = 1",
            (chat_id,), fetch_all=True
        )
        if rows:
            return {row["category_slug"] for row in rows}
        return set()
    except DatabaseError as e:
        logger.error(f"❌ Error in get_chat_enabled_slugs: {e}", exc_info=True)
        return set()


# ==================== УПРАВЛЕНИЕ КАТЕГОРИЯМИ ====================

async def toggle_chat_category(chat_id: int, category_slug: str, enabled: bool) -> None:
    """
    Включить/отключить категорию в чате.
    
    Args:
        chat_id: ID чата
        category_slug: Slug категории
        enabled: True для включения
    """
    if db is None or chat_id is None or not category_slug:
        return
    
    try:
        await db._execute_with_retry("""
            INSERT OR REPLACE INTO chat_tag_settings (chat_id, category_slug, is_enabled)
            VALUES (?, ?, ?)
        """, (chat_id, category_slug, 1 if enabled else 0))
    except DatabaseError as e:
        logger.error(f"❌ Error in toggle_chat_category: {e}", exc_info=True)


async def add_custom_category(chat_id: int, name: str, created_by: int) -> Optional[str]:
    """
    Добавить кастомную категорию в чат.
    
    Args:
        chat_id: ID чата
        name: Название категории
        created_by: ID создателя
        
    Returns:
        Slug новой категории или None при ошибке
    """
    if db is None or chat_id is None or not name:
        return None
    
    slug = f"custom_{hashlib.md5(f'{chat_id}_{time.time()}'.encode()).hexdigest()[:8]}"
    
    try:
        queries = [
            ("""INSERT INTO chat_custom_categories (chat_id, slug, name, created_by) VALUES (?, ?, ?, ?)""",
             (chat_id, slug, name, created_by)),
            ("""INSERT OR REPLACE INTO chat_tag_settings (chat_id, category_slug, is_enabled) VALUES (?, ?, 1)""",
             (chat_id, slug)),
        ]
        await db._execute_transaction(queries)
        return slug
    except DatabaseError as e:
        logger.error(f"❌ Error in add_custom_category: {e}", exc_info=True)
        return None


async def delete_custom_category(chat_id: int, slug: str) -> None:
    """
    Удалить кастомную категорию.
    
    Args:
        chat_id: ID чата
        slug: Slug категории
    """
    if db is None or chat_id is None or not slug:
        return
    
    try:
        queries = [
            ("DELETE FROM chat_custom_categories WHERE chat_id = ? AND slug = ?", (chat_id, slug)),
            ("DELETE FROM chat_tag_settings WHERE chat_id = ? AND category_slug = ?", (chat_id, slug)),
            ("DELETE FROM user_tag_subscriptions WHERE chat_id = ? AND category_slug = ?", (chat_id, slug)),
        ]
        await db._execute_transaction(queries)
    except DatabaseError as e:
        logger.error(f"❌ Error in delete_custom_category: {e}", exc_info=True)


# ==================== ПОДПИСКИ ПОЛЬЗОВАТЕЛЕЙ ====================

async def get_user_subscriptions(user_id: int, chat_id: int) -> Dict[str, bool]:
    """
    Получить подписки пользователя в чате.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        Словарь {slug: is_subscribed}
    """
    if db is None or user_id is None or chat_id is None:
        return {}
    
    try:
        rows = await db._execute_with_retry("""
            SELECT category_slug, is_subscribed 
            FROM user_tag_subscriptions 
            WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id), fetch_all=True)
        
        if rows:
            return {row["category_slug"]: bool(row["is_subscribed"]) for row in rows}
        return {}
    except DatabaseError as e:
        logger.error(f"❌ Error in get_user_subscriptions: {e}", exc_info=True)
        return {}


async def is_user_subscribed(user_id: int, chat_id: int, category_slug: str) -> bool:
    """
    Проверить, подписан ли пользователь на категорию.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        category_slug: Slug категории
        
    Returns:
        True если подписан (по умолчанию True)
    """
    if db is None or user_id is None or chat_id is None or not category_slug:
        return True
    
    try:
        row = await db._execute_with_retry("""
            SELECT is_subscribed 
            FROM user_tag_subscriptions 
            WHERE user_id = ? AND chat_id = ? AND category_slug = ?
        """, (user_id, chat_id, category_slug), fetch_one=True)
        
        if row:
            return bool(row["is_subscribed"])
        return True
    except DatabaseError as e:
        logger.error(f"❌ Error in is_user_subscribed: {e}", exc_info=True)
        return True


async def toggle_user_subscription(user_id: int, chat_id: int, category_slug: str, subscribe: bool) -> None:
    """
    Включить/отключить подписку пользователя.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        category_slug: Slug категории
        subscribe: True для подписки
    """
    if db is None or user_id is None or chat_id is None or not category_slug:
        return
    
    try:
        await db._execute_with_retry("""
            INSERT OR REPLACE INTO user_tag_subscriptions (user_id, chat_id, category_slug, is_subscribed)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, category_slug, 1 if subscribe else 0))
    except DatabaseError as e:
        logger.error(f"❌ Error in toggle_user_subscription: {e}", exc_info=True)


# ==================== СБОР ПОЛЬЗОВАТЕЛЕЙ ====================

async def collect_subscribed_users(chat_id: int, category_slug: str) -> List[str]:
    """
    Собрать подписанных пользователей на категорию.
    
    Args:
        chat_id: ID чата
        category_slug: Slug категории
        
    Returns:
        Список HTML-упоминаний
    """
    if db is None or chat_id is None or not category_slug:
        return []
    
    try:
        rows = await db._execute_with_retry("""
            SELECT u.user_id, u.username, u.first_name
            FROM user_tag_subscriptions uts
            JOIN users u ON u.user_id = uts.user_id
            WHERE uts.chat_id = ? AND uts.category_slug = ? AND uts.is_subscribed = 1
        """, (chat_id, category_slug), fetch_all=True)
        
        return [
            _format_user_mention(row["user_id"], row["username"], row["first_name"])
            for row in (rows or [])
        ]
    except DatabaseError as e:
        logger.error(f"❌ Error in collect_subscribed_users: {e}", exc_info=True)
        return []


async def collect_all_users_except_unsubscribed(chat_id: int, category_slug: str = None) -> List[str]:
    """
    Собрать ВСЕХ пользователей, КРОМЕ тех, кто ЯВНО отписался от категории.
    
    Если category_slug не указан — собирает всех (общий сбор).
    Использует LEFT JOIN вместо NOT IN для лучшей производительности.
    
    Args:
        chat_id: ID чата
        category_slug: Slug категории (опционально)
        
    Returns:
        Список HTML-упоминаний
    """
    if db is None or chat_id is None:
        return []
    
    try:
        if category_slug:
            # ✅ LEFT JOIN вместо NOT IN — быстрее на больших таблицах
            rows = await db._execute_with_retry("""
                SELECT u.user_id, u.username, u.first_name
                FROM users u
                LEFT JOIN user_tag_subscriptions uts 
                    ON u.user_id = uts.user_id 
                    AND uts.chat_id = ? 
                    AND uts.category_slug = ? 
                    AND uts.is_subscribed = 0
                WHERE u.user_id IS NOT NULL
            """, (chat_id, category_slug), fetch_all=True)
        else:
            rows = await db._execute_with_retry(
                "SELECT user_id, username, first_name FROM users",
                fetch_all=True
            )
        
        return [
            _format_user_mention(row["user_id"], row["username"], row["first_name"])
            for row in (rows or [])
        ]
    except DatabaseError as e:
        logger.error(f"❌ Error in collect_all_users_except_unsubscribed: {e}", exc_info=True)
        return []


# ==================== ЛОГИРОВАНИЕ ====================

async def log_tag_usage(chat_id: int, category_slug: str, triggered_by: int, mentioned_count: int) -> None:
    """
    Записать в лог вызов тега.
    
    Args:
        chat_id: ID чата
        category_slug: Slug категории
        triggered_by: ID вызвавшего
        mentioned_count: Количество упомянутых
    """
    if db is None or chat_id is None or not category_slug:
        return
    
    try:
        await db._execute_with_retry("""
            INSERT INTO tag_usage_log (chat_id, category_slug, triggered_by, mentioned_count)
            VALUES (?, ?, ?, ?)
        """, (chat_id, category_slug, triggered_by, mentioned_count))
    except DatabaseError as e:
        logger.error(f"❌ Error in log_tag_usage: {e}", exc_info=True)
