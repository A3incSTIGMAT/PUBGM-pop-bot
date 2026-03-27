from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()
last_daily = {}

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    await message.answer("💰 Баланс: 100 NCoin")

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    user_id = message.from_user.id
    now = datetime.now()
    last = last_daily.get(user_id)
    
    if last and now - last < timedelta(hours=24):
        await message.answer("⏰ Бонус уже получен сегодня")
        return
    
    last_daily[user_id] = now
    await message.answer("🎁 +50 NCoin!")
