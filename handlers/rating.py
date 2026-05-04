#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/rating.py
# ВЕРСИЯ: 2.1.0-production (исправленная после аудита)
# ОПИСАНИЕ: Рейтинг чатов и статистика
# ============================================
# ИСПРАВЛЕНИЯ v2.1.0:
#   🔴 Убраны ВСЕ commit=True из _execute_with_retry
#   🟡 Устранён прямой вызов роутер-хендлера
#   🟡 Все DatabaseError логируются (не проглатываются)
#   🟡 Награды вынесены в os.getenv()
#   🟡 Добавлена проверка callback.message
#   🟢 Добавлены docstrings
#   🟢 MEDALS генерируется динамически
# ============================================

import asyncio
import html
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ (НАСТРАИВАЕМЫЕ) ====================

# Награды для топ чатов
TOP_CHAT_REWARDS: Dict[int, Dict[str, int]] = {
    1: {
        "coins": int(os.getenv("RATING_REWARD_1_COINS", "5000")),
        "vip_days": int(os.getenv("RATING_REWARD_1_VIP", "30"))
    },
    2: {
        "coins": int(os.getenv("RATING_REWARD_2_COINS", "3000")),
        "vip_days": int(os.getenv("RATING_REWARD_2_VIP", "0"))
    },
    3: {
        "coins": int(os.getenv("RATING_REWARD_3_COINS", "1000")),
        "vip_days": int(os.getenv("RATING_REWARD_3_VIP", "0"))
    },
}

CONSOLATION_REWARD = int(os.getenv("RATING_CONSOLATION_REWARD", "500"))
TOP_CHATS_LIMIT = int(os.getenv("RATING_TOP_LIMIT", "10"))


def _get_medals(count: int) -> List[str]:
    """
    Генерация списка медалей для топа.
    
    Args:
        count: Количество медалей
        
    Returns:
        Список строк с эмодзи медалей
    """
    base = ["🥇", "🥈", "🥉"]
    result = base[:min(count, 3)]
    for i in range(4, count + 1):
        result.append(f"{i}.")
    return result


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """
    Безопасное экранирование HTML.
    
    Args:
        text: Строка для экранирования
        
    Returns:
        Экранированная строка
    """
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def _safe_int(value: Any, default: int = 0) -> int:
    """Безопасное преобразование в int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


async def _safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = True) -> None:
    """
    Безопасный ответ на callback.
    
    Обрабатывает случай, когда callback уже был отвечен.
    """
    if callback is None:
        return
    
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramAPIError:
        pass


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
                 chat_title, points, points, points)
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
                (chat_id, points, points, points, points, points, points)
            )
        
        # Обновление специфичных счетчиков
        if activity_type == "game":
            await db._execute_with_retry(
                "UPDATE chat_rating SET games_played = games_played + 1 WHERE chat_id = ?",
                (chat_id,)
            )
        elif activity_type == "message":
            await db._execute_with_retry(
                "UPDATE chat_rating SET messages_count = messages_count + 1 WHERE chat_id = ?",
                (chat_id,)
            )
            
    except DatabaseError as e:
        logger.error(f"❌ Failed to update chat activity for {chat_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error updating chat activity: {e}", exc_info=True)


async def get_chat_rating(chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Получить рейтинг конкретного чата.
    
    Args:
        chat_id: ID чата
        
    Returns:
        Словарь с данными чата или None при ошибке
    """
    try:
        row = await db._execute_with_retry(
            """SELECT activity_points, games_played, messages_count, 
                      week_activity, month_activity
               FROM chat_rating WHERE chat_id = ?""",
            (chat_id,),
            fetch_one=True
        )
        
        if row:
            # Получаем позицию в рейтинге
            pos_row = await db._execute_with_retry(
                "SELECT COUNT(*) + 1 as position FROM chat_rating WHERE activity_points > ?",
                (row['activity_points'],),
                fetch_one=True
            )
            position = pos_row['position'] if pos_row else 0
            
            return {
                'points': row['activity_points'] or 0,
                'games': row['games_played'] or 0,
                'messages': row['messages_count'] or 0,
                'week': row['week_activity'] or 0,
                'month': row['month_activity'] or 0,
                'position': position
            }
    except DatabaseError as e:
        logger.error(f"❌ Failed to get chat rating for {chat_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting chat rating: {e}", exc_info=True)
    
    return None


