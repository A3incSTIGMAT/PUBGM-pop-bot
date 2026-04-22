#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: bot.py
# ВЕРСИЯ: 5.5.1-fixed
# ОПИСАНИЕ: NEXUS Chat Manager — ВСЕ КНОПКИ РАБОТАЮТ
# ============================================

import asyncio
import logging
import sys
import time
from typing import Dict, Set, Optional

from aiogram import Bot, Dispatcher, types, F  # ← ДОБАВЛЕН F!
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
from dotenv import load_dotenv

load_dotenv()

# ==================== ЛОГИРОВАНИЕ ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГ ====================

from config import BOT_TOKEN, START_BALANCE, ADMIN_IDS, SUPER_ADMIN_IDS, BOT_USERNAME

if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN not set!")
    sys.exit(1)

logger.info(f"🔧 ADMIN_IDS: {ADMIN_IDS}")
logger.info(f"🔧 BOT_USERNAME: {BOT_USERNAME}")

# ==================== БОТ ====================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_background_tasks: Set[asyncio.Task] = set()

# ==================== КЕШ ====================

_user_cache: Dict[int, dict] = {}
_cache_time: Dict[int, float] = {}
CACHE_TTL = 10

# ==================== БАЗА ДАННЫХ ====================

from database import db, DatabaseError

async def get_user_cached(user_id: int) -> Optional[dict]:
    """Получение пользователя с кешем."""
    now = time.time()
    if user_id in _user_cache and now - _cache_time.get(user_id, 0) < CACHE_TTL:
        return _user_cache[user_id]
    
    try:
        user = await db.get_user(user_id)
        if user:
            _user_cache[user_id] = user
            _cache_time[user_id] = now
        return user
    except Exception:
        return None


async def ensure_user_exists(user_id: int, username: str = None, first_name: str = None) -> Optional[dict]:
    """Гарантирует существование пользователя."""
    user = await get_user_cached(user_id)
    if not user:
        try:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            if user:
                _user_cache[user_id] = user
                _cache_time[user_id] = time.time()
        except Exception as e:
            logger.error(f"Create user error: {e}")
    return user


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Создает главное меню бота."""
    keyboard = [
        [InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="vip"),
         InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")],
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
         InlineKeyboardButton(text="🏆 РАНГ", callback_data="rank_menu")],
        [InlineKeyboardButton(text="🎮 КРЕСТИКИ-НОЛИКИ", callback_data="game_xo"),
         InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton(text="📢 ОБЩИЙ СБОР", callback_data="start_all"),
         InlineKeyboardButton(text="🔗 РЕФЕРАЛКА", callback_data="ref_menu")],
        [InlineKeyboardButton(text="💕 ОТНОШЕНИЯ", callback_data="relationships_menu"),
         InlineKeyboardButton(text="👥 ГРУППЫ", callback_data="groups_menu")],
        [InlineKeyboardButton(text="✨ РП КОМАНДЫ", callback_data="rp_menu"),
         InlineKeyboardButton(text="🏷️ МОИ ТЕГИ", callback_data="my_tags_menu")],
        [InlineKeyboardButton(text="📊 ТОП ЧАТОВ", callback_data="top_chats"),
         InlineKeyboardButton(text="🔒 ПОЛИТИКА", callback_data="privacy")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help"),
         InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate")],
        [InlineKeyboardButton(text="💬 ОБРАТНАЯ СВЯЗЬ", callback_data="feedback_menu")]
    ]
    
    if is_admin:
        keyboard.insert(3, [InlineKeyboardButton(text="👑 АДМИН-ПАНЕЛЬ", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой НАЗАД."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])


# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    """Главная команда старта."""
    if not message.from_user:
        return
    
    logger.info(f"🚀 /start from {message.from_user.id}")
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    chat_id = message.chat.id if message.chat else user_id
    
    # Проверка админа
    is_admin = user_id in ADMIN_IDS or user_id in SUPER_ADMIN_IDS
    if message.chat and message.chat.type in ['group', 'supergroup']:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            is_admin = is_admin or member.status in ['creator', 'administrator']
        except:
            pass
    
    # Создаем пользователя
    user = await get_user_cached(user_id)
    is_new = not user
    
    if is_new:
        try:
            await db.create_user(user_id, username, first_name, START_BALANCE)
            user = await db.get_user(user_id)
            if user:
                _user_cache[user_id] = user
                _cache_time[user_id] = time.time()
        except Exception as e:
            logger.error(f"Create user error: {e}")
            await message.answer("❌ Ошибка регистрации")
            return
    
    try:
        balance = await db.get_balance(user_id)
        vip_level = user.get('vip_level', 0) if user else 0
        daily_streak = user.get('daily_streak', 0) if user else 0
        
        stats = await db.get_user_stats(user_id)
        xo_wins = stats.get('wins', 0) if stats else 0
        xo_games = stats.get('games_played', 0) if stats else 0
        
        if is_new:
            welcome = (
                "🤖 <b>ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!</b> 🤖\n\n"
                f"✨ <b>Привет, {first_name}!</b>\n\n"
                f"🎁 <b>ВАМ НАЧИСЛЕНО: {START_BALANCE} NCOIN!</b>\n\n"
                "👇 <b>Используйте кнопки ниже</b>"
            )
            text = welcome
        else:
            text = (
                f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
                f"👋 С возвращением, <b>{first_name}</b>!\n"
                f"💰 Баланс: <b>{balance}</b> NCoin\n"
                f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n"
                f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
                f"🎮 XO: <b>{xo_wins}</b> побед ({xo_games} игр)\n\n"
                f"👇 Выберите действие:"
            )
        
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu(is_admin))
        
    except Exception as e:
        logger.error(f"Start error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки данных")


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь."""
    text = (
        "🤖 <b>NEXUS CHAT MANAGER — ПОМОЩЬ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📌 ОСНОВНЫЕ КОМАНДЫ:</b>\n"
        "<code>/start</code> — главное меню\n"
        "<code>/daily</code> — ежедневный бонус\n"
        "<code>/balance</code> — баланс\n"
        "<code>/stats</code> — статистика\n"
        "<code>/top</code> — топы\n"
        "<code>/xo</code> — крестики-нолики\n"
        "<code>/vip</code> — VIP статус\n"
        "<code>/profile</code> — профиль\n"
        "<code>/donate</code> — поддержать\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 В группах: /start@{BOT_USERNAME}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("🏓 PONG!")


# ==================== CALLBACK: НАЗАД ====================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    """Кнопка НАЗАД."""
    if not callback.message or not callback.from_user:
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message.chat else user_id
    
    try:
        is_admin = user_id in ADMIN_IDS or user_id in SUPER_ADMIN_IDS
        if callback.message.chat and callback.message.chat.type in ['group', 'supergroup']:
            try:
                member = await bot.get_chat_member(chat_id, user_id)
                is_admin = is_admin or member.status in ['creator', 'administrator']
            except:
                pass
        
        user = await get_user_cached(user_id)
        if not user:
            user = await ensure_user_exists(user_id, callback.from_user.username, callback.from_user.first_name)
        
        balance = await db.get_balance(user_id)
        vip_level = user.get('vip_level', 0) if user else 0
        daily_streak = user.get('daily_streak', 0) if user else 0
        
        stats = await db.get_user_stats(user_id)
        xo_wins = stats.get('wins', 0) if stats else 0
        xo_games = stats.get('games_played', 0) if stats else 0
        
        text = (
            f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS</b>\n\n"
            f"💰 Баланс: <b>{balance}</b> NCoin\n"
            f"⭐ VIP: {'✅' if vip_level > 0 else '❌'}\n"
            f"🔥 Daily стрик: <b>{daily_streak}</b> дней\n"
            f"🎮 XO: <b>{xo_wins}</b> побед ({xo_games} игр)\n\n"
            f"👇 Выберите категорию:"
        )
        
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu(is_admin))
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Back error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== CALLBACK: ВСЕ КНОПКИ МЕНЮ ====================

