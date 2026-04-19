"""
Модуль вызова тега по категории
Команда: /tagcat <slug> [текст]
Поддержка из умного парсера
Тегает ВСЕХ, кроме явно отписавшихся
"""

import logging
import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from handlers.tag_categories import (
    get_chat_enabled_categories, 
    collect_all_users_except_unsubscribed,
    log_tag_usage
)

logger = logging.getLogger(__name__)
router = Router()

# Настройки
BATCH_SIZE = 10
BATCH_DELAY = 1.0
MAX_MENTIONS = 50  # Максимум упоминаний за раз


async def trigger_tag(message: types.Message, category_slug: str, msg_text: str):
    """
    Вызов тега из умного парсера.
    Тегает ВСЕХ пользователей, КРОМЕ тех, кто явно отписался от категории.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        return
    
    # Проверка существования категории
    categories = await get_chat_enabled_categories(chat_id)
    category = next((c for c in categories if c["slug"] == category_slug), None)
    
    if not category:
        await message.answer(
            f"❌ Категория <code>{category_slug}</code> не найдена или отключена", 
            parse_mode=ParseMode.HTML
        )
        return
    
    # Отправляем сообщение "Сбор..."
    status_msg = await message.answer(
        f"🔄 <b>Сбор участников...</b>\n"
        f"Категория: {category['icon']} {category['name']}",
        parse_mode=ParseMode.HTML
    )
    
    # Сбор ВСЕХ пользователей, КРОМЕ отписавшихся
    subscribers = await collect_all_users_except_unsubscribed(chat_id, category_slug)
    
    if not subscribers:
        await status_msg.edit_text(
            f"😔 <b>Некого упоминать!</b>\n\n"
            f"Категория: {category['icon']} {category['name']}\n"
            f"Все пользователи отписались от этой категории.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Ограничиваем количество упоминаний
    total_mentions = len(subscribers)
    mentions_to_send = subscribers[:MAX_MENTIONS]
    
    # Удаляем статусное сообщение
    try:
        await status_msg.delete()
    except:
        pass
    
    # Формируем и отправляем сообщения пачками
    safe_name = message.from_user.full_name.replace('<', '&lt;').replace('>', '&gt;')
    safe_text = msg_text.replace('<', '&lt;').replace('>', '&gt;')
    
    batches = [mentions_to_send[i:i + BATCH_SIZE] for i in range(0, len(mentions_to_send), BATCH_SIZE)]
    
    for batch_idx, batch in enumerate(batches):
        batch_text = " ".join(batch)
        
        if batch_idx == 0:
            response = (
                f"{category['icon']} <b>{category['name']}</b>\n\n"
                f"👤 <b>{safe_name}</b>: {safe_text}\n\n"
                f"🔔 <b>ВНИМАНИЕ!</b>\n"
                f"{batch_text}\n"
            )
        else:
            response = (
                f"{category['icon']} <b>{category['name']}</b> (продолжение {batch_idx + 1}/{len(batches)})\n\n"
                f"{batch_text}\n"
            )
        
        try:
            await message.bot.send_message(chat_id, response, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send batch {batch_idx}: {e}")
        
        if batch_idx < len(batches) - 1:
            await asyncio.sleep(BATCH_DELAY)
    
    # Итоговое сообщение
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
    
    # Логируем
    await log_tag_usage(chat_id, category_slug, user_id, len(mentions_to_send))
    logger.info(f"Tag triggered: chat={chat_id}, cat={category_slug}, mentions={len(mentions_to_send)}")


@router.message(Command("tagcat"))
async def cmd_tagcat(message: types.Message):
    """Вызов тега по категории: /tagcat pubg текст"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    args = message.text.split(maxsplit=2)
    
    # Если нет аргументов — показываем доступные категории
    if len(args) < 2:
        categories = await get_chat_enabled_categories(chat_id)
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
                text += f"  <i>{cat['description']}</i>\n"
            text += "\n"
        text += "💡 <b>Пример:</b> <code>/tagcat pubg Ищу сквад на ранкед</code>\n\n"
        text += "🔔 <i>Бот упомянет всех, кроме отписавшихся от категории</i>"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        return
    
    category_slug = args[1].lower()
    msg_text = args[2] if len(args) > 2 else "Внимание!"
    
    # Вызываем основную функцию
    await trigger_tag(message, category_slug, msg_text)


@router.message(Command("tagcat_help"))
async def cmd_tagcat_help(message: types.Message):
    """Помощь по тегам"""
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
