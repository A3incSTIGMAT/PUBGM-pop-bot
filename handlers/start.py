"""
Модуль навигации, старта, помощи, управления данными и доната
"""

import asyncio
import logging
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE, DONATE_URL, DONATE_RECEIVER, DONATE_BANK
from utils.auto_delete import track_and_delete_bot_message, delete_bot_message_after
from utils.keyboards import main_menu, back_button, admin_menu

router = Router()
logger = logging.getLogger(__name__)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def _escape_html(text: str | None) -> str:
    """Безопасное экранирование для ParseMode.HTML"""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def is_admin_in_chat(bot: Bot, user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь администратором чата"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception as e:
        logger.warning(f"Admin check failed for {user_id} in {chat_id}: {e}")
        return False


# ==================== КОМАНДЫ ====================

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    chat_id = message.chat.id
    
    # Рефералка
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        parts = args[1].split("_")
        if len(parts) == 3:
            try:
                ref_chat_id = int(parts[1])
                ref_code = parts[2]
                from handlers.referral import process_referral_start
                await process_referral_start(message, ref_chat_id, ref_code)
            except Exception as e:
                logger.error(f"Referral processing error: {e}")
    
    user = await db.get_user(user_id)
    is_admin = await is_admin_in_chat(message.bot, user_id, chat_id) if message.chat.type in ['group', 'supergroup'] else False
    
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        
        presentation_text = (
            "🤖 <b>ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!</b> 🤖\n\n"
            f"✨ <b>Привет, {_escape_html(first_name)}!</b>\n\n"
            "Я — <b>NEXUS Chat Manager</b> — твой личный помощник в управлении чатом!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🎯 ЧТО Я УМЕЮ:</b>\n\n"
            "├ 🎮 <b>Игры</b> — слоты, рулетка, КНБ, дуэли\n"
            "├ 💰 <b>Экономика</b> — баланс, переводы\n"
            "├ 📢 <b>Общий сбор</b> — оповещение всех участников\n"
            "├ 🤖 <b>AI помощник</b> — отвечаю на вопросы\n"
            "├ 🔗 <b>Рефералка</b> — приглашай друзей, получай NCoins\n"
            "└ ❤️ <b>Поддержка</b> — помочь развитию проекта\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🗣️ КАК КО МНЕ ОБРАЩАТЬСЯ:</b>\n\n"
            "📝 <i>Текстовые команды:</i>\n"
            "• <code>Нексус, оповести всех</code>\n"
            "• <code>Nexus, общий сбор</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>📌 БЫСТРЫЙ СТАРТ:</b>\n\n"
            "├ <code>/daily</code> — получить бонус\n"
            "├ <code>/slot 100</code> — сыграть в слот\n"
            "├ <code>/balance</code> — проверить баланс\n"
            "├ <code>/all</code> — оповестить всех\n"
            "├ <code>/my_ref</code> — получить реферальную ссылку\n"
            "└ <code>/donate</code> — поддержать разработчика\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 <b>ВАМ НАЧИСЛЕНО: {START_BALANCE} МОНЕТ!</b>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 НАЧАТЬ ИСПОЛЬЗОВАТЬ", callback_data="back_to_menu")],
            [InlineKeyboardButton(text="🔗 МОЯ РЕФЕРАЛЬНАЯ ССЫЛКА", callback_data="my_ref")]
        ])
        
        msg = await message.answer(presentation_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await track_and_delete_bot_message(message.bot, chat_id, user_id, msg.message_id, delay=60)
    else:
        msg = await message.answer(
            f"👋 <b>С возвращением, {_escape_html(first_name)}!</b>\n\n"
            f"💰 Ваш баланс: <b>{user['balance']}</b> NCoins\n"
            f"⭐ VIP статус: {'✅ АКТИВИРОВАН' if user.get('vip_level', 0) > 0 else '❌ НЕТ'}\n\n"
            f"👇 Выберите действие в меню:",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(is_admin=is_admin)
        )
        await track_and_delete_bot_message(message.bot, chat_id, user_id, msg.message_id, delay=30)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    chat_id = message.chat.id
    
    help_text = (
        "🤖 <b>NEXUS CHAT MANAGER — ПОМОЩЬ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🗣️ КАК ОБРАЩАТЬСЯ:</b>\n\n"
        "📝 <i>Примеры текстовых команд:</i>\n"
        "• <code>Нексус, оповести всех</code>\n"
        "• <code>Nexus, общий сбор</code>\n"
        "• <code>Нексус, найди сквад в PUBG</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📋 ОСНОВНЫЕ КОМАНДЫ:</b>\n\n"
        "<b>💰 ЭКОНОМИКА</b>\n"
        "<code>/balance</code> — баланс\n"
        "<code>/daily</code> — бонус дня\n"
        "<code>/transfer @user 100</code> — перевод\n\n"
        "<b>🎮 ИГРЫ</b>\n"
        "<code>/slot 100</code> — слот\n"
        "<code>/roulette 100 красный</code> — рулетка\n"
        "<code>/rps камень</code> — КНБ\n"
        "<code>/duel @user 100</code> — дуэль\n\n"
        "<b>👤 ПРОФИЛЬ</b>\n"
        "<code>/profile</code> — профиль\n"
        "<code>/vip</code> — VIP статус\n\n"
        "<b>📢 ОПОВЕЩЕНИЯ И ТЭГИ</b>\n"
        "<code>/all</code> — общий сбор (админы)\n"
        "<code>/tag @user</code> — упомянуть пользователя\n"
        "<code>/tagrole админы</code> — написать админам\n"
        "<code>/mytags</code> — мои подписки на теги\n"
        "<code>/tagcat pubg текст</code> — вызов тега по категории\n\n"
        "<b>🔗 РЕФЕРАЛЬНАЯ СИСТЕМА</b>\n"
        "<code>/my_ref</code> — получить реферальную ссылку\n\n"
        "<b>❤️ ПОДДЕРЖКА</b>\n"
        "<code>/donate</code> — поддержать разработчика\n\n"
        "<b>🔒 ПРОЧЕЕ</b>\n"
        "<code>/privacy</code> — политика конфиденциальности\n"
        "<code>/delete_my_data</code> — удалить мои данные\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ <i>Все команды работают и через меню!</i>"
    )
    msg = await message.answer(help_text, parse_mode=ParseMode.HTML)
    await delete_bot_message_after(message.bot, message.chat.id, msg.message_id, delay=30)


@router.message(Command("privacy"))
async def cmd_privacy(message: types.Message):
    privacy_text = (
        "🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ NEXUS CHAT MANAGER</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📌 КАКИЕ ДАННЫЕ СОБИРАЮТСЯ:</b>\n\n"
        "├ Telegram ID\n"
        "├ Имя пользователя\n"
        "├ Баланс монет\n"
        "├ Статистика игр\n"
        "└ Данные анкеты (если заполнены)\n\n"
        "<b>📌 КАК ИСПОЛЬЗУЮТСЯ:</b>\n\n"
        "├ Для работы игр и экономики\n"
        "├ Для сохранения прогресса\n"
        "└ Для упоминаний в общем сборе\n\n"
        "<b>📌 ХРАНЕНИЕ:</b>\n\n"
        "├ Данные хранятся в зашифрованной БД\n"
        "├ Не передаются третьим лицам\n"
        "└ Удаляются по команде <code>/delete_my_data</code>\n\n"
        "<b>📌 КОНТАКТЫ:</b>\n\n"
        "└ @A3incSTIGMAT\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ <b>ВСЕ ДАННЫЕ ХРАНЯТСЯ ТОЛЬКО В БОТЕ</b>"
    )
    await message.answer(privacy_text, parse_mode=ParseMode.HTML)


@router.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА, УДАЛИТЬ", callback_data="confirm_delete"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_delete")]
    ])
    
    await message.answer(
        "⚠️ <b>УДАЛЕНИЕ ДАННЫХ</b>\n\n"
        "Вы уверены? Будут удалены:\n"
        "├ Баланс монет\n"
        "├ Статистика игр\n"
        "├ Анкета\n"
        "└ История транзакций\n\n"
        "❗ Это действие <b>НЕЛЬЗЯ</b> отменить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.message(Command("about"))
async def cmd_about(message: types.Message):
    chat_id = message.chat.id
    
    about_text = (
        "🤖 <b>NEXUS CHAT MANAGER v5.0</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📖 О БОТЕ:</b>\n\n"
        "NEXUS Chat Manager — это многофункциональный бот для управления чатами, игр и экономики.\n\n"
        "<b>🔧 ТЕХНОЛОГИИ:</b>\n"
        "├ Python 3.11\n"
        "├ Aiogram 3.x\n"
        "├ SQLite\n"
        "└ Docker\n\n"
        "<b>👨‍💻 РАЗРАБОТЧИК:</b>\n"
        "@A3incSTIGMAT\n\n"
        "<b>🗣️ ОБРАЩЕНИЯ:</b>\n"
        "• <i>Нексус, Нэкс, Nexus</i>\n"
        "• <i>Отметь, тэгни, упомяни, оповести</i>\n"
        "• <i>Собери, созывай, общий сбор</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ <i>Спасибо, что используете NEXUS!</i>"
    )
    msg = await message.answer(about_text, parse_mode=ParseMode.HTML)
    await delete_bot_message_after(message.bot, message.chat.id, msg.message_id, delay=30)


@router.message(Command("donate"))
async def cmd_donate(message: types.Message):
    """Поддержка разработчика — добровольный донат"""
    donate_text = f"""
❤️ <b>ПОДДЕРЖКА РАЗРАБОТЧИКА</b> ❤️

Спасибо, что хотите поддержать проект NEXUS Chat Manager!

━━━━━━━━━━━━━━━━━━━━━

<b>📌 НА ЧТО ИДУТ СРЕДСТВА:</b>

├ 🤖 Содержание серверов
├ 🎮 Разработка новых игр
├ ✨ Улучшение качества работы
├ 🐛 Исправление багов
└ 💡 Реализация новых функций

━━━━━━━━━━━━━━━━━━━━━

<b>💳 РЕКВИЗИТЫ ДЛЯ ПОДДЕРЖКИ:</b>

🏦 Банк: {DONATE_BANK}
👤 Получатель: {DONATE_RECEIVER}

📱 <b>СБП (быстро и без комиссии):</b>
<code>{DONATE_URL}</code>

━━━━━━━━━━━━━━━━━━━━━

<b>⚠️ ВАЖНО:</b>

• Это <b>ДОБРОВОЛЬНОЕ</b> пожертвование
• Оно не является платой за товары или услуги
• Вы не получаете за него игровые преимущества
• Все средства идут на развитие бота

━━━━━━━━━━━━━━━━━━━━━

💝 <b>Спасибо за поддержку NEXUS!</b>

Ваша помощь делает бота лучше!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 ПЕРЕЙТИ К ОПЛАТЕ", url=DONATE_URL)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(donate_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    is_admin = await is_admin_in_chat(callback.bot, user_id, chat_id) if callback.message.chat.type in ['group', 'supergroup'] else False
    
    await callback.message.edit_text(
        "🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS CHAT MANAGER</b>\n\n👇 Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(is_admin=is_admin)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    if not await is_admin_in_chat(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только администраторы имеют доступ!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "my_ref")
async def my_ref_callback(callback: types.CallbackQuery):
    from handlers.referral import my_referral_link
    
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


@router.callback_query(F.data == "confirm_delete")
async def confirm_delete(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    def _delete_user_data():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM transactions WHERE from_id = ? OR to_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM user_tag_subscriptions WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM referrals WHERE inviter_id = ? OR invitee_id = ?", (user_id, user_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    try:
        await asyncio.to_thread(_delete_user_data)
        await callback.message.edit_text(
            "✅ <b>ВАШИ ДАННЫЕ УДАЛЕНЫ!</b>\n\n"
            "Вы можете начать заново с <code>/start</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Data deletion failed for {user_id}: {e}")
        await callback.answer("❌ Ошибка при удалении данных", show_alert=True)


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено", reply_markup=back_button())
    await callback.answer()


@router.callback_query(F.data == "privacy")
async def privacy_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>\n\n"
        "📌 <b>Собираемые данные:</b>\n"
        "• Telegram ID\n"
        "• Имя пользователя\n"
        "• Баланс монет\n"
        "• Статистика игр\n\n"
        "📌 <b>Использование:</b>\n"
        "• Работа игр и экономики\n"
        "• Сохранение прогресса\n"
        "• Упоминания в чате\n\n"
        "📌 <b>Удаление данных:</b>\n"
        "<code>/delete_my_data</code>\n\n"
        "📌 <b>Контакты:</b>\n"
        "@A3incSTIGMAT",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤖 <b>NEXUS CHAT MANAGER — ПОМОЩЬ</b>\n\n"
        "<b>💰 ЭКОНОМИКА</b>\n"
        "<code>/balance</code> — баланс\n"
        "<code>/daily</code> — бонус дня\n"
        "<code>/transfer @user 100</code> — перевод\n\n"
        "<b>🎮 ИГРЫ</b>\n"
        "<code>/slot 100</code> — слот\n"
        "<code>/roulette 100 красный</code> — рулетка\n"
        "<code>/rps камень</code> — КНБ\n"
        "<code>/duel @user 100</code> — дуэль\n\n"
        "<b>📢 ОПОВЕЩЕНИЯ И ТЭГИ</b>\n"
        "<code>/all</code> — общий сбор (админы)\n"
        "<code>/tag @user</code> — упомянуть\n"
        "<code>/tagrole админы</code> — админам\n"
        "<code>/mytags</code> — мои подписки\n"
        "<code>/tagcat pubg текст</code> — вызов тега\n\n"
        "<b>🔗 РЕФЕРАЛКА</b>\n"
        "<code>/my_ref</code> — моя ссылка\n\n"
        "<b>❤️ ПОДДЕРЖКА</b>\n"
        "<code>/donate</code> — поддержать проект\n\n"
        "<b>🔒 ПРОЧЕЕ</b>\n"
        "<code>/privacy</code> — политика\n"
        "<code>/delete_my_data</code> — удалить данные",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data == "donate")
async def donate_callback(callback: types.CallbackQuery):
    """Кнопка поддержки из меню"""
    await cmd_donate(callback.message)
    await callback.answer()
