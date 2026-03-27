from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в NEXUS!\n\n"
        "🤖 Я интеллектуальный ассистент.\n\n"
        "📌 Команды:\n"
        "/ask [вопрос] — спросить у AI\n"
        "/balance — баланс NCoin\n"
        "/daily — ежедневный бонус\n"
        "/menu — главное меню"
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 Справка NEXUS\n\n"
        "👤 Пользовательские команды:\n"
        "/start — приветствие\n"
        "/help — это сообщение\n"
        "/stats — статистика\n"
        "/balance — баланс NCoin\n"
        "/daily — ежедневный бонус\n"
        "/ask — вопрос AI\n"
        "/menu — главное меню"
    )
