from aiogram import Router, Bot
from aiogram.types import CallbackQuery

from database.db import get_log_channel
from keyboards.setup_menu import get_setup_menu, get_reports_setup_menu, get_safezone_menu

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

@router.callback_query(lambda c: c.data == "setup_reports")
async def setup_reports(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    log_channel = get_log_channel(chat_id)
    
    if not log_channel:
        await callback.message.edit_text(
            "🛡 **Настройка анонимных репортов**\n\n"
            "1️⃣ Создайте приватный канал\n"
            "2️⃣ Добавьте бота в канал как администратора\n"
            "3️⃣ Введите: /setlogchannel @ваш_канал\n\n"
            "После настройки участники смогут использовать /report",
            reply_markup=get_reports_setup_menu()
        )
    else:
        await callback.message.edit_text(
            f"🛡 **Анонимные репорты**\n\n✅ Лог-канал настроен: {log_channel}",
            reply_markup=get_reports_setup_menu()
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_logchannel")
async def setup_logchannel(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 **Настройка лог-канала**\n\n"
        "1️⃣ Создайте канал\n"
        "2️⃣ Добавьте бота в канал как администратора\n"
        "3️⃣ Введите: /setlogchannel @ваш_канал"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_help_reports")
async def help_reports(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛡 **Анонимные репорты**\n\n"
        "Участник пишет: /report @нарушитель спамит\n"
        "Бот отправляет жалобу в лог-канал\n"
        "Админ видит нарушителя, но не видит, кто пожаловался\n\n"
        "✅ Нет страха мести\n"
        "✅ Участники активнее сообщают о проблемах",
        reply_markup=get_setup_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "reports_enable")
async def reports_enable(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    log_channel = get_log_channel(chat_id)
    
    if log_channel:
        await callback.answer("✅ Анонимные репорты уже включены!", show_alert=True)
    else:
        await callback.answer("⚠️ Сначала настройте лог-канал командой /setlogchannel", show_alert=True)
    
    await callback.message.edit_text(
        "🛡 **Анонимные репорты**\n\nУчастники могут жаловаться: /report @username [причина]",
        reply_markup=get_setup_menu()
    )

@router.callback_query(lambda c: c.data == "setup_back")
async def setup_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚙️ **Главное меню настроек**\n\nВыберите, что хотите настроить:",
        reply_markup=get_setup_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_close")
async def setup_close(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

@router.callback_query(lambda c: c.data == "setup_safezone")
async def setup_safezone(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔐 **Безопасная зона**\n\n"
        "• 🌙 Ночной режим\n"
        "• 🚫 Блокировка ссылок\n"
        "• 📵 Блокировка медиа\n\n"
        "⚙️ Настройка будет добавлена в следующем обновлении.",
        reply_markup=get_safezone_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("safezone_"))
async def safezone_action(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔐 **Безопасная зона**\n\nФункция в разработке.",
        reply_markup=get_safezone_menu()
    )
    await callback.answer()
