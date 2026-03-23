from aiagram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_log_channel, save_report, get_reports_count
from handlers.admin import get_user_role, can_configure
from utils.logger import log_admin

router = Router()

@router.message(Command("report"))
async def anonymous_report(message: Message):
    """Анонимная жалоба на пользователя"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "🛡 **Анонимный репорт**\n\n"
            "Использование: /report @username [причина]\n"
            "Пример: /report @spammer спам в чате\n\n"
            "Администраторы увидят вашу жалобу, но не узнают, кто отправил.\n"
            "Это помогает избежать конфликтов и мести."
        )
        return
    
    target_username = args[1].replace("@", "")
    reason = " ".join(args[2:]) if len(args) > 2 else "без указания причины"
    
    reporter_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем, настроен ли лог-канал
    log_channel_id = get_log_channel(chat_id)
    if not log_channel_id:
        await message.answer(
            "❌ В этом чате не настроен канал для жалоб.\n"
            "Пожалуйста, сообщите администратору о необходимости настроить /setlogchannel"
        )
        return
    
    # Находим ID пользователя по username
    target_id = None
    target_name = target_username
    try:
        # Пытаемся найти пользователя в чате
        async for member in message.chat.get_members():
            if member.user.username and member.user.username.lower() == target_username.lower():
                target_id = member.user.id
                target_name = member.user.full_name
                break
    except:
        pass
    
    # Сохраняем жалобу в БД
    save_report(chat_id, reporter_id, target_id or 0, reason)
    
    # Отправляем анонимное сообщение в лог-канал
    from bot import bot
    
    await bot.send_message(
        log_channel_id,
        f"🛡 **АНОНИМНАЯ ЖАЛОБА**\n\n"
        f"👤 Нарушитель: @{target_username} ({target_name})\n"
        f"📝 Причина: {reason}\n"
        f"💬 Чат: {message.chat.title}\n"
        f"📊 Всего жалоб на этого пользователя: {get_reports_count(chat_id, target_id) + 1}\n\n"
        f"⚡ Действия: /ban @{target_username} | /mute @{target_username}"
    )
    
    await message.answer(
        f"✅ Жалоба на @{target_username} анонимно отправлена администраторам.\n"
        f"Спасибо, что помогаете поддерживать порядок в чате!"
    )
    
    log_admin(message.from_user.full_name, "отправил анонимную жалобу", f"@{target_username}")

@router.message(Command("reports_stats"))
async def reports_stats(message: Message):
    """Статистика жалоб (только для админов)"""
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут просматривать статистику жалоб.")
        return
    
    chat_id = message.chat.id
    pending_count = get_reports_count(chat_id)
    
    await message.answer(
        f"📊 **Статистика анонимных жалоб**\n\n"
        f"📋 Ожидают рассмотрения: {pending_count}\n"
        f"✅ Рассмотрено: ...\n\n"
        f"Для просмотра жалоб проверьте ваш лог-канал."
    )
