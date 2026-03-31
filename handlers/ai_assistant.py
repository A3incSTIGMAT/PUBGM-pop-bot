"""
ai_assistant.py — AI помощник (OpenRouter)
"""

import aiohttp
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from config import OPENROUTER_API_KEY, AI_ENABLED
from utils.keyboards import back_button

router = Router()


@router.callback_query(F.data == "ai")
async def ai_menu(callback: CallbackQuery):
    """Меню AI помощника"""
    text = (
        "🤖 *AI Помощник*\n\n"
        "Задайте любой вопрос — я постараюсь ответить.\n\n"
        "Использование: `/ask [вопрос]`\n\n"
        "Пример: `/ask Как дела?`"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


@router.message(Command("ask"))
async def ask_ai(message: Message):
    """Запрос к AI"""
    if not AI_ENABLED or not OPENROUTER_API_KEY:
        await message.answer("🤖 AI пока недоступен")
        return

    query = message.text.replace("/ask", "", 1).strip()
    if not query:
        await message.answer("❓ Напишите вопрос после /ask")
        return

    await message.answer("🤔 Думаю...")

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 500
            }

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    answer = result["choices"][0]["message"]["content"]
                    await message.answer(f"🤖 {answer}")
                else:
                    await message.answer("⚠️ Ошибка AI сервиса")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {str(e)[:100]}")
