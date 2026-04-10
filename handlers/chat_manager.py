"""
Модуль чат-менеджера
Функции: анкеты участников, упоминания, роли
Добавлен без изменения существующего кода
"""

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import re
from datetime import datetime

from database import db
from config import ADMIN_IDS

router = Router()

# ==================== ДОПОЛНИТЕЛЬНЫЕ ТАБЛИЦЫ ДЛЯ БД ====================
# Эти таблицы будут созданы при первом запуске, не трогая существующие

async def ensure_tables():
    """Создаёт дополнительные таблицы, если их нет"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Таблица анкет пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            age INTEGER,
            city TEXT,
            timezone TEXT,
            about TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    
    # Таблица ролей пользователей в чатах
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id INTEGER,
            chat_id INTEGER,
            role_level INTEGER DEFAULT 0,
            role_name TEXT DEFAULT 'участник',
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    
    # Таблица групп для массовых упоминаний
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mention_groups (
            chat_id INTEGER,
            group_name TEXT,
            user_ids TEXT,
            PRIMARY KEY (chat_id, group_name)
        )
    """)
    
    conn.commit()
    conn.close()

# ==================== АНКЕТЫ ПОЛЬЗОВАТЕЛЕЙ ====================

@router.message(Command("setprofile"))
async def cmd_set_profile(message: types.Message):
    """Начать заполнение анкеты"""
    await ensure_tables()
    
    # Сохраняем состояние пользователя (что он заполняет)
    # Временное хранилище в памяти (для простоты)
    if not hasattr(cmd_set_profile, 'user_states'):
        cmd_set_profile.user_states = {}
    
    user_id = message.from_user.id
    cmd_set_profile.user_states[user_id] = {'step': 1}
    
    await message.answer(
        "📝 *Создание анкеты*\n\n"
        "Шаг 1 из 5: Введите ваше имя\n\n"
        "Пример: `Александр`\n\n"
        "❌ Отмена: /cancel_profile",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("cancel_profile"))
async def cmd_cancel_profile(message: types.Message):
    """Отмена заполнения анкеты"""
    if hasattr(cmd_set_profile, 'user_states'):
        user_id = message.from_user.id
        if user_id in cmd_set_profile.user_states:
            del cmd_set_profile.user_states[user_id]
    await message.answer("❌ Заполнение анкеты отменено.")

@router.message(F.text, lambda m: hasattr(cmd_set_profile, 'user_states') and m.from_user.id in cmd_set_profile.user_states)
async def process_profile_step(message: types.Message):
    """Обработка шагов заполнения анкеты"""
    user_id = message.from_user.id
    state = cmd_set_profile.user_states.get(user_id)
    if not state:
        return
    
    step = state['step']
    
    if step == 1:
        state['full_name'] = message.text
        state['step'] = 2
        await message.answer(
            "📝 *Шаг 2 из 5*\n\n"
            "Введите ваш возраст (число):\n\n"
            "Пример: `25`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 2:
        try:
            age = int(message.text)
            if age < 1 or age > 150:
                raise ValueError
            state['age'] = age
            state['step'] = 3
            await message.answer(
                "📝 *Шаг 3 из 5*\n\n"
                "Введите ваш город:\n\n"
                "Пример: `Москва`",
                parse_mode=ParseMode.MARKDOWN
            )
        except ValueError:
            await message.answer("❌ Введите корректный возраст (число от 1 до 150)")
    
    elif step == 3:
        state['city'] = message.text
        state['step'] = 4
        await message.answer(
            "📝 *Шаг 4 из 5*\n\n"
            "Введите ваш часовой пояс (UTC):\n\n"
            "Пример: `UTC+3` или `+3`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 4:
        state['timezone'] = message.text
        state['step'] = 5
        await message.answer(
            "📝 *Шаг 5 из 5*\n\n"
            "Расскажите немного о себе:\n\n"
            "Пример: `Люблю игры и программирование`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 5:
        state['about'] = message.text
        
        # Сохраняем в БД
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_profiles 
            (user_id, full_name, age, city, timezone, about, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM user_profiles WHERE user_id = ?), ?), ?)
        """, (
            user_id, state['full_name'], state['age'], state['city'], 
            state['timezone'], state['about'], user_id, datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        
        # Показываем результат
        await message.answer(
            "✅ *Анкета сохранена!*\n\n"
            f"📛 Имя: {state['full_name']}\n"
            f"📅 Возраст: {state['age']}\n"
            f"🏙️ Город: {state['city']}\n"
            f"🕐 Часовой пояс: {state['timezone']}\n"
            f"📝 О себе: {state['about']}\n\n"
            "Используйте /viewprofile для просмотра своей анкеты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Очищаем состояние
        del cmd_set_profile.user_states[user_id]

@router.message(Command("viewprofile"))
async def cmd_view_profile(message: types.Message):
    """Просмотр анкеты пользователя"""
    await ensure_tables()
    
    # Определяем, чью анкету показывать
    args = message.text.split()
    if len(args) > 1:
        # Пользователь указал username
        username = args[1].replace('@', '')
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            await message.answer(f"❌ Пользователь @{username} не найден")
            return
        user_id = row[0]
    else:
        user_id = message.from_user.id
    
    # Получаем анкету
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(
            "❌ Анкета не найдена!\n\n"
            "Используйте /setprofile для создания анкеты"
        )
        return
    
    await message.answer(
        f"👤 *Анкета пользователя*\n\n"
        f"📛 Имя: {row[1]}\n"
        f"📅 Возраст: {row[2]}\n"
        f"🏙️ Город: {row[3]}\n"
        f"🕐 Часовой пояс: {row[4]}\n"
        f"📝 О себе: {row[5]}\n\n"
        f"📅 Создана: {row[6][:10] if row[6] else 'Неизвестно'}",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("myprofile"))
async def cmd_my_profile(message: types.Message):
    """Показать свою анкету"""
    await cmd_view_profile(message)

# ==================== РОЛИ ПОЛЬЗОВАТЕЛЕЙ ====================

async def get_user_role(user_id: int, chat_id: int) -> int:
    """Получить уровень роли пользователя в чате"""
    await ensure_tables()
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role_level FROM user_roles WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

async def set_user_role(user_id: int, chat_id: int, level: int, name: str = "участник"):
    """Установить роль пользователя"""
    await ensure_tables()
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_roles (user_id, chat_id, role_level, role_name)
        VALUES (?, ?, ?, ?)
    """, (user_id, chat_id, level, name))
    conn.commit()
    conn.close()

