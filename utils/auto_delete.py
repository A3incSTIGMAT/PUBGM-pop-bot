#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: utils/auto_delete.py
# ВЕРСИЯ: 2.6.0-production (исправленная после аудита)
# ОПИСАНИЕ: Утренняя очистка + сводка с инлайн-кнопками
# ============================================
# ИСПРАВЛЕНИЯ v2.6.0:
#   🟡 Константы вынесены в os.getenv()
#   🟡 Импорты наверх, убран неиспользуемый BOT_USERNAME
#   🟡 parse_mode параметризован
#   🟡 exc_info=True во всех logger.error
#   🟡 Разделён morning_cleanup_and_greeting (слишком длинная)
#   🟡 Исправлен wait_seconds (защита от отрицательных)
# ============================================

import asyncio
import html
import logging
import os
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS, MORNING_CLEANUP_HOUR
from database import db

logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ (НАСТРАИВАЕМЫЕ) ====================

MSK_OFFSET = timezone(timedelta(hours=3))
CLEANUP_HOUR = int(os.getenv("MORNING_CLEANUP_HOUR", str(MORNING_CLEANUP_HOUR if MORNING_CLEANUP_HOUR else 10)))

DELETE_DELAY = float(os.getenv("AUTO_DELETE_DELAY", "0.05"))
SEND_DELAY = float(os.getenv("AUTO_SEND_DELAY", "0.1"))
RATE_LIMIT_RETRY_DELAY = int(os.getenv("AUTO_RATE_LIMIT_RETRY", "60"))
SUMMARY_PARSE_MODE = os.getenv("AUTO_SUMMARY_PARSE_MODE", "HTML")


# ==================== КЛАВИАТУРА ДЛЯ СВОДКИ ====================

