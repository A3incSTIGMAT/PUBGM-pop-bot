#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: handlers/ai_assistant.py
# ВЕРСИЯ: 1.2.0-production (исправленная после аудита)
# ОПИСАНИЕ: AI помощник через OpenRouter API
# ============================================
# ИСПРАВЛЕНИЯ v1.2.0:
#   🔴 Устранена утечка aiohttp сессии
#   🟡 Добавлен retry с экспоненциальной задержкой
#   🟡 API ключ маскируется в логах
#   🟡 Добавлена обработка CancelledError
#   🟢 Сессия переиспользуется между запросами
#   🟢 Настраиваемые параметры через переменные окружения
#   🟢 Системный промпт загружается из переменной окружения
# ============================================

import asyncio
import html
import logging
import os
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
import aiohttp

router = Router()
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ (НАСТРАИВАЕМЫЕ) ====================

# Загрузка из переменных окружения с fallback-значениями
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-3.5-turbo")
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "150"))
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "30"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))
AI_RETRY_DELAY = float(os.getenv("AI_RETRY_DELAY", "1.0"))
MAX_RESPONSE_LENGTH = int(os.getenv("AI_MAX_RESPONSE_LENGTH", "1000"))

# Системный промпт — загружается из переменной окружения или используется默认ный
SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    """Ты — NEXUS AI, помощник в чат-боте NEXUS Chat Manager.
Отвечай кратко, дружелюбно и по делу. 
Бот имеет функции: крестики-нолики, экономику, VIP, ежедневные бонусы, реферальную систему, теги.
Отвечай на русском языке. Максимум 3-4 предложения."""
)


# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================

# Переиспользуемая сессия aiohttp (создаётся при старте)
_session: Optional[aiohttp.ClientSession] = None
_session_lock: asyncio.Lock = asyncio.Lock()


async def get_session() -> aiohttp.ClientSession:
    """
    Получение или создание переиспользуемой сессии aiohttp.
    
    Сессия создаётся один раз и переиспользуется для всех запросов.
    При остановке бота должна быть закрыта через close_session().
    
    Returns:
        Активная aiohttp.ClientSession
        
    Example:
        >>> session = await get_session()
        >>> async with session.get(url) as resp:
        ...     data = await resp.json()
    """
    global _session
    
    async with _session_lock:
        if _session is None or _session.closed:
            timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT)
            _session = aiohttp.ClientSession(timeout=timeout)
            logger.info("✅ AI assistant HTTP session created")
    
    return _session


async def close_session() -> None:
    """Закрытие HTTP-сессии при остановке бота."""
    global _session
    
    async with _session_lock:
        if _session and not _session.closed:
            await _session.close()
            _session = None
            logger.info("✅ AI assistant HTTP session closed")


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """
    Безопасное экранирование HTML.
    
    Args:
        text: Строка для экранирования
        
    Returns:
        Экранированная строка или пустая строка при ошибке
    """
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def _mask_api_key(key: str) -> str:
    """Маскировка API ключа для безопасного логирования."""
    if not key:
        return "[NOT SET]"
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


