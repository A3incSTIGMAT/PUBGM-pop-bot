#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: utils/auto_delete.py
# ВЕРСИЯ: 2.3.0-final
# ОПИСАНИЕ: Утренняя очистка + сводка дня + анализ тем — ФИНАЛЬНАЯ ВЕРСИЯ
# ============================================

import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from config import ADMIN_IDS, MORNING_CLEANUP_HOUR

logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

# Московское время (UTC+3)
MSK_OFFSET = timezone(timedelta(hours=3))

# Час запуска очистки
CLEANUP_HOUR = MORNING_CLEANUP_HOUR if MORNING_CLEANUP_HOUR else 10

# Задержки для API-запросов
DELETE_DELAY = 0.05
SEND_DELAY = 0.1
RATE_LIMIT_RETRY_DELAY = 60

# Тематические ключевые слова с границами слов
TOPIC_KEYWORDS = {
    "🎮 Игры": [r"\bигра\b", r"\bxo\b", r"\bкрестики\b", r"\bнолики\b", r"\bпобеда\b", r"\bставка\b", r"\bбот\b"],
    "💰 Экономика": [r"\bбаланс\b", r"\bмонеты\b", r"\bdaily\b", r"\bбонус\b", r"\bперевод\b", r"\bncoin\b"],
    "👑 VIP и ранги": [r"\bvip\b", r"\bстатус\b", r"\bранг\b", r"\bуровень\b", r"\bxp\b", r"\bопыт\b"],
    "💕 Отношения": [r"\bлюбовь\b", r"\bпара\b", r"\bсемья\b", r"\bотношения\b", r"\bбрак\b"],
    "🏷️ Теги": [r"\bтег\b", r"\bкатегория\b", r"\bподписка\b", r"\bуведомление\b"],
    "🤖 Бот": [r"\bnexus\b", r"\bнексус\b", r"\bкоманда\b", r"\bфункция\b", r"\bбаг\b"],
    "💬 Общение": [r"\bпривет\b", r"\bпока\b", r"\bспасибо\b", r"\bдоброе\b", r"\bутро\b", r"\bвечер\b"],
}


# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

class MessageTracker:
    """Потокобезопасный трекер сообщений бота."""
    
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending_cleanup: Set[Tuple[int, int]] = set()
        self._active_chats: Set[int] = set()
    
    async def add_pending(self, chat_id: int, message_id: int) -> None:
        if chat_id is None or message_id is None:
            return
        async with self._lock:
            self._pending_cleanup.add((chat_id, message_id))
            self._active_chats.add(chat_id)
    
    async def add_active_chat(self, chat_id: int) -> None:
        if chat_id is None:
            return
        async with self._lock:
            self._active_chats.add(chat_id)
    
    async def get_and_clear_pending(self) -> List[Tuple[int, int]]:
        async with self._lock:
            pending = list(self._pending_cleanup)
            self._pending_cleanup.clear()
            return pending
    
    async def get_active_chats(self) -> List[int]:
        async with self._lock:
            return list(self._active_chats)
    
    async def sync_chats_from_db(self, db) -> None:
        try:
            if db and hasattr(db, 'get_all_chats_with_bot'):
                chats = await db.get_all_chats_with_bot()
                async with self._lock:
                    for chat_id in chats:
                        if chat_id:
                            self._active_chats.add(chat_id)
                logger.info(f"✅ Synced {len(chats)} chats from database")
        except Exception as e:
            logger.warning(f"Failed to sync chats from DB: {e}")


_tracker = MessageTracker()
_shutdown_event = asyncio.Event()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def format_top_name(user: Optional[Dict]) -> str:
    if user is None or not isinstance(user, dict):
        return "Игрок"
    username = user.get("username")
    if username:
        return f"@{safe_html_escape(str(username))}"
    first_name = user.get("first_name")
    if first_name:
        escaped = safe_html_escape(str(first_name))
        return escaped[:20] if len(escaped) > 20 else escaped
    return "Игрок"


def format_number(num: Any) -> str:
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError, OverflowError):
        return "0"


