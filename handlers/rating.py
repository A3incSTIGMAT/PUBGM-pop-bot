"""
Модуль рейтинга чатов и мотивации для лидеров
"""

import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)


async def init_rating_tables():
    """Инициализация таблиц рейтинга чатов"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Таблица активности чатов
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
    
    # Таблица наград чатов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id BIGINT NOT NULL,
            reward_type TEXT,
            reward_amount INTEGER,
            awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица личной статистики пользователей (для игр без спама)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_game_stats (
            user_id INTEGER PRIMARY KEY,
            total_games INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_coins INTEGER DEFAULT 0,
            slot_played INTEGER DEFAULT 0,
            roulette_played INTEGER DEFAULT 0,
            rps_played INTEGER DEFAULT 0,
            duel_played INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


async def update_chat_activity(chat_id: int, activity_type: str, points: int = 1):
    """Обновить активность чата"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO chat_rating (chat_id, activity_points)
        VALUES (?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            activity_points = activity_points + ?,
            last_updated = CURRENT_TIMESTAMP
    """, (chat_id, points, points))
    
    if activity_type == "game":
        cursor.execute("""
            UPDATE chat_rating SET games_played = games_played + 1 WHERE chat_id = ?
        """, (chat_id,))
    elif activity_type == "message":
        cursor.execute("""
            UPDATE chat_rating SET messages_count = messages_count + 1 WHERE chat_id = ?
        """, (chat_id,))
    
    conn.commit()
    conn.close()


async def get_top_chats(limit: int = 10) -> list:
    """Получить топ чатов по активности"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id, chat_title, activity_points, games_played, messages_count
        FROM chat_rating
        ORDER BY activity_points DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "chat_id": row[0],
            "title": row[1] or f"Чат {row[0]}",
            "points": row[2],
            "games": row[3],
            "messages": row[4]
        }
        for row in rows
    ]


async def award_chat_owner(chat_id: int, owner_id: int, reward_type: str, amount: int):
    """Наградить владельца чата"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO chat_rewards (chat_id, reward_type, reward_amount)
        VALUES (?, ?, ?)
    """, (chat_id, reward_type, amount))
    
    conn.commit()
    conn.close()
    
    # Начисляем монеты владельцу
    from database import update_balance
    await update_balance(owner_id, amount, f"Награда за топ чата: {reward_type}")


@router.message(Command("top_chats"))
async def cmd_top_chats(message: types.Message):
    """Топ чатов по активности"""
    top = await get_top_chats(10)
    
    if not top:
        await message.answer("📊 Пока нет чатов в рейтинге!\n\nАктивизируйте свой чат, играя в игры!")
        return
    
    text = "📊 *ТОП ЧАТОВ ПО АКТИВНОСТИ*\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, chat in enumerate(top):
        medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
        text += f"{medal} *{chat['title'][:30]}*\n"
        text += f"   └ 🎮 {chat['games']} игр | 💬 {chat['messages']} сообщений | 📊 {chat['points']} очков\n\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━━\n"
    text += "🏆 *Награды для лидеров:*\n"
    text += "├ 1 место: 5000 NCoins + VIP статус\n"
    text += "├ 2 место: 3000 NCoins\n"
    text += "├ 3 место: 1000 NCoins\n"
    text += "└ 4-10 места: 500 NCoins\n\n"
    text += "📌 Награды начисляются автоматически раз в неделю!"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("chat_stats"))
async def cmd_chat_stats(message: types.Message):
    """Статистика текущего чата"""
    chat_id = message.chat.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT activity_points, games_played, messages_count
        FROM chat_rating WHERE chat_id = ?
    """, (chat_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(
            "📊 Статистика чата:\n\n"
            "🎮 Игр сыграно: 0\n"
            "💬 Сообщений: 0\n"
            "📊 Очков активности: 0\n\n"
            "💡 Играйте в игры через бота, чтобы поднять рейтинг чата!"
        )
        return
    
    points, games, messages = row
    
    # Получаем позицию в рейтинге
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) + 1 FROM chat_rating WHERE activity_points > ?
    """, (points,))
    position = cursor.fetchone()[0]
    conn.close()
    
    await message.answer(
        f"📊 *СТАТИСТИКА ЧАТА*\n\n"
        f"📛 Название: {message.chat.title}\n"
        f"📈 Позиция в рейтинге: {position}\n"
        f"🎮 Игр сыграно: {games}\n"
        f"💬 Сообщений: {messages}\n"
        f"📊 Очков активности: {points}\n\n"
        f"🏆 Для поднятия рейтинга:\n"
        f"├ Играйте в игры через бота\n"
        f"├ Приглашайте друзей\n"
        f"└ Будьте активны!",
        parse_mode=ParseMode.MARKDOWN
    )