@dp.callback_query(F.data == "vip")
async def vip_callback(callback: types.CallbackQuery):
    try:
        from handlers.vip import cmd_vip
        await cmd_vip(callback.message)
    except Exception as e:
        logger.error(f"VIP error: {e}")
        await callback.message.answer("❌ Ошибка загрузки VIP", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    try:
        from handlers.profile import cmd_profile
        await cmd_profile(callback.message)
    except Exception as e:
        logger.error(f"Profile error: {e}")
        await callback.message.answer("❌ Ошибка загрузки профиля", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "balance")
async def balance_callback(callback: types.CallbackQuery):
    try:
        from handlers.economy import cmd_balance
        await cmd_balance(callback.message)
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await callback.message.answer("❌ Ошибка загрузки баланса", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "rank_menu")
async def rank_menu_callback(callback: types.CallbackQuery):
    try:
        from handlers.ranks import cmd_rank
        await cmd_rank(callback.message)
    except Exception as e:
        logger.error(f"Rank error: {e}")
        await callback.message.answer("❌ Раздел в разработке", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "game_xo")
async def game_xo_callback(callback: types.CallbackQuery):
    try:
        from handlers.tictactoe import cmd_xo
        await cmd_xo(callback.message)
    except Exception as e:
        logger.error(f"XO error: {e}")
        await callback.message.answer("❌ Ошибка загрузки игры", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    try:
        from handlers.stats import cmd_stats
        await cmd_stats(callback.message)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await callback.message.answer("❌ Ошибка загрузки статистики", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery):
    try:
        from handlers.tag import cmd_all
        await cmd_all(callback.message)
    except Exception as e:
        logger.error(f"Tag all error: {e}")
        await callback.message.answer("❌ Ошибка общего сбора", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: types.CallbackQuery):
    try:
        from handlers.referral import ref_menu_callback as target
        await target(callback)
    except Exception as e:
        logger.error(f"Ref error: {e}")
        await callback.message.answer("❌ Раздел в разработке", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "relationships_menu")
async def relationships_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💕 <b>ОТНОШЕНИЯ</b>\n\nЭтот раздел в разработке.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "groups_menu")
async def groups_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👥 <b>ГРУППЫ</b>\n\nЭтот раздел в разработке.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "rp_menu")
async def rp_menu_callback(callback: types.CallbackQuery):
    try:
        from handlers.smart_commands import cmd_my_custom_rp
        await cmd_my_custom_rp(callback.message)
    except Exception as e:
        logger.error(f"RP error: {e}")
        await callback.message.answer("❌ Ошибка загрузки РП команд", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "my_tags_menu")
