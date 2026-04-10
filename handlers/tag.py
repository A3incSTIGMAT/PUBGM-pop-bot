from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import asyncio

router = Router()

# Хранилище для отмены
cancel_flag = {}


@router.message(Command("tag"))
async def cmd_tag(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📢 `/tag @username текст`", parse_mode="Markdown")
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
        "⚠️ Участники получат уведомления, даже если они выключены в чате!\n\n"
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
    
    # Получаем список участников (только тех, у кого есть username)
    members = []
    try:
        # Пытаемся получить участников через get_chat_administrators (это работает всегда)
        admins = await callback.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot and admin.user.id != user_id:
                if admin.user.username:
                    members.append(admin.user)
        
        # Пытаемся получить больше участников (если получится)
        try:
            async for member in callback.bot.get_chat_members(chat_id):
                if not member.user.is_bot and member.user.id != user_id and member.user not in members:
                    if member.user.username:
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
    
    # Отправляем сообщения пачками по 5-10 упоминаний (как в Iris)
    batch_size = 8  # по 8 участников в сообщении
    cancel_flag[chat_id] = False
    
    # Первое сообщение — заголовок
    await callback.bot.send_message(
        chat_id,
        f"🔔 *ОБЩИЙ СБОР!* 🔔\n\n"
        f"👤 *{user_name}*\n\n"
        f"📢 ВНИМАНИЕ, УЧАСТНИКИ!\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n",
        parse_mode="Markdown"
    )
    
    # Отправляем пачки упоминаний
    for i in range(0, len(members), batch_size):
        if cancel_flag.get(chat_id, False):
            await callback.bot.send_message(chat_id, "❌ Общий сбор отменён")
            break
        
        batch = members[i:i+batch_size]
        mentions = []
        for member in batch:
            if member.username:
                mentions.append(f"@{member.username}")
            else:
                mentions.append(f"[{member.full_name}](tg://user?id={member.id})")
        
        mention_text = " ".join(mentions)
        
        await callback.bot.send_message(
            chat_id,
            f"📢 *Участники:*\n{mention_text}\n",
            parse_mode="Markdown"
        )
        
        # Небольшая задержка, чтобы не спамить
        await asyncio.sleep(0.5)
    
    if not cancel_flag.get(chat_id, False):
        await callback.bot.send_message(
            chat_id,
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *Общий сбор завершён!*\n"
            f"👥 Упомянуто: {len(members)} участников",
            parse_mode="Markdown"
        )
    
    # Удаляем исходное сообщение с кнопками
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
        await message.answer("📢 `/tagrole админы текст`", parse_mode="Markdown")
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
    
    mentions = []
    for admin in admins:
        if admin.username:
            mentions.append(f"@{admin.username}")
        else:
            mentions.append(f"[{admin.full_name}](tg://user?id={admin.id})")
    
    # Отправляем как в Iris — отдельное сообщение с упоминаниями
    await message.answer(
        f"🛡️ *Обращение к {role}:*\n\n"
        f"{' '.join(mentions)}\n\n"
        f"📢 {clean_text if clean_text else 'Внимание!'}",
        parse_mode="Markdown"
    )


@router.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Общий сбор", callback_data="start_all")],
        [InlineKeyboardButton(text="🛡️ Написать админам", callback_data="tag_admins")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Общий сбор*\n\n"
        "• `/all` — начать общий сбор (как в Iris)\n"
        "• `/tag @user` — упомянуть пользователя\n"
        "• `/tagrole админы` — написать админам\n\n"
        "✨ Участники получат уведомления, даже если они выключены в чате!",
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
    
    mentions = []
    for admin in admins:
        if admin.username:
            mentions.append(f"@{admin.username}")
        else:
            mentions.append(f"[{admin.full_name}](tg://user?id={admin.id})")
    
    await callback.message.edit_text(
        f"🛡️ *Администраторы:*\n\n{' '.join(mentions)}",
        parse_mode="Markdown"
    )
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
