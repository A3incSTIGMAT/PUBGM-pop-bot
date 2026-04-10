from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import asyncio

router = Router()

# Хранилище для отмены
cancel_flag = {}

# Ключевые слова для активации общего сбора
ALL_KEYWORDS = [
    'оповести всех', 'общий сбор', 'собери всех', 'созывай всех',
    'отметь всех', 'упомяни всех', 'позови всех', 'тэг всех',
    'all', 'everyone', 'всех участников', 'все в чате'
]

# Ключевые слова для активации бота
BOT_KEYWORDS = ['нексус', 'нэксус', 'nexus', 'некс', 'нэкс', 'бот']


def detect_all_intent(text: str) -> bool:
    """Определить, хочет ли пользователь оповестить всех"""
    text_lower = text.lower()
    
    # Проверяем наличие ключевых слов бота
    has_bot = any(kw in text_lower for kw in BOT_KEYWORDS)
    
    # Проверяем наличие ключевых слов оповещения
    has_all = any(kw in text_lower for kw in ALL_KEYWORDS)
    
    return has_bot and has_all


@router.message(lambda message: message.text and not message.text.startswith('/'))
async def smart_tag_handler(message: types.Message):
    """Умный обработчик — только для общего сбора"""
    text = message.text.strip()
    
    # Проверяем, хочет ли пользователь оповестить всех
    if detect_all_intent(text):
        await cmd_all(message)
        return
    
    # ВСЁ ОСТАЛЬНОЕ ИГНОРИРУЕМ


# ==================== ГОЛОСОВЫЕ СООБЩЕНИЯ — ПОЛНОСТЬЮ ИГНОРИРУЕМ ====================
@router.message(lambda message: message.voice)
async def ignore_voice(message: types.Message):
    """Полностью игнорируем голосовые сообщения — НИЧЕГО НЕ ПИШЕМ"""
    pass  # Просто ничего не делаем


