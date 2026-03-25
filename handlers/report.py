"""
Анонимные репорты для NEXUS бота.
"""

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_log_channel, save_report, get_reports_count, get_reports_stats
from handlers.roles import can_configure
from utils.logger import log_admin

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

@router.message(Command("report"))
async def anonymous_report(message: Message):
    """Анонимная жалоба на пользователя"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "🛡 **Анонимный репорт**\n\n"
            "Использование: /report @username [причина]\n"
            "Пример: /report @spammer спам в чате\n\n"
            "Администраторы увидят вашу жалобу, но не узнают, кто отправил."
        )
        return
    
    target_username = args[1].replace("@", "")
    reason = " ".join(args[2:]) if len(args) > 2 else "без указания причины"
    
    chat_id = message.chat.id
    
    log_channel_id = get_log_channel(chat_id)
    if not log_channel_id:
        await message.answer(
            "❌ В этом чате не настроен канал для жалоб.\n"
            "Пожалуйста, сообщите администратору о необходимости настроить /setlogchannel"
        )
        return
    
    target_id = None
    try:
        async for member in message.chat.get_members():
            if member.user.username and member.user.username.lower() == target_username.lower():
                target_id = member.user.id
                break
    except:
        pass
    
    save_report(chat_id, message.from_user.id, target_id or 0, reason)
    
    await bot.send_message(
        log_channel_id,
        f"🛡 **АНОНИМНАЯ ЖАЛОБА**\n\n"
        f"👤 Нарушитель: @{target_username}\n"
        f"📝 Причина: {reason}\n"
        f"💬 Чат: {message.chat.title}\n"
        f"📊 Жалоб: {get_reports_count(chat_id, target_id) + 1}\n\n"
        f"⚡ Действия: /ban @{target_username} | /mute @{target_username}"
    )
    
    await message.answer(
        f"✅ Жалоба на @{target_username} анонимно отправлена администраторам."
    )
    log_admin(message.from_user.full_name, "отправил анонимную жалобу", f"@{target_username}")

@router.message(Command("reports_stats"))
async def reports_stats(message: Message):
    """Статистика жалоб"""
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут просматривать статистику жалоб.")
        return
    
    stats = get_reports_stats(message.chat.id)
    
    await message.answer(
        f"📊 **Статистика анонимных жалоб**\n\n"
        f"📋 Ожидают рассмотрения: {stats['pending']}\n"
        f"✅ Рассмотрено: {stats['resolved']}\n"
        f"📊 Всего жалоб: {stats['total']}"
    )
