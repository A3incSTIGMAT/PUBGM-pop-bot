"""
AI-агент для NEXUS через DeepSeek API
"""

import aiohttp
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DEEPSEEK_API_KEY, AI_MODEL

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    """Установить экземпляр бота для модуля"""
    global bot
    bot = bot_instance

# Состояние для диалога
class AIState(StatesGroup):
    chatting = State()

# Системный промпт
SYSTEM_PROMPT = """Ты — AI-ассистент чата NEXUS. Ты встроен в чат-менеджер и помогаешь участникам.
Отвечай кратко, дружелюбно и полезно.
Если не знаешь ответа — скажи об этом честно.
Говори на русском языке.

О функциях NEXUS:
• NCoin — внутренняя валюта, можно получить через /daily (50 NCoin раз в сутки)
• VIP-статус даёт +25% к бонусу, эксклюзивные подарки, цветное имя. Цена 500 NCoin
• Игры: /rps (камень-ножницы-бумага), /roulette (рулетка)
• Подарки: /shop
• Модерация: /ban, /mute, /all
• Дни рождения: /setbirthday
• AI-ассистент: /ask, /ai"""

@router.message(Command("ask"))
async def cmd_ask(message: Message):
    """Быстрый вопрос AI"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🤖 **Быстрый вопрос AI**\n\n"
            "Использование: /ask [вопрос]\n"
            "Пример: /ask как получить VIP?\n\n"
            "Для диалога используйте /ai"
        )
        return
    
    if not DEEPSEEK_API_KEY:
        await message.answer(
            "⚠️ **AI-ассистент временно недоступен**\n\n"
            "API ключ не настроен. Пожалуйста, сообщите администратору.\n\n"
            "💡 Получить API ключ: https://platform.deepseek.com/"
        )
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
                    "temperature": 0.7,
                    "max_tokens": 1000
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    answer = data["choices"][0]["message"]["content"]
                else:
                    error_msg = data.get("error", {}).get("message", "Неизвестная ошибка")
                    answer = f"❌ Ошибка API: {error_msg}"
    
    except aiohttp.ClientError as e:
        answer = f"❌ Ошибка соединения: {e}"
    except Exception as e:
        answer = f"❌ Неожиданная ошибка: {e}"
    
    await status.delete()
    
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n... (ответ обрезан)"
    
    await message.answer(f"🤖 **AI-ассистент:**\n\n{answer}")

@router.message(Command("ai"))
async def cmd_ai(message: Message, state: FSMContext):
    """Начать диалог с AI"""
    if not DEEPSEEK_API_KEY:
        await message.answer(
            "⚠️ **AI-ассистент временно недоступен**\n\n"
            "API ключ не настроен. Пожалуйста, сообщите администратору.\n\n"
            "💡 Получить API ключ: https://platform.deepseek.com/"
        )
        return
    
    await state.set_state(AIState.chatting)
    await message.answer(
        "🤖 **AI-ассистент NEXUS**\n\n"
        "Я здесь, чтобы помочь! Можете задавать любые вопросы.\n\n"
        "📌 **Что я умею:**\n"
        "• Отвечать на вопросы о NEXUS\n"
        "• Помогать с настройкой бота\n"
        "• Давать советы\n\n"
        "💬 Просто напишите свой вопрос.\n"
        "❌ Для выхода напишите /cancel"
    )

@router.message(Command("cancel"), AIState.chatting)
async def cancel_ai(message: Message, state: FSMContext):
    """Выход из диалога"""
    await state.clear()
    await message.answer("✅ Выход из режима AI-ассистента. Для возврата используйте /ai")

@router.message(AIState.chatting)
async def process_ai_dialog(message: Message, state: FSMContext):
    """Обработка сообщений в диалоге"""
    if not message.text:
        return
    
    question = message.text
    
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
                        {"role": "user", "content": question}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    answer = data["choices"][0]["message"]["content"]
                else:
                    error_msg = data.get("error", {}).get("message", "Неизвестная ошибка")
                    answer = f"❌ Ошибка API: {error_msg}"
    
    except aiohttp.ClientError as e:
        answer = f"❌ Ошибка соединения: {e}"
    except Exception as e:
        answer = f"❌ Неожиданная ошибка: {e}"
    
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n... (ответ обрезан)"
    
    await message.answer(
        f"🤖 **AI-ассистент:**\n\n{answer}\n\n"
        f"💬 Задайте следующий вопрос или напишите /cancel для выхода"
    )