@router.message(Command("tag"))
async def cmd_tag(message: types.Message):
    """Обычный тэг пользователя (только по команде)"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📢 `/tag @username текст`\nПример: `/tag @user Привет!`", parse_mode="Markdown")
        return
    
    text = args[1]
    match = re.search(r'@(\w+)', text)
    if not match:
        await message.answer("❌ Укажите @username")
        return
    
    username = match.group(1)
    clean = re.sub(r'@\w+', '', text).strip()
    
    if clean:
        result = f"🔔 {clean}\n\n👉 @{username}"
    else:
        result = f"🔔 Вас упомянул {message.from_user.full_name}\n\n👉 @{username}"
    
    await message.answer(result)


@router.message(Command("all"))
async def cmd_all(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Начать общий сбор", callback_data="start_all"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_all")]
    ])
    
    await message.answer(
        "📢 *ОБЩИЙ СБОР*\n\n"
        "Будет отправлено несколько сообщений с упоминаниями участников.\n\n"
        "⚠️ Каждый участник получит ЛИЧНОЕ уведомление!\n\n"
        "Начать?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data == "start_all")
async def start_all(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    user_name = callback.from_user.full_name
    user_id = callback.from_user.id
    
    await callback.answer("✅ Начинаю общий сбор!")
    await callback.message.edit_text("🔄 *Идёт общий сбор...*\n\nСобираю участников...", parse_mode="Markdown")
    
    # Получаем список участников
    members = []
    try:
        # Получаем администраторов (это всегда работает)
        admins = await callback.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot and admin.user.id != user_id:
                members.append(admin.user)
        
        # Пытаемся получить больше участников
        try:
            async for member in callback.bot.get_chat_members(chat_id):
                if not member.user.is_bot and member.user.id != user_id and member.user not in members:
                    members.append(member.user)
                    if len(members) >= 100:
                        break
        except:
            pass
    except Exception as e:
        print(f"Ошибка: {e}")
    
    if not members:
        await callback.message.edit_text(
            f"🔔 *{user_name}* обращается к участникам!\n\n"
            f"📢 ВНИМАНИЕ ВСЕМ!",
            parse_mode="Markdown"
        )
        return
    
    cancel_flag[chat_id] = False
    
    # Первое сообщение — заголовок
    await callback.bot.send_message(
        chat_id,
        f"🔔 *ОБЩИЙ СБОР!* 🔔\n\n"
        f"👤 *{user_name}*\n\n"
        f"📢 Оповещение участников:\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n",
        parse_mode="Markdown"
    )
    
    # Отправляем КАЖДОМУ участнику ОТДЕЛЬНОЕ сообщение с упоминанием
    notified = 0
    for member in members:
        if cancel_flag.get(chat_id, False):
            await callback.bot.send_message(chat_id, "❌ Общий сбор отменён")
            break
        
        # Формируем упоминание
        if member.username:
            mention = f"@{member.username}"
        else:
            mention = f"[{member.full_name}](tg://user?id={member.id})"
        
        # Отправляем отдельное сообщение для каждого участника
        await callback.bot.send_message(
            chat_id,
            f"🔔 *Уведомление для {mention}*\n\n"
            f"👤 {user_name} обращается к вам!\n\n"
            f"📢 Пожалуйста, обратите внимание!",
            parse_mode="Markdown"
        )
        
        notified += 1
        await asyncio.sleep(0.3)
    
    if not cancel_flag.get(chat_id, False):
        await callback.bot.send_message(
            chat_id,
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *Общий сбор завершён!*\n"
            f"👥 Оповещено: {notified} участников",
            parse_mode="Markdown"
        )
    
    try:
        await callback.message.delete()
    except:
        pass


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    cancel_flag[chat_id] = True
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


@router.message(Command("tagrole"))
async def cmd_tag_role(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📢 `/tagrole админы текст`\nПример: `/tagrole админы Внимание!`", parse_mode="Markdown")
        return
    
    text = args[1]
    role_match = re.match(r'(админы?)\s*(.*)', text, re.IGNORECASE)
    
    if not role_match:
        await message.answer("❌ Используйте: `/tagrole админы текст`")
        return
    
    role = role_match.group(1).lower()
    clean_text = role_match.group(2).strip()
    chat_id = message.chat.id
    admins = []
    
    try:
        administrators = await message.bot.get_chat_administrators(chat_id)
        for admin in administrators:
            if not admin.user.is_bot:
                admins.append(admin.user)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        return
    
    if not admins:
        await message.answer("❌ Нет администраторов")
        return
    
    for admin in admins:
        if admin.username:
            mention = f"@{admin.username}"
        else:
            mention = f"[{admin.full_name}](tg://user?id={admin.id})"
        
        await message.answer(
            f"🛡️ *Обращение к {role}:* {mention}\n\n"
            f"📢 {clean_text if clean_text else 'Внимание!'}",
            parse_mode="Markdown"
        )
        await asyncio.sleep(0.3)


@router.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Общий сбор", callback_data="start_all")],
        [InlineKeyboardButton(text="🛡️ Написать админам", callback_data="tag_admins")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Общий сбор*\n\n"
        "📝 *Команды:*\n"
        "• `/all` — начать общий сбор\n"
        "• `/tag @user` — упомянуть пользователя\n"
        "• `/tagrole админы` — написать админам\n\n"
        "📝 *Текстовые команды:*\n"
        "• 'Нексус, оповести всех'\n"
        "• 'Nexus, общий сбор'\n\n"
        "✨ Каждый участник получит ЛИЧНОЕ уведомление!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "tag_admins")
async def tag_admins(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    admins = []
    
    try:
        administrators = await callback.bot.get_chat_administrators(chat_id)
        for admin in administrators:
            if not admin.user.is_bot:
                admins.append(admin.user)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()
        return
    
    if not admins:
        await callback.message.edit_text("❌ Нет администраторов")
        await callback.answer()
        return
    
    for admin in admins:
        if admin.username:
            mention = f"@{admin.username}"
        else:
            mention = f"[{admin.full_name}](tg://user?id={admin.id})"
        
        await callback.bot.send_message(
            chat_id,
            f"🛡️ *Уведомление для {mention}*\n\n"
            f"👤 {callback.from_user.full_name} обращается к администраторам!",
            parse_mode="Markdown"
        )
        await asyncio.sleep(0.3)
    
    await callback.message.edit_text("✅ Уведомления отправлены администраторам!")
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    from utils.keyboards import main_menu
    await callback.message.edit_text(
        "🏠 *Главное меню*",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )
    await callback.answer()
