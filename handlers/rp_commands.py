"""
Модуль РП команд, отношений и групп
"""

import logging
import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)


# ==================== ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ ====================

async def init_rp_tables():
    """Инициализация таблиц РП команд"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Таблица отношений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user1_id, user2_id, type)
        )
    """)
    
    # Таблица групп
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id BIGINT NOT NULL,
            group_name TEXT NOT NULL,
            group_leader INTEGER NOT NULL,
            member_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица участников групп
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            group_id INTEGER,
            user_id INTEGER,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (group_id, user_id)
        )
    """)
    
    # Таблица кастомных РП команд
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_rp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            command TEXT NOT NULL,
            action_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, command)
        )
    """)
    
    conn.commit()
    conn.close()


# ==================== БАЗОВЫЕ РП КОМАНДЫ ====================

RP_ACTIONS = {
    "hug": "🤗 обнял(а)",
    "kiss": "😘 поцеловал(а)",
    "pat": "🖐️ погладил(а) по головке",
    "kick": "🦵 пнул(а)",
    "slap": "🤚 шлёпнул(а)",
    "cuddle": "🤗 прижал(а) к себе",
    "highfive": "✋ дал(а) пять",
    "wink": "😉 подмигнул(а)",
    "lick": "👅 лизнул(а)",
    "bite": "🦷 укусил(а)",
    "tickle": "🪶 пощекотал(а)",
    "punch": "👊 ударил(а)",
    "headpat": "🖐️ потрепал(а) по голове",
    "boop": "👉 ткнул(а) в нос",
    "wave": "👋 помахал(а)",
    "bow": "🙇 поклонился(ась)",
    "dance": "💃 потанцевал(а) с",
    "sing": "🎤 спел(а) для",
    "gift": "🎁 подарил(а) подарок",
}


async def get_user_name(user_id: int) -> str:
    """Получить имя пользователя"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return f"@{row[1]}" if row[1] else row[0]
    return f"Пользователь {user_id}"


@router.message(Command("hug", "kiss", "pat", "kick", "slap", "cuddle", "highfive", "wink", "lick", "bite", "tickle", "punch", "headpat", "boop", "wave", "bow", "dance", "sing", "gift"))
async def rp_command(message: types.Message):
    """Обработка РП команд"""
    command = message.text.split()[0].replace("/", "").lower()
    
    if command not in RP_ACTIONS:
        return
    
    # Проверяем, есть ли упоминание пользователя
    if not message.reply_to_message and len(message.text.split()) < 2:
        await message.answer(
            f"❌ *Как использовать:*\n\n"
            f"`/{command} @username` — выполнить действие над пользователем\n"
            f"или ответьте на сообщение пользователя и напишите `/{command}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Получаем цель
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = await get_user_name(target_id)
    else:
        target_username = message.text.split()[1].replace("@", "")
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (target_username,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            await message.answer(f"❌ Пользователь @{target_username} не найден!")
            return
        target_id = row[0]
        target_name = await get_user_name(target_id)
    
    user_name = await get_user_name(message.from_user.id)
    
    if target_id == message.from_user.id:
        await message.answer(f"🤔 {user_name} {RP_ACTIONS[command]} самого себя... Странно!")
        return
    
    await message.answer(
        f"✨ *{user_name}* {RP_ACTIONS[command]} *{target_name}* ✨",
        parse_mode=ParseMode.MARKDOWN
    )


# ==================== ОТНОШЕНИЯ ====================

@router.message(Command("propose"))
async def cmd_propose(message: types.Message):
    """Предложить отношения"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "💍 *Как предложить отношения:*\n\n"
            "`/propose @username тип`\n\n"
            "Доступные типы:\n"
            "• `wife` — жена/муж\n"
            "• `partner` — парень/девушка\n"
            "• `friend` — лучший друг\n"
            "• `brother` — брат\n"
            "• `sister` — сестра",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    target_username = args[1].replace("@", "")
    rel_type = args[2].lower() if len(args) > 2 else "friend"
    
    rel_names = {
        "wife": "💍 жена/муж",
        "partner": "💑 парень/девушка",
        "friend": "🤝 лучший друг",
        "brother": "👨‍👦 брат",
        "sister": "👩‍👧 сестра"
    }
    
    if rel_type not in rel_names:
        await message.answer(f"❌ Неизвестный тип. Доступны: {', '.join(rel_names.keys())}")
        return
    
    # Находим пользователя
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, first_name FROM users WHERE username = ?", (target_username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer(f"❌ Пользователь @{target_username} не найден!")
        return
    
    target_id = row[0]
    target_name = row[1]
    
    if target_id == message.from_user.id:
        await message.answer("❌ Нельзя предложить отношения самому себе!")
        return
    
    # Проверяем, нет ли уже отношений
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status FROM relationships 
        WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)
    """, (message.from_user.id, target_id, target_id, message.from_user.id))
    existing = cursor.fetchone()
    conn.close()
    
    if existing:
        await message.answer("❌ У вас уже есть отношения с этим пользователем!")
        return
    
    # Сохраняем предложение
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO relationships (user1_id, user2_id, type, status)
        VALUES (?, ?, ?, 'pending')
    """, (message.from_user.id, target_id, rel_type))
    conn.commit()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"accept_rel_{target_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"reject_rel_{target_id}")]
    ])
    
    await message.answer(
        f"💍 {message.from_user.first_name} предлагает вам {rel_names[rel_type]}!\n\n"
        f"@{target_username}, примите предложение:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("accept_rel_"))
async def accept_relationship(callback: types.CallbackQuery):
    """Принять отношения"""
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE relationships SET status = 'accepted'
        WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)
    """, (user_id, user_id, user_id, user_id))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text("✅ Отношения подтверждены! 💕")
    await callback.answer()


@router.callback_query(F.data.startswith("reject_rel_"))
async def reject_relationship(callback: types.CallbackQuery):
    """Отклонить отношения"""
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM relationships
        WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)
    """, (user_id, user_id, user_id, user_id))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text("❌ Отношения отклонены.")
    await callback.answer()


