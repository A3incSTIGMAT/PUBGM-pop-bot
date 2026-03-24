import sqlite3
import os
from contextlib import contextmanager

DATA_DIR = "/data"
DB_PATH = os.path.join(DATA_DIR, "nexus.db")
os.makedirs(DATA_DIR, exist_ok=True)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                chat_id INTEGER,
                username TEXT,
                balance INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                vip_until INTEGER DEFAULT 0,
                birthday TEXT,
                reputation INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_name TEXT,
                welcome_message TEXT,
                log_channel_id INTEGER,
                language TEXT DEFAULT 'ru'
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_admins (
                chat_id INTEGER,
                user_id INTEGER,
                role TEXT DEFAULT 'moderator',
                assigned_by INTEGER,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS captcha (
                user_id INTEGER,
                chat_id INTEGER,
                answer INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id INTEGER,
                chat_id INTEGER,
                birthday TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                reporter_id INTEGER,
                target_id INTEGER,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("✅ База данных инициализирована")

# ========== ПОЛЬЗОВАТЕЛИ ==========

def get_balance(user_id: int, chat_id: int) -> int:
    with get_db() as conn:
        result = conn.execute(
            "SELECT balance FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        return result["balance"] if result else 0

def update_balance(user_id: int, chat_id: int, delta: int):
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
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (user_id, chat_id, username, balance) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, username, 100)
            )

def get_user_stats(user_id: int, chat_id: int):
    with get_db() as conn:
        result = conn.execute(
            "SELECT * FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        return result if result else None

def update_user_stats(user_id: int, chat_id: int, messages_delta: int = 1):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE users SET total_messages = total_messages + ? WHERE user_id = ? AND chat_id = ?",
                (messages_delta, user_id, chat_id)
            )
        else:
            add_user(user_id, chat_id)

# ========== ЧАТЫ ==========

def get_welcome_message(chat_id: int) -> str:
    with get_db() as conn:
        result = conn.execute(
            "SELECT welcome_message FROM chats WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        return result["welcome_message"] if result else None

def set_chat_welcome(chat_id: int, message: str):
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

def get_log_channel(chat_id: int) -> int:
    with get_db() as conn:
        result = conn.execute(
            "SELECT log_channel_id FROM chats WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        return result["log_channel_id"] if result else None

def set_log_channel(chat_id: int, log_channel_id: int):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM chats WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE chats SET log_channel_id = ? WHERE chat_id = ?",
                (log_channel_id, chat_id)
            )
        else:
            conn.execute(
                "INSERT INTO chats (chat_id, log_channel_id) VALUES (?, ?)",
                (chat_id, log_channel_id)
            )

# ========== МОДЕРАТОРЫ ==========

def add_chat_moderator(chat_id: int, user_id: int, assigned_by: int):
    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO chat_admins (chat_id, user_id, role, assigned_by)
            VALUES (?, ?, 'moderator', ?)
        """, (chat_id, user_id, assigned_by))

def remove_chat_moderator(chat_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM chat_admins WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )

def get_chat_moderators(chat_id: int):
    with get_db() as conn:
        return conn.execute("""
            SELECT user_id, username, assigned_by, assigned_at
            FROM chat_admins
            WHERE chat_id = ? AND role = 'moderator'
        """, (chat_id,)).fetchall()

def is_chat_moderator(chat_id: int, user_id: int) -> bool:
    with get_db() as conn:
        result = conn.execute(
            "SELECT 1 FROM chat_admins WHERE chat_id = ? AND user_id = ? AND role = 'moderator'",
            (chat_id, user_id)
        ).fetchone()
        return result is not None

# ========== АНОНИМНЫЕ ЖАЛОБЫ ==========

def save_report(chat_id: int, reporter_id: int, target_id: int, reason: str):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO reports (chat_id, reporter_id, target_id, reason, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (chat_id, reporter_id, target_id, reason))

def get_reports_count(chat_id: int, target_id: int = None) -> int:
    with get_db() as conn:
        if target_id:
            result = conn.execute(
                "SELECT COUNT(*) as count FROM reports WHERE chat_id = ? AND target_id = ? AND status = 'pending'",
                (chat_id, target_id)
            ).fetchone()
        else:
            result = conn.execute(
                "SELECT COUNT(*) as count FROM reports WHERE chat_id = ? AND status = 'pending'",
                (chat_id,)
            ).fetchone()
        return result["count"] if result else 0

def resolve_report(report_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE reports SET status = 'resolved' WHERE id = ?",
            (report_id,)
        )

def get_reports_stats(chat_id: int):
    with get_db() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) as count FROM reports WHERE chat_id = ? AND status = 'pending'",
            (chat_id,)
        ).fetchone()["count"] or 0
        resolved = conn.execute(
            "SELECT COUNT(*) as count FROM reports WHERE chat_id = ? AND status = 'resolved'",
            (chat_id,)
        ).fetchone()["count"] or 0
        return {"pending": pending, "resolved": resolved, "total": pending + resolved}

# ========== КАПЧА ==========

def save_captcha(user_id: int, chat_id: int, answer: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO captcha (user_id, chat_id, answer, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, chat_id, answer)
        )

def get_captcha(user_id: int, chat_id: int):
    with get_db() as conn:
        result = conn.execute(
            "SELECT answer, created_at FROM captcha WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        return result

def delete_captcha(user_id: int, chat_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM captcha WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )

# ========== ДНИ РОЖДЕНИЯ ==========

def set_birthday(user_id: int, chat_id: int, birthday: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO birthdays (user_id, chat_id, birthday) VALUES (?, ?, ?)",
            (user_id, chat_id, birthday)
        )

def get_birthday(user_id: int, chat_id: int):
    with get_db() as conn:
        result = conn.execute(
            "SELECT birthday FROM birthdays WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        return result["birthday"] if result else None
