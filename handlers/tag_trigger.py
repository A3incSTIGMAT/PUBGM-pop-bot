"""
Модуль вызова тега по категории
Команда: /tagcat <slug> [текст]
Поддержка из умного парсера
"""

import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from handlers.tag_categories import (
    get_chat_enabled_categories, collect_subscribed_users
)

logger = logging.getLogger(__name__)
router = Router()


async def trigger_tag(message: types.Message, category_slug: str, msg_text: str):
    """Вызов тега из умного парсера"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        return
    
    # Проверка существования категории
    categories = await get_chat_enabled_categories(chat_id)
    category = next((c for c in categories if c["slug"] == category_slug), None)
    
    if not category:
        await message.answer(f"❌ Категория <code>{category_slug}</code> не найдена или отключена", parse_mode=ParseMode.HTML)
        return
    
    # Сбор подписанных пользователей
    subscribers = await collect_subscribed_users(chat_id, category_slug)
    
    if not subscribers:
        await message.answer(f"😔 На категорию <b>{category['name']}</b> никто не подписан", parse_mode=ParseMode.HTML)
        return
    
    mention_text = " ".join(subscribers[:30])
    
    await message.answer(
        f"{category['icon']} <b>{category['name']}</b>\n\n"
        f"👤 {message.from_user.full_name}: {msg_text}\n\n"
        f"{mention_text}\n\n"
        f"✅ Упомянуто: {len(subscribers)}",
        parse_mode=ParseMode.HTML
    )


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
            await message.answer("📭 В этом чате нет активных категорий тегов")
            return
        
        text = "📌 *ДОСТУПНЫЕ КАТЕГОРИИ*\n\n"
        for cat in categories:
            text += f"• <code>/tagcat {cat['slug']}</code> — {cat['icon']} {cat['name']}\n"
            if cat.get('description'):
                text += f"  <i>{cat['description']}</i>\n"
            text += "\n"
        text += "💡 Пример: <code>/tagcat pubg Ищу сквад</code>"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        return
    
    category_slug = args[1].lower()
    msg_text = args[2] if len(args) > 2 else "Внимание!"
    
    # Проверка существования категории
    categories = await get_chat_enabled_categories(chat_id)
    category = next((c for c in categories if c["slug"] == category_slug), None)
    
    if not category:
        await message.answer(f"❌ Категория <code>{category_slug}</code> не найдена или отключена", parse_mode=ParseMode.HTML)
        return
    
    # Сбор подписанных пользователей
    subscribers = await collect_subscribed_users(chat_id, category_slug)
    
    if not subscribers:
        await message.answer(f"😔 На категорию <b>{category['name']}</b> никто не подписан", parse_mode=ParseMode.HTML)
        return
    
    mention_text = " ".join(subscribers[:30])
    
    await message.answer(
        f"{category['icon']} <b>{category['name']}</b>\n\n"
        f"👤 {message.from_user.full_name}: {msg_text}\n\n"
        f"{mention_text}\n\n"
        f"✅ Упомянуто: {len(subscribers)}",
        parse_mode=ParseMode.HTML
    )
