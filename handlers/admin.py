import asyncio
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from aiogram.exceptions import TelegramAPIError

from database.db import (
    get_welcome_message, set_chat_welcome,
    get_log_channel, set_log_channel,
    add_chat_moderator, remove_chat_moderator, get_chat_moderators
)
from handlers.roles import can_ban, can_mute, can_configure, can_assign_moderator
from keyboards.setup_menu import get_setup_menu
from utils.logger import log_admin

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

async def log_action(chat_id: int, action_text: str):
    log_channel_id = get_log_channel(chat_id)
    if log_channel_id and bot:
        try:
            await bot.send_message(log_channel_id, action_text)
        except:
            pass

# ========== АДМИН-КОМАНДЫ ==========

@router.message(Command("all"))
async def tag_all(message: Message):
    if not await can_ban(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return
    
    await message.answer("🔔 Получаю список участников...")
    
    members = []
    async for member in message.chat.get_chat_members():
        if not member.user.is_bot:
            mention = f"@{member.user.username}" if member.user.username else member.user.full_name
            members.append(mention)
    
    if members:
        text = "🔔 ВНИМАНИЕ ВСЕМ!\n\n" + "\n".join(members[:50])
        await message.answer(text)
        if len(members) > 50:
            await message.answer("\n".join(members[50:100]))
        await log_action(message.chat.id, f"📢 {message.from_user.full_name} вызвал всех")
    else:
        await message.answer("❌ Не удалось получить список участников.")

@router.message(Command("ban"))
async def ban_user(message: Message):
    if not await can_ban(message.chat.id, message.from_user.id):
        await message.answer("❌ У вас нет прав банить пользователей.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите забанить.")
        return
    
    user = message.reply_to_message.from_user
    user_id = user.id
    user_name = user.full_name
    admin_name = message.from_user.full_name
    
    try:
        await message.chat.ban(user_id)
        await message.answer(f"✅ Пользователь {user_name} забанен.")
        await log_action(message.chat.id, f"🔨 {admin_name} забанил {user_name}")
    except TelegramAPIError as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("mute"))
async def mute_user(message: Message):
    if not await can_mute(message.chat.id, message.from_user.id):
        await message.answer("❌ У вас нет прав мутить пользователей.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите заглушить.")
        return
    
    args = message.text.split()
    duration = 10
    
    if len(args) > 1:
        try:
            duration = int(args[1].replace("m", "").replace("h", ""))
        except:
            pass
    
    user = message.reply_to_message.from_user
    user_id = user.id
    user_name = user.full_name
    admin_name = message.from_user.full_name
    
    try:
        permissions = ChatPermissions(can_send_messages=False)
        until_date = asyncio.get_event_loop().time() + duration * 60
        await message.chat.restrict(user_id, permissions, until_date=until_date)
        await message.answer(f"🔇 {user_name} заглушен на {duration} минут.")
        await log_action(message.chat.id, f"🔇 {admin_name} заглушил {user_name}")
    except TelegramAPIError as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("setwelcome"))
async def set_welcome_message(message: Message):
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут настраивать приветствие.")
        return
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        current = get_welcome_message(message.chat.id)
        await message.answer(
            f"📝 **Настройка приветствия**\n\n"
            f"Использование: /setwelcome [текст]\n\n"
            f"Переменные: {{user}} — имя, {{chat}} — название чата\n\n"
            f"Текущее: {current or 'не установлено'}"
        )
        return
    
    welcome_text = args[1]
    set_chat_welcome(message.chat.id, welcome_text)
    await message.answer(f"✅ Приветствие установлено:\n\n{welcome_text}")
    await log_action(message.chat.id, f"✏️ {message.from_user.full_name} изменил приветствие")

@router.message(Command("setlogchannel"))
async def set_log_channel_command(message: Message):
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут настраивать лог-канал.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "📝 **Настройка лог-канала**\n\n"
            "Использование: /setlogchannel @channel\n"
            "Пример: /setlogchannel @mychannel_logs\n\n"
            "Бот должен быть администратором канала!"
        )
        return
    
    channel_username = args[1].replace("@", "")
    try:
        chat = await bot.get_chat(f"@{channel_username}")
        set_log_channel(message.chat.id, chat.id)
        await message.answer(f"✅ Лог-канал установлен: @{channel_username}")
        await log_action(message.chat.id, f"📋 {message.from_user.full_name} установил лог-канал")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("setup"))
async def setup_bot(message: Message):
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут настраивать бота.")
        return
    
    log_channel = get_log_channel(message.chat.id)
    reports_enabled = log_channel is not None
    
    status_text = (
        "⚙️ **Текущие настройки NEXUS**\n\n"
        f"🛡 Анонимные репорты: {'✅ Включены' if reports_enabled else '❌ Не настроены'}\n"
        f"📋 Лог-канал: {'✅ ' + str(log_channel) if log_channel else '❌ Не настроен'}\n\n"
        "Выберите, что хотите настроить:"
    )
    
    await message.answer(status_text, reply_markup=get_setup_menu())

@router.message(Command("addmod"))
async def add_moderator(message: Message):
    if not await can_assign_moderator(message.chat.id, message.from_user.id):
        await message.answer("❌ У вас нет прав назначать модераторов.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите назначить модератором.")
        return
    
    target_user = message.reply_to_message.from_user
    add_chat_moderator(message.chat.id, target_user.id, message.from_user.id)
    await message.answer(f"✅ {target_user.full_name} назначен модератором.")
    await log_action(message.chat.id, f"👮 {message.from_user.full_name} назначил модератора {target_user.full_name}")

@router.message(Command("removemod"))
async def remove_moderator(message: Message):
    if not await can_assign_moderator(message.chat.id, message.from_user.id):
        await message.answer("❌ У вас нет прав удалять модераторов.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите лишить прав.")
        return
    
    target_user = message.reply_to_message.from_user
    remove_chat_moderator(message.chat.id, target_user.id)
    await message.answer(f"✅ {target_user.full_name} лишен прав модератора.")
    await log_action(message.chat.id, f"👮 {message.from_user.full_name} лишил прав модератора {target_user.full_name}")

@router.message(Command("mods"))
async def list_moderators(message: Message):
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ У вас нет прав просматривать список модераторов.")
        return
    
    moderators = get_chat_moderators(message.chat.id)
    
    if not moderators:
        await message.answer("📋 В этом чате нет назначенных модераторов.")
        return
    
    mod_list = []
    for mod in moderators:
        username = mod['username'] or f"user_{mod['user_id']}"
        mod_list.append(f"• {username} (назначен {mod['assigned_at'][:10]})")
    
    await message.answer(f"👮 **Модераторы:**\n\n" + "\n".join(mod_list))
