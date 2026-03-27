"""
NEXUS AI — Интеллектуальный ассистент
"""

import aiohttp
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DEEPSEEK_API_KEY, AI_MODEL

router = Router()

class AIState(StatesGroup):
    chatting = State()

SYSTEM_PROMPT = """Ты — NEXUS AI, интеллектуальный ассистент для Telegram.
Ты понимаешь русский язык, отвечаешь кратко и полезно.
Ты помогаешь пользователям, отвечаешь на вопросы, даёшь советы.
Твоя задача — сделать общение в чате приятным и полезным.
"""

@router.message(Command("ask"))
async def cmd_ask(message: Message):
    """Быстрый вопрос AI"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🤖 **NEXUS AI**\n\n"
            "Использование: /ask [вопрос]\n"
            "Пример: /ask как дела?\n\n"
            "💡 Задай любой вопрос, я постараюсь помочь!"
        )
        return
    
    if not DEEPSEEK_API_KEY:
        await message.answer("⚠️ AI недоступен. API ключ не настроен.")
        return
    
    question = args[1]
    status = await message.answer("🤔 Думаю...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": question}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 1000
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                
                if "choices" in data and data["choices"]:
                    answer = data["choices"][0]["message"]["content"]
                elif "error" in data:
                    answer = f"❌ Ошибка API: {data['error'].get('message', 'Неизвестная ошибка')}"
                else:
                    answer = f"❌ Неожиданный ответ от API: {data}"
                    
    except aiohttp.ClientError as e:
        answer = f"❌ Ошибка соединения: {e}"
    except Exception as e:
        answer = f"❌ Неожиданная ошибка: {e}"
    
    await status.delete()
    
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n... (ответ обрезан)"
    
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")

@router.message(Command("ai"))
async def cmd_ai(message: Message, state: FSMContext):
    """Начать диалог с AI"""
    if not DEEPSEEK_API_KEY:
        await message.answer("⚠️ AI недоступен. API ключ не настроен.")
        return
    
    await state.set_state(AIState.chatting)
    await message.answer(
        "🤖 **NEXUS AI**\n\n"
        "Я здесь, чтобы помочь! Задавайте любые вопросы.\n\n"
        "💡 **Что я умею:**\n"
        "• Отвечать на любые вопросы\n"
        "• Помогать с управлением чатом\n"
        "• Исследовать любые темы\n"
        "• Генерировать идеи и тексты\n\n"
        "❌ Для выхода напишите /cancel"
    )

@router.message(Command("cancel"), AIState.chatting)
async def cancel_ai(message: Message, state: FSMContext):
    """Выход из диалога"""
    await state.clear()
    await message.answer("✅ Выход из режима AI-ассистента.")

@router.message(AIState.chatting)
async def ai_dialog(message: Message, state: FSMContext):
    """Обработка сообщений в диалоге"""
    if not message.text:
        return
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": message.text}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 1000
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                
                if "choices" in data and data["choices"]:
                    answer = data["choices"][0]["message"]["content"]
                elif "error" in data:
                    answer = f"❌ Ошибка API: {data['error'].get('message', 'Неизвестная ошибка')}"
                else:
                    answer = f"❌ Неожиданный ответ от API: {data}"
                    
    except aiohttp.ClientError as e:
        answer = f"❌ Ошибка соединения: {e}"
    except Exception as e:
        answer = f"❌ Неожиданная ошибка: {e}"
    
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n... (ответ обрезан)"
    
    await message.answer(
        f"🤖 **NEXUS AI:**\n\n{answer}\n\n"
        f"💬 Продолжайте или /cancel"
    )
