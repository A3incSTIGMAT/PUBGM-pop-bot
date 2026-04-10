"""
Универсальный модуль тэга участников
Работает без / команд, с голосом, с любыми обращениями (Nexus, Нэкс, Нексус)
"""

import re
import random
from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from database import db

router = Router()

# Ключевые слова для активации тэга (любые формы)
TAG_KEYWORDS = [
    # Русские варианты
    'нексус', 'нэксус', 'некс', 'нэкс', 'нексу', 'нэксу',
    'nexus', 'nex', 'neks', 'neksus',
    # Действия
    'тэгни', 'отметь', 'упомяни', 'позови', 'вызови',
    'собери', 'созывай', 'оповести', 'предупреди',
    # Комбинации
    'тэг всех', 'отметь всех', 'упомяни всех', 'позови всех',
    'всех участников', 'всех в чате', 'всех кто тут',
    'all', 'everyone', 'все', 'всех'
]

# Временное хранилище для ожидающих возраст
waiting_ages = {}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_chat_members_count(chat_id: int) -> int:
    """Получить количество участников чата"""
    try:
        chat = await router.bot.get_chat(chat_id)
        return chat.get_member_count()
    except:
        return 0


async def get_all_chat_members(chat_id: int, limit: int = 50) -> list:
    """Получить участников чата (ограниченное количество)"""
    members = []
    try:
        async for member in router.bot.get_chat_members(chat_id):
            if not member.user.is_bot:
                members.append(member.user)
                if len(members) >= limit:
                    break
    except Exception as e:
        print(f"Ошибка получения участников: {e}")
    return members


def extract_mention_text(text: str) -> str:
    """Извлечь текст для упоминания из фразы"""
    # Удаляем ключевые слова
    clean = text.lower()
    for kw in TAG_KEYWORDS:
        clean = clean.replace(kw.lower(), '')
    
    # Удаляем лишние пробелы и знаки
    clean = re.sub(r'[^\w\s]', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    return clean if clean else "ВНИМАНИЕ!"


def detect_tag_intent(text: str) -> dict:
    """Определить намерение тэга"""
    text_lower = text.lower()
    
    # Проверяем наличие ключевых слов
    has_tag_keyword = any(kw in text_lower for kw in TAG_KEYWORDS)
    
    if not has_tag_keyword:
        return {"intent": None, "target": None}
    
    # Определяем цель
    if any(word in text_lower for word in ['всех', 'all', 'everyone', 'участников', 'в чате', 'тут']):
        return {"intent": "all", "target": "everyone"}
    
    if any(word in text_lower for word in ['админ', 'модер', 'администратор']):
        return {"intent": "role", "target": "admins"}
    
    # Поиск конкретного username
    username_match = re.search(r'@(\w+)', text)
    if username_match:
        return {"intent": "user", "target": username_match.group(1)}
    
    return {"intent": "all", "target": "everyone"} if has_tag_keyword else {"intent": None, "target": None}


# ==================== ОСНОВНОЙ ОБРАБОТЧИК (БЕЗ /) ====================

@router.message(lambda message: message.text and not message.text.startswith('/'))
async def smart_tag_handler(message: types.Message):
    """Умный обработчик тэгов — понимает любые формы обращения"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Проверяем, не в режиме ожидания возраста
    if user_id in waiting_ages:
        await process_age_input(message)
        return
    
    # Определяем намерение
    intent_data = detect_tag_intent(text)
    
    if intent_data["intent"] == "all":
        await handle_tag_all(message, text)
    elif intent_data["intent"] == "user":
        await handle_tag_user(message, intent_data["target"])
    elif intent_data["intent"] == "role":
        await handle_tag_role(message, "admins")
    # Если не распознали тэг — ничего не делаем, другие хендлеры обработают


# ==================== ОБРАБОТЧИК ТЭГА ВСЕХ ====================

async def handle_tag_all(message: types.Message, original_text: str):
    """Обработка тэга всех участников"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем регистрацию
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    # Сохраняем состояние для запроса возраста
    waiting_ages[user_id] = {
        "chat_id": chat_id,
        "original_text": original_text,
        "message_id": message.message_id
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Мне есть 18", callback_data="confirm_age_yes"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_age_no")]
    ])
    
    await message.answer(
        "📢 *ВНИМАНИЕ! МАССОВОЕ УПОМИНАНИЕ*\n\n"
        "⚠️ Вы собираетесь упомянуть всех участников чата.\n\n"
        "Пожалуйста, подтвердите, что вам есть 18 лет:\n\n"
        "_Это требование этики массовых упоминаний_",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data == "confirm_age_yes")
async def confirm_age_yes(callback: types.CallbackQuery):
    """Подтверждение возраста"""
    user_id = callback.from_user.id
    
    if user_id not in waiting_ages:
        await callback.answer("❌ Нет активного запроса", show_alert=True)
        return
    
    data = waiting_ages[user_id]
    
    await callback.message.edit_text(
        "📢 *Массовое упоминание*\n\n"
        "Напишите ваш возраст (число от 1 до 150):",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "confirm_age_no")
