from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re

router = Router()


@router.message(Command("tag"))
async def cmd_tag(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 Использование: `/tag @username текст`\n"
            "Пример: `/tag @user Привет!`",
            parse_mode="Markdown"
        )
        return
    
    text = args[1]
    match = re.search(r'@(\w+)', text)
    if not match:
        await message.answer("❌ Укажите @username пользователя")
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
        [InlineKeyboardButton(text="✅ Да, мне есть 18", callback_data="confirm_all"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_all")]
    ])
    
    await message.answer(
        "📢 *МАССОВОЕ УПОМИНАНИЕ*\n\n"
        "⚠️ Вы собираетесь упомянуть всех участников чата.\n\n"
        "Подтвердите, что вам есть 18 лет:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data == "confirm_all")
async def confirm_all(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    user_name = callback.from_user.full_name
    
    # Сразу отвечаем, чтобы бот не вис
    await callback.answer("✅ Отправляю оповещение!")
    
    # Получаем всех участников с username (для уведомлений)
    mentions = []
    try:
        # Пытаемся получить всех участников чата
        async for member in callback.bot.get_chat_members(chat_id):
            if not member.user.is_bot and member.user.id != callback.from_user.id:
                if member.user.username:
                    mentions.append(f"@{member.user.username}")
                else:
                    # У пользователей без username всё равно будет уведомление через ID
                    mentions.append(f"[{member.user.full_name}](tg://user?id={member.user.id})")
                if len(mentions) >= 50:
                    break
    except:
        # Если не получилось получить всех, берём хотя бы администраторов
        try:
            admins = await callback.bot.get_chat_administrators(chat_id)
            for admin in admins:
                if not admin.user.is_bot and admin.user.id != callback.from_user.id:
                    if admin.user.username:
                        mentions.append(f"@{admin.user.username}")
                    else:
                        mentions.append(f"[{admin.user.full_name}](tg://user?id={admin.user.id})")
        except:
            pass
    
    if not mentions:
        # Если совсем никого не нашли
        await callback.message.edit_text(
            f"🔔 *{user_name}* обращается к участникам чата!\n\n"
            f"📢 ВНИМАНИЕ ВСЕМ!",
            parse_mode="Markdown"
        )
        return
    
    # Формируем одно сообщение со всеми упоминаниями
    mention_text = " ".join(mentions)
    
    # Отправляем сообщение с упоминаниями (у всех сработает уведомление)
    await callback.message.edit_text(
        f"🔔 *ОБЩИЙ СБОР! ВНИМАНИЕ ВСЕМ!* 🔔\n\n"
        f"👤 *{user_name}*\n\n"
        f"📢 Важное сообщение для всех участников!\n\n"
        f"{mention_text}",
        parse_mode="Markdown"
    )
    
    # Удаляем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


@router.message(Command("tagrole"))
async def cmd_tag_role(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 Использование: `/tagrole админы текст`\n"
            "Пример: `/tagrole админы Внимание!`",
            parse_mode="Markdown"
        )
        return
    
    text = args[1]
    role_match = re.match(r'(админы?|модераторы?)\s*(.*)', text, re.IGNORECASE)
    
    if not role_match:
        await message.answer("❌ Не распознана роль. Используйте: `админы`", parse_mode="Markdown")
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
        await message.answer("❌ Нет администраторов в этом чате")
        return
    
    mentions = []
    for admin in admins:
        if admin.username:
            mentions.append(f"@{admin.username}")
        else:
            mentions.append(f"[{admin.full_name}](tg://user?id={admin.id})")
    
    if clean_text:
        result = f"🔔 {clean_text}\n\n{' '.join(mentions)}"
    else:
        result = f"🔔 Обращение к {role}:\n\n{' '.join(mentions)}"
    
    await message.answer(result, parse_mode="Markdown")


# ==================== КНОПКИ В МЕНЮ ====================

@router.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Тэгнуть всех", callback_data="confirm_all")],
        [InlineKeyboardButton(text="🛡️ Тэгнуть админов", callback_data="tag_admins")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Тэги и упоминания*\n\n"
        "*Команды:*\n"
        "• `/all` — оповестить всех (с уведомлениями)\n"
        "• `/tag @user текст` — упомянуть пользователя\n"
        "• `/tagrole админы текст` — упомянуть админов\n\n"
        "✨ *Как это работает:*\n"
        "• Участники получат РЕАЛЬНЫЕ уведомления\n"
        "• Даже при выключенных уведомлениях в чате\n"
        "• Бот должен быть администратором",
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
        await callback.message.edit_text("❌ Нет администраторов в этом чате")
        await callback.answer()
        return
    
    mentions = []
    for admin in admins:
        if admin.username:
            mentions.append(f"@{admin.username}")
        else:
            mentions.append(f"[{admin.full_name}](tg://user?id={admin.id})")
    
    await callback.message.edit_text(
        f"🛡️ *Обращение к администраторам:*\n\n{' '.join(mentions)}",
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
