from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.tag_categories import get_chat_enabled_categories, get_user_subscriptions, toggle_subscription

router = Router()


@router.message(Command("mytags"))
async def cmd_mytags(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    categories = await get_chat_enabled_categories(chat_id)
    if not categories:
        await message.answer("📭 В этом чате нет активных категорий")
        return
    
    subs = await get_user_subscriptions(user_id, chat_id)
    
    keyboard = []
    for cat in categories:
        is_on = subs.get(cat["slug"], True)
        status = "🔔 ВКЛ" if is_on else "🔕 ВЫКЛ"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{cat['icon']} {cat['name']} [{status}]",
                callback_data=f"tagsub_{chat_id}_{cat['slug']}_{1 if not is_on else 0}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")])
    
    await message.answer(
        f"🔔 *ВАШИ ПОДПИСКИ*\n\nЧат: {message.chat.title}\n\nВыберите категории для подписки:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@router.callback_query(F.data.startswith("tagsub_"))
async def toggle_subscription_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    chat_id = int(parts[1])
    category_slug = parts[2]
    value = bool(int(parts[3]))
    
    await toggle_subscription(callback.from_user.id, chat_id, category_slug, value)
    
    status = "включена" if value else "отключена"
    await callback.answer(f"✅ Подписка {status}")
    await cmd_mytags(callback.message)
