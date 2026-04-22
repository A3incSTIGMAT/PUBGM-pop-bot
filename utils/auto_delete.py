#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: utils/auto_delete.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Утренняя очистка + приветствие с топами + итоги дня
# ИСПРАВЛЕНИЯ: Graceful shutdown, синхронизация с БД, защита от гонок
# ============================================

import asyncio
import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from config import ADMIN_IDS, MORNING_CLEANUP_HOUR

logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

# Московское время (UTC+3)
MSK_OFFSET = timezone(timedelta(hours=3))

# Час запуска очистки (из конфига или по умолчанию 10)
CLEANUP_HOUR = MORNING_CLEANUP_HOUR if hasattr(MORNING_CLEANUP_HOUR, '__module__') else 10

# Задержки для API-запросов (защита от флуда)
DELETE_DELAY = 0.05
SEND_DELAY = 0.1
SUMMARY_DELAY = 0.5

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ (с защитой) ====================

class MessageTracker:
    """
    Потокобезопасный трекер сообщений бота для очистки.
    """
    
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending_cleanup: Set[Tuple[int, int]] = set()
        self._last_messages: Dict[str, Dict[str, Any]] = {}
        self._active_chats: Set[int] = set()
    
    async def add_pending(self, chat_id: int, message_id: int) -> None:
        """Добавить сообщение в очередь на очистку."""
        if chat_id is None or message_id is None:
            return
        
        async with self._lock:
            self._pending_cleanup.add((chat_id, message_id))
            self._active_chats.add(chat_id)
    
    async def add_active_chat(self, chat_id: int) -> None:
        """Добавить чат в список активных."""
        if chat_id is None:
            return
        async with self._lock:
            self._active_chats.add(chat_id)
    
    async def set_last_message(self, chat_id: int, message_id: int, user_id: int) -> None:
        """Сохранить последнее сообщение для чата."""
        if chat_id is None:
            return
        
        key = f"chat_{chat_id}"
        async with self._lock:
            self._last_messages[key] = {
                "message_id": message_id,
                "user_id": user_id if user_id is not None else 0,
                "timestamp": datetime.now(MSK_OFFSET)
            }
            self._active_chats.add(chat_id)
    
    async def get_and_clear_pending(self) -> List[Tuple[int, int]]:
        """Получить и очистить очередь на удаление."""
        async with self._lock:
            pending = list(self._pending_cleanup)
            self._pending_cleanup.clear()
            return pending
    
    async def get_and_clear_last_messages(self) -> List[Tuple[int, int]]:
        """Получить последние сообщения для удаления и очистить."""
        async with self._lock:
            messages = []
            for key, data in self._last_messages.items():
                if data and data.get("message_id"):
                    chat_id = int(key.replace("chat_", ""))
                    messages.append((chat_id, data["message_id"]))
            self._last_messages.clear()
            return messages
    
    async def get_active_chats(self) -> List[int]:
        """Получить список активных чатов."""
        async with self._lock:
            return list(self._active_chats)
    
    async def get_active_chats_count(self) -> int:
        """Получить количество активных чатов."""
        async with self._lock:
            return len(self._active_chats)
    
    async def sync_chats_from_db(self, db) -> None:
        """Синхронизировать активные чаты из БД."""
        try:
            chats = await db.get_all_chats_with_bot()
            async with self._lock:
                for chat_id in chats:
                    if chat_id:
                        self._active_chats.add(chat_id)
            logger.info(f"✅ Synced {len(chats)} chats from database")
        except Exception as e:
            logger.warning(f"Failed to sync chats from DB: {e}")


# Глобальный экземпляр трекера
_tracker = MessageTracker()

# Событие для graceful shutdown
_shutdown_event = asyncio.Event()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def format_top_name(user: Optional[Dict]) -> str:
    """Форматирование имени пользователя с защитой от XSS."""
    if user is None:
        return "Игрок"
    
    username = user.get("username")
    if username:
        return f"@{safe_html_escape(username)}"
    
    first_name = user.get("first_name")
    if first_name:
        escaped = safe_html_escape(first_name)
        return escaped[:20] if len(escaped) > 20 else escaped
    
    return "Игрок"


