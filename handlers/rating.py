#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/rating.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Рейтинг чатов и статистика
# ИСПРАВЛЕНИЯ: Совместимость с aiosqlite, безопасное экранирование
# ============================================

import html
import logging
from typing import Optional, List, Dict, Any

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db, DatabaseError

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

# Награды для топ чатов (можно вынести в config)
TOP_CHAT_REWARDS = {
    1: {"coins": 5000, "vip_days": 30},
    2: {"coins": 3000, "vip_days": 0},
    3: {"coins": 1000, "vip_days": 0},
}

CONSOLATION_REWARD = 500  # Для мест 4-10

# Медали для топа
MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def update_chat_activity(
    chat_id: int,
    chat_title: Optional[str] = None,
    activity_type: str = "message",
    points: int = 1
) -> None:
    """
    Обновить активность чата в рейтинге.
    
    Args:
        chat_id: ID чата
        chat_title: Название чата
        activity_type: Тип активности (message/game)
        points: Количество очков
    """
    if chat_id is None:
        return
    
    try:
        # Обновляем название чата если передано
        if chat_title:
            await db._execute_with_retry(
                """INSERT INTO chat_rating (chat_id, chat_title, activity_points, week_activity, month_activity)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                       chat_title = COALESCE(?, chat_title),
                       activity_points = activity_points + ?,
                       week_activity = week_activity + ?,
                       month_activity = month_activity + ?,
                       last_updated = CURRENT_TIMESTAMP""",
                (chat_id, chat_title, points, points, points,
                 chat_title, points, points, points),
                commit=True
            )
        else:
            await db._execute_with_retry(
                """INSERT INTO chat_rating (chat_id, activity_points, week_activity, month_activity)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                       activity_points = activity_points + ?,
                       week_activity = week_activity + ?,
                       month_activity = month_activity + ?,
                       last_updated = CURRENT_TIMESTAMP""",
                (chat_id, points, points, points, points, points, points),
                commit=True
            )
        
        # Обновление специфичных счетчиков
        if activity_type == "game":
            await db._execute_with_retry(
                "UPDATE chat_rating SET games_played = games_played + 1 WHERE chat_id = ?",
                (chat_id,),
                commit=True
            )
        elif activity_type == "message":
            await db._execute_with_retry(
                "UPDATE chat_rating SET messages_count = messages_count + 1 WHERE chat_id = ?",
                (chat_id,),
                commit=True
            )
            
    except DatabaseError as e:
        logger.error(f"Failed to update chat activity for {chat_id}: {e}")