@router.message(Command("my_relationships"))
async def cmd_my_relationships(message: types.Message):
    """Показать мои отношения"""
    user_id = message.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id, u.first_name, u.username, r.type
        FROM relationships r
        JOIN users u ON (u.user_id = r.user1_id OR u.user_id = r.user2_id)
        WHERE (r.user1_id = ? OR r.user2_id = ?) 
          AND u.user_id != ? 
          AND r.status = 'accepted'
    """, (user_id, user_id, user_id))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("💔 У вас пока нет отношений.")
        return
    
    rel_names = {
        "wife": "💍 супруг(а)",
        "partner": "💑 парень/девушка",
        "friend": "🤝 лучший друг",
        "brother": "👨‍👦 брат",
        "sister": "👩‍👧 сестра"
    }
    
    text = "💕 *ВАШИ ОТНОШЕНИЯ*\n\n"
    for row in rows:
        name = f"@{row[2]}" if row[2] else row[1]
        rel_type = rel_names.get(row[3], row[3])
        text += f"• {rel_type}: {name}\n"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


# ==================== ГРУППЫ ====================

@router.message(Command("create_group"))
async def cmd_create_group(message: types.Message):
    """Создать группу"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "👥 *Создание группы*\n\n"
            "`/create_group Название группы`\n\n"
            "Вы станете лидером группы.\n"
            "Другие могут присоединиться через `/join_group название`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    group_name = args[1][:30]
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем, существует ли группа
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM groups WHERE chat_id = ? AND group_name = ?", (chat_id, group_name))
    existing = cursor.fetchone()
    
    if existing:
        await message.answer(f"❌ Группа с названием '{group_name}' уже существует!")
        conn.close()
        return
    
    cursor.execute("""
        INSERT INTO groups (chat_id, group_name, group_leader)
        VALUES (?, ?, ?)
    """, (chat_id, group_name, user_id))
    
    group_id = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO group_members (group_id, user_id)
        VALUES (?, ?)
    """, (group_id, user_id))
    
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Группа *{group_name}* создана! Вы её лидер.\n\nПриглашайте участников через `/join_group {group_name}`", parse_mode=ParseMode.MARKDOWN)


@router.message(Command("join_group"))
async def cmd_join_group(message: types.Message):
    """Присоединиться к группе"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("👥 `/join_group Название группы`", parse_mode=ParseMode.MARKDOWN)
        return
    
    group_name = args[1]
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, group_leader FROM groups WHERE chat_id = ? AND group_name = ?", (chat_id, group_name))
    row = cursor.fetchone()
    
    if not row:
        await message.answer(f"❌ Группа '{group_name}' не найдена!")
        conn.close()
        return
    
    group_id, leader_id = row
    
    # Проверяем, не состоит ли уже
    cursor.execute("SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    if cursor.fetchone():
        await message.answer(f"❌ Вы уже состоите в группе '{group_name}'!")
        conn.close()
        return
    
    cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
    cursor.execute("UPDATE groups SET member_count = member_count + 1 WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Вы присоединились к группе *{group_name}*!", parse_mode=ParseMode.MARKDOWN)


@router.message(Command("my_groups"))
async def cmd_my_groups(message: types.Message):
    """Мои группы"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.group_name, g.group_leader, g.member_count
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_id = ? AND g.chat_id = ?
    """, (user_id, chat_id))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("👥 Вы не состоите ни в одной группе.\n\nСоздайте свою: `/create_group Название`", parse_mode=ParseMode.MARKDOWN)
        return
    
    text = "👥 *ВАШИ ГРУППЫ*\n\n"
    for row in rows:
        group_name, leader_id, count = row
        is_leader = "👑" if leader_id == user_id else ""
        text += f"{is_leader} *{group_name}* — {count} участников\n"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("group_kick"))
