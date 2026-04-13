"""
Модуль вызова тегов по категориям
Команда: /tagcat <slug> [текст]
"""

import logging
import re
import time
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode

from utils.tag_categories import (
    get_chat_enabled_categories,
    collect_subscribed_users,
    log_tag_usage
)

router = Router()
logger = logging.getLogger(__name__)

# Настройки
MAX_MESSAGE_LENGTH = 4000  # Запас до лимита Telegram (4096)
DEFAULT_COOLDOWN = 300  # 5 минут между вызовами одной категории в чате
ADMIN_ONLY_CATEGORIES = {"urgent", "tech"}  # Категории, доступные только админам


def _escape_html(text: str) -> str:
    """Безопасное экранирование для ParseMode.HTML"""
    if not text:
        return ""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


async def _check_cooldown(chat_id: int, category_slug: str) -> bool:
    """Проверка кулдауна категории в чате (упрощённая версия в памяти)"""
    # ⚠️ В продакшене хранить в БД/Redis для распределённой работы
    from handlers.tag_categories import _tag_cooldown_cache  # глобальный кэш {f"{chat_id}_{slug}": timestamp}
    
    key = f"{chat_id}_{category_slug}"
    now = time.time()
    
    if key in _tag_cooldown_cache:
        if now - _tag_cooldown_cache[key] < DEFAULT_COOLDOWN:
            return False
    
    _tag_cooldown_cache[key] = now
    return True


@router.message(Command("tagcat"))
async def cmd_tagcat(message: Message):
    """Вызов тега по категории"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Проверка типа чата
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    # Парсинг аргументов
    args = message.text.split(maxsplit=2)
    
    # Показ списка категорий, если нет аргументов
    if len(args) < 2:
        try:
            categories = await get_chat_enabled_categories(chat_id)
        except Exception as e:
            logger.error(f"Failed to load categories: {e}")
            await message.answer("❌ Ошибка загрузки категорий. Попробуйте позже.")
            return
        
        if not categories:
            await message.answer("❌ В этом чате нет активных категорий")
            return
        
        text = "📌 <b>ДОСТУПНЫЕ КАТЕГОРИИ</b>\n\n"
        for cat in categories:
            safe_name = _escape_html(cat["name"])
            safe_desc = _escape_html(cat["description"] or "")
            text += f"• <code>/tagcat {cat['slug']}</code> — {cat['icon']} {safe_name}\n"
            if safe_desc:
                text += f"  <i>{safe_desc}</i>\n"
            text += "\n"
        
        text += "💡 <i>Пример: /tagcat pubg Ищем ещё одного в сквад!</i>"
        await message.answer(text, parse_mode=ParseMode.HTML)
        return
    
    category_slug = args[1].lower().strip()
    message_text = args[2].strip() if len(args) > 2 else "Внимание!"
    
    # Валидация slug
    if not re.match(r'^[a-z0-9_]+$', category_slug):
        await message.answer("❌ Неверный формат категории")
        return
    
    # Загружаем категории ОДИН раз
    try:
        categories = await get_chat_enabled_categories(chat_id)
    except Exception as e:
        logger.error(f"Failed to load categories: {e}")
        await message.answer("❌ Ошибка загрузки категорий. Попробуйте позже.")
        return
    
    category = next((c for c in categories if c["slug"] == category_slug), None)
    
    if not category:
        safe_slug = _escape_html(category_slug)
        await message.answer(f"❌ Категория <code>{safe_slug}</code> не найдена или отключена", parse_mode=ParseMode.HTML)
        return
    
    # Проверка прав для админ-категорий
    if category_slug in ADMIN_ONLY_CATEGORIES:
        try:
            member = await message.bot.get_chat_member(chat_id, user_id)
            if member.status not in ["creator", "administrator"]:
                safe_name = _escape_html(category["name"])
                await message.answer(f"❌ Категория <b>{safe_name}</b> доступна только администраторам!", parse_mode=ParseMode.HTML)
                return
        except Exception as e:
            logger.warning(f"Admin check failed: {e}")
            await message.answer("❌ Ошибка проверки прав!")
            return
    
    # Проверка кулдауна
    if not await _check_cooldown(chat_id, category_slug):
        safe_name = _escape_html(category["name"])
        await message.answer(f"⏰ Категория <b>{safe_name}</b> на перезарядке. Попробуйте через {DEFAULT_COOLDOWN // 60} мин.", parse_mode=ParseMode.HTML)
        return
    
    # Сбор подписанных пользователей
    try:
        mentioned = await collect_subscribed_users(chat_id, category_slug)
    except Exception as e:
        logger.error(f"Failed to collect users: {e}")
        await message.answer("❌ Ошибка при сборе участников. Попробуйте позже.")
        return
    
    if not mentioned:
        safe_name = _escape_html(category["name"])
        await message.answer(f"😔 На категорию <b>{safe_name}</b> пока никто не подписан", parse_mode=ParseMode.HTML)
        return
    
    # Формирование ответа с экранированием
    safe_icon = category["icon"]
    safe_name = _escape_html(category["name"])
    safe_author = _escape_html(message.from_user.full_name or "Аноним")
    safe_message = _escape_html(message_text)
    
    mention_text = " ".join(mentioned)
    
    # Проверка длины сообщения
    response_text = (
        f"{safe_icon} <b>{safe_name}</b>\n\n"
        f"👤 <i>{safe_author}</i>: {safe_message}\n\n"
        f"{mention_text}\n\n"
        f"✅ Упомянуто: {len(mentioned)}"
    )
    
    if len(response_text) > MAX_MESSAGE_LENGTH:
        # Обрезаем упоминания, если сообщение слишком длинное
        mention_text = " ".join(mentioned[:25])  # Оставляем первые 25
        response_text = (
            f"{safe_icon} <b>{safe_name}</b>\n\n"
            f"👤 <i>{safe_author}</i>: {safe_message}\n\n"
            f"{mention_text}\n\n"
            f"⚠️ Показано 25 из {len(mentioned)} (сообщение обрезано)"
        )
    
    # Отправка упоминания
    await message.answer(response_text, parse_mode=ParseMode.HTML)
    
    # Логирование
    try:
        await log_tag_usage(chat_id, category_slug, user_id, len(mentioned))
    except Exception as e:
        # Логирование не должно ломать основную функциональность
        logger.error(f"Failed to log tag usage: {e}")

