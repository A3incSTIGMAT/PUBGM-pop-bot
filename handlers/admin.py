from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

@router.message(Command("ban"))
async def ban_user(message: Message):
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя")
        return
    
    user = message.reply_to_message.from_user
    await message.chat.ban(user.id)
    await message.answer(f"✅ {user.full_name} забанен")

@router.message(Command("mute"))
async def mute_user(message: Message):
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя")
        return
    
    user = message.reply_to_message.from_user
    await message.chat.restrict(user.id, ChatPermissions(can_send_messages=False))
    await message.answer(f"🔇 {user.full_name} заглушен")
