#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/start.py
# ВЕРСИЯ: 2.1.0-production
# ОПИСАНИЕ: Модуль навигации — /start, /help, /privacy, меню
# ИСПРАВЛЕНИЯ: Добавлена обработка команд с упоминанием бота
# ============================================

import html
import logging
from typing import Optional, Dict

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError

from database import db, DatabaseError
from config import START_BALANCE, ADMIN_IDS, BOT_USERNAME
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

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def is_admin_in_chat(bot: Bot, user_id: int, chat_id: int) -> bool:
    """
    Проверка прав администратора в чате.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        True если администратор, иначе False
    """
    if bot is None or user_id is None or chat_id is None:
        return False
    
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except TelegramAPIError as e:
        logger.warning(f"Admin check failed for {user_id} in {chat_id}: {e}")
        return False


async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict]:
    """
    Получить или создать пользователя.
    
    Args:
        user_id: ID пользователя
        username: Username
        first_name: Имя
        
    Returns:
        Словарь с данными пользователя или None при ошибке
    """
    if user_id is None:
        return None
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            logger.info(f"Created new user: {user_id}")
        return user
    except DatabaseError as e:
        logger.error(f"Database error in get_or_create_user: {e}")
        return None


async def get_user_stats_safe(user_id: int) -> Dict:
    """
    Безопасное получение статистики пользователя с fallback.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Словарь со статистикой
    """
    try:
        stats = await db.get_user_stats(user_id)
        if stats:
            return stats
    except DatabaseError as e:
        logger.error(f"Database error getting stats for {user_id}: {e}")
    
    return {
        'wins': 0,
        'games_played': 0,
    }


def format_welcome_message(first_name: str, is_new: bool = True) -> str:
    """
    Форматирует приветственное сообщение.
    
    Args:
        first_name: Имя пользователя
        is_new: Новый пользователь или существующий
        
    Returns:
        Отформатированный текст
    """
    safe_name = safe_html_escape(first_name)
    
    if is_new:
        return (
            "🤖 <b>ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!</b> 🤖\n\n"
            f"✨ <b>Привет, {safe_name}!</b>\n\n"
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
    else:
        return (
            f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
            f"👋 С возвращением, <b>{safe_name}!</b>\n"
            "👇 Выберите действие:"
        )


async def send_main_menu(
    target: Message | CallbackQuery,
    user_id: int,
    first_name: str,
    is_admin: bool = False,
    is_new: bool = False
) -> None:
    """
    Отправляет или редактирует главное меню с актуальной статистикой.
    
    Args:
        target: Сообщение или callback
        user_id: ID пользователя
        first_name: Имя пользователя
        is_admin: Является ли админом
        is_new: Новый пользователь
    """
    try:
        balance = await db.get_balance(user_id)
        user = await db.get_user(user_id)
        stats = await get_user_stats_safe(user_id)
        
        xo_wins = stats.get('wins', 0)
        xo_games = stats.get('games_played', 0)
        vip_level = user.get('vip_level', 0) if user else 0
        daily_streak = user.get('daily_streak', 0) if user else 0
        
        header = format_welcome_message(first_name, is_new)
        
        text = (
            f"{header}\n\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n"
            f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
            f"🎮 XO: <b>{xo_wins}</b> побед ({xo_games} игр)"
        )
        
        keyboard = main_menu(is_admin=is_admin)
        
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            msg = await target.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            chat_id = target.chat.id if target.chat else user_id
            await track_and_delete_bot_message(target.bot, chat_id, user_id, msg.message_id)
            
    except DatabaseError as e:
        logger.error(f"Database error in send_main_menu: {e}")
        text = "❌ Ошибка загрузки данных. Попробуйте позже."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await target.answer(text, parse_mode=ParseMode.HTML)


# ==================== КОМАНДА /start ====================

@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject) -> None:
    """Главная команда старта."""
    if message is None or message.from_user is None:
        return
    
    logger.info(f"🔥 /start triggered: user={message.from_user.id} chat={message.chat.id} args={command.args}")
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    chat_id = message.chat.id if message.chat else user_id
    
    # Обработка реферальной ссылки
    if command.args and command.args.startswith("ref_"):
        try:
            parts = command.args.split("_")
            if len(parts) == 3:
                ref_chat_id = int(parts[1])
                ref_code = parts[2]
                from handlers.referral import process_referral_start
                await process_referral_start(message, ref_chat_id, ref_code)
        except Exception as e:
            logger.error(f"Referral processing error: {e}")
    
    # Проверка прав администратора
    is_admin = False
    if message.chat and message.chat.type in ['group', 'supergroup']:
        is_admin = await is_admin_in_chat(message.bot, user_id, chat_id)
    
    # Получаем или создаем пользователя
    user = await db.get_user(user_id)
    is_new = user is None
    
    if is_new:
        try:
            await db.create_user(user_id, username, first_name, START_BALANCE)
        except DatabaseError as e:
            logger.error(f"Failed to create user {user_id}: {e}")
            await message.answer("❌ Ошибка регистрации. Попробуйте позже.")
            return
    
    await send_main_menu(message, user_id, first_name, is_admin, is_new)


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ С УПОМИНАНИЕМ БОТА ====================

