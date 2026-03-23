from aiogram import Router
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import Message, ChatMemberUpdated
from database.db import get_welcome_message

router = Router()

# Команда /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в NEXUS!\n\n"
        "Я мощный чат-менеджер с играми и экономикой.\n\n"
        "📌 Основные команды:\n"
        "/help — помощь\n"
        "/stats — моя статистика\n"
        "/balance — мой баланс\n"
        "/daily — ежедневный бонус\n"
        "/gift @username 50 — подарить NCoin\n\n"
        "🎮 Игры:\n"
        "/duel @username 50 — вызвать на дуэль\n"
        "/rps — камень-ножницы-бумага\n"
        "/roulette 100 red — рулетка\n\n"
        "🛡 Админ-команды:\n"
        "/all — отметить всех\n"
        "/ban @username — забанить\n"
        "/mute @username 10m — заглушить"
    )

# Команда /help
@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 Справка NEXUS\n\n"
        "👤 Пользовательские команды:\n"
        "/start — приветствие\n"
        "/help — это сообщение\n"
        "/stats — ваша статистика\n"
        "/balance — ваш баланс NCoin\n"
        "/daily — ежедневный бонус NCoin\n"
        "/gift @username [сумма] — подарить NCoin\n\n"
        "🛡 Админ-команды:\n"
        "/all — отметить всех участников\n"
        "/ban — забанить (ответом на сообщение)\n"
        "/mute [время] — заглушить (ответом)\n"
        "/setwelcome [текст] — настроить приветствие\n\n"
        "🎮 Игры:\n"
        "/duel — дуэль с другим игроком\n"
        "/rps — камень-ножницы-бумага\n"
        "/roulette — рулетка\n\n"
        "💰 Экономика:\n"
        "/top — топ богачей\n"
        "/shop — магазин подарков"
    )

# Приветствие при добавлении бота в чат
@router.my_chat_member(ChatMemberUpdatedFilter(
    member_status_changed=JOIN_TRANSITION
))
async def on_bot_added_to_chat(event: ChatMemberUpdated):
    """Когда бота добавляют в чат"""
    chat = event.chat
    
    welcome_text = (
        f"🤖 **NEXUS Chat Manager**\n\n"
        f"Привет! Я мощный чат-менеджер для Telegram.\n"
        f"Вот что я умею:\n\n"
        f"🛡 **Модерация**\n"
        f"• `/all` — отметить всех участников\n"
        f"• `/ban` — забанить нарушителя\n"
        f"• `/mute` — заглушить на время\n\n"
        f"💰 **Экономика**\n"
        f"• Внутренняя валюта **NCoin**\n"
        f"• `/daily` — ежедневный бонус\n"
        f"• `/gift` — дарить монеты\n"
        f"• `/top` — топ богачей\n\n"
        f"🎮 **Игры**\n"
        f"• `/rps` — камень-ножницы-бумага\n"
        f"• `/roulette` — рулетка на NCoin\n"
        f"• `/duel` — дуэль с игроками\n\n"
        f"✨ **Уникальные фишки**\n"
        f"• Приветствие новых участников\n"
        f"• Система уровней активности\n\n"
        f"🔧 **Для настройки**\n"
        f"• `/setwelcome` — настроить приветствие\n\n"
        f"💡 Дайте мне права администратора!\n\n"
        f"🚀 Готов сделать ваш чат лучше!"
    )
    
    await event.answer(welcome_text)

# Приветствие новых участников в чате
@router.chat_member(ChatMemberUpdatedFilter(
    member_status_changed=IS_NOT_MEMBER >> IS_MEMBER
))
async def on_user_join(event: ChatMemberUpdated):
    """Когда новый пользователь заходит в чат"""
    chat = event.chat
    user = event.new_chat_member.user
    
    if user.is_bot:
        return
    
    welcome_template = get_welcome_message(chat.id)
    
    if welcome_template:
        welcome_text = welcome_template.format(
            user=user.full_name,
            chat=chat.title or "этот чат"
        )
    else:
        welcome_text = (
            f"👋 Добро пожаловать, {user.full_name}!\n\n"
            f"📌 Я NEXUS — чат-менеджер.\n"
            f"/help — помощь\n"
            f"/balance — баланс NCoin\n"
            f"/daily — бонус каждый день!\n\n"
            f"🎮 Игры: /rps /roulette"
        )
    
    await event.answer(welcome_text)
