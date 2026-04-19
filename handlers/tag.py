"""
Модуль тэга участников (чат-менеджер) - ПОЛНОСТЬЮ ИСПРАВЛЕН
- Общий сбор (/all) — упоминает всех участников
- Тэг пользователя (/tag)
- Тэг администраторов (/tagrole)
"""

import logging
import re
import time
import asyncio
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)

# Настройки
TAG_COOLDOWN = 300  # 5 минут между общими сборами
BATCH_SIZE = 10
BATCH_DELAY = 1.0

_cooldown_storage = {}


def _escape_html(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def is_admin_in_chat(bot, user_id: int, chat_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception as e:
        logger.warning(f"Admin check failed for {user_id} in {chat_id}: {e}")
        return False


async def is_bot_admin(bot, chat_id: int) -> bool:
    try:
        bot_me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, bot_me.id)
        return member.status in ['creator', 'administrator']
    except Exception as e:
        logger.warning(f"Bot admin check failed for chat {chat_id}: {e}")
        return False


@router.message(Command("all"))
async def cmd_all(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда /all работает только в группах!")
        return
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    if not await is_admin_in_chat(message.bot, user_id, chat_id):
        await message.answer(
            "❌ <b>Нет прав!</b>\n\n"
            "Только администраторы чата могут использовать /all.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not await is_bot_admin(message.bot, chat_id):
        await message.answer(
            "❌ <b>Ошибка:</b> Бот не является администратором чата!",
            parse_mode=ParseMode.HTML
        )
        return
    
    current_time = time.time()
    cooldown_key = f"all:{chat_id}"
    
    if cooldown_key in _cooldown_storage:
        last_used = _cooldown_storage[cooldown_key]
        if current_time - last_used < TAG_COOLDOWN:
            remaining = int(TAG_COOLDOWN - (current_time - last_used))
            minutes = remaining // 60
            seconds = remaining % 60
            await message.answer(
                f"⏰ <b>Подождите!</b>\n\n"
                f"Следующий сбор через <b>{minutes} мин {seconds} сек</b>.",
                parse_mode=ParseMode.HTML
            )
            return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"confirm_all_{chat_id}"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
    ])
    
    safe_name = _escape_html(message.from_user.full_name)
    await message.answer(
        "📢 <b>ОБЩИЙ СБОР</b> 📢\n\n"
        "⚠️ <b>Внимание!</b>\n"
        "После подтверждения будет отправлено сообщение с упоминанием всех участников.\n\n"
        f"👤 Инициатор: {safe_name}\n"
        f"🛡️ Права: Администратор\n\n"
        "✅ <b>Подтвердите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("confirm_all_"))
async def confirm_all(callback: types.CallbackQuery):
    try:
        parts = callback.data.split("_")
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат запроса", show_alert=True)
            return
        
        chat_id = int(parts[2])
        user_id = callback.from_user.id
        
        if callback.message.chat.id != chat_id:
            await callback.answer("❌ Несоответствие чата", show_alert=True)
            return
        
        # 🔥 ИСПРАВЛЕНО: Проверяем, что нажавший — администратор
        if not await is_admin_in_chat(callback.bot, user_id, chat_id):
            await callback.answer("❌ Только администраторы могут подтвердить!", show_alert=True)
            return
        
        await callback.answer("🔄 Собираю участников...")
        
        _cooldown_storage[f"all:{chat_id}"] = time.time()
        
        members = []
        seen_ids = set()
        
        admins = await callback.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot and admin.user.id not in seen_ids:
                members.append(admin.user)
                seen_ids.add(admin.user.id)
        
        try:
            member_count = 0
            async for member in callback.bot.get_chat_members(chat_id):
                if member_count >= 200:
                    break
                if not member.user.is_bot and member.user.id not in seen_ids:
                    members.append(member.user)
                    seen_ids.add(member.user.id)
                member_count += 1
        except Exception as e:
            logger.warning(f"Could not fetch all members: {e}")
        
        if not members:
            await callback.message.edit_text("❌ Не удалось получить список участников.", parse_mode=ParseMode.HTML)
            return
        
        try:
            await callback.message.delete()
        except:
            pass
        
        mentions = []
        for member in members:
            if member.username:
                mentions.append(f"@{member.username}")
            else:
                safe_name = _escape_html(member.full_name or "Пользователь")
                mentions.append(f'<a href="tg://user?id={member.id}">{safe_name}</a>')
        
        safe_initiator = _escape_html(callback.from_user.full_name)
        
        batch_size = BATCH_SIZE
        total_batches = (len(mentions) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(mentions))
            batch_mentions = mentions[start:end]
            batch_text = " ".join(batch_mentions)
            
            if batch_idx == 0:
                response = (
                    f"📢 <b>ОБЩИЙ СБОР!</b> 📢\n\n"
                    f"👤 <b>{safe_initiator}</b> (администратор)\n\n"
                    f"🔔 <b>ВНИМАНИЕ ВСЕМ УЧАСТНИКАМ!</b>\n\n"
                    f"{batch_text}\n"
                )
            else:
                response = (
                    f"📢 <b>Продолжение ({batch_idx + 1}/{total_batches})</b>\n\n"
                    f"{batch_text}\n"
                )
            
            try:
                await callback.bot.send_message(chat_id, response, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Failed to send batch {batch_idx}: {e}")
            
            if batch_idx < total_batches - 1:
                await asyncio.sleep(BATCH_DELAY)
        
        await callback.bot.send_message(
            chat_id,
            f"✅ <b>Общий сбор завершён!</b>\n\n"
            f"👥 Упомянуто участников: {len(mentions)}",
            parse_mode=ParseMode.HTML
        )
        
        await callback.answer("✅ Общий сбор завершён!")
        
    except Exception as e:
        logger.error(f"confirm_all error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при выполнении", show_alert=True)


@router.callback_query(F.data == "cancel_all")
async def cancel_all(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Общий сбор отменён.", parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(Command("tag"))
async def cmd_tag(message: types.Message):
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 <b>Как тэгать:</b>\n\n"
            "<code>/tag @username текст</code> — упомянуть пользователя\n"
            "Пример: <code>/tag @user Привет!</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = args[1]
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    if not match:
        await message.answer("❌ Укажите @username пользователя")
        return
    
    username = match.group(1)
    clean_text = re.sub(r'@\w+', '', text).strip()
    
    safe_author = _escape_html(message.from_user.full_name)
    if clean_text:
        safe_text = _escape_html(clean_text)
        result = f"🔔 {safe_text}\n\n👉 @{username}"
    else:
        result = f"🔔 Вас упомянул {safe_author}\n\n👉 @{username}"
    
    await message.answer(result, parse_mode=ParseMode.HTML)


@router.message(Command("tagrole"))
async def cmd_tag_role(message: types.Message):
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📢 <b>Как тэгать по роли:</b>\n\n"
            "<code>/tagrole админы текст</code> — упомянуть всех админов",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = args[1]
    role_match = re.match(r'(админы?)\s*(.*)', text, re.IGNORECASE)
    
    if not role_match:
        await message.answer("❌ Используйте: <code>/tagrole админы текст</code>", parse_mode=ParseMode.HTML)
        return
    
    clean_text = role_match.group(2).strip()
    
    admins = []
    try:
        administrators = await message.bot.get_chat_administrators(message.chat.id)
        for admin in administrators:
            if not admin.user.is_bot:
                admins.append(admin.user)
    except Exception as e:
        logger.error(f"Failed to get admins: {e}")
        await message.answer(f"❌ Ошибка: {_escape_html(str(e))}", parse_mode=ParseMode.HTML)
        return
    
    if not admins:
        await message.answer("❌ Нет администраторов в этом чате", parse_mode=ParseMode.HTML)
        return
    
    mentions = []
    for admin in admins:
        if admin.username:
            mentions.append(f"@{admin.username}")
        else:
            safe_name = _escape_html(admin.full_name or "Админ")
            mentions.append(f'<a href="tg://user?id={admin.id}">{safe_name}</a>')
    
    safe_text = _escape_html(clean_text) if clean_text else ""
    if safe_text:
        result = f"🔔 {safe_text}\n\n{' '.join(mentions)}"
    else:
        result = f"🛡️ <b>Обращение к администраторам:</b>\n\n{' '.join(mentions)}"
    
    await message.answer(result, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "tag_menu")
async def tag_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    is_admin = await is_admin_in_chat(callback.bot, user_id, chat_id)
    
    if is_admin:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР (/all)", callback_data="start_all")],
            [InlineKeyboardButton(text="🛡️ НАПИСАТЬ АДМИНАМ", callback_data="tag_admins")],
            [InlineKeyboardButton(text="🔔 КАК ПОЛЬЗОВАТЬСЯ", callback_data="tag_help")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await callback.message.edit_text(
            "📢 <b>УПРАВЛЕНИЕ ТЭГАМИ</b> (АДМИНИСТРАТОР)\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "• <code>/all</code> — общий сбор (1 раз в 5 минут)\n"
            "• <code>/tag @user</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы</code> — написать админам",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛡️ НАПИСАТЬ АДМИНАМ", callback_data="tag_admins")],
            [InlineKeyboardButton(text="🔔 КАК ПОЛЬЗОВАТЬСЯ", callback_data="tag_help")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
        ])
        
        await callback.message.edit_text(
            "📢 <b>УПРАВЛЕНИЕ ТЭГАМИ</b>\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "• <code>/tag @user</code> — упомянуть пользователя\n"
            "• <code>/tagrole админы</code> — написать админам\n\n"
            "⚠️ <b>Общий сбор (/all)</b>\n"
            "Доступен только для администраторов.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    
    await callback.answer()


@router.callback_query(F.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    if not await is_admin_in_chat(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только администраторы!", show_alert=True)
        return
    
    if not await is_bot_admin(callback.bot, chat_id):
        await callback.answer("❌ Бот не администратор!", show_alert=True)
        return
    
    current_time = time.time()
    cooldown_key = f"all:{chat_id}"
    
    if cooldown_key in _cooldown_storage:
        last_used = _cooldown_storage[cooldown_key]
        if current_time - last_used < TAG_COOLDOWN:
            remaining = int(TAG_COOLDOWN - (current_time - last_used))
            await callback.answer(f"⏰ Подождите {remaining} сек", show_alert=True)
            return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"confirm_all_{chat_id}"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
    ])
    
    safe_name = _escape_html(callback.from_user.full_name)
    await callback.message.edit_text(
        "📢 <b>ОБЩИЙ СБОР</b> 📢\n\n"
        "⚠️ <b>Внимание!</b>\n"
        "После подтверждения будет отправлено сообщение с упоминанием всех участников.\n\n"
        f"👤 Инициатор: {safe_name}\n"
        f"🛡️ Права: Администратор\n\n"
        "✅ <b>Подтвердите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "tag_admins")
async def tag_admins_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    
    admins = []
    try:
        administrators = await callback.bot.get_chat_administrators(chat_id)
        for admin in administrators:
            if not admin.user.is_bot:
                admins.append(admin.user)
    except Exception as e:
        logger.error(f"Failed to get admins: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if not admins:
        await callback.answer("❌ Нет администраторов", show_alert=True)
        return
    
    mentions = []
    for admin in admins:
        if admin.username:
            mentions.append(f"@{admin.username}")
        else:
            safe_name = _escape_html(admin.full_name or "Админ")
            mentions.append(f'<a href="tg://user?id={admin.id}">{safe_name}</a>')
    
    await callback.message.edit_text(
        f"🛡️ <b>АДМИНИСТРАТОРЫ ЧАТА:</b>\n\n{' '.join(mentions)}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_menu")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "tag_help")
async def tag_help_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="tag_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 <b>ПОМОЩЬ ПО ТЭГАМ</b>\n\n"
        "<b>📝 КОМАНДЫ ДЛЯ ВСЕХ:</b>\n"
        "• <code>/tag @user текст</code> — упомянуть пользователя\n"
        "• <code>/tagrole админы текст</code> — написать администраторам\n\n"
        "<b>👑 КОМАНДЫ ДЛЯ АДМИНОВ:</b>\n"
        "• <code>/all</code> — общий сбор (1 раз в 5 минут)",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()
