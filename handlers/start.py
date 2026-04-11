from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE
from utils.auto_delete import track_and_delete_bot_message, delete_bot_message_after
from utils.keyboards import main_menu, back_button

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    chat_id = message.chat.id
    
    # Обработка реферальной ссылки
    args = message.text.split()
    if len(args) > 1:
        start_param = args[1]
        if start_param.startswith("ref_"):
            parts = start_param.split("_")
            if len(parts) == 3:
                ref_chat_id = int(parts[1])
                ref_code = parts[2]
                from handlers.referral import process_referral_start
                await process_referral_start(message, ref_chat_id, ref_code)
    
    user = await db.get_user(user_id)
    
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        
        presentation_text = f"""
🤖 *ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!* 🤖

✨ *Привет, {first_name}!*

Я — *NEXUS Chat Manager* — твой личный помощник в управлении чатом!

━━━━━━━━━━━━━━━━━━━━━

*🎯 ЧТО Я УМЕЮ:*

├ 🎮 *Игры* — слоты, рулетка, КНБ, дуэли
├ 💰 *Экономика* — баланс, переводы
├ 📢 *Общий сбор* — оповещение всех участников
├ 🛡️ *Модерация* — автоудаление сообщений
├ 🤖 *AI помощник* — отвечаю на вопросы
└ 🔗 *Рефералка* — приглашай друзей, получай NCoins

━━━━━━━━━━━━━━━━━━━━━

*🗣️ КАК КО МНЕ ОБРАЩАТЬСЯ:*

📝 *Текстовые команды:*
• `Нексус, оповести всех`
• `Nexus, общий сбор`
• `собери всех участников`

━━━━━━━━━━━━━━━━━━━━━

*📌 БЫСТРЫЙ СТАРТ:*

├ /daily — получить бонус {START_BALANCE} монет
├ /slot 100 — сыграть в слот
├ /balance — проверить баланс
├ /all — оповестить всех участников
└ /my_ref — получить реферальную ссылку

━━━━━━━━━━━━━━━━━━━━━

*🎁 ВАМ НАЧИСЛЕНО: {START_BALANCE} МОНЕТ!*
"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Начать использовать", callback_data="back_to_menu")],
            [InlineKeyboardButton(text="🔗 Моя реферальная ссылка", callback_data="my_ref")]
        ])
        
        msg = await message.answer(presentation_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        await track_and_delete_bot_message(message.bot, chat_id, user_id, msg.message_id, delay=60)
    else:
        msg = await message.answer(
            f"👋 <b>С возвращением, {first_name}!</b>\n\n"
            f"💰 Ваш баланс: {user['balance']} монет\n"
            f"⭐ VIP статус: {'Да' if user['vip_level'] > 0 else 'Нет'}\n\n"
            f"Выберите действие в меню 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        await track_and_delete_bot_message(message.bot, chat_id, user_id, msg.message_id, delay=30)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    help_text = """
🤖 *NEXUS Chat Manager — ПОМОЩЬ*

━━━━━━━━━━━━━━━━━━━━━

*🗣️ КАК ОБРАЩАТЬСЯ:*

📝 *Примеры текстовых команд:*
• `Нексус, оповести всех`
• `Nexus, общий сбор`

━━━━━━━━━━━━━━━━━━━━━

*📋 ОСНОВНЫЕ КОМАНДЫ:*

*💰 Экономика*
/balance — баланс
/daily — бонус дня
/transfer @user 100 — перевод

*🎮 Игры*
/slot 100 — слот
/roulette 100 красный — рулетка
/rps камень — КНБ
/duel @user 100 — дуэль

*👤 Профиль*
/profile — профиль
/vip — VIP статус

*📢 Оповещения*
/all — общий сбор
/tag @user — упомянуть
/tagrole админы — написать админам

*🔗 Реферальная система*
/my_ref — получить реферальную ссылку
/enable_ref — включить (только владелец чата)

*🔒 Прочее*
/privacy — политика конфиденциальности
/delete_my_data — удалить мои данные

━━━━━━━━━━━━━━━━━━━━━

