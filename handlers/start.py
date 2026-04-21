# ============================================
# ФАЙЛ: handlers/start.py
# ОПИСАНИЕ: Модуль навигации, старта, помощи
# ИСПРАВЛЕНО: Статистика побед из xo_stats вместо users.wins/losses
# ЗАЩИТА ОТ NULL: ПОЛНАЯ
# ============================================

import asyncio
import logging
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from config import START_BALANCE, ADMIN_IDS
from utils.auto_delete import track_and_delete_bot_message, delete_bot_message_after
from utils.keyboards import (
    main_menu, back_button, games_category_menu, profile_category_menu,
    finance_category_menu, social_category_menu, notifications_category_menu,
    settings_category_menu, admin_panel_menu
)

router = Router()
logger = logging.getLogger(__name__)


# ==================== FSM ДЛЯ ОБРАТНОЙ СВЯЗИ ====================

class FeedbackState(StatesGroup):
    waiting_for_message = State()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def _escape_html(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_markdown(text: str | None) -> str:
    if not text:
        return ""
    chars = "_*[]()~`>#+-=|{}.!"
    for char in chars:
        text = text.replace(char, f"\\{char}")
    return text


async def is_admin_in_chat(bot: Bot, user_id: int, chat_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception as e:
        logger.warning(f"Admin check failed for {user_id} in {chat_id}: {e}")
        return False


async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
    return user


# ==================== КОМАНДА /start ====================

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if message is None:
        return
        
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    chat_id = message.chat.id
    
    # Рефералка
    args = message.text.split() if message.text else []
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
        
        welcome_text = (
            "🤖 <b>ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!</b> 🤖\n\n"
            f"✨ <b>Привет, {_escape_html(first_name)}!</b>\n\n"
            "Я — <b>NEXUS Chat Manager</b> — твой личный помощник в чате!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🎯 ЧТО Я УМЕЮ:</b>\n\n"
            "├ 🎮 <b>Крестики-нолики</b> — играй с ботом и друзьями\n"
            "├ 💰 <b>Экономика</b> — баланс, переводы, бонусы\n"
            "├ 📢 <b>Общий сбор</b> — оповещение всех участников\n"
            "├ 🏷️ <b>Умные теги</b> — поиск игроков по категориям\n"
            "├ 💕 <b>Отношения</b> — создавай пары и группы\n"
            "├ 🏆 <b>Ранги</b> — повышай уровень, получай бонусы\n"
            "└ ❤️ <b>Поддержка</b> — помоги развитию проекта\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🗣️ УМНЫЕ КОМАНДЫ (пишите в чат):</b>\n\n"
            "• <code>Нексус, оповести всех</code>\n"
            "• <code>Nexus, найди сквад в PUBG</code>\n"
            "• <code>Нексус, собери пати в доту</code>\n"
            "• <code>Бот, нужен совет</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>📌 БЫСТРЫЙ СТАРТ:</b>\n\n"
            "├ <code>/daily</code> — получить бонус\n"
            "├ <code>/balance</code> — проверить баланс\n"
            "└ <code>/help</code> — помощь\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 <b>ВАМ НАЧИСЛЕНО: {START_BALANCE} NCOIN!</b>\n\n"
            "👇 <b>Используйте кнопки ниже для навигации</b>"
        )
        
        msg = await message.answer(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(is_admin=is_admin)
        )
        await track_and_delete_bot_message(message.bot, chat_id, user_id, msg.message_id, delay=60)
    else:
        # 🔥 ПОЛУЧАЕМ СВЕЖИЙ БАЛАНС И СТАТИСТИКУ XO
        balance = await db.get_balance(user_id)
        xo_stats = await db.get_user_stats(user_id)
        
        xo_wins = xo_stats.get('wins', 0) if xo_stats else 0
        xo_games = xo_stats.get('games_played', 0) if xo_stats else 0
        vip_level = user.get('vip_level', 0) or 0
        daily_streak = user.get('daily_streak', 0) or 0
        
        msg = await message.answer(
            f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
            f"👋 С возвращением, <b>{_escape_html(first_name)}</b>!\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n"
            f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
            f"🎮 XO: <b>{xo_wins}</b> побед ({xo_games} игр)\n\n"
            "👇 Выберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(is_admin=is_admin)
        )
        await track_and_delete_bot_message(message.bot, chat_id, user_id, msg.message_id, delay=30)


# ==================== КОМАНДА /help ====================

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if message is None:
        return
        
    help_text = (
        "🤖 <b>NEXUS CHAT MANAGER — ПОМОЩЬ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🗣️ УМНЫЕ КОМАНДЫ (пишите в чат):</b>\n\n"
        "• <code>Нексус, оповести всех</code> — общий сбор\n"
        "• <code>Nexus, общий сбор</code>\n"
        "• <code>Нексус, найди сквад в PUBG</code>\n"
        "• <code>Нексус, собери пати в доту</code>\n"
        "• <code>Нексус, ищу напарников в CS2</code>\n"
        "• <code>Бот, нужен совет</code>\n"
        "• <code>Нексус, розыгрыш</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📌 ОСНОВНЫЕ КОМАНДЫ (с /):</b>\n\n"
        "<code>/start</code> — главное меню с кнопками\n"
        "<code>/daily</code> — ежедневный бонус (+100-500 NCoin)\n"
        "<code>/balance</code> — проверить баланс\n"
        "<code>/help</code> — эта помощь\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎮 КРЕСТИКИ-НОЛИКИ (через меню):</b>\n"
        "├ Игра с ботом (3 уровня сложности)\n"
        "├ Игра с игроком (дуэли)\n"
        "├ Ставки на NCoin\n"
        "└ Статистика и топы\n\n"
        "<b>👤 ПРОФИЛЬ (через меню):</b>\n"
        "├ Анкета\n"
        "├ VIP статус\n"
        "├ Ранг и прогресс\n"
        "└ Статистика игр\n\n"
        "<b>📢 ОПОВЕЩЕНИЯ (через меню):</b>\n"
        "├ Общий сбор (для админов)\n"
        "├ Мои теги — управление подписками\n"
        "└ Топ чатов\n\n"
        "<b>💕 СОЦИАЛКА (через меню):</b>\n"
        "├ Отношения (пары)\n"
        "├ Группы\n"
        "└ РП команды\n\n"
        "<b>❤️ ПОДДЕРЖКА:</b>\n"
        "└ Кнопка «ПОДДЕРЖАТЬ» в главном меню\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <b>Совет:</b> Всё доступно через кнопки в главном меню!\n"
        "Нажмите /start чтобы открыть меню."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
    ])
    
    msg = await message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await delete_bot_message_after(message.bot, message.chat.id, msg.message_id, delay=60)


# ==================== КОМАНДА /privacy ====================

@router.message(Command("privacy"))
async def cmd_privacy(message: types.Message):
    if message is None:
        return
        
    privacy_text = (
        "🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📌 КАКИЕ ДАННЫЕ СОБИРАЮТСЯ:</b>\n"
        "├ Telegram ID\n"
        "├ Имя пользователя\n"
        "├ Баланс монет\n"
        "├ Статистика игр\n"
        "├ Ранг и XP\n"
        "└ Данные анкеты (если заполнены)\n\n"
        "<b>📌 КАК ИСПОЛЬЗУЮТСЯ:</b>\n"
        "├ Для работы игр и экономики\n"
        "├ Для сохранения прогресса\n"
        "└ Для упоминаний в общем сборе\n\n"
        "<b>📌 ХРАНЕНИЕ:</b>\n"
        "├ Данные хранятся в зашифрованной БД\n"
        "├ Не передаются третьим лицам\n"
        "└ Удаляются по команде /delete_my_data\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ <b>ВСЕ ДАННЫЕ ХРАНЯТСЯ ТОЛЬКО В БОТЕ</b>"
    )
    await message.answer(privacy_text, parse_mode=ParseMode.HTML)


# ==================== КОМАНДА /delete_my_data ====================

@router.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: types.Message):
    if message is None:
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА, УДАЛИТЬ", callback_data="confirm_delete"),
         InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_delete")]
    ])
    
    await message.answer(
        "⚠️ <b>УДАЛЕНИЕ ДАННЫХ</b>\n\n"
        "Вы уверены? Будут удалены:\n"
        "├ Баланс монет\n"
        "├ Статистика игр\n"
        "├ Ранг и XP\n"
        "├ Анкета\n"
        "├ Отношения и группы\n"
        "└ История транзакций\n\n"
        "❗ Это действие <b>НЕЛЬЗЯ</b> отменить!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


# ==================== ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ ====================

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    is_admin = False
    if callback.message.chat.type in ['group', 'supergroup']:
        is_admin = await is_admin_in_chat(callback.bot, user_id, chat_id)
    
    await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    
    # 🔥 СВЕЖИЙ БАЛАНС И СТАТИСТИКА XO
    balance = await db.get_balance(user_id)
    user = await db.get_user(user_id)
    xo_stats = await db.get_user_stats(user_id)
    
    xo_wins = xo_stats.get('wins', 0) if xo_stats else 0
    xo_games = xo_stats.get('games_played', 0) if xo_stats else 0
    vip_level = user.get('vip_level', 0) if user else 0
    daily_streak = user.get('daily_streak', 0) if user else 0
    
    await callback.message.edit_text(
        f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
        f"💰 Баланс: <b>{balance}</b> NCoin\n"
        f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n"
        f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
        f"🎮 XO: <b>{xo_wins}</b> побед ({xo_games} игр)\n\n"
        f"👇 Выберите категорию:",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(is_admin=is_admin)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    if not await is_admin_in_chat(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только администраторы имеют доступ!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        "Управление ботом и чатом:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_panel_menu()
    )
    await callback.answer()


# ==================== ОБРАБОТЧИКИ КАТЕГОРИЙ МЕНЮ ====================

@router.callback_query(F.data == "games_category")
async def games_category_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=games_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "profile_category")
async def profile_category_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "👤 <b>ПРОФИЛЬ</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=profile_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "finance_category")
async def finance_category_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "💰 <b>ФИНАНСЫ</b>\n\nУправление балансом:",
        parse_mode=ParseMode.HTML,
        reply_markup=finance_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "social_category")
