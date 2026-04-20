"""
Умное автоудаление сообщений бота + Утреннее приветствие с топами
ПОЛНОСТЬЮ ЗАЩИЩЕНО ОТ NULL
"""

import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
import pytz

logger = logging.getLogger(__name__)

# Хранилище последних сообщений бота по чатам
_last_bot_messages = {}

# Список служебных сообщений для утренней очистки
_pending_cleanup = set()

# Список чатов для утреннего приветствия
_active_chats = set()


async def track_and_delete_bot_message(bot: Bot, chat_id: int, user_id: int, message_id: int, delay: int = None):
    """
    Отслеживает сообщение бота и удаляет предыдущее в этом чате.
    """
    if bot is None or chat_id is None or message_id is None:
        return
        
    key = f"chat_{chat_id}"
    
    # Добавляем чат в активные
    if chat_id:
        _active_chats.add(chat_id)
    
    # Удаляем предыдущее сообщение
    if key in _last_bot_messages:
        old_msg = _last_bot_messages.get(key)
        if old_msg and old_msg.get("message_id"):
            try:
                await bot.delete_message(chat_id, old_msg["message_id"])
                _pending_cleanup.discard((chat_id, old_msg["message_id"]))
            except Exception as e:
                logger.debug(f"Could not delete previous message: {e}")
    
    # Сохраняем новое
    _last_bot_messages[key] = {
        "message_id": message_id,
        "user_id": user_id if user_id is not None else 0,
        "timestamp": datetime.now()
    }
    
    _pending_cleanup.add((chat_id, message_id))


async def delete_bot_message_after(bot: Bot, chat_id: int, message_id: int, delay: int = 30):
    """Устаревший метод для совместимости"""
    if bot is None or chat_id is None or message_id is None:
        return
        
    if chat_id:
        _active_chats.add(chat_id)
    _pending_cleanup.add((chat_id, message_id))


async def clear_chat_history(bot: Bot, chat_id: int):
    """Очищает историю сообщений бота в чате"""
    if chat_id is None:
        return
        
    key = f"chat_{chat_id}"
    if key in _last_bot_messages:
        del _last_bot_messages[key]
    
    to_remove = {(c, m) for c, m in _pending_cleanup if c == chat_id}
    _pending_cleanup.difference_update(to_remove)


def format_top_name(user: dict) -> str:
    """Безопасное форматирование имени пользователя"""
    if user is None:
        return "Игрок"
    
    username = user.get("username")
    if username:
        return f"@{username}"
    
    first_name = user.get("first_name")
    if first_name:
        return first_name[:20] if len(first_name) > 20 else first_name
    
    return "Игрок"


def format_number(num: any) -> str:
    """Безопасное форматирование числа"""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


