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
    """Отметить всех участников чата"""
    if not await can_ban(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return
    
    chat = message.chat
    chat_type = chat.type
    
    # ========== ПРОВЕРКА ТИПА ЧАТА ==========
    if chat_type == "group":
        await message.answer(
            "⚠️ **Это обычная группа.**\n\n"
            "Для работы команды /all необходимо:\n\n"
            "1️⃣ **Преобразовать группу в супергруппу**\n"
            "   Нажмите на название группы → Информация → Преобразовать\n\n"
            "2️⃣ **Назначить бота администратором**\n"
            "   Дайте права: `can_restrict_members` и `can_manage_chat`\n\n"
            "После этого команда заработает."
        )
        return
    
    # ========== ПРОВЕРКА ПРАВ БОТА ==========
    try:
        bot_member = await chat.get_member(bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            await message.answer(
                "❌ **Бот не является администратором чата!**\n\n"
                "Для работы /all необходимо:\n"
                "1. Назначить бота администратором\n"
                "2. Включить права:\n"
                "   • `can_restrict_members` — для банов и мутов\n"
                "   • `can_manage_chat` — для просмотра участников\n\n"
                "После этого повторите команду."
            )
            return
        
        # Проверяем наличие прав
        if bot_member.status == 'administrator':
            if not bot_member.can_restrict_members or not bot_member.can_manage_chat:
                await message.answer(
                    "⚠️ **У бота недостаточно прав!**\n\n"
                    "Включите права:\n"
                    f"• `can_restrict_members`: {'✅' if bot_member.can_restrict_members else '❌'}\n"
                    f"• `can_manage_chat`: {'✅' if bot_member.can_manage_chat else '❌'}\n\n"
                    "Настройте права в управлении группой."
                )
                return
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при проверке прав: {e}")
        return
    
    # ========== ПОЛУЧЕНИЕ УЧАСТНИКОВ ==========
    status_msg = await message.answer("🔄 Получаю список участников...")
    
    members = []
    count = 0
    
    try:
        async for member in chat.get_chat_members():
            if not member.user.is_bot:
                if member.user.username:
                    mention = f"@{member.user.username}"
                else:
                    mention = member.user.full_name
                members.append(mention)
                count += 1
                
                if count % 50 == 0:
                    try:
                        await status_msg.edit_text(f"🔄 Получаю список участников... ({count} найдено)")
                    except:
                        pass
        
        await status_msg.delete()
        
        if not members:
            await message.answer(
                "❌ **Не удалось получить список участников.**\n\n"
                "Возможные причины:\n"
                "• В чате нет других участников\n"
                "• Бот не имеет прав на просмотр участников\n"
                "• Чат слишком большой"
            )
            return
        
        total = len(members)
        await message.answer(f"👥 **Найдено {total} участников.** Отправляю список...")
        
        # Отправляем всех участников (разбиваем на части по 50)
        for i in range(0, total, 50):
            chunk = members[i:i+50]
            text = f"🔔 **УЧАСТНИКИ** ({i+1}-{min(i+50, total)} из {total}):\n\n" + "\n".join(chunk)
            await message.answer(text)
        
        await log_action(chat.id, f"📢 {message.from_user.full_name} вызвал всех участников чата ({total} чел)")
        
    except Exception as e:
        error_msg = str(e)
        await message.answer(
            f"❌ **Ошибка:** {error_msg[:200]}\n\n"
            f"Попробуйте:\n"
            f"• Убедиться, что бот администратор\n"
            f"• Преобразовать группу в супергруппу\n"
            f"• Проверить права бота в настройках группы"
        )

@router.message(Command("ban"))
async def ban_user(message: Message):
    """Забанить пользователя"""
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
    """Заглушить пользователя на время"""
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
    """Настроить приветственное сообщение для новых участников"""
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
            f"Пример: /setwelcome Добро пожаловать, {{user}}! Рады видеть в {{chat}}!\n\n"
            f"Текущее приветствие: {current or 'не установлено'}"
        )
        return
    
    welcome_text = args[1]
    set_chat_welcome(message.chat.id, welcome_text)
    await message.answer(f"✅ Приветствие установлено:\n\n{welcome_text}")
    await log_action(message.chat.id, f"✏️ {message.from_user.full_name} изменил приветствие")

@router.message(Command("setlogchannel"))
async def set_log_channel_command(message: Message):
    """Установить канал для логов и жалоб"""
    if not await can_configure(message.chat.id, message.from_user.id):
        await message.answer("❌ Только администраторы могут настраивать лог-канал.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "📝 **Настройка лог-канала**\n\n"
            "Использование: /setlogchannel @channel\n"
            "Пример: /setlogchannel @mychannel_logs\n\n"
            "Все действия бота (баны, муты, жалобы) будут отправляться в этот канал.\n"
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
        await message.answer(f"❌ Ошибка: {e}\n\nУбедитесь, что бот добавлен в канал как администратор.")

@router.message(Command("setup"))
async def setup_bot(message: Message):
    """Мастер настройки бота"""
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
    """Назначить модератора бота"""
    if not await can_assign_moderator(message.chat.id, message.from_user.id):
        await message.answer("❌ У вас нет прав назначать модераторов.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите назначить модератором.")
        return
    
    target_user = message.reply_to_message.from_user
    target_id = target_user.id
    
    # Проверяем, не является ли пользователь уже админом
    try:
        chat = await bot.get_chat(message.chat.id)
        member = await chat.get_member(target_id)
        if member.status in ['creator', 'administrator']:
            await message.answer(f"❌ {target_user.full_name} уже является администратором Telegram.")
            return
    except:
        pass
    
    add_chat_moderator(message.chat.id, target_id, message.from_user.id)
    await message.answer(f"✅ {target_user.full_name} назначен модератором бота.")
    await log_action(message.chat.id, f"👮 {message.from_user.full_name} назначил модератора {target_user.full_name}")

@router.message(Command("removemod"))
async def remove_moderator(message: Message):
    """Удалить модератора бота"""
    if not await can_assign_moderator(message.chat.id, message.from_user.id):
        await message.answer("❌ У вас нет прав удалять модераторов.")
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя, которого хотите лишить прав.")
        return
    
    target_user = message.reply_to_message.from_user
    target_id = target_user.id
    
    remove_chat_moderator(message.chat.id, target_id)
    await message.answer(f"✅ {target_user.full_name} лишен прав модератора.")
    await log_action(message.chat.id, f"👮 {message.from_user.full_name} лишил прав модератора {target_user.full_name}")

@router.message(Command("mods"))
async def list_moderators(message: Message):
    """Список модераторов бота"""
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
    
    await message.answer(f"👮 **Модераторы бота:**\n\n" + "\n".join(mod_list))