async def social_category_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "👥 <b>СОЦИАЛКА</b>\n\nОтношения, группы, РП:",
        parse_mode=ParseMode.HTML,
        reply_markup=social_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "notifications_category")
async def notifications_category_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "📢 <b>ОПОВЕЩЕНИЯ</b>\n\nУправление тегами:",
        parse_mode=ParseMode.HTML,
        reply_markup=notifications_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "settings_category")
async def settings_category_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "⚙️ <b>НАСТРОЙКИ</b>\n\nПомощь и информация:",
        parse_mode=ParseMode.HTML,
        reply_markup=settings_category_menu()
    )
    await callback.answer()


# ==================== ОБРАТНАЯ СВЯЗЬ ====================

@router.callback_query(F.data == "feedback_menu")
async def feedback_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback is None or callback.message is None:
        return
        
    await state.set_state(FeedbackState.waiting_for_message)
    
    msg = await callback.message.answer(
        "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\n"
        "Напишите ваше сообщение в ответ.\n\n"
        "📌 <i>Что можно написать:</i>\n"
        "• Предложение по улучшению\n"
        "• Сообщение об ошибке\n"
        "• Вопрос по работе бота\n\n"
        "❌ Для отмены: /cancel",
        parse_mode=ParseMode.HTML
    )
    await state.update_data(prompt_msg_id=msg.message_id)
    await callback.answer()


