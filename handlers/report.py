"""
Анонимные репорты для NEXUS бота.
Позволяет участникам анонимно сообщать о нарушениях.
"""

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_log_channel, save_report, get_reports_count
from handlers.roles import can_configure
from utils.logger import log_admin

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    """Установить экземпляр бота"""
    global bot
    bot = bot_instance

@router.message(Command("report"))
async def anonymous_report(message: Message):
    """
    Анонимная жалоба на пользователя.
    Формат: /report @username [причина]
    """
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
        async for member in message.chat.get_members():
            if member.user.username and member.user.username.lower() == target_username.lower():
                target_id = member.user.id
                target_name = member.user.full_name
                break
    except:
        pass
    
    # Сохраняем жалобу в БД
    save_report(chat_id, reporter_id, target_id or 0, reason)
    
    # Получаем количество жалоб на этого пользователя
    reports_count = get_reports_count(chat_id, target_id) + 1
    
    # Отправляем анонимное сообщение в лог-канал
    await bot.send_message(
        log_channel_id,
        f"🛡 **АНОНИМНАЯ ЖАЛОБА**\n\n"
        f"👤 Нарушитель: @{target_username} ({target_name})\n"
        f"📝 Причина: {reason}\n"
        f"💬 Чат: {message.chat.title}\n"
        f"📊 Всего жалоб на этого пользователя: {reports_count}\n\n"
        f"⚡ Действия: /ban @{target_username} | /mute @{target_username}"
    )
    
    await message.answer(
        f"✅ Жалоба на @{target_username} анонимно отправлена администраторам.\n"
        f"Спасибо, что помогаете поддерживать порядок в чате!"
    )
    
    log_admin(message.from_user.full_name, "отправил анонимную жалобу", f"@{target_username}")

@router.message(Command("reports_stats"))
async def reports_stats(message: Message):
    """
    Статистика жалоб (только для админов)
    """
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут просматривать статистику жалоб.")
        return
    
    chat_id = message.chat.id
    pending_count = get_reports_count(chat_id)
    
    from database.queries import get_reports_stats
    stats = get_reports_stats(chat_id)
    
    if stats["total"] == 0:
        await message.answer(
            "📊 **Статистика анонимных жалоб**\n\n"
            "📋 Жалоб пока нет.\n\n"
            "Участники могут использовать /report для анонимных сообщений о нарушениях."
        )
        return
    
    top_targets_text = ""
    if stats["top_targets"]:
        top_targets_text = "\n\n🔥 **Чаще всего жалуются:**"
        for target in stats["top_targets"][:5]:
            top_targets_text += f"\n• {target['target_id']} — {target['count']} жалоб"
    
    await message.answer(
        f"📊 **Статистика анонимных жалоб**\n\n"
        f"📋 Ожидают рассмотрения: {stats['pending']}\n"
        f"✅ Рассмотрено: {stats['resolved']}\n"
        f"📊 Всего жалоб: {stats['total']}"
        f"{top_targets_text}\n\n"
        f"💡 Для просмотра жалоб проверьте ваш лог-канал."
    )

@router.message(Command("resolve_report"))
async def resolve_report(message: Message):
    """
    Отметить жалобу как рассмотренную (админ-команда)
    """
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "📝 **Отметить жалобу**\n\n"
            "Использование: /resolve_report [ID_жалобы]\n"
            "ID жалобы можно найти в лог-канале."
        )
        return
    
    try:
        report_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID жалобы должен быть числом.")
        return
    
    from database.db import resolve_report as resolve_report_db
    resolve_report_db(report_id)
    
    await message.answer(f"✅ Жалоба #{report_id} отмечена как рассмотренная.")
    
    log_admin(message.from_user.full_name, "отметил жалобу как рассмотренную", f"#{report_id}")
