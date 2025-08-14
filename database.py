import sqlite3

DB_NAME = "db.sqlite3"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            popularity INTEGER DEFAULT 0,
            referred_by INTEGER,
            last_daily_chicken INTEGER,
            last_daily_bike INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            popularity INTEGER,
            system TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id, username, full_name, referred_by=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, referred_by) VALUES (?, ?, ?, ?)",
                (user_id, username, full_name, referred_by))
    conn.commit()

    if referred_by and referred_by != user_id:
        cur.execute("SELECT popularity FROM users WHERE user_id = ?", (referred_by,))
        ref_info = cur.fetchone()
        if ref_info:
            bonus = 50
            cur.execute("UPDATE users SET popularity = popularity + ? WHERE user_id = ?", (bonus, referred_by))
            cur.execute("INSERT INTO referrals (referrer_id, referred_id, bonus) VALUES (?, ?, ?)",
                        (referred_by, user_id, bonus))
            conn.commit()
            conn.close()
            return referred_by, bonus
    conn.close()
    return None

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0],
            "username": row[1],
            "full_name": row[2],
            "popularity": row[3],
            "referred_by": row[4],
            "last_daily_chicken": row[5],
            "last_daily_bike": row[6]
        }
    return None

def update_popularity(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET popularity = popularity + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_top_users(limit=10):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT username, full_name, popularity FROM users ORDER BY popularity DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def add_payment(user_id, amount, popularity, system):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO payments (user_id, amount, popularity, system) VALUES (?, ?, ?, ?)",
                (user_id, amount, popularity, system))
    conn.commit()
    conn.close()
