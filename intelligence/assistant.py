"""
NEXUS AI — Hugging Face (новый API)
"""

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import HUGGINGFACE_TOKEN

router = Router()

# Используем модель Mistral — легкая и стабильная
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
                f"https://router.huggingface.co/{MODEL_ID}",  # ← НОВЫЙ URL!
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
                data = await resp.json()
                
                if isinstance(data, list) and len(data) > 0:
                    answer = data[0].get("generated_text", "")
                    answer = answer.split("[/INST]")[-1].strip()
                    if not answer:
                        answer = "Не могу ответить. Попробуй переформулировать."
                elif "error" in data:
                    answer = f"⚠️ Ошибка: {data['error']}"
                else:
                    answer = "⚠️ Не удалось получить ответ."
                    
    except Exception as e:
        answer = f"❌ Ошибка: {e}"
    
    await status.delete()
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")
