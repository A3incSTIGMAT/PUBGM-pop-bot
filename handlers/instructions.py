from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from handlers.roles import get_user_role

router = Router()

@router.message(Command("admin_guide"))
async def admin_guide(message: Message):
    """Руководство для администраторов"""
    role = await get_user_role(message.chat.id, message.from_user.id)
    
    if role not in ['global_admin', 'creator', 'admin']:
        await message.answer("❌ Это руководство предназначено для администраторов чата.")
        return
    
    guide = (
        "📘 **Руководство администратора NEXUS**\n\n"
        "🔧 **Быстрый старт:**\n"
        "1. Назначьте бота администратором чата\n"
        "2. Используйте /setup для настройки\n"
        "3. Настройте лог-канал для анонимных репортов\n\n"
        "🛡 **Анонимные репорты:**\n"
        "• Участники пишут /report @username [причина]\n"
        "• Жалобы приходят в лог-канал\n\n"
        "👮 **Управление модераторами:**\n"
        "/addmod — назначить модератора\n"
        "/removemod — удалить модератора\n"
        "/mods — список модераторов\n\n"
        "📋 **Команды админа:**\n"
        "/setup — мастер настройки\n"
        "/setlogchannel — установить лог-канал\n"
        "/setwelcome — настроить приветствие\n"
        "/all — отметить всех\n"
        "/ban — забанить\n"
        "/mute — заглушить\n\n"
        "🚀 Готово!"
    )
    await message.answer(guide)