async def _send_with_retry(bot: Bot, chat_id: int, text: str, max_retries: int = 3) -> bool:
    """Отправка сообщения с обработкой лимитов."""
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
            return True
        except TelegramRetryAfter as e:
            wait_time = min(e.retry_after, RATE_LIMIT_RETRY_DELAY)
            logger.warning(f"⏳ Rate limited, waiting {wait_time}s")
            await asyncio.sleep(wait_time)
        except TelegramForbiddenError:
            logger.debug(f"Bot kicked from chat {chat_id}")
            return False
        except TelegramAPIError as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to send to {chat_id}: {e}")
                return False
            await asyncio.sleep(1)
    return False


async def analyze_chat_topics(chat_id: int, db) -> List[Tuple[str, int]]:
    """Анализ тем общения в чате."""
    if db is None:
        return []
    
    try:
        words = await db.get_chat_top_words(chat_id, 100)
        if not words:
            return []
        
        topic_scores = {topic: 0 for topic in TOPIC_KEYWORDS}
        
        for word, count in words:
            word_lower = word.lower()
            for topic, patterns in TOPIC_KEYWORDS.items():
                if any(re.search(pattern, word_lower, re.IGNORECASE) for pattern in patterns):
                    topic_scores[topic] += count
                    break
        
        sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
        return [(topic, count) for topic, count in sorted_topics if count > 0]
        
    except Exception as e:
        logger.error(f"Error analyzing topics for chat {chat_id}: {e}")
        return []


async def get_chat_stats_for_greeting(chat_id: int, db) -> Dict[str, Any]:
    """Получить статистику конкретного чата."""
    if db is None:
        return {}
    
    result = {
        'total_messages': 0,
        'unique_users': 0,
        'top_balance': [],
        'top_xo': [],
        'top_messages': [],
        'topics': [],
    }
    
    try:
        if hasattr(db, 'get_chat_daily_stats'):
            stats = await db.get_chat_daily_stats(chat_id)
            if stats and isinstance(stats, dict):
                result['total_messages'] = stats.get('total_messages', 0) or 0
                result['unique_users'] = stats.get('unique_users', 0) or 0
        
        if hasattr(db, 'get_chat_top_balance'):
            result['top_balance'] = await db.get_chat_top_balance(chat_id, 3) or []
        
        if hasattr(db, 'get_chat_top_xo'):
            result['top_xo'] = await db.get_chat_top_xo(chat_id, 3) or []
        
        if hasattr(db, 'get_chat_top_messages'):
            result['top_messages'] = await db.get_chat_top_messages(chat_id, 3) or []
        
        result['topics'] = await analyze_chat_topics(chat_id, db)
        
    except Exception as e:
        logger.error(f"Error getting stats for chat {chat_id}: {e}")
    
    return result


# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================

async def track_and_delete_bot_message(bot: Bot, chat_id: int, user_id: int, message_id: int, delay: Optional[int] = None) -> None:
    if bot is None or chat_id is None or message_id is None:
        return
    await _tracker.add_pending(chat_id, message_id)
    await _tracker.add_active_chat(chat_id)


async def delete_bot_message_after(bot: Bot, chat_id: int, message_id: int, delay: int = 30) -> None:
    if bot is None or chat_id is None or message_id is None:
        return
    await _tracker.add_active_chat(chat_id)
    
    if delay and delay > 0:
        async def _delayed_delete():
            await asyncio.sleep(delay)
            if _shutdown_event.is_set():
                return
            try:
                await bot.delete_message(chat_id, message_id)
            except TelegramAPIError:
                pass
        asyncio.create_task(_delayed_delete())
    else:
        await _tracker.add_pending(chat_id, message_id)


async def delete_bot_messages(bot: Bot, chat_id: int) -> int:
    """Удалить все сообщения бота в конкретном чате."""
    if bot is None or chat_id is None:
        return 0
    
    pending = await _tracker.get_and_clear_pending()
    
    deleted = 0
    for cid, msg_id in pending:
        if cid != chat_id:
            continue
        if _shutdown_event.is_set():
            break
        try:
            await bot.delete_message(chat_id, msg_id)
            deleted += 1
            await asyncio.sleep(DELETE_DELAY)
        except TelegramAPIError:
            pass
    
    if deleted > 0:
        logger.info(f"🗑️ Deleted {deleted} messages in chat {chat_id}")
    return deleted