def format_number(num: Any) -> str:
    """Форматирование числа с разделителями."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def _format_top_section(
    title: str,
    items: List[Dict],
    value_formatter: callable,
    medals: List[str] = ["🥇", "🥈", "🥉", "4.", "5."]
) -> str:
    """
    Форматирует секцию топа.
    
    Args:
        title: Заголовок секции
        items: Список пользователей
        value_formatter: Функция форматирования значения
        medals: Медали для позиций
        
    Returns:
        Отформатированная строка
    """
    if not items:
        return ""
    
    result = f"{title}\n"
    for i, user in enumerate(items[:5]):
        if user is None:
            continue
        name = format_top_name(user)
        value = value_formatter(user)
        result += f"{medals[i]} {name} — {value}\n"
    
    return result + "\n"


# ==================== ПУБЛИЧНЫЕ ФУНКЦИИ ====================

async def track_and_delete_bot_message(
    bot: Bot,
    chat_id: int,
    user_id: int,
    message_id: int,
    delay: Optional[int] = None
) -> None:
    """
    Отслеживает сообщение бота и удаляет предыдущее сообщение в этом чате.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        user_id: ID пользователя
        message_id: ID сообщения
        delay: Задержка перед удалением (игнорируется, удаляется предыдущее)
    """
    if bot is None or chat_id is None or message_id is None:
        return
    
    key = f"chat_{chat_id}"
    
    # Удаляем предыдущее сообщение если есть
    old_data = _tracker._last_messages.get(key)  # Прямой доступ только для чтения
    if old_data and old_data.get("message_id"):
        try:
            await bot.delete_message(chat_id, old_data["message_id"])
            logger.debug(f"Deleted previous message {old_data['message_id']} from chat {chat_id}")
        except TelegramAPIError as e:
            logger.debug(f"Could not delete previous message: {e}")
    
    # Сохраняем новое
    await _tracker.set_last_message(chat_id, message_id, user_id)
    await _tracker.add_pending(chat_id, message_id)


async def delete_bot_message_after(
    bot: Bot,
    chat_id: int,
    message_id: int,
    delay: int = 30
) -> None:
    """
    Удаляет сообщение через указанную задержку.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        message_id: ID сообщения
        delay: Задержка в секундах
    """
    if bot is None or chat_id is None or message_id is None:
        return
    
    await _tracker.add_active_chat(chat_id)
    
    if delay and delay > 0:
        # Запускаем фоновую задачу на удаление
        async def _delayed_delete():
            await asyncio.sleep(delay)
            if _shutdown_event.is_set():
                return
            try:
                await bot.delete_message(chat_id, message_id)
                logger.debug(f"Deleted message {message_id} after {delay}s")
            except TelegramAPIError as e:
                logger.debug(f"Could not delete message {message_id}: {e}")
        
        asyncio.create_task(_delayed_delete())
    else:
        # Добавляем в очередь на утреннюю очистку
        await _tracker.add_pending(chat_id, message_id)


async def morning_cleanup_and_greeting(bot: Bot) -> None:
    """
    Утренняя очистка сообщений и отправка приветствия с топами.
    
    Args:
        bot: Экземпляр бота
    """
    if bot is None:
        logger.error("Bot is None in morning_cleanup")
        return
    
    # Импорт БД здесь для избежания циклических импортов
    from database import db
    
    # Синхронизируем чаты с БД
    if db:
        await _tracker.sync_chats_from_db(db)
    
    active_chats = await _tracker.get_active_chats()
    active_count = len(active_chats)
    
    logger.info(f"🌅 Starting morning cleanup for {active_count} chats")
    
    # 1. Удаляем все служебные сообщения
    pending = await _tracker.get_and_clear_pending()
    last_messages = await _tracker.get_and_clear_last_messages()
    
    all_to_delete = pending + last_messages
    
    deleted = 0
    for chat_id, message_id in all_to_delete:
        if _shutdown_event.is_set():
            logger.info("Cleanup interrupted by shutdown")
            break
            
        try:
            await bot.delete_message(chat_id, message_id)
            deleted += 1
            await asyncio.sleep(DELETE_DELAY)
        except TelegramAPIError as e:
            logger.debug(f"Could not delete message {message_id} in chat {chat_id}: {e}")
    
    logger.info(f"🗑️ Deleted {deleted} service messages")
    
    # 2. Получаем топы из БД
    top_balance = []
    top_xo = []
    top_messages = []
    top_donors = []
    
    if db:
        try:
            top_balance = await db.get_top_balance(5) or []
            top_xo = await db.get_top_xo(5) or []
            top_messages = await db.get_top_messages(5) or []
            top_donors = await db.get_top_donors(5) or []
        except Exception as e:
            logger.error(f"Failed to get tops from DB: {e}")
    
    # 3. Формируем приветствие
    greeting = (
        "☀️ <b>ДОБРОЕ УТРО, NEXUS!</b>\n\n"
        "🔥 С возвращением в игру! Вот вчерашние топы:\n\n"
    )
    
    # Форматируем секции топов
    greeting += _format_top_section(
        "🏆 <b>ТОП-5 ПО БАЛАНСУ:</b>",
        top_balance,
        lambda u: f"{format_number(u.get('balance', 0))} NCoin"
    )
    
    greeting += _format_top_section(
        "🎮 <b>ТОП-5 ПО КРЕСТИКАМ-НОЛИКАМ:</b>",
        top_xo,
        lambda u: f"{format_number(u.get('wins', 0))} побед ({format_number(u.get('games_played', 0))} игр)"
    )
    
    greeting += _format_top_section(
        "💬 <b>ТОП-5 ПО СООБЩЕНИЯМ:</b>",
        top_messages,
        lambda u: f"{format_number(u.get('messages_total', 0))} сообщений"
    )
    
    greeting += _format_top_section(
        "💎 <b>ТОП-5 ДОНАТЕРОВ:</b>",
        top_donors,
        lambda u: f"{format_number(u.get('total_donated', 0))} ₽"
    )
    
    greeting += (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 Играйте в /xo\n"
        "💰 Не забудьте /daily\n"
        "📊 Статистика: /stats\n\n"
        "Удачного дня! 🚀"
    )
    
    # 4. Отправляем приветствие во все чаты
    sent = 0
    failed = 0
    
    for chat_id in active_chats:
        if _shutdown_event.is_set():
            logger.info("Greeting send interrupted by shutdown")
            break
            
        try:
            msg = await bot.send_message(chat_id, greeting, parse_mode="HTML")
            if msg and msg.message_id:
                await _tracker.add_pending(chat_id, msg.message_id)
                sent += 1
            await asyncio.sleep(SEND_DELAY)
        except TelegramForbiddenError:
            logger.debug(f"Bot was kicked from chat {chat_id}")
            failed += 1
        except TelegramAPIError as e:
            logger.debug(f"Could not send greeting to chat {chat_id}: {e}")
            failed += 1
    
    # 5. Отправляем сводку дня (если есть в БД)
    yesterday = (datetime.now(MSK_OFFSET) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if db:
        for chat_id in active_chats:
            if _shutdown_event.is_set():
                break
                
            try:
                # Используем метод из БД если есть
                if hasattr(db, 'get_chat_daily_summary'):
                    summary = await db.get_chat_daily_summary(chat_id, yesterday)
                    if summary:
                        msg = await bot.send_message(chat_id, summary, parse_mode="HTML")
                        if msg and msg.message_id:
                            await _tracker.add_pending(chat_id, msg.message_id)
                        await asyncio.sleep(SUMMARY_DELAY)
            except TelegramForbiddenError:
                pass
            except Exception as e:
                logger.debug(f"Could not send summary to chat {chat_id}: {e}")
    
    # 6. Отправляем отчёт админам
    await _send_admin_report(bot, deleted, sent, failed, active_count)
    
    logger.info(f"🌅 Morning cleanup completed: {sent}/{active_count} greetings sent")


async def _send_admin_report(
    bot: Bot,
    deleted: int,
    sent: int,
    failed: int,
    total_chats: int
) -> None:
    """Отправляет отчёт об очистке администраторам."""
    if not ADMIN_IDS:
        return
    
    report = (
        f"✅ <b>УТРЕННЯЯ ОЧИСТКА ЗАВЕРШЕНА!</b>\n\n"
        f"🗑️ Удалено сообщений: {deleted}\n"
        f"📨 Отправлено приветствий: {sent}/{total_chats} чатов\n"
        f"❌ Ошибок отправки: {failed}\n"
        f"⏰ Время: {datetime.now(MSK_OFFSET).strftime('%H:%M:%S')}"
    )
    
    for admin_id in ADMIN_IDS:
        if admin_id is None:
            continue
        try:
            await bot.send_message(admin_id, report, parse_mode="HTML")
        except Exception as e:
            logger.debug(f"Could not send report to admin {admin_id}: {e}")


async def schedule_morning_cleanup(bot: Bot) -> None:
    """
    Планировщик ежедневной утренней очистки.
    
    Args:
        bot: Экземпляр бота
    """
    if bot is None:
        logger.error("Bot is None in schedule_morning_cleanup")
        return
    
    logger.info(f"⏰ Morning cleanup scheduler started (target hour: {CLEANUP_HOUR}:00 MSK)")
    
    while not _shutdown_event.is_set():
        try:
            now = datetime.now(MSK_OFFSET)
            next_run = now.replace(hour=CLEANUP_HOUR, minute=0, second=0, microsecond=0)
            
            if now >= next_run:
                next_run += timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            
            hours = wait_seconds / 3600
            logger.info(f"⏰ Next morning cleanup in {hours:.1f} hours (at {CLEANUP_HOUR}:00 MSK)")
            
            # Ждем с проверкой shutdown
            try:
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=wait_seconds
                )
                logger.info("Scheduler interrupted by shutdown")
                break
            except asyncio.TimeoutError:
                pass  # Нормальное завершение таймаута
            
            if _shutdown_event.is_set():
                break
            
            # Запускаем очистку
            try:
                await morning_cleanup_and_greeting(bot)
            except Exception as e:
                logger.error(f"Morning cleanup failed: {e}", exc_info=True)
                
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            await asyncio.sleep(3600)
    
    logger.info("Morning cleanup scheduler stopped")


def signal_shutdown() -> None:
    """Сигнализирует о необходимости завершения."""
    _shutdown_event.set()


async def add_active_chat(chat_id: int) -> None:
    """Добавить чат в список активных."""
    await _tracker.add_active_chat(chat_id)


async def get_active_chats_count() -> int:
    """Получить количество активных чатов."""
    return await _tracker.get_active_chats_count()


# ==================== ЭКСПОРТ ДЛЯ СОВМЕСТИМОСТИ ====================

# Для обратной совместимости с bot.py
_active_chats = set()

def add_active_chat_sync(chat_id: int) -> None:
    """Синхронная версия для обратной совместимости."""
    if chat_id is not None:
        _active_chats.add(chat_id)
        asyncio.create_task(add_active_chat(chat_id))


def get_active_chats_count_sync() -> int:
    """Синхронная версия для обратной совместимости."""
    return len(_active_chats)


# ==================== ТЕСТЫ ====================

if __name__ == "__main__":
    import unittest
    from unittest.mock import AsyncMock, MagicMock
    
    class TestAutoDelete(unittest.IsolatedAsyncioTestCase):
        
        def test_format_top_name_with_username(self):
            user = {"username": "test_user", "first_name": "Test"}
            result = format_top_name(user)
            self.assertEqual(result, "@test_user")
        
        def test_format_top_name_without_username(self):
            user = {"first_name": "Test User"}
            result = format_top_name(user)
            self.assertEqual(result, "Test User")
        
        def test_format_top_name_none(self):
            result = format_top_name(None)
            self.assertEqual(result, "Игрок")
        
        def test_format_top_name_xss(self):
            user = {"username": "<script>alert('xss')</script>"}
            result = format_top_name(user)
            self.assertNotIn("<script>", result)
            self.assertIn("&lt;script&gt;", result)
        
        def test_format_number(self):
            self.assertEqual(format_number(1000), "1 000")
            self.assertEqual(format_number(None), "0")
            self.assertEqual(format_number("not a number"), "0")
        
        async def test_tracker_add_pending(self):
            await _tracker.add_pending(123, 456)
            pending = await _tracker.get_and_clear_pending()
            self.assertIn((123, 456), pending)
        
        async def test_tracker_get_active_chats(self):
            await _tracker.add_active_chat(123)
            await _tracker.add_active_chat(456)
            chats = await _tracker.get_active_chats()
            self.assertEqual(len(chats), 2)
            self.assertIn(123, chats)
            self.assertIn(456, chats)
    
    unittest.main()