@router.message(Command("cancel"))
async def cancel_feedback_command(message: types.Message, state: FSMContext):
    if message is None:
        return
        
    current_state = await state.get_state()
    
    if current_state == FeedbackState.waiting_for_message:
        data = await state.get_data()
        if prompt_id := data.get('prompt_msg_id'):
            try:
                await message.bot.delete_message(message.chat.id, prompt_id)
            except:
                pass
        await state.clear()
        await message.answer("❌ Отправка обратной связи отменена.")
    else:
        await message.answer("ℹ️ Нет активной операции.")


@router.message(FeedbackState.waiting_for_message)
async def process_feedback_message(message: types.Message, state: FSMContext):
    if message is None:
        return
        
    data = await state.get_data()
    
    if prompt_id := data.get('prompt_msg_id'):
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except:
            pass
    
    feedback_text = message.text.strip() if message.text else ""
    
    if feedback_text == '/cancel':
        await state.clear()
        await message.answer("❌ Отправка обратной связи отменена.")
        return
    
    if len(feedback_text) < 5:
        await message.answer("❌ Слишком короткое сообщение!")
        await state.clear()
        return
    
    if ADMIN_IDS:
        for admin_id in ADMIN_IDS:
            if admin_id is None:
                continue
            try:
                await message.bot.send_message(
                    admin_id,
                    f"📝 <b>НОВЫЙ ОТЗЫВ</b>\n\n"
                    f"👤 От: {_escape_html(message.from_user.full_name)}\n"
                    f"🆔 ID: <code>{message.from_user.id}</code>\n"
                    f"💬 Сообщение:\n{_escape_html(feedback_text)}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    await message.answer(
        "✅ <b>Спасибо за обратную связь!</b>\n\n"
        "Ваше сообщение отправлено разработчику.",
        parse_mode=ParseMode.HTML
    )
    await state.clear()