@router.message(F.text)
async def handle_bot_mention(message: Message) -> None:
    """Обработчик сообщений с упоминанием бота."""
    if message is None or message.text is None:
        return
    
    text = message.text.lower()
    bot_username = BOT_USERNAME.lower() if BOT_USERNAME else "nexus_manager_official_bot"
    
    if f"@{bot_username}" not in text:
        return
    
    logger.info(f"🔔 Bot mentioned in: {text[:100]}")
    
    if text.startswith("/start"):
        args = text.replace(f"/start@{bot_username}", "").strip()
        await cmd_start(message, CommandObject(command="start", args=args))
    elif text.startswith("/help"):
        await cmd_help(message)
    elif text.startswith("/profile"):
        from handlers.profile import cmd_profile
        await cmd_profile(message)
    elif text.startswith("/balance"):
        from handlers.economy import cmd_balance
        await cmd_balance(message)
    elif text.startswith("/daily"):
        from handlers.economy import cmd_daily
        await cmd_daily(message)
    elif text.startswith("/stats"):
        from handlers.stats import cmd_stats
        await cmd_stats(message)
    elif text.startswith("/top"):
        from handlers.stats import cmd_top
        await cmd_top(message)
    elif text.startswith("/xo"):
        from handlers.tictactoe import cmd_xo
        await cmd_xo(message)


# ==================== КОМАНДА /help ====================

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Команда помощи."""
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
        "<code>/daily</code> — ежедневный бонус\n"
        "<code>/balance</code> — проверить баланс\n"
        "<code>/stats</code> — статистика\n"
        "<code>/top</code> — топы\n"
        "<code>/help</code> — эта помощь\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎮 КРЕСТИКИ-НОЛИКИ:</b>\n"
        "├ Игра с ботом (3 уровня сложности)\n"
        "├ Игра с игроком (дуэли)\n"
        "├ Ставки на NCoin\n"
        "└ Статистика и топы\n\n"
        "<b>👤 ПРОФИЛЬ:</b>\n"
        "├ Анкета\n"
        "├ VIP статус\n"
        "├ Ранг и прогресс\n"
        "└ Статистика игр\n\n"
        "<b>❤️ ПОДДЕРЖКА:</b>\n"
        "└ Кнопка «ПОДДЕРЖАТЬ» в главном меню\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <b>Совет:</b> Всё доступно через кнопки в главном меню!\n"
        "Нажмите /start чтобы открыть меню.\n\n"
        f"📌 <i>В группах используйте команды с упоминанием бота: /start@{BOT_USERNAME}</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
    ])
    
    msg = await message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await delete_bot_message_after(message.bot, message.chat.id, msg.message_id, delay=60)


# ==================== КОМАНДА /privacy ====================

@router.message(Command("privacy"))
async def cmd_privacy(message: Message) -> None:
    """Политика конфиденциальности."""
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
async def cmd_delete_my_data(message: Message) -> None:
    """Запрос на удаление данных."""
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


@router.callback_query(F.data == "confirm_delete")
async def confirm_delete(callback: CallbackQuery) -> None:
    """Подтверждение удаления данных."""
    if callback is None:
        return
    
    user_id = callback.from_user.id
    
    try:
        await db.cleanup_bot_from_all_tables(user_id)
        
        if callback.message:
            await callback.message.edit_text(
                "✅ <b>ВАШИ ДАННЫЕ УДАЛЕНЫ!</b>\n\n"
                "Вы можете начать заново с /start",
                parse_mode=ParseMode.HTML
            )
        logger.info(f"User {user_id} deleted their data")
        
    except DatabaseError as e:
        logger.error(f"Data deletion failed for {user_id}: {e}")
        await callback.answer("❌ Ошибка при удалении", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error deleting data: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery) -> None:
    """Отмена удаления данных."""
    if callback is None or callback.message is None:
        return
    
    await callback.message.edit_text("❌ Удаление отменено", reply_markup=back_button())
    await callback.answer()


# ==================== ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ ====================

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery) -> None:
    """Возврат в главное меню."""
    if callback is None or callback.message is None:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    first_name = callback.from_user.first_name or "Пользователь"
    
    is_admin = False
    if callback.message.chat and callback.message.chat.type in ['group', 'supergroup']:
        is_admin = await is_admin_in_chat(callback.bot, user_id, chat_id)
    
    await send_main_menu(callback, user_id, first_name, is_admin, is_new=False)
    await callback.answer()


@router.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: CallbackQuery) -> None:
    """Открытие админ-панели."""
    if callback is None or callback.message is None:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    
    if not await is_admin_in_chat(callback.bot, user_id, chat_id):
        await callback.answer("❌ Только администраторы имеют доступ!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\nУправление ботом и чатом:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_panel_menu()
    )
    await callback.answer()


# ==================== КАТЕГОРИИ МЕНЮ ====================

@router.callback_query(F.data == "games_category")
async def games_category_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "🎮 <b>КРЕСТИКИ-НОЛИКИ</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=games_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "profile_category")
async def profile_category_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "👤 <b>ПРОФИЛЬ</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=profile_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "finance_category")
async def finance_category_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "💰 <b>ФИНАНСЫ</b>\n\nУправление балансом:",
        parse_mode=ParseMode.HTML,
        reply_markup=finance_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "social_category")
async def social_category_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "👥 <b>СОЦИАЛКА</b>\n\nОтношения, группы, РП:",
        parse_mode=ParseMode.HTML,
        reply_markup=social_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "notifications_category")
async def notifications_category_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
        return
    await callback.message.edit_text(
        "📢 <b>ОПОВЕЩЕНИЯ</b>\n\nУправление тегами:",
        parse_mode=ParseMode.HTML,
        reply_markup=notifications_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "settings_category")
async def settings_category_callback(callback: CallbackQuery) -> None:
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
async def feedback_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Меню обратной связи."""
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
async def cancel_feedback_command(message: Message, state: FSMContext) -> None:
    """Отмена обратной связи."""
    if message is None:
        return
    
    current_state = await state.get_state()
    
    if current_state == FeedbackState.waiting_for_message:
        data = await state.get_data()
        prompt_id = data.get('prompt_msg_id')
        if prompt_id:
            try:
                await message.bot.delete_message(message.chat.id, prompt_id)
            except TelegramAPIError:
                pass
        await state.clear()
        await message.answer("❌ Отправка обратной связи отменена.")
    else:
        await message.answer("ℹ️ Нет активной операции.")


