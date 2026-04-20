# ============================================
# ФАЙЛ: utils/auto_delete.py
# ОПИСАНИЕ: Утренняя очистка + приветствие с топами + итоги дня
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# ============================================

import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
import pytz

logger = logging.getLogger(__name__)

_last_bot_messages = {}
_pending_cleanup = set()
_active_chats = set()


async def track_and_delete_bot_message(bot: Bot, chat_id: int, user_id: int, message_id: int, delay: int = None):
    if bot is None or chat_id is None or message_id is None:
        return
        
    key = f"chat_{chat_id}"
    
    if chat_id:
        _active_chats.add(chat_id)
    
    if key in _last_bot_messages:
        old_msg = _last_bot_messages.get(key)
        if old_msg and old_msg.get("message_id"):
            try:
                await bot.delete_message(chat_id, old_msg["message_id"])
                _pending_cleanup.discard((chat_id, old_msg["message_id"]))
            except Exception as e:
                logger.debug(f"Could not delete previous message: {e}")
    
    _last_bot_messages[key] = {
        "message_id": message_id,
        "user_id": user_id if user_id is not None else 0,
        "timestamp": datetime.now()
    }
    
    _pending_cleanup.add((chat_id, message_id))


async def delete_bot_message_after(bot: Bot, chat_id: int, message_id: int, delay: int = 30):
    if bot is None or chat_id is None or message_id is None:
        return
        
    if chat_id:
        _active_chats.add(chat_id)
    _pending_cleanup.add((chat_id, message_id))


def format_top_name(user: dict) -> str:
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
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


async def morning_cleanup_and_greeting(bot: Bot):
    from database import db
    
    if bot is None:
        logger.error("Bot is None in morning_cleanup")
        return
    
    active_count = len(_active_chats) if _active_chats else 0
    logger.info(f"🌅 Starting morning cleanup for {active_count} chats")
    
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
    
    # 2. Получаем топы
    top_balance = await db.get_top_balance(5) if db else []
    top_xo = await db.get_top_xo(5) if db else []
    top_messages = await db.get_top_messages(5) if db else []
    top_donors = await db.get_top_donors(5) if db else []
    
    # 3. Формируем приветствие с топами
    greeting = (
        "☀️ <b>ДОБРОЕ УТРО, NEXUS!</b>\n\n"
        "🔥 С возвращением в игру! Вот вчерашние топы:\n\n"
    )
    
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
    
    # 4. Отправляем приветствие во все чаты
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
    
    # 5. Генерируем и отправляем итоги дня
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for chat_id in list(_active_chats):
        if chat_id is None:
            continue
        try:
            if db:
                summary = await db.generate_and_save_summary(chat_id, yesterday)
                if summary:
                    msg = await bot.send_message(chat_id, summary, parse_mode="HTML")
                    if msg and msg.message_id:
                        _pending_cleanup.add((chat_id, msg.message_id))
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"Could not send summary to chat {chat_id}: {e}")
    
    # 6. Отчёт админам
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
    
    logger.info(f"🌅 Morning cleanup completed: {sent}/{active_count} greetings sent")


async def schedule_morning_cleanup(bot: Bot):
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
    if chat_id is not None:
        _active_chats.add(chat_id)


def get_active_chats_count() -> int:
    return len(_active_chats) if _active_chats else 0
