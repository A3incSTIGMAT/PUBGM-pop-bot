"""
NEXUS AI — Гибридный AI-ассистент с fallback-механизмом
Пробует несколько источников: OpenRouter → Hugging Face → Заглушка
"""

import aiohttp
import json
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import OPENROUTER_API_KEY, HUGGINGFACE_TOKEN

router = Router()

SYSTEM_PROMPT = """Ты — NEXUS AI, дружелюбный помощник для Telegram.
Отвечай кратко, полезно и на русском языке.
Помогай пользователям с вопросами о боте, давай советы."""

# ========== OPENROUTER (попытка 1) ==========
async def ask_openrouter(question: str) -> str:
    """Попытка получить ответ через OpenRouter"""
    if not OPENROUTER_API_KEY:
        return None
    
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
                        {"role": "user", "content": question}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json()
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"]
    except:
        pass
    return None

# ========== HUGGING FACE (попытка 2) ==========
async def ask_huggingface(question: str) -> str:
    """Попытка получить ответ через Hugging Face"""
    if not HUGGINGFACE_TOKEN:
        return None
    
    prompt = f"{SYSTEM_PROMPT}\n\nВопрос: {question}\nОтвет:"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
                headers={"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"},
                json={"inputs": prompt},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    if isinstance(data, list) and len(data) > 0:
                        answer = data[0].get("generated_text", "")
                        if prompt in answer:
                            answer = answer.replace(prompt, "").strip()
                        return answer[:1000]
    except:
        pass
    return None

# ========== ЗАГЛУШКА (последний шанс) ==========
def ask_fallback(question: str) -> str:
    """Ответ-заглушка"""
    return (
        f"⚙️ **AI-ассистент временно недоступен.**\n\n"
        f"Ваш вопрос: {question}\n\n"
        f"💡 **А пока вы можете:**\n"
        f"• /balance — проверить баланс\n"
        f"• /daily — получить бонус\n"
        f"• /menu — открыть меню\n"
        f"• /pay — пополнить баланс\n\n"
        f"🔧 Технические работы. AI скоро вернется!"
    )

@router.message(Command("ask"))
async def cmd_ask(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🤖 **NEXUS AI**\n\n"
            "Использование: /ask [вопрос]\n"
            "Пример: /ask как получить VIP?\n\n"
            "💡 Задай любой вопрос, и я постараюсь помочь!"
        )
        return
    
    question = args[1]
    status = await message.answer("🤔 Думаю...")
    
    # Пробуем OpenRouter
    answer = await ask_openrouter(question)
    
    # Если не получилось — пробуем Hugging Face
    if not answer:
        answer = await ask_huggingface(question)
    
    # Если ничего не сработало — заглушка
    if not answer:
        answer = ask_fallback(question)
    
    await status.delete()
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")

@router.message(Command("ai"))
async def cmd_ai(message: Message):
    """Справка по AI-ассистенту"""
    await message.answer(
        "🤖 **NEXUS AI — Интеллектуальный ассистент**\n\n"
        "📌 **Команды:**\n"
        "/ask [вопрос] — быстрый ответ\n"
        "/ai — эта справка\n\n"
        "💡 **Что я умею:**\n"
        "• Отвечать на любые вопросы\n"
        "• Помогать с настройкой бота\n"
        "• Рассказывать о функциях NEXUS\n"
        "• Давать советы и идеи\n\n"
        "⚡ **Технологии:** OpenRouter + Hugging Face\n"
        "🎁 **Бесплатно, без ограничений**"
    )
