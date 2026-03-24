"""
Сложные SQL-запросы для NEXUS бота.
Содержит функции для получения рейтингов, статистики и агрегированных данных.
"""

from database.db import get_db
from typing import List, Dict, Any

def get_top_balance(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Получить топ пользователей по балансу"""
    with get_db() as conn:
        results = conn.execute("""
            SELECT user_id, username, balance 
            FROM users 
            WHERE chat_id = ? AND balance > 0
            ORDER BY balance DESC 
            LIMIT ?
        """, (chat_id, limit)).fetchall()
        return [dict(row) for row in results]

def get_top_messages(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Получить топ пользователей по количеству сообщений"""
    with get_db() as conn:
        results = conn.execute("""
            SELECT user_id, username, total_messages 
            FROM users 
            WHERE chat_id = ? AND total_messages > 0
            ORDER BY total_messages DESC 
            LIMIT ?
        """, (chat_id, limit)).fetchall()
        return [dict(row) for row in results]

def get_top_reputation(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Получить топ пользователей по репутации"""
    with get_db() as conn:
        results = conn.execute("""
            SELECT user_id, username, reputation 
            FROM users 
            WHERE chat_id = ? AND reputation > 0
            ORDER BY reputation DESC 
            LIMIT ?
        """, (chat_id, limit)).fetchall()
        return [dict(row) for row in results]

def get_game_leaderboard(chat_id: int, game_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Получить таблицу лидеров по конкретной игре"""
    with get_db() as conn:
        results = conn.execute("""
            SELECT u.user_id, u.username, g.wins, g.losses, g.total_played,
                   ROUND(CAST(g.wins AS FLOAT) / NULLIF(g.total_played, 0) * 100, 1) as winrate
            FROM game_stats g
            JOIN users u ON u.user_id = g.user_id AND u.chat_id = g.chat_id
            WHERE g.chat_id = ? AND g.game_name = ?
            ORDER BY g.wins DESC
            LIMIT ?
        """, (chat_id, game_name, limit)).fetchall()
        return [dict(row) for row in results]

def get_chat_activity_stats(chat_id: int) -> Dict[str, Any]:
    """Получить статистику активности чата"""
    with get_db() as conn:
        total_messages = conn.execute("""
            SELECT SUM(total_messages) as total 
            FROM users 
            WHERE chat_id = ?
        """, (chat_id,)).fetchone()["total"] or 0
        
        active_users = conn.execute("""
            SELECT COUNT(*) as count 
            FROM users 
            WHERE chat_id = ? AND total_messages > 10
        """, (chat_id,)).fetchone()["count"] or 0
        
        total_balance = conn.execute("""
            SELECT SUM(balance) as total 
            FROM users 
            WHERE chat_id = ?
        """, (chat_id,)).fetchone()["total"] or 0
        
        return {
            "total_messages": total_messages,
            "active_users": active_users,
            "total_balance": total_balance,
            "total_users": active_users + 10
        }

def get_user_rank(user_id: int, chat_id: int, by: str = "balance") -> Dict[str, Any]:
    """Получить место пользователя в рейтинге"""
    with get_db() as conn:
        if by == "balance":
            query = """
                SELECT COUNT(*) + 1 as rank 
                FROM users 
                WHERE chat_id = ? AND balance > (SELECT balance FROM users WHERE user_id = ? AND chat_id = ?)
            """
            result = conn.execute(query, (chat_id, user_id, chat_id)).fetchone()
        elif by == "messages":
            query = """
                SELECT COUNT(*) + 1 as rank 
                FROM users 
                WHERE chat_id = ? AND total_messages > (SELECT total_messages FROM users WHERE user_id = ? AND chat_id = ?)
            """
            result = conn.execute(query, (chat_id, user_id, chat_id)).fetchone()
        else:
            return {"rank": 0, "total": 0}
        
        total = conn.execute("SELECT COUNT(*) as total FROM users WHERE chat_id = ?", (chat_id,)).fetchone()["total"]
        
        return {
            "rank": result["rank"] if result else 1,
            "total": total
        }

def get_reports_stats(chat_id: int) -> Dict[str, Any]:
    """Получить статистику жалоб"""
    with get_db() as conn:
        pending = conn.execute("""
            SELECT COUNT(*) as count FROM reports WHERE chat_id = ? AND status = 'pending'
        """, (chat_id,)).fetchone()["count"] or 0
        
        resolved = conn.execute("""
            SELECT COUNT(*) as count FROM reports WHERE chat_id = ? AND status = 'resolved'
        """, (chat_id,)).fetchone()["count"] or 0
        
        top_targets = conn.execute("""
            SELECT target_id, COUNT(*) as count 
            FROM reports 
            WHERE chat_id = ? 
            GROUP BY target_id 
            ORDER BY count DESC 
            LIMIT 5
        """, (chat_id,)).fetchall()
        
        return {
            "pending": pending,
            "resolved": resolved,
            "total": pending + resolved,
            "top_targets": [dict(row) for row in top_targets]
        }
