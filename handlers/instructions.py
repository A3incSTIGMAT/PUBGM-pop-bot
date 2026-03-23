from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from handlers.admin import get_user_role, can_configure

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
        "• Жалобы приходят в лог-канал\n"
        "• Вы не видите, кто пожаловался\n"
        "• Идеально для крупных чатов\n\n"
        "👮 **Управление модераторами:**\n"
        "/addmod — назначить модератора (ответом)\n"
        "/removemod — удалить модератора (ответом)\n"
        "/mods — список модераторов\n\n"
        "📋 **Команды админа:**\n"
        "/setup — мастер настройки\n"
        "/setlogchannel @channel — установить лог-канал\n"
        "/setwelcome [текст] — настроить приветствие\n"
        "/all — отметить всех\n"
        "/ban — забанить (ответом)\n"
        "/mute — заглушить (ответом)\n\n"
        "📊 **Статистика:**\n"
        "/stats — моя статистика\n"
        "/top — топ участников\n"
        "/reports_stats — статистика жалоб\n\n"
        "💡 **Советы:**\n"
        "• Лог-канал сделайте приватным\n"
        "• Проверяйте жалобы регулярно\n"
        "• Используйте /report для теста\n\n"
        "🚀 Готово! Ваш чат под надежной защитой!"
    )
    
    await message.answer(guide)
