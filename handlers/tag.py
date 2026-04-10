from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import asyncio

router = Router()

# Хранилище для ожидающих подтверждения (если нужно)
waiting_all = {}


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
        [InlineKeyboardButton(text="✅ Подтверждаю", callback_data="confirm_all"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_all")]
    ])
    
    await message.answer(
        "📢 *МАССОВОЕ УПОМИНАНИЕ*\n\n"
        "⚠️ Вы собираетесь упомянуть всех участников чата.\n\n"
        "Подтвердите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data == "confirm_all")
async def confirm_all(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # Отвечаем на callback сразу, чтобы не было "висения"
    await callback.answer("🔔 Обрабатываю...")
    
    # Отправляем сообщение "печатает"
    await callback.bot.send_chat_action(chat_id, "typing")
    
    # Проверяем права бота
    try:
        bot_member = await callback.bot.get_chat_member(chat_id, callback.bot.id)
        if bot_member.status not in ['creator', 'administrator']:
            await callback.message.edit_text(
                "❌ *Ошибка:* Бот не является администратором чата!\n\n"
                "Чтобы использовать /all, добавьте бота в группу и выдайте ему права администратора.\n\n"
                "Необходимые права: `Получать список участников`",
                parse_mode="Markdown"
            )
            return
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка проверки прав: {e}")
        return
    
    # Получаем участников чата (упрощённо — только администраторов)
    members = []
    try:
        # Получаем администраторов (это всегда работает)
        admins = await callback.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot:
                members.append(admin.user)
        
        # Пытаемся получить обычных участников через get_chat (если бот может)
        try:
            chat = await callback.bot.get_chat(chat_id)
            # Если есть возможность получить участников
            async for member in callback.bot.get_chat_members(chat_id):
                if not member.user.is_bot and member.user.id not in [m.id for m in members]:
                    members.append(member.user)
                    if len(members) >= 30:  # Ограничиваем до 30, чтобы не виснуть
                        break
        except:
            pass
            
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка получения участников: {e}")
        return
    
    if not members:
        await callback.message.edit_text(
            "❌ Не удалось получить список участников.\n\n"
            "Убедитесь, что бот является администратором чата."
        )
        return
    
    # Формируем упоминания
    mentions = []
    for member in members:
        if member.username:
            mentions.append(f"@{member.username}")
        else:
            mentions.append(f"[{member.full_name}](tg://user?id={member.id})")
    
    # Отправляем сообщение с упоминаниями
    mention_text = " ".join(mentions[:30])
    
    await callback.message.edit_text(
        f"🔔 *ОБЩИЙ СБОР! ВНИМАНИЕ ВСЕМ!* 🔔\n\n"
        f"👤 *{callback.from_user.full_name}*\n\n"
        f"📢 Важное сообщение для всех участников!\n\n"
        f"{mention_text}",
        parse_mode="Markdown"
    )
    
    if len(mentions) > 30:
        await callback.message.answer(f"... и ещё {len(mentions) - 30} участников")
    
    # Удаляем исходное сообщение с кнопками
    try:
        await callback.message.delete()
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
            "Пример: `/tagrole админы Внимание, проверьте чат!`",
            parse_mode="Markdown"
        )
        return
    
    text = args[1]
    role_match = re.match(r'(админы?|модераторы?)\s*(.*)', text, re.IGNORECASE)
    
    if not role_match:
        await message.answer("❌ Не распознана роль. Используйте: `админы` или `модераторы`", parse_mode="Markdown")
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
                if len(admins) >= 20:
                    break
    except Exception as e:
        await message.answer(f"❌ Ошибка получения администраторов: {e}")
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


# ==================== КНОПКА В МЕНЮ ====================

@router.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Тэгнуть всех", callback_data="confirm_all")],
        [InlineKeyboardButton(text="🛡️ Тэгнуть админов", callback_data="tag_admins")],
        [InlineKeyboardButton(text="🔔 Как пользоваться", callback_data="tag_help")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Тэги и упоминания*\n\n"
        "*Как пользоваться:*\n\n"
        "📝 *Команды:*\n"
        "• `/all` — упомянуть всех\n"
        "• `/tag @user текст` — упомянуть пользователя\n"
        "• `/tagrole админы текст` — упомянуть админов\n\n"
        "📝 *Без команд:*\n"
        "• Напишите: `Нексус, отметь всех`\n"
        "• Или: `@user Привет!`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "tag_admins")
async def tag_admins(callback: types.CallbackQuery):
    """Тэгнуть админов из меню"""
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


@router.callback_query(lambda c: c.data == "tag_help")
async def tag_help(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="tag_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Помощь по тэгам*\n\n"
        "*Примеры команд:*\n\n"
        "📝 *Текстовые:*\n"
        "• `/all` — упомянуть всех\n"
        "• `/tag @user Привет` — упомянуть пользователя\n"
        "• `/tagrole админы Срочно!` — упомянуть админов\n\n"
        "✨ Бот понимает команды без `/`:\n"
        "• `Нексус, отметь всех`\n"
        "• `@user Привет`",
        parse_mode="Markdown",
        reply_markup=keyboard
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