async def ask_openrouter(question: str) -> Optional[str]:
    """
    Отправляет запрос к OpenRouter API с повторными попытками.
    
    Args:
        question: Вопрос пользователя
        
    Returns:
        Ответ от AI или None при ошибке
        
    Example:
        >>> answer = await ask_openrouter("Как заработать монеты?")
        >>> print(answer)
        'Используйте /daily, играйте в /xo, приглашайте друзей.'
    """
    if not OPENROUTER_API_KEY:
        logger.warning("⚠️ OpenRouter API key not configured")
        return None
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ],
        "max_tokens": AI_MAX_TOKENS,
        "temperature": AI_TEMPERATURE,
    }
    
    last_error: Optional[Exception] = None
    
    for attempt in range(AI_MAX_RETRIES):
        try:
            session = await get_session()
            
            async with session.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and "choices" in data and len(data["choices"]) > 0:
                        answer = data["choices"][0]["message"]["content"]
                        logger.info(
                            "✅ AI response received (attempt %d/%d, len=%d)",
                            attempt + 1, AI_MAX_RETRIES, len(answer)
                        )
                        return answer.strip()
                    else:
                        logger.warning("⚠️ Empty AI response structure")
                        return None
                
                elif response.status == 429:
                    # Rate limit — ждём и пробуем снова
                    retry_after = response.headers.get("Retry-After", str(AI_RETRY_DELAY * (2 ** attempt)))
                    wait_time = min(float(retry_after), 60)
                    logger.warning(
                        "⏱ OpenRouter rate limit (429), waiting %.1fs (attempt %d/%d)",
                        wait_time, attempt + 1, AI_MAX_RETRIES
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                else:
                    error_text = await response.text()
                    logger.error(
                        "❌ OpenRouter API error: %d (attempt %d/%d, question='%s...')",
                        response.status, attempt + 1, AI_MAX_RETRIES, question[:50]
                    )
                    if attempt < AI_MAX_RETRIES - 1:
                        await asyncio.sleep(AI_RETRY_DELAY * (2 ** attempt))
                    continue
                    
        except asyncio.TimeoutError:
            last_error = asyncio.TimeoutError()
            logger.warning(
                "⏱ OpenRouter timeout (attempt %d/%d)", attempt + 1, AI_MAX_RETRIES
            )
            if attempt < AI_MAX_RETRIES - 1:
                await asyncio.sleep(AI_RETRY_DELAY * (2 ** attempt))
                
        except asyncio.CancelledError:
            logger.debug("🛑 AI request cancelled")
            raise
            
        except aiohttp.ClientError as e:
            last_error = e
            logger.warning(
                "⚠️ OpenRouter connection error: %s (attempt %d/%d)",
                e, attempt + 1, AI_MAX_RETRIES
            )
            if attempt < AI_MAX_RETRIES - 1:
                await asyncio.sleep(AI_RETRY_DELAY * (2 ** attempt))
                
        except Exception as e:
            logger.error("❌ OpenRouter unexpected error: %s", e, exc_info=True)
            return None
    
    # Исчерпаны все попытки
    logger.error(
        "❌ All %d attempts failed. Last error: %s", AI_MAX_RETRIES, last_error
    )
    return None


# ==================== ОБРАБОТЧИКИ ====================

@router.message(Command("ask"))
async def cmd_ask(message: types.Message) -> None:
    """
    AI помощник — отвечает на вопросы.
    
    Использование: /ask [вопрос]
    Пример: /ask как заработать монеты?
    """
    if message is None:
        return
    
    # Проверка доступности AI
    if not AI_ENABLED:
        await message.answer("🤖 AI помощник временно отключён.")
        return
    
    if not OPENROUTER_API_KEY:
        await message.answer(
            "🤖 AI помощник не настроен.\n"
            "Администратор должен добавить OPENROUTER_API_KEY в .env файл."
        )
        return
    
    # Извлечение вопроса (устойчиво к регистру команды)
    if message.text is None:
        await message.answer("❌ Пустой запрос.")
        return
    
    # Удаляем команду (работает для /ask и /ASK)
    text = message.text.strip()
    if text.lower().startswith("/ask"):
        question = text[4:].strip()  # Удаляем "/ask"
    else:
        question = text
    
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
    
    thinking_msg = None
    try:
        # Отправляем статус
        thinking_msg = await message.answer(
            "🤖 <i>Думаю над ответом...</i>", parse_mode=ParseMode.HTML
        )
        
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
        
        # Отправляем ответ
        await message.answer(response_text, parse_mode=ParseMode.HTML)
        
    except asyncio.CancelledError:
        logger.debug("🛑 AI handler cancelled")
        raise
    except Exception as e:
        logger.error("❌ AI handler error: %s", e, exc_info=True)
        await message.answer(
            "🤖 <b>NEXUS AI:</b>\n\nПроизошла ошибка. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
    finally:
        # Удаляем статусное сообщение в любом случае
        if thinking_msg:
            try:
                await thinking_msg.delete()
            except TelegramAPIError:
                pass  # Сообщение уже удалено или недоступно


@router.message(Command("ai"))
async def cmd_ai(message: types.Message) -> None:
    """Алиас для /ask."""
    await cmd_ask(message)


# ==================== ШУТДАУН ХУК ====================

async def on_shutdown() -> None:
    """Закрытие HTTP-сессии при остановке бота."""
    await close_session()
    logger.info("✅ AI assistant shutdown complete")
