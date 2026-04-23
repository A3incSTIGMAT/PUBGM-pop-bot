#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/tag_trigger.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Вызов тегов по категориям
# ============================================

import asyncio
import html
import logging
from typing import Optional, List

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from handlers.tag_categories import (
    get_chat_enabled_categories, 
    collect_all_users_except_unsubscribed,
    log_tag_usage
)
from database import DatabaseError

logger = logging.getLogger(__name__)
router = Router()

# ==================== КОНСТАНТЫ ====================

BATCH_SIZE = 10
BATCH_DELAY = 1.0
MAX_MENTIONS = 50  # Максимум упоминаний за раз


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def send_batch_messages(
    bot,
    chat_id: int,
    batches: List[List[str]],
    category: dict,
    initiator_name: str,
    msg_text: str
) -> int:
    """
    Отправляет сообщения пачками.
    
    Returns:
        Количество отправленных сообщений
    """
    sent = 0
    safe_name = safe_html_escape(initiator_name)
    safe_text = safe_html_escape(msg_text)
    
    for batch_idx, batch in enumerate(batches):
        batch_text = " ".join(batch)
        
        if batch_idx == 0:
            response = (
                f"{category['icon']} <b>{category['name']}</b>\n\n"
                f"👤 <b>{safe_name}</b>: {safe_text}\n\n"
                f"🔔 <b>ВНИМАНИЕ!</b>\n"
                f"{batch_text}"
            )
        else:
            response = (
                f"{category['icon']} <b>{category['name']}</b> "
                f"(продолжение {batch_idx + 1}/{len(batches)})\n\n"
                f"{batch_text}"
            )
        
        try:
            await bot.send_message(chat_id, response, parse_mode=ParseMode.HTML)
            sent += 1
        except TelegramAPIError as e:
            logger.error(f"Failed to send batch {batch_idx}: {e}")
        
        if batch_idx < len(batches) - 1:
            await asyncio.sleep(BATCH_DELAY)
    
    return sent


# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================

