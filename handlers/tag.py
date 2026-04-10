from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re

router = Router()

# Хранилище для ожидающих подтверждения
waiting_all = {}

@router.message(Command("tag"))
async def cmd_tag(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📢 Использование: `/tag @username текст`", parse_mode="Markdown")
        return
    
    text = args[1]
    match = re.search(r'@(\w+)', text)
    if not match:
        await message.answer("❌ Укажите @username")
        return
    
    username = match.group(1)
    clean = re.sub(r'@\w+', '', text).strip()
    result = f"🔔 {clean}\n\n👉 @{username}" if clean else f"🔔 Вас упомянул {message.from_user.full_name}\n\n👉 @{username}"
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
    
    # Проверяем права бота
    try:
        bot_member = await callback.bot.get_chat_member(chat_id, callback.bot.id)
        if bot_member.status not in ['creator', 'administrator']:
            await callback.message.edit_text(
                "❌ *Ошибка:* Бот не администратор чата!\n\n"
                "Добавьте бота в группу и выдайте права администратора.",
                parse_mode="Markdown"
            )
            await callback.answer()
            return
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()
        return
    
    # Получаем участников
    members = []
    try:
        admins = await callback.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot:
                members.append(admin.user)
        
        try:
            async for member in callback.bot.get_chat_members(chat_id):
                if not member.user.is_bot and member.user.id not in [m.id for m in members]:
                    members.append(member.user)
                    if len(members) >= 50:
                        break
        except:
            pass
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка получения участников: {e}")
        await callback.answer()
        return
    
    if not members:
        await callback.message.edit_text("❌ Не удалось получить список участников")
        await callback.answer()
        return
    
    # Формируем упоминания
    mentions = []
    for member in members:
        if member.username:
            mentions.append(f"@{member.username}")
        else:
            mentions.append(f"[{member.full_name}](tg://user?id={member.id})")
    
    # Отправляем
    await callback.message.edit_text(
        f"🔔 *ОБЩИЙ СБОР! ВНИМАНИЕ ВСЕМ!* 🔔\n\n"
        f"👤 {callback.from_user.full_name}\n\n"
        f"{' '.join(mentions[:40])}",
        parse_mode="Markdown"
    )
    
    if len(mentions) > 40:
        await callback.message.answer(f"... и ещё {len(mentions) - 40} участников")
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()

@router.message(Command("tagrole"))
async def cmd_tag_role(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📢 Использование: `/tagrole админы текст`", parse_mode="Markdown")
        return
    
    text = args[1]
    role_match = re.match(r'(админы?|модераторы?)\s*(.*)', text, re.IGNORECASE)
    
    if not role_match:
        await message.answer("❌ Роль: админы или модераторы")
        return
    
    role = role_match.group(1).lower()
    clean = role_match.group(2).strip()
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
    
    mentions = [f"@{a.username}" if a.username else f"[{a.full_name}](tg://user?id={a.id})" for a in admins]
    
    result = f"🔔 {clean}\n\n{' '.join(mentions)}" if clean else f"🔔 Обращение к {role}:\n\n{' '.join(mentions)}"
    await message.answer(result, parse_mode="Markdown")
