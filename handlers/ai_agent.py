"""
AI-агент для NEXUS на базе OpenAkita
Полностью интегрирован в бота, пользователь не видит разницы
"""

import os
import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from openakita import AkitaAgent
from openakita.memory import SQLiteMemory
from openakita.tools import load_tools

router = Router()

# Состояния для диалога с AI
class AIState(StatesGroup):
    chatting = State()

# Инициализация агента
class NexusAIAgent:
    def __init__(self):
        self.agent = None
        self.memory = None
        self.is_ready = False
    
    async def initialize(self):
        """Инициализация AI-агента"""
        try:
            # Настройка памяти (SQLite для постоянного хранения)
            self.memory = SQLiteMemory(db_path="/data/akita_memory.db")
            
            # Загрузка инструментов
            tools = load_tools([
                "web_search",
                "calculator", 
                "datetime",
                "text_generation"
            ])
            
            # Создание агента
            self.agent = AkitaAgent(
                model="deepseek-chat",  # бесплатная модель
                memory=self.memory,
                tools=tools,
                system_prompt=(
                    "Ты — AI-ассистент чата NEXUS. "
                    "Ты встроен в чат-менеджер и помогаешь участникам. "
                    "Отвечай кратко, дружелюбно и полезно. "
                    "Если не знаешь ответа — скажи об этом честно. "
                    "Говори на русском языке."
                )
            )
            
            self.is_ready = True
            print("✅ AI-агент OpenAkita инициализирован")
            
        except Exception as e:
            print(f"❌ Ошибка инициализации AI-агента: {e}")
            self.is_ready = False
    
    async def ask(self, question: str, user_id: int, chat_id: int, username: str) -> str:
        """Задать вопрос AI-агенту"""
        if not self.is_ready:
            return "🤖 AI-ассистент временно недоступен. Попробуйте позже."
        
        try:
            # Добавляем контекст пользователя
            context = f"Пользователь: {username}\nВопрос: {question}"
            
            # Получаем ответ от агента
            response = await self.agent.chat(
                message=context,
                user_id=str(user_id),
                session_id=str(chat_id)
            )
            
            return response
        
        except Exception as e:
            return f"❌ Ошибка: {e}"

# Глобальный экземпляр агента
ai_agent = NexusAIAgent()

# Клавиатура для AI-помощника
def get_ai_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🤖 Задать вопрос", callback_data="ai_ask"),
            InlineKeyboardButton(text="🗑️ Очистить память", callback_data="ai_clear")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика AI", callback_data="ai_stats"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="ai_close")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== КОМАНДЫ AI ==========

@router.message(Command("ai"))
async def cmd_ai(message: Message, state: FSMContext):
    """Команда /ai — открыть AI-ассистента"""
    if not ai_agent.is_ready:
        await message.answer(
            "🤖 **AI-ассистент NEXUS**\n\n"
            "В настоящее время инициализация агента...\n"
            "Попробуйте через несколько секунд."
        )
        return
    
    await state.set_state(AIState.chatting)
    await message.answer(
        "🤖 **AI-ассистент NEXUS**\n\n"
        "Я встроенный AI-помощник. Можешь задать любой вопрос!\n\n"
        "📌 **Что я умею:**\n"
        "• Отвечать на вопросы\n"
        "• Помогать с настройкой бота\n"
        "• Рассказывать о функциях NEXUS\n"
        "• Давать советы\n\n"
        "💬 Просто напиши свой вопрос, и я отвечу.\n"
        "❌ Для выхода напишите /cancel",
        reply_markup=get_ai_keyboard()
    )

@router.message(Command("cancel"), AIState.chatting)
async def cancel_ai(message: Message, state: FSMContext):
    """Выход из режима AI"""
    await state.clear()
    await message.answer("✅ Выход из режима AI-ассистента. Для возврата используйте /ai")

@router.message(AIState.chatting)
async def process_ai_question(message: Message, state: FSMContext):
    """Обработка вопроса к AI"""
    if not message.text:
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.full_name
    
    # Отправляем статус "печатает"
    await message.bot.send_chat_action(chat_id, "typing")
    
    # Получаем ответ от AI
    response = await ai_agent.ask(message.text, user_id, chat_id, username)
    
    # Отправляем ответ (с кнопкой продолжения)
    await message.answer(
        f"🤖 **AI-ассистент:**\n\n{response}\n\n"
        f"💬 Задайте следующий вопрос или напишите /cancel для выхода",
        reply_markup=get_ai_keyboard()
    )

# ========== ОБРАБОТЧИКИ КНОПОК ==========

@router.callback_query(lambda c: c.data == "ai_ask")
async def ai_ask_callback(callback: CallbackQuery, state: FSMContext):
    """Кнопка задать вопрос"""
    await state.set_state(AIState.chatting)
    await callback.message.edit_text(
        "🤖 **AI-ассистент**\n\n"
        "Напишите свой вопрос, и я отвечу.\n"
        "❌ Для выхода напишите /cancel",
        reply_markup=get_ai_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "ai_clear")
async def ai_clear_callback(callback: CallbackQuery):
    """Очистить память AI"""
    if ai_agent.memory:
        await ai_agent.memory.clear_user_session(callback.from_user.id)
        await callback.message.edit_text(
            "✅ **Память AI-ассистента очищена!**\n\n"
            "Теперь я не помню предыдущие вопросы.",
            reply_markup=get_ai_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ Память недоступна.",
            reply_markup=get_ai_keyboard()
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "ai_stats")
async def ai_stats_callback(callback: CallbackQuery):
    """Статистика AI"""
    if ai_agent.memory:
        stats = await ai_agent.memory.get_stats()
        await callback.message.edit_text(
            f"📊 **Статистика AI-ассистента**\n\n"
            f"• Активных сессий: {stats.get('sessions', 0)}\n"
            f"• Всего сообщений: {stats.get('messages', 0)}\n"
            f"• Статус: {'✅ Работает' if ai_agent.is_ready else '❌ Ошибка'}",
            reply_markup=get_ai_keyboard()
        )
    else:
        await callback.message.edit_text(
            "📊 Статистика временно недоступна.",
            reply_markup=get_ai_keyboard()
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "ai_close")
async def ai_close_callback(callback: CallbackQuery, state: FSMContext):
    """Закрыть AI-ассистента"""
    await state.clear()
    await callback.message.delete()
    await callback.answer()
