from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

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