async def send_daily_summary(bot: Bot, chat_id: int) -> bool:
    """
    Отправить сводку дня в КОНКРЕТНЫЙ чат.
    🔥 ВСЕГДА отправляет сообщение, даже если статистика пустая!
    Возвращает True если отправлено успешно.
    """
    if bot is None or chat_id is None:
        return False
    
    from database import db
    
    try:
        stats = await get_chat_stats_for_greeting(chat_id, db)
        
        # 🔥 ВСЕГДА формируем текст
        if not stats or stats.get('total_messages', 0) == 0:
            text = (
                "📊 <b>ИТОГИ ДНЯ В ЧАТЕ</b>\n\n"
                "💬 Сообщений: <b>0</b>\n"
                "👥 Активных участников: <b>0</b>\n\n"
                "😴 <i>Похоже, вчера все отдыхали!</i>"
            )
        else:
            text = f"📊 <b>ИТОГИ ДНЯ В ЧАТЕ</b>\n\n"
            text += f"💬 Сообщений: <b>{stats['total_messages']}</b>\n"
            text += f"👥 Активных участников: <b>{stats['unique_users']}</b>\n\n"
            
            if stats.get('top_messages'):
                text += "<b>💬 ТОП-3 ПО СООБЩЕНИЯМ:</b>\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, u in enumerate(stats['top_messages'][:3]):
                    name = format_top_name(u)
                    msgs = u.get('messages_total', u.get('message_count', 0)) or 0
                    text += f"{medals[i]} {name} — {msgs} сообщ.\n"
                text += "\n"
            
            if stats.get('topics'):
                text += "<b>📝 О ЧЁМ ГОВОРИЛИ:</b>\n"
                for topic, count in stats['topics'][:5]:
                    text += f"• {topic} — {count} упоминаний\n"
                text += "\n"
        
        await _send_with_retry(bot, chat_id, text)
        logger.info(f"📊 Сводка отправлена в чат {chat_id}")
        return True
        
    except TelegramForbiddenError:
        logger.warning(f"🚫 Бот заблокирован в чате {chat_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сводки в чат {chat_id}: {e}")
        return False


