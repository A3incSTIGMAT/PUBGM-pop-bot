#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/ai_assistant.py
# ВЕРСИЯ: 1.1.0-production
# ОПИСАНИЕ: AI помощник через OpenRouter API
# ============================================

import asyncio
import logging
import html
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
import aiohttp

from config import OPENROUTER_API_KEY, AI_ENABLED

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_TIMEOUT = 30  # секунд
MAX_RESPONSE_LENGTH = 1000

# Системный промпт для бота
SYSTEM_PROMPT = """Ты — NEXUS AI, помощник в чат-боте NEXUS Chat Manager.
Отвечай кратко, дружелюбно и по делу. 
Бот имеет функции: крестики-нолики, экономику, VIP, ежедневные бонусы, реферальную систему, теги.
Отвечай на русском языке. Максимум 3-4 предложения."""


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


async def ask_openrouter(question: str) -> Optional[str]:
    """
    Отправляет запрос к OpenRouter API.
    
    Args:
        question: Вопрос пользователя
        
    Returns:
        Ответ от AI или None при ошибке
    """
    if not OPENROUTER_API_KEY:
        return None
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": "openai/gpt-3.5-turbo",  # Бесплатная модель
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ],
        "max_tokens": 150,
        "temperature": 0.7,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and "choices" in data and len(data["choices"]) > 0:
                        answer = data["choices"][0]["message"]["content"]
                        return answer.strip()
                else:
                    error_text = await response.text()
                    logger.error(f"OpenRouter API error: {response.status} - {error_text[:200]}")
                    return None
    except asyncio.TimeoutError:
        logger.error("OpenRouter API timeout")
        return None
    except aiohttp.ClientError as e:
        logger.error(f"OpenRouter connection error: {e}")
        return None
    except Exception as e:
        logger.error(f"OpenRouter unexpected error: {e}", exc_info=True)
        return None


# ==================== ОБРАБОТЧИКИ ====================

@router.message(Command("ask"))
async def cmd_ask(message: types.Message) -> None:
    """AI помощник — отвечает на вопросы."""
    if message is None:
        return
    
    # Проверка доступности AI
    if not AI_ENABLED:
        await message.answer("🤖 AI помощник временно отключён.")
        return
    
    if not OPENROUTER_API_KEY:
        await message.answer("🤖 AI помощник не настроен. Добавьте OPENROUTER_API_KEY.")
        return
    
    # Извлечение вопроса
    if message.text is None:
        await message.answer("❌ Пустой запрос.")
        return
    
    question = message.text.replace("/ask", "", 1).strip()
    
    if not question:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/ask как заработать монеты?</code>\n\n"
            "<b>Примеры вопросов:</b>\n"
            "• Как играть в крестики-нолики?\n"
            "• Что даёт VIP статус?\n"
            "• Как получить ежедневный бонус?\n"
            "• Как пригласить друга?",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Отправляем статус
    thinking_msg = await message.answer("🤖 <i>Думаю над ответом...</i>", parse_mode=ParseMode.HTML)
    
    try:
        # Запрос к API
        answer = await ask_openrouter(question)
        
        if answer:
            # Экранируем и обрезаем ответ
            safe_answer = safe_html_escape(answer)
            if len(safe_answer) > MAX_RESPONSE_LENGTH:
                safe_answer = safe_answer[:MAX_RESPONSE_LENGTH] + "..."
            
            response_text = f"🤖 <b>NEXUS AI:</b>\n\n{safe_answer}"
        else:
            response_text = (
                "🤖 <b>NEXUS AI:</b>\n\n"
                "Извините, не могу ответить сейчас. Попробуйте позже.\n\n"
                "💡 <i>Пока я учусь, вот ответы на частые вопросы:</i>\n\n"
                "• <b>Заработать монеты:</b> /daily, играйте в /xo, приглашайте друзей\n"
                "• <b>VIP статус:</b> /vip — бонусы к выигрышам и daily\n"
                "• <b>Игры:</b> /xo — крестики-нолики с ботом и игроками"
            )
        
        # Удаляем статус и отправляем ответ
        await thinking_msg.delete()
        await message.answer(response_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"AI handler error: {e}", exc_info=True)
        try:
            await thinking_msg.delete()
        except:
            pass
        await message.answer("🤖 <b>NEXUS AI:</b>\n\nПроизошла ошибка. Попробуйте позже.", parse_mode=ParseMode.HTML)


@router.message(Command("ai"))
async def cmd_ai(message: types.Message) -> None:
    """Алиас для /ask."""
    await cmd_ask(message)
