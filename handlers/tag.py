from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re

router = Router()


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
    """Использует встроенный @all Telegram"""
    chat_id = message.chat.id
    chat_type = message.chat.type
    
    # Проверяем, что это группа
    if chat_type not in ['group', 'supergroup']:
        await message.answer("❌ Команда /all работает только в группах!")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтверждаю", callback_data="confirm_all"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_all")]
    ])
    
    await message.answer(
        "📢 *ВНИМАНИЕ!*\n\n"
        "Вы собираетесь упомянуть ВСЕХ участников чата.\n\n"
        "Для этого будет использована команда `@all` (встроенная функция Telegram).\n\n"
        "Подтвердите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data == "confirm_all")
async def confirm_all(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    user_name = callback.from_user.full_name
    
    await callback.answer("✅ Отправляю!")
    
    # Отправляем сообщение с @all (Telegram сам разошлёт уведомления)
    await callback.bot.send_message(
        chat_id,
        f"🔔 *ОБЩИЙ СБОР!* 🔔\n\n"
        f"👤 *{user_name}*\n\n"
        f"📢 ВНИМАНИЕ ВСЕМ УЧАСТНИКАМ!\n\n"
        f"@all",
        parse_mode="Markdown"
    )
    
    # Удаляем сообщение с кнопками
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
    
    await message.answer(
        f"🛡️ *Обращение к {role}:*\n\n"
        f"{' '.join(mentions)}\n\n"
        f"📢 {clean_text if clean_text else 'Внимание!'}",
        parse_mode="Markdown"
    )


@router.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Общий сбор (@all)", callback_data="confirm_all")],
        [InlineKeyboardButton(text="🛡️ Написать админам", callback_data="tag_admins")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Общий сбор*\n\n"
        "• `/all` — упомянуть ВСЕХ участников (через @all)\n"
        "• `/tag @user` — упомянуть пользователя\n"
        "• `/tagrole админы` — написать админам\n\n"
        "✨ `@all` — встроенная команда Telegram, которая гарантированно оповещает всех!",
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