async def morning_cleanup_and_greeting(bot: Bot) -> None:
    """Утренняя очистка и отправка приветствия В КАЖДЫЙ ЧАТ ОТДЕЛЬНО."""
    if bot is None:
        return
    
    from database import db
    
    await _tracker.sync_chats_from_db(db)
    
    active_chats = await _tracker.get_active_chats()
    logger.info(f"🌅 Утренняя очистка для {len(active_chats)} чатов")
    
    # 1. Удаление сообщений
    pending = await _tracker.get_and_clear_pending()
    deleted = 0
    for chat_id, message_id in pending:
        if _shutdown_event.is_set():
            break
        try:
            await bot.delete_message(chat_id, message_id)
            deleted += 1
            await asyncio.sleep(DELETE_DELAY)
        except TelegramAPIError:
            pass
    
    logger.info(f"🗑️ Удалено {deleted} сообщений")
    
    # 2. Отправка приветствия в каждый чат
    sent = 0
    failed = 0
    
    for chat_id in active_chats:
        if _shutdown_event.is_set():
            break
        
        try:
            stats = await get_chat_stats_for_greeting(chat_id, db)
            
            greeting = "☀️ <b>ДОБРОЕ УТРО, NEXUS!</b>\n\n"
            
            if stats.get('top_balance'):
                greeting += "<b>🏆 ТОП-3 ПО БАЛАНСУ:</b>\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, u in enumerate(stats['top_balance'][:3]):
                    name = format_top_name(u)
                    greeting += f"{medals[i]} {name} — {format_number(u.get('balance', 0))} NCoin\n"
                greeting += "\n"
            
            if stats.get('top_xo'):
                greeting += "<b>🎮 ТОП-3 ПО КРЕСТИКАМ-НОЛИКАМ:</b>\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, u in enumerate(stats['top_xo'][:3]):
                    name = format_top_name(u)
                    greeting += f"{medals[i]} {name} — {u.get('wins', 0)} побед ({u.get('games_played', 0)} игр)\n"
                greeting += "\n"
            
            if stats.get('top_messages'):
                greeting += "<b>💬 ТОП-3 ПО СООБЩЕНИЯМ:</b>\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, u in enumerate(stats['top_messages'][:3]):
                    name = format_top_name(u)
                    greeting += f"{medals[i]} {name} — {u.get('messages_total', u.get('message_count', 0))} сообщ.\n"
                greeting += "\n"
            
            if stats.get('topics'):
                greeting += "<b>📝 О ЧЁМ ГОВОРИЛИ ВЧЕРА:</b>\n"
                for topic, count in stats['topics'][:3]:
                    greeting += f"• {topic} — {count} упоминаний\n"
                greeting += "\n"
            
            greeting += (
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🎮 <b>Играть:</b> /xo\n"
                "💰 <b>Бонус:</b> /daily\n"
                "📊 <b>Статистика:</b> /stats\n"
                "❤️ <b>Поддержать:</b> /donate\n\n"
                "Удачного дня! 🚀"
            )
            
            success = await _send_with_retry(bot, chat_id, greeting)
            if success:
                sent += 1
            else:
                failed += 1
            
            await asyncio.sleep(SEND_DELAY)
            
        except TelegramForbiddenError:
            failed += 1
        except Exception as e:
            logger.error(f"Ошибка отправки в чат {chat_id}: {e}")
            failed += 1
    
    logger.info(f"🌅 Утренняя очистка: {sent}/{len(active_chats)} приветствий, {failed} ошибок")
    
    # 3. Отчёт админам
    if ADMIN_IDS:
        report = (
            f"✅ <b>УТРЕННЯЯ ОЧИСТКА ЗАВЕРШЕНА!</b>\n\n"
            f"🗑️ Удалено сообщений: {deleted}\n"
            f"📨 Отправлено приветствий: {sent}/{len(active_chats)}\n"
            f"❌ Ошибок: {failed}\n"
            f"⏰ Время: {datetime.now(MSK_OFFSET).strftime('%H:%M:%S')}"
        )
        for admin_id in ADMIN_IDS:
            if admin_id is None:
                continue
            try:
                await _send_with_retry(bot, admin_id, report)
            except Exception:
                pass


async def schedule_morning_cleanup(bot: Bot) -> None:
    """Планировщик ежедневной утренней очистки."""
    if bot is None:
        return
    
    logger.info(f"⏰ Планировщик запущен (очистка в {CLEANUP_HOUR}:00 МСК)")
    
    while not _shutdown_event.is_set():
        try:
            now = datetime.now(MSK_OFFSET)
            next_run = now.replace(hour=CLEANUP_HOUR, minute=0, second=0, microsecond=0)
            
            if now >= next_run:
                next_run += timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"⏰ Следующая очистка через {wait_seconds/3600:.1f} ч")
            
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=wait_seconds)
                break
            except asyncio.TimeoutError:
                pass
            
            if _shutdown_event.is_set():
                break
            
            await morning_cleanup_and_greeting(bot)
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")
            await asyncio.sleep(3600)
    
    logger.info("Планировщик остановлен")


def signal_shutdown() -> None:
    _shutdown_event.set()


async def add_active_chat(chat_id: int) -> None:
    await _tracker.add_active_chat(chat_id)


async def get_active_chats_count() -> int:
    return len(await _tracker.get_active_chats())


async def cleanup_all_chats(bot: Bot) -> None:
    await morning_cleanup_and_greeting(bot)


# ==================== ЗАГЛУШКИ ДЛЯ СОВМЕСТИМОСТИ ====================

async def get_chat_daily_stats(chat_id: int) -> Dict:
    from database import db
    if db:
        return await db.get_chat_daily_stats(chat_id) or {}
    return {'total_messages': 0, 'unique_users': 0}


async def get_chat_top_words(chat_id: int, limit: int = 10) -> List:
    from database import db
    if db:
        return await db.get_chat_top_words(chat_id, limit) or []
    return []


async def get_chat_active_users(chat_id: int, limit: int = 5) -> List:
    from database import db
    if db:
        return await db.get_chat_active_users(chat_id, limit) or []
    return []
