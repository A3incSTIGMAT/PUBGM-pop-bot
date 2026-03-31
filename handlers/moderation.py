"""
moderation.py — Модерация: бан, мут, предупреждения
"""

from aiogram import Router, F
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command
from datetime import datetime, timedelta
from config import ADMIN_IDS, MAX_WARN_COUNT, MAX_MUTE_DAYS
from database import db

router = Router()


def is_admin(message: Message) -> bool:
    """Проверка прав администратора"""
    return message.from_user.id in ADMIN_IDS


@router.message(Command("ban"))
async def ban_user(message: Message):
    if not is_admin(message):
        return
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя")
        return

    user = message.reply_to_message.from_user
    reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Без причины"

    await message.chat.ban(user.id)
    await message.answer(f"🔨 *{user.full_name} забанен*\n📝 Причина: {reason}", parse_mode="Markdown")


@router.message(Command("unban"))
async def unban_user(message: Message):
    if not is_admin(message):
        return
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя")
        return

    user = message.reply_to_message.from_user
    await message.chat.unban(user.id)
    await message.answer(f"🔓 *{user.full_name} разбанен*", parse_mode="Markdown")


@router.message(Command("mute"))
async def mute_user(message: Message):
    if not is_admin(message):
        return
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение")
        return

    user = message.reply_to_message.from_user
    args = message.text.split()
    duration = 60  # секунд по умолчанию

    if len(args) > 1:
        try:
            duration = int(args[1])
            if duration > MAX_MUTE_DAYS * 86400:
                duration = MAX_MUTE_DAYS * 86400
        except ValueError:
            pass

    until = datetime.now() + timedelta(seconds=duration)
    await message.chat.restrict(
        user.id,
        ChatPermissions(can_send_messages=False),
        until_date=until
    )
    await message.answer(f"🔇 *{user.full_name} замучен* на {duration // 60} минут", parse_mode="Markdown")


@router.message(Command("unmute"))
async def unmute_user(message: Message):
    if not is_admin(message):
        return
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение")
        return

    user = message.reply_to_message.from_user
    await message.chat.restrict(
        user.id,
        ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
    )
    await message.answer(f"🔊 *{user.full_name} размучен*", parse_mode="Markdown")


@router.message(Command("warn"))
async def warn_user(message: Message):
    if not is_admin(message):
        return
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение")
        return

    user = message.reply_to_message.from_user
    reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Без причины"

    count = await db.add_warn(message.chat.id, user.id, message.from_user.id, reason)

    await message.answer(
        f"⚠️ *{user.full_name} получил предупреждение* ({count}/{MAX_WARN_COUNT})\n📝 Причина: {reason}",
        parse_mode="Markdown"
    )

    if count >= MAX_WARN_COUNT:
        await message.chat.ban(user.id)
        await message.answer(f"🔨 *Авто-бан:* {user.full_name} (3 предупреждения)")


@router.message(Command("warns"))
async def show_warns(message: Message):
    if not is_admin(message):
        return
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение")
        return

    user = message.reply_to_message.from_user
    warns = await db.get_warns(message.chat.id, user.id)

    if not warns:
        await message.answer(f"✅ У *{user.full_name}* нет предупреждений", parse_mode="Markdown")
        return

    text = f"📋 *Предупреждения {user.full_name}:*\n\n"
    for i, w in enumerate(warns[:10], 1):
        text += f"{i}. {w['reason']} (админ: {w['admin_id']}, {w['timestamp'][:16]})\n"

    await message.answer(text, parse_mode="Markdown")
