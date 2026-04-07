from aiogram import Router, F
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command
from datetime import datetime, timedelta
from config import ADMIN_IDS, MAX_WARN_COUNT
from database import db

router = Router()

def is_admin(message): return message.from_user.id in ADMIN_IDS

@router.message(Command("ban"))
async def ban_user(message: Message):
    if not is_admin(message) or not message.reply_to_message: return
    user = message.reply_to_message.from_user
    await message.chat.ban(user.id)
    await message.answer(f"🔨 {user.full_name} забанен")

@router.message(Command("unban"))
async def unban_user(message: Message):
    if not is_admin(message) or not message.reply_to_message: return
    user = message.reply_to_message.from_user
    await message.chat.unban(user.id)
    await message.answer(f"🔓 {user.full_name} разбанен")

@router.message(Command("warn"))
async def warn_user(message: Message):
    if not is_admin(message) or not message.reply_to_message: return
    user = message.reply_to_message.from_user
    reason = message.text.split(maxsplit=1)[1] if len(message.text.split())>1 else "Нарушение"
    count = await db.add_warn(message.chat.id, user.id, message.from_user.id, reason)
    await message.answer(f"⚠️ {user.full_name} предупреждение ({count}/{MAX_WARN_COUNT})")
    if count >= MAX_WARN_COUNT:
        await message.chat.ban(user.id)
        await message.answer(f"🔨 Авто-бан: {user.full_name}")
