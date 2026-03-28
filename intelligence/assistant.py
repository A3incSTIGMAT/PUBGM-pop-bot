"""
NEXUS AI — Временная версия (без API)
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("ask"))
async def cmd_ask(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🤖 **NEXUS AI**\n\n"
            "Использование: /ask [вопрос]\n"
            "Пример: /ask как получить VIP?\n\n"
            "💡 AI-ассистент настраивается. Скоро будет доступен!"
        )
        return
    
    # Временный ответ
    await message.answer(
        f"🤖 **NEXUS AI:**\n\n"
        f"Ваш вопрос: {args[1]}\n\n"
        f"⚙️ AI-ассистент в разработке. В ближайшее время он научится отвечать на любые вопросы!\n\n"
        f"А пока вы можете:\n"
        f"• /balance — проверить баланс\n"
        f"• /daily — получить бонус\n"
        f"• /menu — открыть меню\n"
        f"• /shop — магазин подарков"
    )

@router.message(Command("ai"))
async def cmd_ai(message: Message):
    await message.answer(
        "🤖 **NEXUS AI — Интеллектуальный ассистент**\n\n"
        "📌 **Статус:** В разработке\n\n"
        "✨ В ближайшее время AI научится:\n"
        "• Отвечать на любые вопросы\n"
        "• Помогать с настройкой бота\n"
        "• Рассказывать о функциях NEXUS\n"
        "• Давать советы и идеи\n\n"
        "⚡ Пока доступны:\n"
        "• /balance — баланс NCoin\n"
        "• /daily — ежедневный бонус\n"
        "• /menu — главное меню\n"
        "• /shop — магазин подарков"
    )
