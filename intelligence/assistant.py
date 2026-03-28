"""
NEXUS AI — OpenRouter API (рабочая модель)
"""

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import OPENROUTER_API_KEY

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
            "Пример: /ask как получить VIP?"
        )
        return
    
    status = await message.answer("🤔 Думаю...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "mistralai/mistral-7b-instruct:free",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": args[1]}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            ) as resp:
                data = await resp.json()
                if "choices" in data and data["choices"]:
                    answer = data["choices"][0]["message"]["content"]
                else:
                    error = data.get("error", {})
                    answer = f"⚠️ Ошибка: {error.get('message', 'Неизвестная ошибка')}"
    except Exception as e:
        answer = f"❌ Ошибка: {e}"
    
    await status.delete()
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")