async def cmd_group_kick(message: types.Message):
    """Исключить из группы (только лидер)"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("👑 `/group_kick @username`", parse_mode=ParseMode.MARKDOWN)
        return
    
    target_username = args[1].replace("@", "")
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Находим пользователя
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (target_username,))
    row = cursor.fetchone()
    if not row:
        await message.answer(f"❌ Пользователь @{target_username} не найден!")
        conn.close()
        return
    
    target_id = row[0]
    
    # Находим группу, где пользователь лидер
    cursor.execute("SELECT id FROM groups WHERE chat_id = ? AND group_leader = ?", (chat_id, user_id))
    group = cursor.fetchone()
    
    if not group:
        await message.answer("❌ Вы не являетесь лидером ни одной группы!")
        conn.close()
        return
    
    group_id = group[0]
    
    # Удаляем участника
    cursor.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, target_id))
    cursor.execute("UPDATE groups SET member_count = member_count - 1 WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Пользователь @{target_username} исключён из группы!")


# ==================== КАСТОМНЫЕ РП КОМАНДЫ ====================

@router.message(Command("add_rp"))
async def cmd_add_rp(message: types.Message):
    """Добавить свою РП команду"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "✨ *Добавление РП команды*\n\n"
            "`/add_rp команда действие`\n\n"
            "Пример: `/add_rp покормить покормил(а) вкусняшкой`\n\n"
            "После добавления команда будет работать как `/покормить @user`\n\n"
            "⚠️ Максимум 5 команд на пользователя.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    command = args[1].lower()
    action = args[2]
    
    user_id = message.from_user.id
    
    # Проверяем количество команд
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM custom_rp WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    
    if count >= 5:
        await message.answer("❌ Вы уже добавили максимум 5 команд! Удалите ненужные через `/del_rp`")
        conn.close()
        return
    
    # Проверяем, не существует ли уже
    cursor.execute("SELECT 1 FROM custom_rp WHERE user_id = ? AND command = ?", (user_id, command))
    if cursor.fetchone():
        await message.answer(f"❌ Команда `{command}` уже существует! Используйте `/del_rp {command}` для удаления.")
        conn.close()
        return
    
    cursor.execute("""
        INSERT INTO custom_rp (user_id, command, action_text)
        VALUES (?, ?, ?)
    """, (user_id, command, action))
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ Команда *{command}* добавлена!\n\n"
        f"Теперь можно использовать: `/{command} @user`\n"
        f"Действие: {action}",
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(Command("del_rp"))
async def cmd_del_rp(message: types.Message):
    """Удалить свою РП команду"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("✨ `/del_rp команда`", parse_mode=ParseMode.MARKDOWN)
        return
    
    command = args[1].lower()
    user_id = message.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM custom_rp WHERE user_id = ? AND command = ?", (user_id, command))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected:
        await message.answer(f"✅ Команда `{command}` удалена!")
    else:
        await message.answer(f"❌ Команда `{command}` не найдена.")


@router.message(Command("my_rp"))
async def cmd_my_rp(message: types.Message):
    """Мои кастомные РП команды"""
    user_id = message.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT command, action_text FROM custom_rp WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer(
            "✨ *Ваши РП команды*\n\n"
            "У вас пока нет кастомных команд.\n\n"
            "Добавьте: `/add_rp команда действие`\n"
            "Пример: `/add_rp покормить покормил(а) вкусняшкой`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    text = "✨ *ВАШИ РП КОМАНДЫ*\n\n"
    for cmd, action in rows:
        text += f"• `/{cmd}` — {action}\n"
    
    text += "\n⚠️ Максимум 5 команд. Удалить: `/del_rp команда`"
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


# Обработчик кастомных РП команд
@router.message()
async def custom_rp_handler(message: types.Message):
    """Обработка кастомных РП команд"""
    if not message.text or not message.text.startswith('/'):
        return
    
    command = message.text.split()[0].replace("/", "").lower()
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT action_text FROM custom_rp WHERE user_id = ? AND command = ?", 
                   (message.from_user.id, command))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return
    
    action_text = row[0]
    
    # Проверяем, есть ли цель
    if not message.reply_to_message and len(message.text.split()) < 2:
        await message.answer(
            f"❌ *Как использовать:*\n\n"
            f"`/{command} @username`\n"
            f"или ответьте на сообщение пользователя и напишите `/{command}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Получаем цель
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = await get_user_name(target_id)
    else:
        target_username = message.text.split()[1].replace("@", "")
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (target_username,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            await message.answer(f"❌ Пользователь @{target_username} не найден!")
            return
        target_id = row[0]
        target_name = await get_user_name(target_id)
    
    user_name = await get_user_name(message.from_user.id)
    
    if target_id == message.from_user.id:
        await message.answer(f"🤔 {user_name} {action_text} самого себя... Странно!")
        return
    
    await message.answer(
        f"✨ *{user_name}* {action_text} *{target_name}* ✨",
        parse_mode=ParseMode.MARKDOWN
    )