async def trigger_tag(message: types.Message, category_slug: str, msg_text: str) -> None:
    """
    Вызов тега из умного парсера.
    Тегает ВСЕХ пользователей, КРОМЕ тех, кто явно отписался от категории.
    """
    if not message or not message.chat or not message.from_user:
        logger.warning("trigger_tag called with invalid message")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        return
    
    # Проверка существования категории
    try:
        categories = await get_chat_enabled_categories(chat_id)
    except DatabaseError as e:
        logger.error(f"Database error getting categories: {e}")
        await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
        return
    
    category = next((c for c in categories if c["slug"] == category_slug), None)
    
    if not category:
        await message.answer(
            f"❌ Категория <code>{safe_html_escape(category_slug)}</code> не найдена или отключена",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Отправляем статус
    status_msg = await message.answer(
        f"🔄 <b>Сбор участников...</b>\n"
        f"Категория: {category['icon']} {category['name']}",
        parse_mode=ParseMode.HTML
    )
    
    # Сбор пользователей
    try:
        subscribers = await collect_all_users_except_unsubscribed(chat_id, category_slug)
    except DatabaseError as e:
        logger.error(f"Database error collecting users: {e}")
        await status_msg.edit_text("❌ Ошибка при сборе участников.")
        return
    
    if not subscribers:
        await status_msg.edit_text(
            f"😔 <b>Некого упоминать!</b>\n\n"
            f"Категория: {category['icon']} {category['name']}\n"
            f"Все пользователи отписались от этой категории.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Ограничиваем количество
    total_mentions = len(subscribers)
    mentions_to_send = subscribers[:MAX_MENTIONS]
    
    # Удаляем статус
    try:
        await status_msg.delete()
    except TelegramAPIError:
        pass
    
    # Разбиваем на батчи
    batches = [
        mentions_to_send[i:i + BATCH_SIZE] 
        for i in range(0, len(mentions_to_send), BATCH_SIZE)
    ]
    
    # Отправляем
    initiator_name = message.from_user.full_name or "Пользователь"
    await send_batch_messages(
        message.bot, chat_id, batches, category, initiator_name, msg_text
    )
    
    # Итоговое сообщение
    try:
        if total_mentions > MAX_MENTIONS:
            await message.bot.send_message(
                chat_id,
                f"✅ <b>Готово!</b>\n"
                f"👥 Упомянуто: {MAX_MENTIONS} из {total_mentions}\n"
                f"📌 Категория: {category['icon']} {category['name']}\n\n"
                f"💡 <i>Отписаться: /mytags</i>",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.bot.send_message(
                chat_id,
                f"✅ <b>Готово!</b>\n"
                f"👥 Упомянуто: {total_mentions}\n"
                f"📌 Категория: {category['icon']} {category['name']}\n\n"
                f"💡 <i>Отписаться от уведомлений: /mytags</i>",
                parse_mode=ParseMode.HTML
            )
    except TelegramAPIError as e:
        logger.error(f"Failed to send final message: {e}")
    
    # Логируем
    try:
        await log_tag_usage(chat_id, category_slug, user_id, len(mentions_to_send))
        logger.info(f"Tag triggered: chat={chat_id}, cat={category_slug}, mentions={len(mentions_to_send)}")
    except DatabaseError as e:
        logger.error(f"Failed to log tag usage: {e}")


# ==================== КОМАНДЫ ====================

@router.message(Command("tagcat"))
async def cmd_tagcat(message: types.Message) -> None:
    """Вызов тега по категории: /tagcat pubg текст"""
    if not message or not message.chat or not message.from_user:
        return
    
    chat_id = message.chat.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if not message.text:
        return
    
    args = message.text.split(maxsplit=2)
    
    # Если нет аргументов — показываем доступные категории
    if len(args) < 2:
        try:
            categories = await get_chat_enabled_categories(chat_id)
        except DatabaseError as e:
            logger.error(f"Database error: {e}")
            await message.answer("❌ Ошибка загрузки категорий.")
            return
        
        if not categories:
            await message.answer(
                "📭 <b>В этом чате нет активных категорий тегов</b>\n\n"
                "Администратор может включить их через /tagadmin",
                parse_mode=ParseMode.HTML
            )
            return
        
        text = "📌 <b>ДОСТУПНЫЕ КАТЕГОРИИ</b>\n\n"
        for cat in categories:
            text += f"• <code>/tagcat {cat['slug']}</code> — {cat['icon']} {cat['name']}\n"
            if cat.get('description'):
                text += f"  <i>{safe_html_escape(cat['description'])}</i>\n"
            text += "\n"
        text += "💡 <b>Пример:</b> <code>/tagcat pubg Ищу сквад на ранкед</code>\n\n"
        text += "🔔 <i>Бот упомянет всех, кроме отписавшихся от категории</i>"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        return
    
    category_slug = args[1].lower()
    msg_text = args[2] if len(args) > 2 else "Внимание!"
    
    await trigger_tag(message, category_slug, msg_text)


@router.message(Command("tagcat_help"))
async def cmd_tagcat_help(message: types.Message) -> None:
    """Помощь по тегам."""
    if not message:
        return
    
    help_text = (
        "🏷️ <b>УМНЫЕ ТЕГИ — КАК ЭТО РАБОТАЕТ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📝 КОМАНДЫ:</b>\n"
        "• <code>/tagcat [категория] [текст]</code> — вызвать тег\n"
        "• <code>/mytags</code> — управление подписками\n"
        "• <code>/tagcat</code> — список категорий\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎯 ПРИМЕРЫ:</b>\n"
        "• <code>/tagcat pubg Нужен +1 в сквад</code>\n"
        "• <code>/tagcat cs2 Ищем пятого на фейсит</code>\n"
        "• <code>/tagcat important Важный опрос</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🔔 КОГО УПОМИНАЕТ:</b>\n"
        "• <b>ВСЕХ</b> участников чата\n"
        "• <b>КРОМЕ</b> тех, кто явно отписался в /mytags\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🤖 УМНЫЙ ВЫЗОВ:</b>\n"
        "• <code>Нексус, найди сквад в PUBG</code>\n"
        "• <code>Нексус, собери пати в доту</code>\n"
        "• <code>Бот, нужен совет по важному вопросу</code>\n\n"
        "💡 <i>Бот сам определит категорию по ключевым словам!</i>"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)
