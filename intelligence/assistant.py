"""
NEXUS AI — Meta-Llama-3.1-8B-Instruct через Hugging Face
"""

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import HUGGINGFACE_TOKEN

router = Router()

MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"

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
                    "inputs": f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{SYSTEM_PROMPT}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{args[1]}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
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
                    # Очищаем ответ
                    answer = answer.split("assistant<|end_header_id|>")[-1].strip()
                    answer = answer.split("<|eot_id|>")[0].strip()
                    if not answer:
                        answer = "Не могу ответить. Попробуй переформулировать."
                else:
                    answer = "⚠️ Не удалось получить ответ."
                    
    except Exception as e:
        answer = f"❌ Ошибка: {e}"
    
    await status.delete()
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")