✨ *Все команды работают и через меню!*
"""
    msg = await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)
    await delete_bot_message_after(message.bot, chat_id, msg.message_id, delay=30)


@router.message(Command("privacy"))
async def cmd_privacy(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    privacy_text = """
🔒 *Политика конфиденциальности NEXUS Chat Manager*

━━━━━━━━━━━━━━━━━━━━━

*Какие данные собираются:*
├ Telegram ID
├ Имя пользователя
├ Баланс монет
├ Статистика игр
└ Данные анкеты (если заполнены)

*Как используются:*
├ Для работы игр и экономики
├ Для сохранения прогресса
└ Для упоминаний в общем сборе

*Хранение:*
├ Данные хранятся в зашифрованной БД
├ Не передаются третьим лицам
└ Удаляются по команде /delete_my_data

*Контакты:*
└ @A3incSTIGMAT

━━━━━━━━━━━━━━━━━━━━━

📄 Полная версия: 
https://github.com/A3incSTIGMAT/NEXUS-bot/blob/main/PRIVACY.md
"""
    msg = await message.answer(privacy_text, parse_mode=ParseMode.MARKDOWN)
    await delete_bot_message_after(message.bot, chat_id, msg.message_id, delay=30)


@router.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
    ])
    
    await message.answer(
        "⚠️ *УДАЛЕНИЕ ДАННЫХ*\n\n"
        "Вы уверены? Будут удалены:\n"
        "├ Баланс монет\n"
        "├ Статистика игр\n"
        "├ Анкета\n"
        "└ История транзакций\n\n"
        "Это действие НЕЛЬЗЯ отменить!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.message(Command("about"))
async def cmd_about(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    about_text = """
🤖 *NEXUS Chat Manager v5.0*

━━━━━━━━━━━━━━━━━━━━━

*📖 О БОТЕ:*

NEXUS Chat Manager — это многофункциональный бот для управления чатами, игр и экономики.

*🔧 ТЕХНОЛОГИИ:*
├ Python 3.11
├ Aiogram 3.x
├ SQLite
└ Docker

*👨‍💻 РАЗРАБОТЧИК:*
@A3incSTIGMAT

*🗣️ ОБРАЩЕНИЯ:*
• Нексус, Нэкс, Nexus
• Отметь, тэгни, упомяни, оповести
• Собери, созывай, общий сбор

━━━━━━━━━━━━━━━━━━━━━

✨ *Спасибо, что используете NEXUS!*
"""
    msg = await message.answer(about_text, parse_mode=ParseMode.MARKDOWN)
    await delete_bot_message_after(message.bot, chat_id, msg.message_id, delay=30)


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        "🏠 *Главное меню NEXUS Chat Manager*\n\nВыберите действие:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "my_ref")
async def my_ref_callback(callback: types.CallbackQuery):
    """Реферальная ссылка из меню"""
    from handlers.referral import my_referral_link
    
    # Создаём фейковое сообщение
    class FakeMessage:
        def __init__(self, from_user, chat, bot):
            self.from_user = from_user
            self.chat = chat
            self.bot = bot
            self.text = "/my_ref"
        
        async def answer(self, text, parse_mode=None, reply_markup=None):
            await callback.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    
    fake_msg = FakeMessage(callback.from_user, callback.message.chat, callback.bot)
    await my_referral_link(fake_msg)
    await callback.answer()


@router.callback_query(lambda c: c.data == "confirm_delete")
async def confirm_delete(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM transactions WHERE from_id = ? OR to_id = ?", (user_id, user_id))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        "✅ *Ваши данные удалены!*\n\n"
        "Вы можете начать заново с /start",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_delete")
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено")
    await callback.answer()


@router.callback_query(lambda c: c.data == "privacy")
async def privacy_callback(callback: types.CallbackQuery):
    privacy_text = """
🔒 *Политика конфиденциальности*

*Собираемые данные:*
• Telegram ID
• Имя пользователя
• Баланс монет
• Статистика игр

*Использование:*
• Работа игр и экономики
• Сохранение прогресса
• Упоминания в чате

*Удаление данных:*
/delete_my_data

*Контакты:*
@A3incSTIGMAT

📄 https://github.com/A3incSTIGMAT/NEXUS-bot/blob/main/PRIVACY.md
"""
    await callback.message.edit_text(privacy_text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_button())
    await callback.answer()