async def get_chat_rating(chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Получить рейтинг конкретного чата.
    
    Args:
        chat_id: ID чата
        
    Returns:
        Словарь с данными чата или None
    """
    try:
        row = await db._execute_with_retry(
            """SELECT activity_points, games_played, messages_count, week_activity, month_activity
               FROM chat_rating WHERE chat_id = ?""",
            (chat_id,),
            fetch_one=True
        )
        
        if row:
            # Получаем позицию в рейтинге
            pos_row = await db._execute_with_retry(
                "SELECT COUNT(*) + 1 FROM chat_rating WHERE activity_points > ?",
                (row['activity_points'],),
                fetch_one=True
            )
            position = pos_row['COUNT(*) + 1'] if pos_row else 0
            
            return {
                'points': row['activity_points'],
                'games': row['games_played'],
                'messages': row['messages_count'],
                'week': row['week_activity'],
                'month': row['month_activity'],
                'position': position
            }
    except DatabaseError as e:
        logger.error(f"Failed to get chat rating for {chat_id}: {e}")
    
    return None


async def get_top_chats(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Получить топ чатов по активности.
    
    Args:
        limit: Количество чатов
        
    Returns:
        Список чатов
    """
    try:
        rows = await db._execute_with_retry(
            """SELECT chat_id, chat_title, activity_points, games_played, messages_count
               FROM chat_rating
               ORDER BY activity_points DESC
               LIMIT ?""",
            (limit,),
            fetch_all=True
        )
        
        if rows:
            return [
                {
                    "chat_id": row['chat_id'],
                    "title": safe_html_escape(row['chat_title'] or f"Чат {row['chat_id']}"),
                    "points": row['activity_points'] or 0,
                    "games": row['games_played'] or 0,
                    "messages": row['messages_count'] or 0
                }
                for row in rows
            ]
    except DatabaseError as e:
        logger.error(f"Failed to get top chats: {e}")
    
    return []


async def award_chat_owner(chat_id: int, owner_id: int, reward_type: str, amount: int) -> bool:
    """
    Наградить владельца чата.
    
    Args:
        chat_id: ID чата
        owner_id: ID владельца
        reward_type: Тип награды
        amount: Сумма
        
    Returns:
        True если успешно
    """
    try:
        # Записываем награду
        await db._execute_with_retry(
            """INSERT INTO chat_rewards (chat_id, reward_type, reward_amount)
               VALUES (?, ?, ?)""",
            (chat_id, reward_type, amount),
            commit=True
        )
        
        # Начисляем монеты владельцу
        await db.update_balance(owner_id, amount, f"Награда за топ чата: {reward_type}")
        
        logger.info(f"Awarded {amount} coins to owner {owner_id} of chat {chat_id}")
        return True
        
    except DatabaseError as e:
        logger.error(f"Failed to award chat owner: {e}")
        return False


async def award_vip_to_owner(chat_id: int, owner_id: int, days: int) -> bool:
    """
    Выдать VIP владельцу чата.
    
    Args:
        chat_id: ID чата
        owner_id: ID владельца
        days: Количество дней VIP
        
    Returns:
        True если успешно
    """
    try:
        from datetime import datetime, timedelta
        
        new_until = (datetime.now() + timedelta(days=days)).isoformat()
        
        # Проверяем текущий VIP
        user = await db.get_user(owner_id)
        current_vip = user.get('vip_level', 0) if user else 0
        
        # Выдаем VIP 1 уровня если нет выше
        new_level = max(current_vip, 1)
        
        await db._execute_with_retry(
            "UPDATE users SET vip_level = ?, vip_until = ? WHERE user_id = ?",
            (new_level, new_until, owner_id),
            commit=True
        )
        
        logger.info(f"Awarded VIP level {new_level} for {days} days to owner {owner_id}")
        return True
        
    except DatabaseError as e:
        logger.error(f"Failed to award VIP: {e}")
        return False


async def get_chat_owner(chat_id: int) -> Optional[int]:
    """
    Получить ID создателя чата.
    
    Args:
        chat_id: ID чата
        
    Returns:
        ID создателя или None
    """
    try:
        # Пытаемся получить из chat_rating
        row = await db._execute_with_retry(
            "SELECT owner_id FROM chat_rating WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        if row and row.get('owner_id'):
            return row['owner_id']
    except DatabaseError:
        pass
    
    return None


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("top_chats"))
async def cmd_top_chats(message: Message) -> None:
    """Топ чатов по активности."""
    if message is None:
        return
    
    try:
        top = await get_top_chats(10)
        
        if not top:
            await message.answer(
                "📊 <b>ТОП ЧАТОВ</b>\n\n"
                "Пока нет чатов в рейтинге!\n\n"
                "💡 Активизируйте свой чат, играя в игры и общаясь!",
                parse_mode=ParseMode.HTML
            )
            return
        
        lines = ["📊 <b>ТОП ЧАТОВ ПО АКТИВНОСТИ</b>\n"]
        
        for i, chat in enumerate(top):
            medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
            lines.append(
                f"{medal} <b>{chat['title'][:30]}</b>\n"
                f"   └ 🎮 {chat['games']} игр | 💬 {chat['messages']} сообщ | 📊 {chat['points']} очков\n"
            )
        
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            "🏆 <b>Награды для лидеров:</b>",
            "├ 🥇 1 место: 5000 NCoins + VIP статус",
            "├ 🥈 2 место: 3000 NCoins",
            "├ 🥉 3 место: 1000 NCoins",
            "└ 4-10 места: 500 NCoins",
            "",
            "📌 Награды начисляются автоматически раз в неделю!"
        ])
        
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in cmd_top_chats: {e}")
        await message.answer("❌ Ошибка загрузки рейтинга.")