@router.message(FeedbackState.waiting_for_message)
async def process_feedback_message(message: Message, state: FSMContext) -> None:
    """Обработка сообщения обратной связи."""
    if message is None or message.from_user is None:
        return
    
    data = await state.get_data()
    prompt_id = data.get('prompt_msg_id')
    
    if prompt_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except TelegramAPIError:
            pass
    
    feedback_text = (message.text or "").strip()
    
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
                    f"👤 От: {safe_html_escape(message.from_user.full_name)}\n"
                    f"🆔 ID: <code>{message.from_user.id}</code>\n"
                    f"💬 Сообщение:\n{safe_html_escape(feedback_text)}",
                    parse_mode=ParseMode.HTML
                )
            except TelegramAPIError as e:
                logger.warning(f"Failed to send feedback to admin {admin_id}: {e}")
    
    await message.answer(
        "✅ <b>Спасибо за обратную связь!</b>\n\n"
        "Ваше сообщение отправлено разработчику.",
        parse_mode=ParseMode.HTML
    )
    await state.clear()


# ==================== ПРОКСИ-КОЛЛБЭКИ ====================

@router.callback_query(F.data == "privacy")
async def privacy_callback(callback: CallbackQuery) -> None:
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
async def help_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    await cmd_help(callback.message)
    await callback.answer()


# ==================== ДОНАТ ====================

@router.message(Command("donate"))
async def cmd_donate_proxy(message: Message) -> None:
    if message is None:
        return
    from handlers.economy import cmd_donate as economy_donate
    await economy_donate(message)


@router.callback_query(F.data == "donate")
async def donate_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.economy import cmd_donate as economy_donate
    await economy_donate(callback.message)
    await callback.answer()


# ==================== ПРОКСИ ДЛЯ ДРУГИХ МОДУЛЕЙ ====================

@router.callback_query(F.data == "my_stats")
async def my_stats_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.profile import my_stats_callback as target
    await target(callback)


@router.callback_query(F.data == "rank_menu")
async def rank_menu_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.ranks import cmd_rank
    await cmd_rank(callback.message)
    await callback.answer()


@router.callback_query(F.data == "private_games")
async def private_games_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.tictactoe import cmd_xo
    await cmd_xo(callback.message)
    await callback.answer()


@router.callback_query(F.data == "top_chats")
async def top_chats_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.rating import cmd_top_chats
    await cmd_top_chats(callback.message)
    await callback.answer()


@router.callback_query(F.data == "relationships_menu")
async def relationships_menu_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
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
async def groups_menu_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
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
async def rp_menu_callback(callback: CallbackQuery) -> None:
    if callback is None or callback.message is None:
        return
    from handlers.smart_commands import cmd_my_custom_rp
    await cmd_my_custom_rp(callback.message)
    await callback.answer()


@router.callback_query(F.data == "my_tags_menu")
async def my_tags_menu_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    try:
        from handlers.tag_user import cmd_mytags
        await cmd_mytags(callback.message)
    except Exception as e:
        logger.error(f"Error in my_tags_menu: {e}")
        if callback.message:
            await callback.message.edit_text(
                "❌ <b>Ошибка загрузки тегов</b>\n\nИспользуйте /mytags",
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
    await callback.answer()


@router.callback_query(F.data == "start_all")
async def start_all_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.tag import cmd_all
    await cmd_all(callback.message)
    await callback.answer()


@router.callback_query(F.data == "my_ref")
async def my_ref_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.referral import my_referral_link
    await my_referral_link(callback.message)
    await callback.answer()


@router.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: CallbackQuery) -> None:
    if callback is None:
        return
    from handlers.referral import ref_menu_callback as target
    await target(callback)
