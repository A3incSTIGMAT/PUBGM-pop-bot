from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from config import OPENROUTER_API_KEY, AI_ENABLED

router = Router()

@router.message(Command("ask"))
async def cmd_ask(message: types.Message):
    if not AI_ENABLED or not OPENROUTER_API_KEY:
        await message.answer("🤖 AI помощник временно недоступен. Попробуйте позже.")
        return
    
    question = message.text.replace("/ask", "").strip()
    if not question:
        await message.answer("❌ Использование: /ask <вопрос>\nПример: /ask как заработать монеты?")
        return
    
    await message.answer("🤖 Думаю... ⏳")
    
    # Здесь будет запрос к OpenRouter API
    await message.answer(f"🤖 Ваш вопрос: {question}\n\n(API ключ настроен, ожидается ответ)")
