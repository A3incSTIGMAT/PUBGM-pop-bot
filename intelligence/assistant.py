"""
NEXUS AI — Hugging Face Inference API (правильный формат)
"""

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import HUGGINGFACE_TOKEN

router = Router()

MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"

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
                f"https://api-inference.huggingface.co/models/{MODEL_ID}",
                headers={"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"},
                json={
                    "inputs": f"<s>[INST] {SYSTEM_PROMPT}\n\nВопрос: {args[1]} [/INST]",
                    "parameters": {
                        "max_new_tokens": 500,
                        "temperature": 0.7,
                        "do_sample": True
                    }
                }
            ) as resp:
                # Получаем текст ответа
                text = await resp.text()
                
                if resp.status == 200:
                    import json
                    data = json.loads(text)
                    if isinstance(data, list) and len(data) > 0:
                        answer = data[0].get("generated_text", "")
                        answer = answer.split("[/INST]")[-1].strip()
                        if not answer:
                            answer = "Не могу ответить. Попробуй переформулировать."
                    else:
                        answer = "⚠️ Неожиданный формат ответа."
                elif resp.status == 503:
                    answer = "⚠️ Модель загружается. Попробуй через 10 секунд."
                else:
                    answer = f"⚠️ Ошибка {resp.status}: {text[:200]}"
                    
    except Exception as e:
        answer = f"❌ Ошибка: {e}"
    
    await status.delete()
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")