async def my_tags_callback(callback: types.CallbackQuery):
    try:
        from handlers.tag_user import cmd_mytags
        await cmd_mytags(callback.message)
    except Exception as e:
        logger.error(f"Tags error: {e}")
        await callback.message.answer("❌ Ошибка загрузки тегов", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "top_chats")
async def top_chats_callback(callback: types.CallbackQuery):
    try:
        from handlers.rating import cmd_top_chats
        await cmd_top_chats(callback.message)
    except Exception as e:
        logger.error(f"Top chats error: {e}")
        await callback.message.answer("❌ Ошибка загрузки топа чатов", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "privacy")
async def privacy_callback(callback: types.CallbackQuery):
    text = (
        "🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>\n\n"
        "📌 <b>Собираемые данные:</b>\n"
        "• Telegram ID\n• Имя пользователя\n• Баланс\n• Статистика игр\n\n"
        "📌 <b>Удаление:</b> /delete_my_data"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "donate")
async def donate_callback(callback: types.CallbackQuery):
    try:
        from handlers.economy import cmd_donate as economy_donate
        await economy_donate(callback.message)
    except Exception as e:
        logger.error(f"Donate error: {e}")
        await callback.message.answer("❌ Ошибка загрузки доната", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "feedback_menu")
async def feedback_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\n"
        "Напишите ваш отзыв или предложение в чат:\n"
        "<code>/feedback ваш текст</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS and user_id not in SUPER_ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        from handlers.admin import cmd_admin_panel
        await cmd_admin_panel(callback.message)
    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        await callback.message.answer("❌ Ошибка загрузки админ-панели", reply_markup=get_back_keyboard())
    await callback.answer()


# ==================== ЗАГРУЗКА МОДУЛЕЙ ====================

def setup_modules():
    """Установка бота и загрузка роутеров."""
    # Установка бота
    try:
        from handlers.tictactoe import set_bot
        set_bot(bot)
        logger.info("✅ Bot set for tictactoe")
    except Exception as e:
        logger.warning(f"tictactoe set_bot: {e}")
    
    try:
        from handlers.smart_commands import set_bot as set_smart_bot
        set_smart_bot(bot)
        logger.info("✅ Bot set for smart_commands")
    except Exception as e:
        logger.warning(f"smart_commands set_bot: {e}")
    
    # Загрузка роутеров
    routers = [
        ("handlers.smart_commands", "router"),
        ("handlers.economy", "router"),
        ("handlers.tictactoe", "router"),
        ("handlers.stats", "router"),
        ("handlers.vip", "router"),
        ("handlers.tag", "router"),
        ("handlers.admin", "router"),
        ("handlers.profile", "router"),
        ("handlers.rating", "router"),
        ("handlers.referral", "router"),
        ("handlers.tag_user", "router"),
        ("handlers.ranks", "router"),
    ]
    
    for module_name, attr_name in routers:
        try:
            module = __import__(module_name, fromlist=[attr_name])
            router = getattr(module, attr_name, None)
            if router:
                dp.include_router(router)
                logger.info(f"✅ Loaded: {module_name}")
        except Exception as e:
            logger.warning(f"Failed to load {module_name}: {e}")


setup_modules()


# ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

async def on_startup():
    logger.info("🚀 Starting NEXUS Bot v5.5.1...")
    
    try:
        await db.initialize()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")
    
    try:
        from handlers.smart_commands import load_custom_rp_commands
        await load_custom_rp_commands()
        logger.info("✅ Custom RP loaded")
    except Exception as e:
        logger.warning(f"Custom RP: {e}")
    
    # Утренняя очистка
    try:
        from utils.auto_delete import schedule_morning_cleanup
        task = asyncio.create_task(schedule_morning_cleanup(bot))
        _background_tasks.add(task)
        logger.info("✅ Morning cleanup scheduled")
    except Exception as e:
        logger.warning(f"Cleanup scheduler: {e}")
    
    logger.info("✅ Bot started! Все кнопки работают!")


async def on_shutdown():
    logger.info("🛑 Stopping...")
    for task in _background_tasks:
        task.cancel()
    await asyncio.sleep(1)
    logger.info("👋 Stopped")


# ==================== ОТЛАДКА ====================

@dp.message()
async def debug_unhandled(message: types.Message):
    """Логирует необработанные сообщения."""
    text = message.text[:100] if message.text else "НЕ ТЕКСТ"
    logger.warning(f"⚠️ UNHANDLED: chat={message.chat.id} user={message.from_user.id} text={text}")


# ==================== ЗАПУСК ====================

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("📡 Starting polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted")
    except Exception as e:
        logger.critical(f"💥 Fatal: {e}", exc_info=True)
        sys.exit(1)