@router.message(Command("chat_stats"))
async def cmd_chat_stats(message: Message) -> None:
    """Статистика текущего чата."""
    if message is None or message.chat is None:
        return
    
    chat_id = message.chat.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    try:
        stats = await get_chat_rating(chat_id)
        
        if not stats:
            await message.answer(
                "📊 <b>СТАТИСТИКА ЧАТА</b>\n\n"
                "🎮 Игр сыграно: 0\n"
                "💬 Сообщений: 0\n"
                "📊 Очков активности: 0\n\n"
                "💡 Играйте в игры через бота, чтобы поднять рейтинг чата!",
                parse_mode=ParseMode.HTML
            )
            return
        
        chat_title = safe_html_escape(message.chat.title or f"Чат {chat_id}")
        
        text = (
            f"📊 <b>СТАТИСТИКА ЧАТА</b>\n\n"
            f"📛 Название: {chat_title}\n"
            f"📈 Позиция в рейтинге: {stats['position']}\n"
            f"🎮 Игр сыграно: {stats['games']}\n"
            f"💬 Сообщений: {stats['messages']}\n"
            f"📊 Очков активности: {stats['points']}\n"
            f"📅 За неделю: {stats['week']}\n"
            f"📆 За месяц: {stats['month']}\n\n"
            f"🏆 <b>Для поднятия рейтинга:</b>\n"
            f"├ Играйте в игры через бота\n"
            f"├ Приглашайте друзей\n"
            f"└ Будьте активны в чате!"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in cmd_chat_stats: {e}")
        await message.answer("❌ Ошибка загрузки статистики.")


@router.callback_query(F.data == "top_chats")
async def top_chats_callback(callback: CallbackQuery) -> None:
    """Callback для топа чатов."""
    if callback is None:
        return
    
    await cmd_top_chats(callback.message)
    await callback.answer()


# ==================== ИНТЕГРАЦИОННЫЕ ФУНКЦИИ ====================

async def track_chat_activity(
    chat_id: int,
    chat_title: Optional[str] = None,
    activity_type: str = "message",
    points: int = 1
) -> None:
    """
    Отслеживание активности чата (для вызова из других модулей).
    
    Args:
        chat_id: ID чата
        chat_title: Название чата
        activity_type: Тип активности
        points: Очки
    """
    await update_chat_activity(chat_id, chat_title, activity_type, points)


async def process_weekly_rewards() -> None:
    """
    Обработка еженедельных наград для топ чатов.
    Вызывается из планировщика.
    """
    try:
        top = await get_top_chats(10)
        
        if not top:
            logger.info("No chats to award")
            return
        
        awarded = 0
        for i, chat in enumerate(top):
            position = i + 1
            chat_id = chat['chat_id']
            
            owner_id = await get_chat_owner(chat_id)
            if not owner_id:
                logger.warning(f"No owner found for chat {chat_id}")
                continue
            
            if position == 1:
                reward = TOP_CHAT_REWARDS[1]
                await award_chat_owner(chat_id, owner_id, "weekly_top_1", reward['coins'])
                if reward['vip_days'] > 0:
                    await award_vip_to_owner(chat_id, owner_id, reward['vip_days'])
                awarded += 1
            elif position == 2:
                await award_chat_owner(chat_id, owner_id, "weekly_top_2", TOP_CHAT_REWARDS[2]['coins'])
                awarded += 1
            elif position == 3:
                await award_chat_owner(chat_id, owner_id, "weekly_top_3", TOP_CHAT_REWARDS[3]['coins'])
                awarded += 1
            elif position <= 10:
                await award_chat_owner(chat_id, owner_id, "weekly_top_10", CONSOLATION_REWARD)
                awarded += 1
        
        # Сброс недельной активности
        await db._execute_with_retry(
            "UPDATE chat_rating SET week_activity = 0",
            commit=True
        )
        
        logger.info(f"Weekly rewards processed: {awarded} chats awarded")
        
    except Exception as e:
        logger.error(f"Error processing weekly rewards: {e}")


async def process_monthly_rewards() -> None:
    """Обработка ежемесячных наград."""
    try:
        # Сброс месячной активности
        await db._execute_with_retry(
            "UPDATE chat_rating SET month_activity = 0",
            commit=True
        )
        logger.info("Monthly activity reset")
        
    except Exception as e:
        logger.error(f"Error processing monthly rewards: {e}")