async def confirm_age_no(callback: types.CallbackQuery):
    """Отмена массового упоминания"""
    user_id = callback.from_user.id
    
    if user_id in waiting_ages:
        del waiting_ages[user_id]
    
    await callback.message.edit_text("❌ Массовое упоминание отменено.")
    await callback.answer()


async def process_age_input(message: types.Message):
    """Обработка ввода возраста"""
    user_id = message.from_user.id
    
    if user_id not in waiting_ages:
        return
    
    data = waiting_ages[user_id]
    chat_id = data["chat_id"]
    original_text = data.get("original_text", "")
    
    try:
        age = int(message.text.strip())
        if age < 1 or age > 150:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректный возраст (число от 1 до 150)")
        return
    
    # Сохраняем возраст
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ages (
            user_id INTEGER PRIMARY KEY,
            age INTEGER,
            updated_at TEXT
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO user_ages (user_id, age, updated_at)
        VALUES (?, ?, ?)
    """, (user_id, age, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Очищаем состояние
    del waiting_ages[user_id]
    
    # Получаем участников
    members = await get_all_chat_members(chat_id, limit=50)
    
    if not members:
        await message.answer(
            "❌ Не удалось получить список участников.\n\n"
            "Убедитесь, что бот является администратором чата."
        )
        return
    
    # Формируем текст сообщения
    mention_text = extract_mention_text(original_text)
    
    # Строим упоминания
    mentions = []
    for member in members:
        if member.username:
            mentions.append(f"@{member.username}")
        else:
            mentions.append(f"[{member.full_name}](tg://user?id={member.id})")
    
    # Отправляем
    await message.answer(
        f"📢 *{mention_text}*\n\n"
        f"👥 Участников: {len(mentions)}\n"
        f"👤 От: {message.from_user.full_name} (возраст: {age})\n\n"
        f"{' '.join(mentions[:30])}",
        parse_mode="Markdown"
    )
    
    if len(mentions) > 30:
        await message.answer(f"... и ещё {len(mentions) - 30} участников")


# ==================== ТЭГ КОНКРЕТНОГО ПОЛЬЗОВАТЕЛЯ ====================

async def handle_tag_user(message: types.Message, username: str):
    """Тэг конкретного пользователя"""
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    # Извлекаем текст сообщения
    text = message.text.strip()
    # Убираем @username из текста
    clean_text = re.sub(r'@\w+', '', text).strip()
    # Убираем ключевые слова
    for kw in TAG_KEYWORDS:
        clean_text = clean_text.replace(kw, '')
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    if clean_text:
        result_text = f"🔔 {clean_text}\n\n👉 @{username}"
    else:
        result_text = f"🔔 Вас упомянул {message.from_user.full_name}\n\n👉 @{username}"
    
    await message.answer(result_text)


# ==================== ТЭГ ПО РОЛИ ====================

async def handle_tag_role(message: types.Message, role: str):
    """Тэг по роли"""
    chat_id = message.chat.id
    target_users = []
    
    try:
        async for member in router.bot.get_chat_members(chat_id):
            if member.user.is_bot:
                continue
            if role == "admins" and member.status in ['creator', 'administrator']:
                target_users.append(member.user)
            elif role == "moderators" and member.status in ['creator', 'administrator']:
                target_users.append(member.user)
    except:
        pass
    
    if not target_users:
        await message.answer("❌ Нет пользователей с такой ролью")
        return
    
    # Извлекаем текст
    text = message.text.strip()
    for kw in TAG_KEYWORDS:
        text = text.replace(kw, '')
    text = re.sub(r'\s+', ' ', text).strip()
    
    mentions = []
    for user in target_users:
        if user.username:
            mentions.append(f"@{user.username}")
        else:
            mentions.append(f"[{user.full_name}](tg://user?id={user.id})")
    
    if text:
        result_text = f"🔔 {text}\n\n{' '.join(mentions)}"
    else:
        result_text = f"🔔 Обращение к {role}:\n\n{' '.join(mentions)}"
    
    await message.answer(result_text, parse_mode="Markdown")


# ==================== ГОЛОСОВЫЕ КОМАНДЫ ====================

@router.message(lambda message: message.voice)
async def voice_tag_handler(message: types.Message):
    """Обработка голосовых команд для тэга"""
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    # Отправляем сообщение о распознавании
    processing_msg = await message.answer("🎤 Распознаю голосовую команду... ⏳")
    
    # Пытаемся распознать
    recognized_text = await recognize_voice(message)
    
    if not recognized_text:
        await processing_msg.edit_text(
            "❌ Не удалось распознать голосовую команду.\n\n"
            "Попробуйте:\n"
            "• Говорите чётче\n"
            "• Используйте текстовые команды\n"
            "• Пример: 'Нексус, отметь всех'"
        )
        return
    
    await processing_msg.edit_text(f"🎤 Распознано: *{recognized_text}*\n\n🔄 Обрабатываю...", parse_mode="Markdown")
    
    # Определяем намерение
    intent_data = detect_tag_intent(recognized_text)
    
    if intent_data["intent"] == "all":
        # Подменяем message.text для обработки
        message.text = recognized_text
        await handle_tag_all(message, recognized_text)
        await processing_msg.delete()
    elif intent_data["intent"] == "user":
        await handle_tag_user(message, intent_data["target"])
        await processing_msg.delete()
    else:
        await processing_msg.edit_text(
            f"🎤 *Голосовая команда*\n\n"
            f"Распознано: \"{recognized_text}\"\n\n"
            "❌ Не удалось определить команду.\n\n"
            "Попробуйте:\n"
            "• \"Нексус, отметь всех\"\n"
            "• \"Nexus, тэгни @user\"\n"
            "• \"Собери всех участников\"",
            parse_mode="Markdown"
        )


async def recognize_voice(message: types.Message) -> str:
    """Распознавание голоса (заглушка без OpenAI)"""
    # Без OpenAI возвращаем None
    # При наличии OPENAI_API_KEY можно подключить Whisper
    return None


# ==================== КОМАНДЫ С / ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ====================

@router.message(lambda message: message.text and message.text.startswith('/tag'))
async def cmd_tag_slash(message: types.Message):
    """Обработка /tag для обратной совместимости"""
    text = message.text.replace('/tag', '').strip()
    if text:
        message.text = text
        await smart_tag_handler(message)
    else:
        await message.answer(
            "📢 *Как пользоваться тэгами:*\n\n"
            "Просто напишите:\n"
            "• `Нексус, отметь всех` — упомянуть всех\n"
            "• `@username Привет!` — упомянуть пользователя\n"
            "• `Nexus, тэгни админов` — упомянуть админов\n\n"
            "🎤 *Голосовые команды:*\n"
            "Скажите: 'Нексус, отметь всех'",
            parse_mode="Markdown"
        )


@router.message(lambda message: message.text and message.text.startswith('/all'))
async def cmd_all_slash(message: types.Message):
    """Обработка /all для обратной совместимости"""
    message.text = "Нексус, отметь всех"
    await smart_tag_handler(message)


# ==================== КНОПКИ В МЕНЮ ====================

@router.callback_query(lambda c: c.data == "tag_menu")
async def tag_menu(callback: types.CallbackQuery):
    """Меню тэгов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Тэгнуть всех", callback_data="tag_all_confirm")],
        [InlineKeyboardButton(text="🔔 Как пользоваться", callback_data="tag_help")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Тэги и упоминания*\n\n"
        "*Как пользоваться:*\n\n"
        "📝 *Текст:*\n"
        "• `Нексус, отметь всех` — упомянуть всех\n"
        "• `@username Привет!` — упомянуть пользователя\n"
        "• `Nexus, тэгни админов` — упомянуть админов\n\n"
        "🎤 *Голос:*\n"
        "• Скажите: 'Нексус, отметь всех'\n"
        "• Или: 'Nexus, собери участников'\n\n"
        "✨ Бот понимает любые формы обращения!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "tag_all_confirm")
async def tag_all_confirm(callback: types.CallbackQuery):
    """Подтверждение массового тэга из меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтверждаю", callback_data="confirm_age_yes"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_age_no")]
    ])
    
    # Сохраняем состояние
    waiting_ages[callback.from_user.id] = {
        "chat_id": callback.message.chat.id,
        "original_text": "ВНИМАНИЕ!",
        "message_id": callback.message.message_id
    }
    
    await callback.message.edit_text(
        "📢 *МАССОВОЕ УПОМИНАНИЕ*\n\n"
        "⚠️ Вы собираетесь упомянуть всех участников чата.\n\n"
        "Подтвердите, что вам есть 18 лет:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "tag_help")
async def tag_help(callback: types.CallbackQuery):
    """Помощь по тэгам"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="tag_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *Помощь по тэгам*\n\n"
        "*Примеры команд:*\n\n"
        "📝 *Текстовые:*\n"
        "• `Нексус, отметь всех`\n"
        "• `Nexus, собери участников`\n"
        "• `@user Привет, как дела?`\n"
        "• `Тэгни админов, срочно!`\n\n"
        "🎤 *Голосовые:*\n"
        "• \"Нексус, отметь всех\"\n"
        "• \"Nexus, тэгни @user\"\n"
        "• \"Собери всех\"\n\n"
        "✨ Бот понимает:\n"
        "• Нексус, Нэкс, Nexus, Nex\n"
        "• Отметь, тэгни, упомяни, позови\n"
        "• Всех, участников, в чате, тут",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()
