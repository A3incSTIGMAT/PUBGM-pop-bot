import asyncio
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from aiogram.exceptions import TelegramAPIError

from config import ADMIN_IDS
from database.db import get_welcome_message, set_chat_welcome

router = Router()

# Проверка прав админа
async def is_admin(message: Message) -> bool:
    # Глобальные админы из .env
    if message.from_user.id in ADMIN_IDS:
        return True
    
    # Проверка прав в чате
    try:
        member = await message.chat.get_member(message.from_user.id)
        return member.status in ["administrator", "creator"]
    except:
        return False

# /all — тегирование всех участников
@router.message(Command("all"))
async def tag_all(message: Message):
    if not await is_admin(message):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return
    
    await message.answer("🔔 Получаю список участников...")
    
    members = []
    async for member in message.chat.get_members():
        if not member.user.is_bot:
            mention = f"@{member.user.username}" if member.user.username else member.user.full_name
            members.append(mention)
    
    if members:
        # Отправляем частями, чтобы не превысить лимит сообщения
        text = "🔔 ВНИМАНИЕ ВСЕМ!\n\n" + "\n".join(members[:50])
        await message.answer(text)
        
        if len(members) > 50:
            await message.answer("\n".join(members[50:100]))
    else:
        await message.answer("❌ Не удалось получить список участников.")

# /ban — забанить пользователя
@router.message(Command("ban"))
async def ban_user(message: Message):
    if not await is_admin(message):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите забанить.")
        return
    
    user = message.reply_to_message.from_user
    user_id = user.id
    user_name = user.full_name
    
    try:
        await message.chat.ban(user_id)
        await message.answer(f"✅ Пользователь {user_name} забанен.")
    except TelegramAPIError as e:
        await message.answer(f"❌ Ошибка: {e}")

# /mute — заглушить пользователя
@router.message(Command("mute"))
async def mute_user(message: Message):
    if not await is_admin(message):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите заглушить.")
        return
    
    # Парсим время из команды /mute 10m
    args = message.text.split()
    duration = 10  # минут по умолчанию
    
    if len(args) > 1:
        try:
            duration = int(args[1].replace("m", "").replace("h", ""))
        except:
            pass
    
    user = message.reply_to_message.from_user
    user_id = user.id
    user_name = user.full_name
    
    try:
        permissions = ChatPermissions(can_send_messages=False)
        until_date = asyncio.get_event_loop().time() + duration * 60
        await message.chat.restrict(user_id, permissions, until_date=until_date)
        await message.answer(f"🔇 Пользователь {user_name} заглушен на {duration} минут.")
    except TelegramAPIError as e:
        await message.answer(f"❌ Ошибка: {e}")

# Настройка приветственного сообщения для чата
@router.message(Command("setwelcome"))
async def set_welcome_message(message: Message):
    if not await is_admin(message):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "📝 **Настройка приветствия**\n\n"
            "Использование: /setwelcome [текст]\n\n"
            "Переменные:\n"
            "• `{user}` — имя нового участника\n"
            "• `{chat}` — название чата\n\n"
            "Пример: /setwelcome Добро пожаловать, {user}! Рады видеть в {chat}!\n\n"
            f"Текущее приветствие: {get_welcome_message(message.chat.id) or 'не установлено'}"
        )
        return
    
    welcome_text = args[1]
    
    # Сохраняем в базу данных
    set_chat_welcome(message.chat.id, welcome_text)
    
    await message.answer(f"✅ Приветственное сообщение установлено:\n\n{welcome_text}")