# ==================== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ====================

@router.callback_query(F.data == "confirm_delete")
async def confirm_delete(callback: types.CallbackQuery):
    if callback is None:
        return
        
    user_id = callback.from_user.id
    
    def _delete_user_data():
        conn = db._get_connection()
        if conn is None:
            return
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM transactions WHERE from_id = ? OR to_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM user_tag_subscriptions WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM ref_links WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM ref_invites WHERE inviter_id = ? OR invited_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM user_ranks WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM xo_stats WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_economy_stats WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM relationships WHERE user1_id = ? OR user2_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM group_members WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM custom_rp WHERE user_id = ?", (user_id,))
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
            "Вы можете начать заново с /start",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Data deletion failed: {e}")
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text("❌ Удаление отменено", reply_markup=back_button())
    await callback.answer()


@router.callback_query(F.data == "privacy")
async def privacy_callback(callback: types.CallbackQuery):
    if callback is None or callback.message is None:
        return
        
    await callback.message.edit_text(
        "🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>\n\n"
        "📌 <b>Собираемые данные:</b>\n"
        "• Telegram ID\n• Имя пользователя\n• Баланс\n• Статистика игр\n\n"
        "📌 <b>Удаление:</b> /delete_my_data",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    if callback is None:
        return
        
    await cmd_help(callback.message)
    await callback.answer()


# ==================== ДОНАТ — ПЕРЕАДРЕСАЦИЯ В ECONOMY ====================

@router.message(Command("donate"))
async def cmd_donate_proxy(message: types.Message):
    if message is None:
        return
        
    from handlers.economy import cmd_donate as economy_donate
    await economy_donate(message)


@router.callback_query(F.data == "donate")
async def donate_callback(callback: types.CallbackQuery):
    if callback is None:
        return
        
    from handlers.economy import cmd_donate as economy_donate
    await economy_donate(callback.message)
    await callback.answer()


# ==================== ПРОКСИ-КОЛЛБЭКИ ДЛЯ ДРУГИХ МОДУЛЕЙ ====================

@router.callback_query(F.data == "my_stats")
async def my_stats_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.profile import my_stats_callback as target
    await target(callback)


@router.callback_query(F.data == "rank_menu")
async def rank_menu_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.ranks import cmd_rank
    await cmd_rank(callback.message)
    await callback.answer()


@router.callback_query(F.data == "private_games")
async def private_games_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.tictactoe import cmd_xo
    await cmd_xo(callback.message)
    await callback.answer()


@router.callback_query(F.data == "top_chats")
async def top_chats_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.rating import cmd_top_chats
    await cmd_top_chats(callback.message)
    await callback.answer()


@router.callback_query(F.data == "relationships_menu")
async def relationships_menu_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    await callback.message.edit_text(
        "💕 <b>ОТНОШЕНИЯ</b>\n\n"
        "Этот раздел в разработке.\n"
        "Скоро здесь можно будет создавать пары и семьи!",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data == "groups_menu")
async def groups_menu_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    await callback.message.edit_text(
        "👥 <b>ГРУППЫ</b>\n\n"
        "Этот раздел в разработке.\n"
        "Скоро здесь можно будет создавать группы!",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data == "rp_menu")
async def rp_menu_callback(callback: types.CallbackQuery):
    """Кнопка РП КОМАНДЫ — показывает кастомные РП команды"""
    if callback is None:
        return
    from handlers.smart_commands import cmd_my_custom_rp
    await cmd_my_custom_rp(callback.message)
    await callback.answer()


@router.callback_query(F.data == "my_tags_menu")
async def my_tags_menu_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.tag_user import cmd_mytags
    try:
        await cmd_mytags(callback.message)
    except Exception as e:
        logger.error(f"Error in my_tags_menu: {e}")
        await callback.message.edit_text(
            "❌ <b>Ошибка загрузки тегов</b>\n\nИспользуйте /mytags",
            parse_mode=ParseMode.HTML,
            reply_markup=back_button()
        )
    await callback.answer()


@router.callback_query(F.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.tag import cmd_all
    await cmd_all(callback.message)
    await callback.answer()


@router.callback_query(F.data == "my_ref")
async def my_ref_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.referral import my_referral_link
    await my_referral_link(callback.message)
    await callback.answer()


@router.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: types.CallbackQuery):
    if callback is None:
        return
    from handlers.referral import ref_menu_callback
    await ref_menu_callback(callback)
