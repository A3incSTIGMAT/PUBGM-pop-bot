from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # Обработка реферальной ссылки
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        parts = args[1].split("_")
        if len(parts) == 3:
            chat_id = int(parts[1])
            ref_code = parts[2]
            from handlers.referral import process_referral_start
            await process_referral_start(message, chat_id, ref_code)
            return
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    user = await db.get_user(user_id)
    
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
    
    # Красивая презентация бота
    presentation_text = f"""
🤖 *ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!* 🤖

✨ *Привет, {first_name}!*

Я — *NEXUS Chat Manager* — твой личный помощник в управлении чатом!

━━━━━━━━━━━━━━━━━━━━━

*🎯 ЧТО Я УМЕЮ:*

├ 🎮 *Игры* — слоты, рулетка, КНБ, дуэли
├ 💰 *Экономика* — баланс, переводы
├ ⭐ *VIP статус* — бесплатно за победы
├ 📢 *Общий сбор* — оповещение всех участников
├ 🔗 *Реферальная система* — приглашай друзей
└ 🤖 *AI помощник* — отвечаю на вопросы

━━━━━━━━━━━━━━━━━━━━━

*🗣️ КАК КО МНЕ ОБРАЩАТЬСЯ:*

📝 *Текстовые команды:*
• `Нексус, оповести всех`
• `Nexus, общий сбор`
• `@username` — упомянуть пользователя

━━━━━━━━━━━━━━━━━━━━━

*📌 БЫСТРЫЙ СТАРТ:*

├ /daily — получить бонус {START_BALANCE} монет
├ /slot 100 — сыграть в слот
├ /balance — проверить баланс
├ /my_ref — получить реферальную ссылку
└ /all — оповестить всех участников

━━━━━━━━━━━━━━━━━━━━━

*🎁 ВАМ НАЧИСЛЕНО: {START_BALANCE} МОНЕТ!*

Нажми на кнопку ниже, чтобы начать 👇
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать использовать", callback_data="back_to_menu")],
        [InlineKeyboardButton(text="🔗 Получить реферальную ссылку", callback_data="my_ref")]
    ])
    
    await message.answer(
        presentation_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """
🤖 *NEXUS Chat Manager — ПОМОЩЬ*

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
/vip — VIP статус (бесплатно!)

*📢 Оповещения*
/all — общий сбор
/tag @user — упомянуть
/tagrole админы — написать админам

*🔗 Реферальная система*
/my_ref — получить ссылку
/enable_ref — включить (только владелец чата)

━━━━━━━━━━━━━━━━━━━━━

*🔒 КОНФИДЕНЦИАЛЬНОСТЬ*
/privacy — политика конфиденциальности
/delete_my_data — удалить мои данные

━━━━━━━━━━━━━━━━━━━━━

✨ *Все команды работают и через меню!*
"""
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("about"))
async def cmd_about(message: types.Message):
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

━━━━━━━━━━━━━━━━━━━━━

✨ *Спасибо, что используете NEXUS!*
"""
    await message.answer(about_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("privacy"))
async def cmd_privacy(message: types.Message):
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
    await message.answer(privacy_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("delete_my_data"))
async def cmd_delete_data(message: types.Message):
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


@router.callback_query(lambda c: c.data == "confirm_delete")
async def confirm_delete(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM transactions WHERE from_id = ? OR to_id = ?", (user_id, user_id))
    cursor.execute("DELETE FROM ref_links WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM ref_invites WHERE inviter_id = ? OR invited_id = ?", (user_id, user_id))
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
    await cmd_privacy(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    from utils.keyboards import main_menu
    await callback.message.edit_text(
        "🏠 *Главное меню NEXUS Chat Manager*\n\nВыберите действие:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )
    await callback.answer()
