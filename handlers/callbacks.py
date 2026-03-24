from aiogram import Router, Bot
from aiogram.types import CallbackQuery

from database.db import get_log_channel
from keyboards.setup_menu import get_setup_menu, get_reports_setup_menu, get_safezone_menu

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    """Установить экземпляр бота"""
    global bot
    bot = bot_instance

@router.callback_query(lambda c: c.data == "setup_reports")
async def setup_reports(callback: CallbackQuery):
    """Настройка анонимных репортов"""
    chat_id = callback.message.chat.id
    log_channel = get_log_channel(chat_id)
    
    if not log_channel:
        await callback.message.edit_text(
            "🛡 **Настройка анонимных репортов**\n\n"
            "Для работы анонимных репортов необходимо:\n\n"
            "1️⃣ **Создайте приватный канал** (или группу)\n"
            "   Куда будут отправляться все жалобы.\n\n"
            "2️⃣ **Добавьте бота в этот канал** как администратора\n\n"
            "3️⃣ **Введите команду:** /setlogchannel @ваш_канал\n\n"
            "После настройки участники смогут использовать /report\n\n"
            "💡 **Совет:** Сделайте канал скрытым, чтобы админы видели жалобы, а участники — нет.",
            reply_markup=get_reports_setup_menu()
        )
    else:
        await callback.message.edit_text(
            f"🛡 **Анонимные репорты**\n\n"
            f"✅ Лог-канал настроен: {log_channel}\n\n"
            f"📊 Статистика жалоб: /reports_stats\n\n"
            f"Участники могут использовать:\n"
            f"/report @username [причина] — пожаловаться анонимно",
            reply_markup=get_reports_setup_menu()
        )
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_logchannel")
async def setup_logchannel(callback: CallbackQuery):
    """Настройка лог-канала"""
    await callback.message.edit_text(
        "📋 **Настройка лог-канала**\n\n"
        "Лог-канал — это место, куда бот отправляет:\n"
        "• Анонимные жалобы\n"
        "• Действия администраторов\n"
        "• Важные уведомления\n\n"
        "**Как настроить:**\n\n"
        "1️⃣ Создайте канал (приватный или публичный)\n"
        "2️⃣ Добавьте бота в канал как администратора\n"
        "3️⃣ Введите команду: /setlogchannel @ваш_канал\n\n"
        "⚠️ **Важно:** Бот должен быть администратором канала!"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_help_reports")
async def help_reports(callback: CallbackQuery):
    """Справка по анонимным репортам"""
    await callback.message.edit_text(
        "🛡 **Что такое анонимные репорты?**\n\n"
        "Это функция, которая позволяет участникам сообщать о нарушениях,\n"
        "не раскрывая свою личность.\n\n"
        "**Как это работает:**\n\n"
        "1️⃣ Участник пишет: /report @нарушитель спамит\n"
        "2️⃣ Бот отправляет жалобу в лог-канал\n"
        "3️⃣ Администратор видит нарушителя и причину\n"
        "4️⃣ Администратор не знает, кто отправил жалобу\n\n"
        "**Почему это важно:**\n\n"
        "✅ Нет страха мести от нарушителей\n"
        "✅ Участники активнее сообщают о проблемах\n"
        "✅ Модерация становится эффективнее\n\n"
        "**Для крупных чатов — обязательная функция!**",
        reply_markup=get_setup_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "reports_enable")
async def reports_enable(callback: CallbackQuery):
    """Включение анонимных репортов (проверка)"""
    chat_id = callback.message.chat.id
    log_channel = get_log_channel(chat_id)
    
    if log_channel:
        await callback.answer("✅ Анонимные репорты уже включены!", show_alert=True)
    else:
        await callback.answer(
            "⚠️ Сначала настройте лог-канал командой /setlogchannel",
            show_alert=True
        )
    
    await callback.message.edit_text(
        "🛡 **Анонимные репорты**\n\n"
        "Функция готова к использованию!\n\n"
        "Участники могут жаловаться: /report @username [причина]\n\n"
        "Все жалобы будут отправляться в лог-канал.",
        reply_markup=get_setup_menu()
    )

@router.callback_query(lambda c: c.data == "setup_back")
async def setup_back(callback: CallbackQuery):
    """Назад в главное меню настроек"""
    await callback.message.edit_text(
        "⚙️ **Главное меню настроек**\n\n"
        "Выберите, что хотите настроить:",
        reply_markup=get_setup_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_close")
async def setup_close(callback: CallbackQuery):
    """Закрыть меню настроек"""
    await callback.message.delete()
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_safezone")
async def setup_safezone(callback: CallbackQuery):
    """Безопасная зона"""
    await callback.message.edit_text(
        "🔐 **Безопасная зона**\n\n"
        "Функции для защиты чата:\n\n"
        "• 🌙 **Ночной режим** — ограничение сообщений ночью\n"
        "• 🚫 **Блокировка ссылок** — автоматическое удаление ссылок\n"
        "• 📵 **Блокировка медиа** — запрет фото/видео в указанное время\n\n"
        "Выберите функцию для настройки:",
        reply_markup=get_safezone_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("safezone_"))
async def safezone_action(callback: CallbackQuery):
    """Действия безопасной зоны"""
    action = callback.data.replace("safezone_", "")
    
    messages = {
        "night": "🌙 **Ночной режим**\n\nВременно отключает возможность отправки сообщений в указанный период (например, 23:00-07:00).\n\n⚙️ Настройка будет добавлена в следующем обновлении.",
        "links": "🚫 **Блокировка ссылок**\n\nАвтоматически удаляет сообщения со ссылками от пользователей без прав модератора.\n\n⚙️ Настройка будет добавлена в следующем обновлении.",
        "media": "📵 **Блокировка медиа**\n\nВременно запрещает отправку фото, видео и стикеров в указанный период.\n\n⚙️ Настройка будет добавлена в следующем обновлении."
    }
    
    await callback.message.edit_text(
        messages.get(action, "🔐 **Безопасная зона**\n\nФункция в разработке."),
        reply_markup=get_safezone_menu()
    )
    await callback.answer()