async def get_top_chats(limit: int = TOP_CHATS_LIMIT) -> List[Dict[str, Any]]:
    """
    Получить топ чатов по активности.
    
    Args:
        limit: Количество чатов
        
    Returns:
        Список словарей с данными чатов
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
                    "title": safe_html_escape(str(row['chat_title'] or f"Чат {row['chat_id']}")),
                    "points": row['activity_points'] or 0,
                    "games": row['games_played'] or 0,
                    "messages": row['messages_count'] or 0
                }
                for row in rows
            ]
    except DatabaseError as e:
        logger.error(f"❌ Failed to get top chats: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting top chats: {e}", exc_info=True)
    
    return []


async def award_chat_owner(chat_id: int, owner_id: int, reward_type: str, amount: int) -> bool:
    """
    Наградить владельца чата монетами.
    
    Args:
        chat_id: ID чата
        owner_id: ID владельца
        reward_type: Тип награды (для логов)
        amount: Сумма монет
        
    Returns:
        True при успехе, False при ошибке
    """
    try:
        # Записываем награду
        await db._execute_with_retry(
            """INSERT INTO chat_rewards (chat_id, reward_type, reward_amount)
               VALUES (?, ?, ?)""",
            (chat_id, reward_type, amount)
        )
        
        # Начисляем монеты владельцу
        if hasattr(db, 'update_balance') and callable(db.update_balance):
            await db.update_balance(owner_id, amount, f"Награда за топ чата: {reward_type}")
        else:
            await db._execute_with_retry(
                "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?",
                (amount, owner_id)
            )
        
        logger.info(f"🏆 Awarded {amount} coins to owner {owner_id} of chat {chat_id}")
        return True
        
    except DatabaseError as e:
        logger.error(f"❌ Failed to award chat owner: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error awarding chat owner: {e}", exc_info=True)
        return False


async def award_vip_to_owner(chat_id: int, owner_id: int, days: int) -> bool:
    """
    Выдать VIP владельцу чата.
    
    Args:
        chat_id: ID чата
        owner_id: ID владельца
        days: Количество дней VIP
        
    Returns:
        True при успехе, False при ошибке
    """
    try:
        new_until = (datetime.now() + timedelta(days=days)).isoformat()
        
        # Проверяем текущий VIP
        try:
            user = await db.get_user(owner_id)
            current_vip = user.get('vip_level', 0) if user else 0
        except (DatabaseError, Exception) as e:
            logger.warning(f"⚠️ Could not get user {owner_id} for VIP award: {e}")
            current_vip = 0
        
        # Выдаем VIP 1 уровня если нет выше
        new_level = max(current_vip, 1)
        
        await db._execute_with_retry(
            "UPDATE users SET vip_level = ?, vip_until = ? WHERE user_id = ?",
            (new_level, new_until, owner_id)
        )
        
        logger.info(f"⭐ Awarded VIP level {new_level} for {days} days to owner {owner_id}")
        return True
        
    except DatabaseError as e:
        logger.error(f"❌ Failed to award VIP: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error awarding VIP: {e}", exc_info=True)
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
        row = await db._execute_with_retry(
            "SELECT owner_id FROM chat_rating WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        if row and row.get('owner_id'):
            return row['owner_id']
    except DatabaseError as e:
        logger.warning(f"⚠️ Could not get chat owner for {chat_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error getting chat owner: {e}", exc_info=True)
    
    return None


# ==================== ПОСТРОИТЕЛИ ТЕКСТА ====================

async def _build_top_chats_text() -> Tuple[str, InlineKeyboardMarkup]:
    """
    Построить текст и клавиатуру для топа чатов.
    
    Returns:
        Tuple[HTML-текст, клавиатура]
    """
    top = await get_top_chats(TOP_CHATS_LIMIT)
    medals = _get_medals(TOP_CHATS_LIMIT)
    
    if not top:
        return (
            "📊 <b>ТОП ЧАТОВ</b>\n\n"
            "Пока нет чатов в рейтинге!\n\n"
            "💡 Активизируйте свой чат, играя в игры и общаясь!",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
            ])
        )
    
    lines = ["📊 <b>ТОП ЧАТОВ ПО АКТИВНОСТИ</b>\n"]
    
    for i, chat in enumerate(top):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        lines.append(
            f"{medal} <b>{safe_html_escape(str(chat['title'])[:30])}</b>\n"
            f"   └ 🎮 {chat['games']} игр | 💬 {chat['messages']} сообщ | 📊 {chat['points']} очков\n"
        )
    
    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "🏆 <b>Награды для лидеров:</b>",
        f"├ 🥇 1 место: {TOP_CHAT_REWARDS[1]['coins']} NCoins" + 
        (f" + VIP {TOP_CHAT_REWARDS[1]['vip_days']} дн" if TOP_CHAT_REWARDS[1]['vip_days'] > 0 else ""),
        f"├ 🥈 2 место: {TOP_CHAT_REWARDS[2]['coins']} NCoins",
        f"├ 🥉 3 место: {TOP_CHAT_REWARDS[3]['coins']} NCoins",
        f"└ 4-{TOP_CHATS_LIMIT} места: {CONSOLATION_REWARD} NCoins",
        "",
        "📌 Награды начисляются автоматически раз в неделю!"
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    return "\n".join(lines), keyboard


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@router.message(Command("top_chats"))
async def cmd_top_chats(message: Message) -> None:
    """
    Топ чатов по активности.
    
    Отображает рейтинг чатов с наградами для лидеров.
    """
    if message is None:
        return
    
    try:
        text, keyboard = await _build_top_chats_text()
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        logger.info("✅ Top chats viewed")
        
    except Exception as e:
        logger.error(f"❌ Error in cmd_top_chats: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки рейтинга.")


@router.message(Command("chat_stats"))
async def cmd_chat_stats(message: Message) -> None:
    """
    Статистика текущего чата.
    
    Отображает позицию в рейтинге, активность за неделю и месяц.
    """
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
        logger.info(f"✅ Chat stats viewed for {chat_id}")
        
    except Exception as e:
        logger.error(f"❌ Error in cmd_chat_stats: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки статистики.")


@router.callback_query(F.data == "top_chats")
async def top_chats_callback(callback: CallbackQuery) -> None:
    """
    Callback для топа чатов.
    
    Использует _build_top_chats_text для формирования ответа.
    """
    if callback is None or callback.message is None:
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    try:
        text, keyboard = await _build_top_chats_text()
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        logger.info("✅ Top chats callback viewed")
    except TelegramAPIError as e:
        logger.warning(f"⚠️ Failed to edit top chats message: {e}")
    except Exception as e:
        logger.error(f"❌ Error in top_chats_callback: {e}", exc_info=True)
        await _safe_callback_answer(callback, "❌ Ошибка")
        return
    
    await _safe_callback_answer(callback)


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
    
    Вызывается из планировщика (utils/auto_delete.py).
    Начисляет монеты и VIP владельцам топ-чатов.
    """
    try:
        top = await get_top_chats(TOP_CHATS_LIMIT)
        
        if not top:
            logger.info("📊 No chats to award")
            return
        
        awarded = 0
        for i, chat in enumerate(top):
            position = i + 1
            chat_id = chat['chat_id']
            
            owner_id = await get_chat_owner(chat_id)
            if not owner_id:
                logger.warning(f"⚠️ No owner found for chat {chat_id}")
                continue
            
            # Используем словарь наград
            if position in TOP_CHAT_REWARDS:
                reward = TOP_CHAT_REWARDS[position]
                await award_chat_owner(chat_id, owner_id, f"weekly_top_{position}", reward['coins'])
                if reward.get('vip_days', 0) > 0:
                    await award_vip_to_owner(chat_id, owner_id, reward['vip_days'])
                awarded += 1
            elif position <= TOP_CHATS_LIMIT:
                await award_chat_owner(chat_id, owner_id, f"weekly_top_{position}", CONSOLATION_REWARD)
                awarded += 1
        
        # Сброс недельной активности
        await db._execute_with_retry("UPDATE chat_rating SET week_activity = 0")
        
        logger.info(f"🏆 Weekly rewards processed: {awarded} chats awarded")
        
    except DatabaseError as e:
        logger.error(f"❌ Database error processing weekly rewards: {e}")
    except Exception as e:
        logger.error(f"❌ Error processing weekly rewards: {e}", exc_info=True)


async def process_monthly_rewards() -> None:
    """
    Обработка ежемесячных наград.
    
    Сбрасывает месячную активность для нового периода.
    """
    try:
        await db._execute_with_retry("UPDATE chat_rating SET month_activity = 0")
        logger.info("📅 Monthly activity reset")
        
    except DatabaseError as e:
        logger.error(f"❌ Database error processing monthly rewards: {e}")
    except Exception as e:
        logger.error(f"❌ Error processing monthly rewards: {e}", exc_info=True)


async def on_shutdown() -> None:
    """Корректное завершение модуля."""
    logger.info("✅ Rating module shutdown complete")
