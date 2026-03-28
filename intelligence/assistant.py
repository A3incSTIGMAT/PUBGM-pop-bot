"""
NEXUS AI — Ollama (локальная модель на Amvera)
"""

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import OLLAMA_URL

router = Router()

SYSTEM_PROMPT = """Ты — NEXUS AI, дружелюбный помощник для Telegram.
Отвечай кратко, полезно и на русском языке.
Помогай пользователям с вопросами о боте, давай советы."""

@router.message(Command("ask"))
async def cmd_ask(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🤖 **NEXUS AI**\n\n"
            "Использование: /ask [вопрос]\n"
            "Пример: /ask как получить VIP?\n\n"
            "💡 Задай любой вопрос!"
        )
        return
    
    status = await message.answer("🤔 Думаю...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": "tinyllama",
                    "prompt": f"{SYSTEM_PROMPT}\n\nВопрос: {args[1]}\nОтвет:",
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 500
                    }
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data.get("response", "Не удалось получить ответ")
                else:
                    answer = f"⚠️ Ошибка {resp.status}: модель загружается. Попробуй через минуту."
    except aiohttp.ClientError as e:
        answer = f"❌ Ошибка соединения: {e}"
    except Exception as e:
        answer = f"❌ Ошибка: {e}"
    
    await status.delete()
    
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n... (ответ обрезан)"
    
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")

@router.message(Command("ai"))
async def cmd_ai(message: Message):
    """Справка по AI-ассистенту"""
    await message.answer(
        "🤖 **NEXUS AI — Интеллектуальный ассистент**\n\n"
        "📌 **Команды:**\n"
        "/ask [вопрос] — быстрый ответ\n"
        "/ai — эта справка\n\n"
        "💡 **Что умеет:**\n"
        "• Отвечать на любые вопросы\n"
        "• Помогать с настройкой бота\n"
        "• Рассказывать о функциях NEXUS\n"
        "• Давать советы и идеи\n\n"
        "⚡ **Технологии:** локальная модель tinyllama (Ollama)\n"
        "🎁 **Бесплатно, без ограничений**"
    )
