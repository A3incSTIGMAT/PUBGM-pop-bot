#!/usr/bin/env python3
"""
NEXUS Chat Manager v5.0 — Точка входа
Запуск на платформе Amvera
С ПРЯМЫМИ ОБРАБОТЧИКАМИ ДЛЯ ДИАГНОСТИКИ
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from config import BOT_TOKEN
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set!")
    sys.exit(1)

# Создаём бота и диспетчер
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==================== ПРЯМЫЕ ОБРАБОТЧИКИ (ДИАГНОСТИКА) ====================

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    """Проверка работоспособности бота"""
    logger.critical("🔥 PING COMMAND RECEIVED!")
    await message.answer("🏓 PONG! Бот работает!")


@dp.message(Command("testdaily"))
async def cmd_testdaily(message: types.Message):
    """Тестовый daily"""
    logger.critical("🔥🔥🔥 TESTDAILY COMMAND RECEIVED! 🔥🔥🔥")
    await message.answer("✅ Тестовая команда /testdaily работает!")


@dp.message(Command("daily"))
async def direct_daily(message: types.Message):
    """ПРЯМОЙ ОБРАБОТЧИК /daily"""
    logger.critical("🔥🔥🔥 DIRECT /daily HANDLER CALLED! 🔥🔥🔥")
    
    from database import db
    import asyncio as aio
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Получаем или создаём пользователя
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, 1000)
        user = await db.get_user(user_id)
        logger.info(f"Created new user {user_id}")
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    
    # Проверка на уже полученный бонус
    if last_daily == today:
        await message.answer(
            f"⏰ <b>БОНУС УЖЕ ПОЛУЧЕН!</b>\n\n"
            f"🔥 Стрик: <b>{user.get('daily_streak', 0)}</b> дней\n"
            f"⏰ Следующий бонус: <b>завтра</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Расчёт стрика
    streak = user.get("daily_streak", 0)
    if last_daily:
        try:
            last_date = datetime.strptime(last_daily, "%Y-%m-%d").date()
            yesterday = datetime.now().date() - __import__('datetime').timedelta(days=1)
            if last_date == yesterday:
                streak += 1
            else:
                streak = 1
        except:
            streak = 1
    else:
        streak = 1
    
    # Расчёт бонуса
    base_bonus = 100 + (streak * 50)
    vip_level = user.get("vip_level", 0) or 0
    vip_bonus = vip_level * 50 if vip_level > 0 else 0
    total_bonus = base_bonus + vip_bonus
    
    # Обновление БД
    def _sync_update():
        conn = db._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            # Обновляем баланс
            cursor.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (total_bonus, user_id)
            )
            
            # Обновляем стрик и дату
            cursor.execute(
                "UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
                (streak, today, user_id)
            )
            
            # Получаем новый баланс
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
        new_balance = await aio.to_thread(_sync_update)
        
        # Эмодзи для стрика
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
        await db.create_user(user_id, message.from_user.username, message.from_user.first_name, 1000)
        user = await db.get_user(user_id)
    
    await message.answer(
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{user['balance']}</b> NCoin\n\n"
        f"📊 Побед: {user.get('wins', 0)} | Поражений: {user.get('losses', 0)}",
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("start"))
async def direct_start(message: types.Message):
    """Прямой обработчик /start"""
    from database import db
    from config import START_BALANCE
    
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await db.create_user(user_id, message.from_user.username, message.from_user.first_name, START_BALANCE)
        await message.answer(
            f"🤖 <b>ВЕЛКОМ ТО NEXUS!</b>\n\n"
            f"✨ Привет, {message.from_user.first_name}!\n\n"
            f"🎁 Вам начислено: {START_BALANCE} NCoin\n\n"
            f"Используйте кнопки внизу для навигации.\n"
            f"Команды: /daily, /balance, /help",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer(
            f"👋 С возвращением, {message.from_user.first_name}!\n"
            f"💰 Баланс: {user['balance']} NCoin\n"
            f"🔥 Стрик: {user.get('daily_streak', 0)} дней",
            parse_mode=ParseMode.HTML
        )


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
    
    # Подключаем все роутеры
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
    """Инициализация при запуске"""
    logger.info("🚀 Запуск NEXUS Bot v5.0...")
    
    try:
        await db.init()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.critical(f"❌ Ошибка инициализации БД: {e}")
        sys.exit(1)
    
    # Инициализация категорий тегов
    try:
        from handlers.tag_categories import init_categories
        await init_categories()
        logger.info("✅ Категории тегов инициализированы")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации категорий: {e}")
    
    logger.info("✅ NEXUS Bot v5.0 успешно запущен на Amvera!")
    logger.info("📡 Прямые обработчики: /ping, /testdaily, /daily, /balance, /start")


async def on_shutdown():
    """Очистка при остановке"""
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