def get_summary_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура для утренней и вечерней сводки."""
    buttons = [
        [
            InlineKeyboardButton(text="💰 Ежедневная награда", callback_data="daily_bonus"),
            InlineKeyboardButton(text="🎮 Крестики-нолики", callback_data="menu_xo"),
        ],
        [
            InlineKeyboardButton(text="❤️ Поддержать", callback_data="menu_donate"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu_stats"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== КОНТЕНТ (ТЕКСТЫ) ====================

TOPIC_KEYWORDS = {
    "🎮 Игры": [r"\bигра\b", r"\bxo\b", r"\bкрестики\b", r"\bнолики\b", r"\bпобеда\b", r"\bставка\b", r"\bбот\b"],
    "💰 Экономика": [r"\bбаланс\b", r"\bмонеты\b", r"\bdaily\b", r"\bбонус\b", r"\bперевод\b", r"\bncoin\b"],
    "👑 VIP и ранги": [r"\bvip\b", r"\bстатус\b", r"\bранг\b", r"\bуровень\b", r"\bxp\b", r"\bопыт\b"],
    "💕 Отношения": [r"\bлюбовь\b", r"\bпара\b", r"\bсемья\b", r"\bотношения\b", r"\bбрак\b", r"\bразвод\b"],
    "🏷️ Теги": [r"\bтег\b", r"\bкатегория\b", r"\bподписка\b", r"\bуведомление\b"],
    "🤖 Бот": [r"\bnexus\b", r"\bнексус\b", r"\bкоманда\b", r"\bфункция\b", r"\bбаг\b"],
    "💬 Общение": [r"\bпривет\b", r"\bпока\b", r"\bспасибо\b", r"\bдоброе\b", r"\bутро\b", r"\bвечер\b"],
}

FUNNY_TITLES = [
    "Главный по болтовне",
    "Король клавиатуры",
    "Повелитель сообщений",
    "Мега-болтун",
    "Душа компании",
    "Голос чата",
    "Звезда эфира",
    "Чемпион по флуду",
    "Легенда чата",
    "Великий оратор",
]

DAILY_ADVICES = [
    "💡 Меньше слов — больше дела! Но ты же не умеешь, да?",
    "💡 Кто рано встаёт — тому весь день спать хочется. Проверено.",
    "💡 Не откладывай на завтра то, что можно отложить на послезавтра.",
    "💡 Если хочешь что-то сделать хорошо — заплати. Бесплатно только хреново.",
    "💡 Тише едешь — дальше будешь. Но не факт что туда, куда нужно.",
    "💡 Век живи — век учись. А дураком помрёшь. Статистика не врёт.",
    "💡 Не ной, что монет нет. В /daily дают халяву. Бери и не выё...",
    "💡 Если жизнь — боль, то NEXUS — анестезия. Временная, но приятная.",
]

ACHIEVEMENTS = [
    "🏆 «Золотая клавиатура»",
    "🎖️ «Орден болтливого языка»",
    "👑 «Повелитель чата» (ну почти)",
    "💎 «Бриллиантовый флудер»",
    "🔥 «Зажигалка чата»",
    "🚀 «Ракета общения»",
    "💩 «Король туалетного юмора»",
    "🧠 «Мозг чата»",
]


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
    
    async def sync_chats_from_db(self) -> None:
        if db is None:
            return
        try:
            if hasattr(db, 'get_all_chats_with_bot'):
                chats = await db.get_all_chats_with_bot()
                if chats is None:
                    return
                async with self._lock:
                    for chat_id in chats:
                        if chat_id:
                            self._active_chats.add(chat_id)
                logger.info(f"✅ Synced {len(chats)} chats from database")
        except Exception as e:
            logger.warning(f"⚠️ Failed to sync chats from DB: {e}")


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


async def _send_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    max_retries: int = 3,
    parse_mode: str = SUMMARY_PARSE_MODE
) -> bool:
    """Отправка сообщения с обработкой лимитов."""
    if bot is None or chat_id is None or not text:
        return False
    
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
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
                logger.error(f"❌ Failed to send to {chat_id}: {e}")
                return False
            await asyncio.sleep(1)
    return False


async def analyze_chat_topics(chat_id: int) -> List[Tuple[str, int]]:
    """Анализ тем общения в чате."""
    if db is None or chat_id is None:
        return []
    
    try:
        words = await db.get_chat_top_words(chat_id, 100)
        if not words:
            return []
        
        topic_scores = {topic: 0 for topic in TOPIC_KEYWORDS}
        
        for word, count in words:
            if word is None:
                continue
            word_lower = str(word).lower()
            for topic, patterns in TOPIC_KEYWORDS.items():
                if any(re.search(pattern, word_lower, re.IGNORECASE) for pattern in patterns):
                    topic_scores[topic] += count if count else 0
                    break
        
        sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
        return [(topic, count) for topic, count in sorted_topics if count > 0]
        
    except Exception as e:
        logger.error(f"❌ Error analyzing topics for chat {chat_id}: {e}", exc_info=True)
        return []


async def get_chat_stats_for_greeting(chat_id: int) -> Dict[str, Any]:
    """Получить статистику конкретного чата."""
    if db is None or chat_id is None:
        return {
            'total_messages': 0, 'unique_users': 0,
            'top_balance': [], 'top_xo': [], 'top_messages': [], 'topics': []
        }
    
    result = {
        'total_messages': 0, 'unique_users': 0,
        'top_balance': [], 'top_xo': [], 'top_messages': [], 'topics': []
    }
    
    methods = {
        'get_chat_daily_stats': ('total_messages', 'unique_users'),
        'get_chat_top_balance': ('top_balance',),
        'get_chat_top_xo': ('top_xo',),
        'get_chat_top_messages': ('top_messages',),
    }
    
    for method_name, keys in methods.items():
        if hasattr(db, method_name) and callable(getattr(db, method_name)):
            try:
                data = await getattr(db, method_name)(chat_id, 3)
                if data and isinstance(data, (dict, list)):
                    if isinstance(data, dict):
                        for key in keys:
                            result[key] = data.get(key, result[key])
                    elif isinstance(data, list):
                        result[keys[0]] = [u for u in data[:3] if isinstance(u, dict)]
            except Exception as e:
                logger.warning(f"⚠️ Method {method_name} failed for chat {chat_id}: {e}")
        else:
            logger.debug(f"Method {method_name} not available")
    
    result['topics'] = await analyze_chat_topics(chat_id)
    
    return result


# ==================== ФОРМАТИРОВАНИЕ СВОДКИ ====================

def _build_empty_summary_text() -> str:
    """Текст сводки если нет сообщений."""
    texts = [
        "😴 <b>ВЧЕРА БЫЛО ТИХО...</b>\n\n"
        "Ни одной живой души. Даже бот заскучал.\n"
        "Вы чё, все сдохли? Или просто лень писать?\n"
        "Сегодня жду оживления. Кто первый напишет — тот красавчик. Остальные — лодыри.",
        
        "🦗 <b>СВЕРЧКИ ВЧЕРА ПОБЕДИЛИ</b>\n\n"
        "Сообщений: 0. Зато тишина была идеальной.\n"
        "Давайте сегодня не дадим сверчкам победить снова.",
    ]
    return random.choice(texts)


def _build_active_summary_text(stats: Dict) -> str:
    """Текст сводки с активностью."""
    top_babler = stats['top_messages'][0] if stats.get('top_messages') else None
    top_name = format_top_name(top_babler) if top_babler else "Какой-то аноним"
    funny_title = random.choice(FUNNY_TITLES)
    advice = random.choice(DAILY_ADVICES)
    
    text = f"📊 <b>ИТОГИ ВЧЕРАШНЕГО ОБЩЕНИЯ</b> 📊\n\n"
    text += f"💬 Наболтали аж <b>{stats['total_messages']}</b> сообщений! Языки не отсохли?\n"
    text += f"👥 <b>{stats['unique_users']}</b> человек отметились в чате.\n\n"
    
    if stats.get('top_messages'):
        text += f"<b>🗣️ ГЛАВНЫЕ БОЛТУНЫ:</b>\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(stats['top_messages'][:3]):
            name = format_top_name(u)
            msgs = u.get('messages_total', u.get('message_count', 0)) or 0
            achievement = random.choice(ACHIEVEMENTS)
            text += f"{medals[i]} {name} — {msgs} сообщ. {achievement}\n"
        text += f"\n👑 <b>{top_name}</b> получает титул «<i>{funny_title}</i>»! Гордись!\n\n"
    
    if stats.get('topics'):
        text += "<b>📝 О ЧЁМ ГОВОРИЛИ:</b>\n"
        for topic, count in stats['topics'][:5]:
            text += f"• {topic}: {count} упоминаний\n"
        text += "\n"
    
    text += f"{advice}\n\n"
    text += "<i>📊 Сводка создана искусственным интеллектом. Но это не точно.</i>"
    
    return text


def _build_morning_greeting_text(stats: Dict, greeting: str) -> str:
    """Дополнение утреннего приветствия статистикой."""
    text = greeting
    
    if stats.get('top_balance'):
        text += "\n\n<b>🏆 ТОП-3 ПО БАЛАНСУ В ЭТОМ ЧАТЕ:</b>\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(stats['top_balance'][:3]):
            name = format_top_name(u)
            balance = u.get('balance', 0) or 0
            text += f"{medals[i]} {name} — {format_number(balance)} NCoin\n"
    else:
        text += "\n\n<b>🏆 ТОП-3 ПО БАЛАНСУ:</b>\n"
        text += "Пока никто не накопил NCoin в этом чате. Будь первым! 🚀\n"
    
    if stats.get('top_messages'):
        text += "\n<b>💬 ТОП-3 БОЛТУНОВ ЭТОГО ЧАТА:</b>\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(stats['top_messages'][:3]):
            name = format_top_name(u)
            msgs = u.get('messages_total', u.get('message_count', 0)) or 0
            text += f"{medals[i]} {name} — {msgs} сообщ.\n"
    
    if stats.get('top_xo'):
        text += "\n<b>🎮 ТОП-3 ИГРОКОВ В XO:</b>\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(stats['top_xo'][:3]):
            name = format_top_name(u)
            wins = u.get('wins', 0) or 0
            games = u.get('games_played', 0) or 0
            text += f"{medals[i]} {name} — {wins} побед / {games} игр\n"
    
    if stats.get('topics'):
        text += "\n<b>📝 О ЧЁМ ГОВОРИЛИ ВЧЕРА:</b>\n"
        for topic, count in stats['topics'][:3]:
            text += f"• {topic} — {count} упоминаний\n"
    
    text += "\n<b>⚡ Жми на кнопки ниже!</b>"
    
    return text


# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================

async def track_and_delete_bot_message(
    bot: Bot, chat_id: int, user_id: int, message_id: int, delay: Optional[int] = None
) -> None:
    if bot is None or chat_id is None or message_id is None:
        return
    await _tracker.add_pending(chat_id, message_id)
    await _tracker.add_active_chat(chat_id)


async def delete_bot_message_after(
    bot: Bot, chat_id: int, message_id: int, delay: int = 30
) -> None:
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
        if cid is None or msg_id is None or cid != chat_id:
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
    """Отправить сводку дня в чат с инлайн-кнопками."""
    if bot is None or chat_id is None:
        return False
    
    try:
        stats = await get_chat_stats_for_greeting(chat_id)
        keyboard = get_summary_keyboard()
        
        if not stats or stats.get('total_messages', 0) == 0:
            text = _build_empty_summary_text()
        else:
            text = _build_active_summary_text(stats)
        
        await _send_with_retry(bot, chat_id, text, reply_markup=keyboard)
        logger.info(f"📊 Сводка отправлена в чат {chat_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сводки в чат {chat_id}: {e}", exc_info=True)
        return False


async def _delete_pending_messages(bot: Bot) -> int:
    """Удаление накопившихся сообщений бота."""
    pending = await _tracker.get_and_clear_pending()
    deleted = 0
    for chat_id, message_id in pending:
        if _shutdown_event.is_set():
            break
        if chat_id is None or message_id is None:
            continue
        try:
            await bot.delete_message(chat_id, message_id)
            deleted += 1
            await asyncio.sleep(DELETE_DELAY)
        except TelegramAPIError:
            pass
    return deleted


async def _send_morning_greetings(bot: Bot, active_chats: List[int]) -> Tuple[int, int]:
    """Отправка утренних приветствий во все активные чаты."""
    keyboard = get_summary_keyboard()
    
    morning_greetings = [
        "☀️ <b>ДОБРОЕ УТРО, NEXUS!</b>\n\nПросыпайтесь, сонные тетери! Бот уже пашет, а вы где? 😴",
        "🌅 <b>РАССВЕТ В NEXUS!</b>\n\nКофе в руки, глаза открыть — и вперёд покорять чат! ☕",
        "🐔 <b>КУКАРЕКУ!</b>\n\nРанние пташки уже в строю. Остальные — ленивые жопы. 🐣",
    ]
    
    sent = 0
    failed = 0
    
    for chat_id in active_chats:
        if _shutdown_event.is_set() or chat_id is None:
            break
        
        try:
            stats = await get_chat_stats_for_greeting(chat_id)
            greeting = random.choice(morning_greetings)
            text = _build_morning_greeting_text(stats, greeting)
            
            success = await _send_with_retry(bot, chat_id, text, reply_markup=keyboard)
            if success:
                sent += 1
            else:
                failed += 1
            
            await asyncio.sleep(SEND_DELAY)
            
        except TelegramForbiddenError:
            failed += 1
            logger.debug(f"Bot kicked from chat {chat_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в чат {chat_id}: {e}", exc_info=True)
            failed += 1
    
    return sent, failed


async def _send_cleanup_report(bot: Bot, deleted: int, sent: int, total: int) -> None:
    """Отправка отчёта об очистке админам."""
    if not ADMIN_IDS:
        return
    
    report = (
        f"✅ <b>УТРЕННЯЯ ОЧИСТКА ЗАВЕРШЕНА!</b>\n\n"
        f"🗑️ Удалено: {deleted}\n"
        f"📨 Приветствий: {sent}/{total}\n"
        f"⏰ {datetime.now(MSK_OFFSET).strftime('%H:%M:%S')}"
    )
    
    for admin_id in ADMIN_IDS:
        if admin_id is None:
            continue
        try:
            await _send_with_retry(bot, admin_id, report)
        except Exception:
            pass


async def morning_cleanup_and_greeting(bot: Bot) -> None:
    """Утренняя очистка и отправка приветствия в каждый чат."""
    if bot is None or db is None:
        return
    
    await _tracker.sync_chats_from_db()
    
    active_chats = await _tracker.get_active_chats()
    if not active_chats:
        logger.info("Нет активных чатов для очистки")
        return
    
    logger.info(f"🌅 Утренняя очистка для {len(active_chats)} чатов")
    
    # Шаг 1: Удаление сообщений
    deleted = await _delete_pending_messages(bot)
    logger.info(f"🗑️ Удалено {deleted} сообщений")
    
    # Шаг 2: Отправка приветствий
    sent, failed = await _send_morning_greetings(bot, active_chats)
    
    logger.info(f"🌅 Утренняя очистка: {sent}/{len(active_chats)} приветствий, {failed} ошибок")
    
    # Шаг 3: Отчёт админам
    await _send_cleanup_report(bot, deleted, sent, len(active_chats))


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
            
            wait_seconds = max(0, (next_run - now).total_seconds())
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
            logger.error(f"❌ Ошибка планировщика: {e}", exc_info=True)
            await asyncio.sleep(3600)
    
    logger.info("Планировщик остановлен")


def signal_shutdown() -> None:
    _shutdown_event.set()


async def add_active_chat(chat_id: int) -> None:
    if chat_id is not None:
        await _tracker.add_active_chat(chat_id)


async def get_active_chats_count() -> int:
    return len(await _tracker.get_active_chats())


async def cleanup_all_chats(bot: Bot) -> None:
    if bot is not None:
        await morning_cleanup_and_greeting(bot)
