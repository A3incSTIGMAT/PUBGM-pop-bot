from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

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
        "/gift @username 50 — подарить монеты\n\n"
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
        "/balance — ваш баланс\n"
        "/gift @username [сумма] — подарить монеты\n\n"
        "🛡 Админ-команды:\n"
        "/all — отметить всех участников\n"
        "/ban — забанить (ответом на сообщение)\n"
        "/mute [время] — заглушить (ответом)\n"
        "/welcome [текст] — настроить приветствие\n\n"
        "🎮 Игры:\n"
        "/duel — дуэль с другим игроком\n"
        "/rps — камень-ножницы-бумага\n"
        "/roulette — рулетка\n\n"
        "💰 Экономика:\n"
        "/top — топ богачей\n"
        "/shop — магазин подарков"
    )
