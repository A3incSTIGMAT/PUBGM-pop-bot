#!/usr/bin/env python3
"""
NEXUS Chat Manager v5.0 — Точка входа
"""

import asyncio
import logging
import os
import sys
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

from database import db

os.makedirs("/data", exist_ok=True)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==================== ВРЕМЕННЫЙ ПРЯМОЙ ОБРАБОТЧИК ====================
@dp.message(Command("daily"))
async def direct_daily(message: types.Message):
    """Прямой обработчик /daily для диагностики"""
    logger.critical("🔥🔥🔥 DIRECT DAILY HANDLER CALLED! 🔥🔥🔥")
    
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await db.create_user(user_id, message.from_user.username, message.from_user.first_name, 1000)
        user = await db.get_user(user_id)
    
    # Принудительно начисляем бонус
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    
    def _force_daily():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + 100, last_daily = ?, daily_streak = daily_streak + 1 WHERE user_id = ?", (today, user_id))
        conn.commit()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    
    import asyncio as aio
    new_balance = await aio.to_thread(_force_daily)
    
    await message.answer(
        f"🎁 <b>ТЕСТОВЫЙ БОНУС НАЧИСЛЕН!</b>\n\n"
        f"💰 +100 NCoin\n"
        f"💎 Новый баланс: <b>{new_balance}</b> NCoin",
        parse_mode=ParseMode.HTML
    )

# ==================== ИМПОРТЫ РОУТЕРОВ ====================
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

# ==================== ПОДКЛЮЧЕНИЕ РОУТЕРОВ ====================
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

# ... остальной код (on_startup, on_shutdown, main) без изменений ...
