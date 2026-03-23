import sqlite3
import os
from contextlib import contextmanager

# Путь к базе данных
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nexus.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

@contextmanager
def get_db():
    """Контекстный менеджер для работы с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Инициализация таблиц в базе данных"""
    with get_db() as conn:
        # Таблица пользователей
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                chat_id INTEGER,
                username TEXT,
                balance INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                vip_until INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        # Таблица чатов
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_name TEXT,
                welcome_message TEXT,
                language TEXT DEFAULT 'ru'
            )
        """)
        
        # Таблица подарков
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user INTEGER,
                to_user INTEGER,
                chat_id INTEGER,
                gift_type TEXT,
                amount INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица игр
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                game_name TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_played INTEGER DEFAULT 0
            )
        """)
        
        print("✅ База данных инициализирована")

def get_balance(user_id: int, chat_id: int) -> int:
    """Получить баланс пользователя"""
    with get_db() as conn:
        result = conn.execute(
            "SELECT balance FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        return result["balance"] if result else 0

def update_balance(user_id: int, chat_id: int, delta: int):
    """Изменить баланс пользователя"""
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        
        if exists:
            conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ? AND chat_id = ?",
                (delta, user_id, chat_id)
            )
        else:
            conn.execute(
                "INSERT INTO users (user_id, chat_id, balance) VALUES (?, ?, ?)",
                (user_id, chat_id, max(0, delta))
            )

def add_user(user_id: int, chat_id: int, username: str = None):
    """Добавить нового пользователя, если его нет"""
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        
        if not exists:
            conn.execute(
                "INSERT INTO users (user_id, chat_id, username, balance) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, username, 100)  # Приветственный бонус 100 NCoin
            )
            print(f"✅ Новый пользователь {username} добавлен в чат {chat_id}, бонус 100 NCoin")

def get_welcome_message(chat_id: int) -> str:
    """Получить приветственное сообщение для чата"""
    with get_db() as conn:
        result = conn.execute(
            "SELECT welcome_message FROM chats WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        return result["welcome_message"] if result else None

def set_chat_welcome(chat_id: int, message: str):
    """Установить приветственное сообщение для чата"""
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM chats WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        
        if exists:
            conn.execute(
                "UPDATE chats SET welcome_message = ? WHERE chat_id = ?",
                (message, chat_id)
            )
        else:
            conn.execute(
                "INSERT INTO chats (chat_id, welcome_message) VALUES (?, ?)",
                (chat_id, message)
            )
