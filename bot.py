#!/usr/bin/env python3
"""
NEXUS Chat Manager v5.0 — Точка входа
Запуск на платформе Amvera
ПОЛНОСТЬЮ ИСПРАВЛЕННАЯ ВЕРСИЯ
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from config import BOT_TOKEN, START_BALANCE, ADMIN_IDS
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню бота"""
    keyboard = [
        [InlineKeyboardButton(text="⭐ VIP СТАТУС", callback_data="vip"),
         InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")],
        [InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance"),
         InlineKeyboardButton(text="🏆 РАНГ", callback_data="rank_menu")],
        [InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games"),
         InlineKeyboardButton(text="🎲 ЛИЧНЫЕ ИГРЫ", callback_data="private_games")],
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


# ==================== ПРЯМЫЕ ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    """Проверка работоспособности"""
    await message.answer("🏓 PONG! Бот работает!")


@dp.message(Command("daily"))
async def direct_daily(message: types.Message):
    """Прямой обработчик /daily"""
    from database import db
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Created new user {user_id}")
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    
    if last_daily == today:
        await message.answer(
            f"⏰ <b>БОНУС УЖЕ ПОЛУЧЕН!</b>\n\n"
            f"🔥 Стрик: <b>{user.get('daily_streak', 0)}</b> дней\n"
            f"⏰ Следующий бонус: <b>завтра</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    streak = user.get("daily_streak", 0)
    if last_daily:
        try:
            last_date = datetime.strptime(last_daily, "%Y-%m-%d").date()
            yesterday = datetime.now().date() - timedelta(days=1)
            streak = streak + 1 if last_date == yesterday else 1
        except:
            streak = 1
    else:
        streak = 1
    
    base_bonus = 100 + (streak * 50)
    vip_level = user.get("vip_level", 0) or 0
    vip_bonus = vip_level * 50 if vip_level > 0 else 0
    total_bonus = base_bonus + vip_bonus
    
    def _sync_update():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_bonus, user_id))
            cursor.execute("UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?", (streak, today, user_id))
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            new_balance = row[0] if row else user['balance'] + total_bonus
            conn.commit()
            return new_balance
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    try:
        new_balance = await asyncio.to_thread(_sync_update)
        
        if streak >= 30:
            emoji = "🔥🔥🔥"
        elif streak >= 7:
            emoji = "🔥🔥"
        elif streak >= 3:
            emoji = "🔥"
        else:
            emoji = "⭐"
        
        text = (
            f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС ПОЛУЧЕН!</b>\n\n"
            f"💰 Начислено: <b>+{total_bonus} NCoin</b>\n"
        )
        if vip_bonus > 0:
            text += f"   ├ Базовый: {base_bonus} NCoin\n"
            text += f"   └ VIP бонус: +{vip_bonus} NCoin\n"
        
        text += (
            f"\n{emoji} Стрик: <b>{streak}</b> дней\n"
            f"💎 Новый баланс: <b>{new_balance} NCoin</b>"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        logger.info(f"✅ DAILY: user={user_id}, bonus={total_bonus}, streak={streak}")
        
    except Exception as e:
        logger.error(f"❌ DAILY FAILED: {e}", exc_info=True)
        await message.answer("❌ Ошибка при начислении бонуса. Попробуйте позже.")


@dp.message(Command("balance"))
async def direct_balance(message: types.Message):
    """Прямой обработчик /balance"""
    from database import db
    
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await db.create_user(user_id, message.from_user.username, message.from_user.first_name, START_BALANCE)
        user = await db.get_user(user_id)
    
    await message.answer(
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{user['balance']}</b> NCoin\n\n"
        f"📊 Побед: {user.get('wins', 0)} | Поражений: {user.get('losses', 0)}",
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("start"))
async def direct_start(message: types.Message):
    """Прямой обработчик /start с главным меню"""
    from database import db
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    chat_id = message.chat.id
    
    # Проверка прав админа
    is_admin = False
    if message.chat.type in ['group', 'supergroup']:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            is_admin = member.status in ['creator', 'administrator']
        except:
            pass
    
    user = await db.get_user(user_id)
    
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        
        welcome_text = (
            f"🤖 <b>ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!</b> 🤖\n\n"
            f"✨ <b>Привет, {first_name}!</b>\n\n"
            f"Я — <b>NEXUS Chat Manager</b> — твой личный помощник в управлении чатом!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>🎯 ЧТО Я УМЕЮ:</b>\n\n"
            f"├ 🎮 <b>Игры</b> — слоты, рулетка, КНБ, дуэли\n"
            f"├ 💰 <b>Экономика</b> — баланс, переводы\n"
            f"├ 📢 <b>Общий сбор</b> — оповещение всех участников\n"
            f"├ 🤖 <b>AI помощник</b> — отвечаю на вопросы\n"
            f"├ 🔗 <b>Рефералка</b> — приглашай друзей, получай NCoins\n"
            f"├ 🏆 <b>Ранги</b> — повышай уровень, получай бонусы\n"
            f"├ 💕 <b>Отношения</b> — создавай семьи и группы\n"
            f"└ ❤️ <b>Поддержка</b> — помочь развитию проекта\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📌 БЫСТРЫЙ СТАРТ:</b>\n\n"
            f"├ <code>/daily</code> — получить бонус\n"
            f"├ <code>/balance</code> — проверить баланс\n"
            f"├ <code>/slot 100</code> — сыграть в слот\n"
            f"└ <code>/help</code> — все команды\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 <b>ВАМ НАЧИСЛЕНО: {START_BALANCE} NCOIN!</b>"
        )
        
        await message.answer(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu(is_admin=is_admin)
        )
    else:
        await message.answer(
            f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS CHAT MANAGER</b>\n\n"
            f"👋 С возвращением, <b>{first_name}</b>!\n"
            f"💰 Баланс: <b>{user['balance']}</b> NCoin\n"
            f"⭐ VIP: {'✅' if user.get('vip_level', 0) > 0 else '❌'}\n"
            f"🔥 Стрик: <b>{user.get('daily_streak', 0)}</b> дней\n\n"
            f"👇 Выберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu(is_admin=is_admin)
        )


@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    from database import db
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    is_admin = False
    if callback.message.chat.type in ['group', 'supergroup']:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            is_admin = member.status in ['creator', 'administrator']
        except:
            pass
    
    user = await db.get_user(user_id)
    balance = user['balance'] if user else 0
    vip = user.get('vip_level', 0) if user else 0
    streak = user.get('daily_streak', 0) if user else 0
    
    await callback.message.edit_text(
        f"🏠 <b>ГЛАВНОЕ МЕНЮ NEXUS CHAT MANAGER</b>\n\n"
        f"💰 Баланс: <b>{balance}</b> NCoin\n"
        f"⭐ VIP: {'✅' if vip > 0 else '❌'}\n"
        f"🔥 Стрик: <b>{streak}</b> дней\n\n"
        f"👇 Выберите категорию:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu(is_admin=is_admin)
    )
    await callback.answer()


# ==================== ИМПОРТЫ РОУТЕРОВ ====================
from database import db

try:
    from handlers.start import router as start_router
    from handlers.profile import router as profile_router
    from handlers.economy import router as economy_router
    from handlers.games import router as games_router
    from handlers.vip import router as vip_router
    from handlers.tag import router as tag_router
    from handlers.ai_assistant import router as ai_assistant_router
    from handlers.referral import router as referral_router
    from handlers.tag_admin import router as tag_admin_router
    from handlers.tag_user import router as tag_user_router
    from handlers.tag_trigger import router as tag_trigger_router
    from handlers.ranks import router as ranks_router
    from handlers.rating import router as rating_router
    from handlers.games_private import router as games_private_router
    from handlers.rp_commands import router as rp_commands_router
    from handlers.smart_commands import router as smart_commands_router
    
    dp.include_routers(
        start_router,
        profile_router,
        economy_router,
        games_router,
        vip_router,
        tag_router,
        ai_assistant_router,
        referral_router,
        tag_admin_router,
        tag_user_router,
        tag_trigger_router,
        ranks_router,
        rating_router,
        games_private_router,
        rp_commands_router,
        smart_commands_router,
    )
    logger.info("✅ Все роутеры загружены")
except Exception as e:
    logger.warning(f"⚠️ Некоторые роутеры не загружены: {e}")


# ==================== ЖИЗНЕННЫЙ ЦИКЛ БОТА ====================

async def on_startup():
    logger.info("🚀 Запуск NEXUS Bot v5.0...")
    
    try:
        await db.init()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.critical(f"❌ Ошибка инициализации БД: {e}")
        sys.exit(1)
    
    try:
        from handlers.tag_categories import init_categories
        await init_categories()
        logger.info("✅ Категории тегов инициализированы")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации категорий: {e}")
    
    logger.info("✅ NEXUS Bot v5.0 успешно запущен!")


async def on_shutdown():
    logger.info("🛑 Остановка бота...")
    try:
        await db.close()
    except:
        pass
    await bot.session.close()
    logger.info("👋 NEXUS Bot v5.0 остановлен")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    logger.info("📡 Запуск long-polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Прервано пользователем")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