@router.message(Command("setrole"))
async def cmd_set_role(message: types.Message):
    """Установить роль пользователю (только для админов)"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только администраторы могут назначать роли!")
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "❌ Использование: /setrole @username уровень [название]\n\n"
            "Уровни:\n"
            "0 — участник\n"
            "1 — проверенный\n"
            "2 — модератор\n"
            "3 — администратор\n\n"
            "Пример: /setrole @user 2 модератор"
        )
        return
    
    username = args[1].replace('@', '')
    try:
        level = int(args[2])
    except ValueError:
        await message.answer("❌ Уровень должен быть числом")
        return
    
    role_name = " ".join(args[3:]) if len(args) > 3 else "участник"
    
    # Находим пользователя
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{username} не найден")
        return
    
    target_id = row[0]
    chat_id = message.chat.id
    
    await set_user_role(target_id, chat_id, level, role_name)
    await message.answer(f"✅ Пользователю @{username} назначена роль: {role_name} (уровень {level})")

@router.message(Command("myrole"))
async def cmd_my_role(message: types.Message):
    """Показать свою роль в чате"""
    role_level = await get_user_role(message.from_user.id, message.chat.id)
    role_names = {0: "участник", 1: "проверенный", 2: "модератор", 3: "администратор"}
    role_name = role_names.get(role_level, "участник")
    
    await message.answer(f"⭐ Ваша роль в этом чате: *{role_name}* (уровень {role_level})", parse_mode=ParseMode.MARKDOWN)

# ==================== УПОМИНАНИЯ ====================

@router.message(Command("tag"))
async def cmd_tag(message: types.Message):
    """Упомянуть пользователя"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /tag @username [текст]")
        return
    
    username = args[1].replace('@', '')
    text = " ".join(args[2:]) if len(args) > 2 else ""
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{username} не найден")
        return
    
    target_id = row[0]
    
    if text:
        await message.answer(f"🔔 Упоминание от {message.from_user.full_name}: {text}\n\n👉 @{username}")
    else:
        await message.answer(f"🔔 @{username}, вас упомянул {message.from_user.full_name}")

