import asyncio
import random
from datetime import datetime
from aiogram import Router, Bot
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import Message, ChatMemberUpdated

from database.db import (
    get_welcome_message, add_user, update_user_stats,
    save_captcha, get_captcha, delete_captcha,
    set_birthday, get_user_stats
)
from handlers.roles import get_user_role
from utils.antispam import is_spam, is_rate_limited, is_temp_banned, add_temp_ban, add_warning, should_mute
from utils.logger import log_user, log_attack, measure_time

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

@router.message(Command("start"))
@measure_time
async def cmd_start(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    banned, wait_time = is_temp_banned(user_id)
    if banned:
        await message.answer(f"❌ Вы временно заблокированы. Повторите через {wait_time} сек.")
        return
    
    await message.answer(
        "👋 Добро пожаловать в NEXUS!\n\n"
        "Я мощный чат-менеджер с играми и экономикой.\n\n"
        "📌 Основные команды:\n"
        "/help — помощь\n"
        "/stats — моя статистика\n"
        "/balance — мой баланс\n"
        "/daily — ежедневный бонус\n"
        "/gift @username 50 — подарить NCoin\n"
        "/setbirthday DD.MM — установить день рождения\n"
        "/report @username [причина] — анонимная жалоба\n\n"
        "🎮 Игры:\n"
        "/duel @username 50 — вызвать на дуэль\n"
        "/rps камень — камень-ножницы-бумага\n"
        "/roulette 100 red — рулетка\n\n"
        "🛡 Админ-команды:\n"
        "/all — отметить всех\n"
        "/ban — забанить (ответом)\n"
        "/mute — заглушить (ответом)\n"
        "/setlogchannel — установить лог-канал\n"
        "/setup — мастер настройки"
    )
    add_user(message.from_user.id, message.chat.id, message.from_user.username)
    log_user(message.from_user.full_name, "/start")

@router.message(Command("help"))
@measure_time
async def cmd_help(message: Message):
    banned, wait_time = is_temp_banned(message.from_user.id)
    if banned:
        await message.answer(f"❌ Вы временно заблокированы. Повторите через {wait_time} сек.")
        return
    
    await message.answer(
        "📖 Справка NEXUS\n\n"
        "👤 Пользовательские команды:\n"
        "/start — приветствие\n"
        "/help — это сообщение\n"
        "/stats — ваша статистика\n"
        "/balance — ваш баланс NCoin\n"
        "/daily — ежедневный бонус NCoin\n"
        "/gift @username [сумма] — подарить NCoin\n"
        "/setbirthday DD.MM — установить день рождения\n"
        "/report @username [причина] — анонимная жалоба\n"
        "/myrole — показать мою роль в чате\n\n"
        "🛡 Админ-команды:\n"
        "/all — отметить всех участников\n"
        "/ban — забанить (ответом)\n"
        "/mute [время] — заглушить (ответом)\n"
        "/setwelcome [текст] — настроить приветствие\n"
        "/setlogchannel — установить лог-канал\n"
        "/setup — мастер настройки\n"
        "/addmod — назначить модератора (ответом)\n"
        "/removemod — удалить модератора (ответом)\n"
        "/mods — список модераторов\n\n"
        "🎮 Игры:\n"
        "/duel — дуэль\n"
        "/rps — камень-ножницы-бумага\n"
        "/roulette — рулетка\n\n"
        "💰 Экономика:\n"
        "/top — топ богачей\n"
        "/shop — магазин подарков"
    )
    log_user(message.from_user.full_name, "/help")

@router.message(Command("myrole"))
async def show_my_role(message: Message):
    role = await get_user_role(message.chat.id, message.from_user.id)
    
    role_names = {
        'global_admin': '🌍 Глобальный супер-админ',
        'creator': '👑 Владелец чата',
        'admin': '🛡 Администратор Telegram',
        'moderator': '🔨 Модератор бота',
        'user': '👤 Обычный участник'
    }
    
    role_text = role_names.get(role, '👤 Обычный участник')
    await message.answer(f"**Ваша роль:**\n\n{role_text}")

@router.message(Command("stats"))
@measure_time
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    banned, wait_time = is_temp_banned(user_id)
    if banned:
        await message.answer(f"❌ Вы временно заблокированы. Повторите через {wait_time} сек.")
        return
    
    stats = get_user_stats(user_id, message.chat.id)
    
    if stats:
        await message.answer(
            f"📊 **Ваша статистика**\n\n"
            f"💰 Баланс: {stats['balance']} NCoin\n"
            f"💬 Сообщений: {stats['total_messages']}\n"
            f"👑 VIP: {'Да' if stats['is_vip'] else 'Нет'}\n"
            f"⭐ Репутация: {stats['reputation']}\n"
            f"🎂 ДР: {stats['birthday'] or 'не указан'}"
        )
    else:
        await message.answer("📊 Статистика пока пуста.")
    log_user(message.from_user.full_name, "/stats")

@router.message(Command("setbirthday"))
@measure_time
async def set_birthday_command(message: Message):
    user_id = message.from_user.id
    banned, wait_time = is_temp_banned(user_id)
    if banned:
        await message.answer(f"❌ Вы временно заблокированы.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "📅 **Установка дня рождения**\n\n"
            "Использование: /setbirthday DD.MM\n"
            "Пример: /setbirthday 15.07"
        )
        return
    
    birthday = args[1]
    try:
        datetime.strptime(birthday, "%d.%m")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте ДД.ММ")
        return
    
    set_birthday(message.from_user.id, message.chat.id, birthday)
    await message.answer(f"✅ День рождения {birthday} сохранен!")

# ========== ПРИВЕТСТВИЕ ПРИ ДОБАВЛЕНИИ БОТА ==========

@router.my_chat_member(ChatMemberUpdatedFilter(
    member_status_changed=JOIN_TRANSITION
))
async def on_bot_added_to_chat(event: ChatMemberUpdated):
    chat = event.chat
    chat_id = chat.id
    
    try:
        bot_member = await chat.get_member(bot.id)
        has_admin_rights = bot_member.status == "administrator"
    except:
        has_admin_rights = False
    
    welcome_text = (
        f"🤖 **NEXUS Chat Manager**\n\n"
        f"Привет! Я мощный чат-менеджер с защитой приватности.\n\n"
        f"🛡 **Ключевая фишка — Анонимные репорты**\n"
        f"Участники могут сообщать о нарушениях, не раскрывая себя.\n"
    )
    
    if not has_admin_rights:
        welcome_text += (
            f"\n⚠️ **Важно!** У меня нет прав администратора.\n"
            f"Назначьте меня администратором в настройках чата!\n"
        )
    
    welcome_text += (
        f"\n🔧 **Быстрая настройка:** /setup\n"
        f"📖 **Справка:** /help\n\n"
        f"🚀 Готов сделать ваш чат безопаснее!"
    )
    
    await event.answer(welcome_text)
    
    from keyboards.setup_menu import get_setup_menu
    await bot.send_message(
        chat_id,
        "⚙️ **Для настройки анонимных репортов нажмите кнопку ниже:**",
        reply_markup=get_setup_menu()
    )
    add_user(chat_id, chat_id, chat.title)

# ========== КАПЧА ==========

@router.chat_member(ChatMemberUpdatedFilter(
    member_status_changed=IS_NOT_MEMBER >> IS_MEMBER
))
async def captcha_on_join(event: ChatMemberUpdated):
    user = event.new_chat_member.user
    if user.is_bot:
        return
    
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    answer = num1 + num2
    
    save_captcha(user.id, event.chat.id, answer)
    
    await event.answer(
        f"🔐 **Проверка на бота**\n\n"
        f"Привет, {user.full_name}!\n"
        f"Решите пример: **{num1} + {num2} = ?**\n\n"
        f"⏱ У вас 60 секунд."
    )
    
    asyncio.create_task(kick_if_not_verified(user.id, event.chat.id))

async def kick_if_not_verified(user_id: int, chat_id: int):
    await asyncio.sleep(60)
    captcha = get_captcha(user_id, chat_id)
    if captcha:
        delete_captcha(user_id, chat_id)
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
        except:
            pass

@router.message()
async def check_captcha_and_spam(message: Message):
    if not message.text:
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    captcha = get_captcha(user_id, chat_id)
    if captcha and message.text.isdigit() and int(message.text) == captcha["answer"]:
        delete_captcha(user_id, chat_id)
        await message.answer("✅ **Проверка пройдена!** Добро пожаловать!")
        add_user(user_id, chat_id, message.from_user.username)
        return
    elif captcha:
        await message.answer("❌ **Неверный ответ.** Попробуйте еще раз.")
        return
    
    # Антиспам
    spam, count = is_spam(user_id)
    if spam:
        warnings = add_warning(user_id, "спам")
        if warnings >= 3:
            add_temp_ban(user_id, 300)
            await message.answer("❌ Вы заблокированы за флуд на 5 минут.")
        else:
            await message.answer(f"⚠️ Не флудите! Предупреждение {warnings}/3.")
        return
    
    update_user_stats(user_id, chat_id)