async def morning_cleanup_and_greeting(bot: Bot):
    """
    Утренняя очистка + приветствие с топами.
    Вызывается в 10:00 по МСК.
    """
    from database import db
    
    if bot is None:
        logger.error("Bot is None in morning_cleanup")
        return
    
    active_count = len(_active_chats) if _active_chats else 0
    logger.info(f"🌅 Starting morning cleanup and greeting for {active_count} chats")
    
    # 1. Удаляем все служебные сообщения
    deleted = 0
    for chat_id, message_id in list(_pending_cleanup):
        if chat_id is None or message_id is None:
            continue
        try:
            await bot.delete_message(chat_id, message_id)
            deleted += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.debug(f"Could not delete message {message_id}: {e}")
    
    _pending_cleanup.clear()
    _last_bot_messages.clear()
    
    logger.info(f"🗑️ Deleted {deleted} service messages")
    
    # 2. Получаем топы (с защитой от NULL)
    top_balance = await db.get_top_balance(5) if db else []
    top_xo = await db.get_top_xo(5) if db else []
    top_messages = await db.get_top_messages(5) if db else []
    top_donors = await db.get_top_donors(5) if db else []
    
    # 3. Формируем приветствие
    greeting = (
        "☀️ <b>ДОБРОЕ УТРО, NEXUS!</b>\n\n"
        "🔥 С возвращением в игру! Вот вчерашние топы:\n\n"
    )
    
    # Топ по балансу
    if top_balance and len(top_balance) > 0:
        greeting += "🏆 <b>ТОП-5 ПО БАЛАНСУ:</b>\n"
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, u in enumerate(top_balance[:5]):
            if u is None:
                continue
            name = format_top_name(u)
            balance = u.get("balance", 0) if u else 0
            greeting += f"{medals[i]} {name} — {format_number(balance)} NCoin\n"
        greeting += "\n"
    
    # Топ по крестикам-ноликам
    if top_xo and len(top_xo) > 0:
        greeting += "🎮 <b>ТОП-5 ПО КРЕСТИКАМ-НОЛИКАМ:</b>\n"
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, u in enumerate(top_xo[:5]):
            if u is None:
                continue
            name = format_top_name(u)
            wins = u.get("wins", 0) if u else 0
            games = u.get("games_played", 0) if u else 0
            greeting += f"{medals[i]} {name} — {format_number(wins)} побед ({format_number(games)} игр)\n"
        greeting += "\n"
    
    # Топ по сообщениям
    if top_messages and len(top_messages) > 0:
        greeting += "💬 <b>ТОП-5 ПО СООБЩЕНИЯМ:</b>\n"
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, u in enumerate(top_messages[:5]):
            if u is None:
                continue
            name = format_top_name(u)
            msgs = u.get("messages_total", 0) if u else 0
            greeting += f"{medals[i]} {name} — {format_number(msgs)} сообщений\n"
        greeting += "\n"
    
    # Топ донатеров
    if top_donors and len(top_donors) > 0:
        greeting += "💎 <b>ТОП-5 ДОНАТЕРОВ:</b>\n"
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, u in enumerate(top_donors[:5]):
            if u is None:
                continue
            name = format_top_name(u)
            donated = u.get("total_donated", 0) if u else 0
            greeting += f"{medals[i]} {name} — {format_number(donated)} ₽\n"
        greeting += "\n"
    
    greeting += (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 Играйте в /xo\n"
        "💰 Не забудьте /daily\n"
        "📊 Статистика: /stats\n\n"
        "Удачного дня! 🚀"
    )
    
    # 4. Отправляем во все активные чаты
    sent = 0
    failed = 0
    
    if _active_chats:
        for chat_id in list(_active_chats):
            if chat_id is None:
                continue
            try:
                msg = await bot.send_message(chat_id, greeting, parse_mode="HTML")
                if msg and msg.message_id:
                    _pending_cleanup.add((chat_id, msg.message_id))
                    sent += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                failed += 1
                logger.debug(f"Could not send greeting to chat {chat_id}: {e}")
    
    # 5. Отправляем админам отчёт
    try:
        from config import ADMIN_IDS
        if ADMIN_IDS:
            report = (
                f"✅ <b>УТРЕННЯЯ ОЧИСТКА ЗАВЕРШЕНА!</b>\n\n"
                f"🗑️ Удалено сообщений: {deleted}\n"
                f"📨 Отправлено приветствий: {sent}/{active_count} чатов\n"
                f"❌ Ошибок отправки: {failed}\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
            )
            for admin_id in ADMIN_IDS:
                if admin_id is None:
                    continue
                try:
                    await bot.send_message(admin_id, report, parse_mode="HTML")
                except:
                    pass
    except Exception as e:
        logger.debug(f"Could not send admin report: {e}")
    
    logger.info(f"🌅 Morning greeting sent to {sent}/{active_count} chats ({failed} failed)")


async def schedule_morning_cleanup(bot: Bot):
    """
    Планировщик утренней очистки.
    Запускается при старте бота и ждёт 10:00 МСК.
    """
    if bot is None:
        logger.error("Bot is None in schedule_morning_cleanup")
        return
        
    try:
        msk_tz = pytz.timezone("Europe/Moscow")
    except:
        msk_tz = None
    
    while True:
        try:
            if msk_tz:
                now = datetime.now(msk_tz)
            else:
                now = datetime.now()
            
            next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
            
            if now >= next_run:
                next_run += timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            if wait_seconds < 0:
                wait_seconds = 3600
            
            hours = wait_seconds / 3600
            logger.info(f"⏰ Next morning cleanup in {hours:.1f} hours (at 10:00 MSK)")
            
            await asyncio.sleep(wait_seconds)
            
            try:
                await morning_cleanup_and_greeting(bot)
            except Exception as e:
                logger.error(f"Morning cleanup failed: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(3600)


def add_active_chat(chat_id: int):
    """Добавляет чат в список активных"""
    if chat_id is not None:
        _active_chats.add(chat_id)


def get_active_chats_count() -> int:
    """Возвращает количество активных чатов"""
    return len(_active_chats) if _active_chats else 0


def get_pending_count() -> int:
    """Возвращает количество сообщений в очереди на удаление"""
    return len(_pending_cleanup) if _pending_cleanup else 0