@router.message(Command("tagrole"))
async def cmd_tag_role(message: types.Message):
    """Упомянуть всех с определённой ролью"""
    user_level = await get_user_role(message.from_user.id, message.chat.id)
    
    # Право на массовые упоминания — минимум уровень 2 (модератор)
    if user_level < 2:
        await message.answer("❌ У вас нет прав на массовые упоминания!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Использование: /tagrole уровень [текст]\n\n"
            "Уровни:\n"
            "0 — все участники\n"
            "1 — проверенные\n"
            "2 — модераторы\n"
            "3 — администраторы\n\n"
            "Пример: /tagrole 2 Внимание, модераторы!"
        )
        return
    
    try:
        target_level = int(args[1])
    except ValueError:
        await message.answer("❌ Уровень должен быть числом")
        return
    
    text = " ".join(args[2:]) if len(args) > 2 else "Внимание!"
    
    # Получаем пользователей с нужным уровнем
    await ensure_tables()
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_roles WHERE chat_id = ? AND role_level >= ?", (message.chat.id, target_level))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer(f"❌ Пользователи с уровнем {target_level} и выше не найдены")
        return
    
    mentions = []
    for row in rows:
        conn2 = db._get_connection()
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT username FROM users WHERE user_id = ?", (row[0],))
        user_row = cursor2.fetchone()
        conn2.close()
        if user_row and user_row[0]:
            mentions.append(f"@{user_row[0]}")
    
    if not mentions:
        await message.answer("❌ Не удалось найти username для упоминания")
        return
    
    mention_text = " ".join(mentions[:50])  # Ограничиваем 50 упоминаний
    await message.answer(f"📢 {text}\n\n{mention_text}")

# ==================== КНОПКА В МЕНЮ ====================

@router.callback_query(lambda c: c.data == "profile")
async def profile_with_mention(callback: types.CallbackQuery):
    """Расширенный профиль с кнопкой анкеты"""
    user_id = callback.from_user.id
    
    # Получаем основную информацию
    user = await db.get_user(user_id)
    if not user:
        await callback.message.edit_text("❌ Используйте /start для регистрации")
        await callback.answer()
        return
    
    # Получаем анкету
    await ensure_tables()
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, age, city FROM user_profiles WHERE user_id = ?", (user_id,))
    profile_row = cursor.fetchone()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Моя анкета", callback_data="view_my_profile")],
        [InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    profile_text = f"""
👤 <b>Профиль пользователя</b>

━━━━━━━━━━━━━━━━━━━━━
📛 <b>Имя:</b> {user.get('first_name', 'Не указано')}
🆔 <b>ID:</b> {user_id}
📅 <b>Регистрация:</b> {user.get('register_date', 'Неизвестно')[:10]}
━━━━━━━━━━━━━━━━━━━━━

💰 <b>Баланс:</b> {user.get('balance', 0)} монет

⭐ <b>VIP статус:</b> {'✅ Активирован' if user.get('vip_level', 0) > 0 else '❌ Нет'}

🏆 <b>Статистика:</b>
├ Побед: {user.get('wins', 0)}
├ Поражений: {user.get('losses', 0)}
└ Всего игр: {user.get('wins', 0) + user.get('losses', 0)}

━━━━━━━━━━━━━━━━━━━━━
<i>Нажмите на кнопку ниже, чтобы заполнить анкету</i>
"""
    
    await callback.message.edit_text(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data == "view_my_profile")
async def view_my_profile_callback(callback: types.CallbackQuery):
    """Показать свою анкету из callback"""
    await ensure_tables()
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (callback.from_user.id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await callback.message.edit_text(
            "❌ Анкета не найдена!\n\nИспользуйте /setprofile для создания анкеты",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"👤 *Ваша анкета*\n\n"
        f"📛 Имя: {row[1]}\n"
        f"📅 Возраст: {row[2]}\n"
        f"🏙️ Город: {row[3]}\n"
        f"🕐 Часовой пояс: {row[4]}\n"
        f"📝 О себе: {row[5]}\n\n"
        f"📅 Создана: {row[6][:10] if row[6] else 'Неизвестно'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
        ])
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "fill_profile")
async def fill_profile_callback(callback: types.CallbackQuery):
    """Заполнить анкету из callback"""
    await callback.message.edit_text(
        "📝 *Создание анкеты*\n\n"
        "Используйте команду /setprofile в чате\n\n"
        "Это диалоговый режим, который недоступен из меню.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
        ])
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile_callback(callback: types.CallbackQuery):
    """Редактировать анкету"""
    await callback.message.edit_text(
        "✏️ *Редактирование анкеты*\n\n"
        "Используйте команду /setprofile для создания новой анкеты\n"
        "(она перезапишет старую)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="view_my_profile")]
        ])
    )
    await callback.answer()
