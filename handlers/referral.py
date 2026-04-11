"""
Модуль реферальной системы
Владелец чата может включить, участники получают NCoins за приглашения
"""

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import secrets
import string

from database import db

router = Router()


def generate_ref_code() -> str:
    """Генерирует уникальный реферальный код"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


# ==================== ПРОВЕРКА ПРАВ В ЧАТЕ ====================

async def is_chat_owner(user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь ВЛАДЕЛЬЦЕМ чата"""
    try:
        member = await router.bot.get_chat_member(chat_id, user_id)
        return member.status == 'creator'
    except Exception:
        return False


async def is_bot_admin(chat_id: int) -> bool:
    """Проверяет, является ли бот администратором чата"""
    try:
        bot_id = (await router.bot.get_me()).id
        member = await router.bot.get_chat_member(chat_id, bot_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False


# ==================== КОМАНДЫ ДЛЯ ВЛАДЕЛЬЦА ЧАТА ====================

@router.message(Command("enable_ref"))
async def enable_referral(message: types.Message):
    """Включить реферальную систему в чате (только владелец)"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if not await is_bot_admin(chat_id):
        await message.answer(
            "❌ *Ошибка:* Бот не является администратором чата!\n\n"
            "Добавьте бота в чат и выдайте права администратора.",
            parse_mode="Markdown"
        )
        return
    
    if not await is_chat_owner(user_id, chat_id):
        await message.answer("❌ Только владелец чата может включить реферальную систему!")
        return
    
    # Генерируем ссылку
    ref_code = generate_ref_code()
    bot_username = (await router.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
    
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ref_settings (
            chat_id INTEGER PRIMARY KEY,
            enabled BOOLEAN DEFAULT 0,
            ref_link TEXT,
            bonus_amount INTEGER DEFAULT 100,
            created_at TEXT
        )
    """)
    
    cursor.execute("""
        INSERT OR REPLACE INTO ref_settings (chat_id, enabled, ref_link, bonus_amount, created_at)
        VALUES (?, 1, ?, 100, ?)
    """, (chat_id, ref_link, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ *Реферальная система ВКЛЮЧЕНА!*\n\n"
        f"🔗 Ссылка чата: {ref_link}\n\n"
        f"📌 Участники используют /my_ref для получения своей ссылки.\n"
        f"💰 За каждого приглашённого: +100 NCoins",
        parse_mode="Markdown"
    )


@router.message(Command("disable_ref"))
async def disable_referral(message: types.Message):
    """Выключить реферальную систему"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if not await is_chat_owner(user_id, chat_id):
        await message.answer("❌ Только владелец чата может выключить реферальную систему!")
        return
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ref_settings SET enabled = 0 WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
    
    await message.answer("❌ *Реферальная система ВЫКЛЮЧЕНА!*", parse_mode="Markdown")


@router.message(Command("ref_stats"))
async def ref_stats(message: types.Message):
    """Статистика реферальной системы"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    if not await is_chat_owner(user_id, chat_id):
        await message.answer("❌ Только владелец чата может смотреть статистику!")
        return
    
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT enabled, bonus_amount FROM ref_settings WHERE chat_id = ?", (chat_id,))
    setting = cursor.fetchone()
    
    cursor.execute("""
        SELECT user_id, invited_count, earned_coins 
        FROM ref_links 
        WHERE chat_id = ? 
        ORDER BY invited_count DESC 
        LIMIT 10
    """, (chat_id,))
    top_inviters = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM ref_invites WHERE chat_id = ?", (chat_id,))
    total_invites = cursor.fetchone()[0]
    
    conn.close()
    
    text = f"📊 *Статистика реферальной системы*\n\n"
    text += f"📢 Статус: {'✅ Включена' if setting and setting[0] else '❌ Выключена'}\n"
    text += f"💰 Бонус: {setting[1] if setting else 100} NCoins\n"
    text += f"👥 Всего приглашений: {total_invites}\n\n"
    
    if top_inviters:
        text += "*🏆 ТОП пригласителей:*\n"
        for i, (uid, count, earned) in enumerate(top_inviters[:5], 1):
            text += f"{i}. Пользователь {uid} — {count} приглашений (+{earned} NCoins)\n"
    
    await message.answer(text, parse_mode="Markdown")


# ==================== КОМАНДЫ ДЛЯ УЧАСТНИКОВ ====================

@router.message(Command("my_ref"))
async def my_referral_link(message: types.Message):
    """Получить свою реферальную ссылку"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах!")
        return
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT enabled, bonus_amount FROM ref_settings WHERE chat_id = ?", (chat_id,))
    setting = cursor.fetchone()
    
    if not setting or not setting[0]:
        await message.answer("❌ Реферальная система не включена владельцем чата!")
        conn.close()
        return
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ref_links (
            user_id INTEGER,
            chat_id INTEGER,
            ref_code TEXT UNIQUE,
            invited_count INTEGER DEFAULT 0,
            earned_coins INTEGER DEFAULT 0,
            created_at TEXT,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    
    cursor.execute("SELECT ref_code, invited_count, earned_coins FROM ref_links WHERE user_id = ? AND chat_id = ?", 
                   (user_id, chat_id))
    user_ref = cursor.fetchone()
    
    if not user_ref:
        ref_code = generate_ref_code()
        cursor.execute("""
            INSERT INTO ref_links (user_id, chat_id, ref_code, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, ref_code, datetime.now().isoformat()))
        conn.commit()
        user_ref = (ref_code, 0, 0)
    else:
        ref_code = user_ref[0]
    
    conn.close()
    
    bot_username = (await router.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
    
    text = f"""
🔗 *Ваша реферальная ссылка*

{ref_link}

📊 *Ваша статистика:*
├ 👥 Приглашено: {user_ref[1]}
└ 💰 Заработано: {user_ref[2]} NCoins

💰 *Бонус:* +{setting[1]} NCoins за каждого друга!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся!")],
        [InlineKeyboardButton(text="💰 Купить VIP", callback_data="buy_vip_ncoins")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


# ==================== ОБРАБОТЧИК ПРИГЛАШЕНИЙ ====================

async def process_referral_start(message: types.Message, chat_id: int, ref_code: str):
    """Обработка перехода по реферальной ссылке"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id FROM ref_links WHERE ref_code = ? AND chat_id = ?", (ref_code, chat_id))
    inviter_row = cursor.fetchone()
    
    if not inviter_row:
        conn.close()
        return
    
    inviter_id = inviter_row[0]
    
    if inviter_id == message.from_user.id:
        await message.answer("❌ Нельзя пригласить самого себя!")
        conn.close()
        return
    
    cursor.execute("SELECT id FROM ref_invites WHERE inviter_id = ? AND invited_id = ? AND chat_id = ?",
                   (inviter_id, message.from_user.id, chat_id))
    if cursor.fetchone():
        await message.answer("✅ Вы уже присоединялись по реферальной ссылке!")
        conn.close()
        return
    
    cursor.execute("SELECT bonus_amount FROM ref_settings WHERE chat_id = ?", (chat_id,))
    setting = cursor.fetchone()
    bonus_amount = setting[0] if setting else 100
    
    cursor.execute("""
        INSERT INTO ref_invites (inviter_id, invited_id, chat_id, invited_at)
        VALUES (?, ?, ?, ?)
    """, (inviter_id, message.from_user.id, chat_id, datetime.now().isoformat()))
    
    cursor.execute("""
        UPDATE ref_links 
        SET invited_count = invited_count + 1, earned_coins = earned_coins + ?
        WHERE user_id = ? AND chat_id = ?
    """, (bonus_amount, inviter_id, chat_id))
    conn.commit()
    conn.close()
    
    from database import update_balance
    await update_balance(inviter_id, bonus_amount, f"Реферальный бонус")
    
    try:
        await router.bot.send_message(
            inviter_id,
            f"🎉 *Поздравляем!*\n\nПо вашей ссылке присоединился новый участник!\n💰 Вам начислено +{bonus_amount} NCoins!",
            parse_mode="Markdown"
        )
    except:
        pass
    
    await message.answer(
        f"✅ *Добро пожаловать!*\n\n"
        f"Вы присоединились по реферальной ссылке!\n"
        f"Пригласивший получил +{bonus_amount} NCoins.\n\n"
        f"📌 Используйте /my_ref для своей ссылки!",
        parse_mode="Markdown"
    )


# ==================== КНОПКИ ====================

@router.callback_query(lambda c: c.data == "ref_menu")
async def ref_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Моя ссылка", callback_data="my_ref")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(
        "📢 *Реферальная система*\n\nПриглашайте друзей и получайте NCoins!\n💰 За каждого друга: +100 NCoins",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "my_ref")
async def my_ref_callback(callback: types.CallbackQuery):
    await my_referral_link(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "buy_vip_ncoins")
async def buy_vip_ncoins(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    vip_price = 500
    
    user = await db.get_user(user_id)
    if not user or user["balance"] < vip_price:
        await callback.answer(f"❌ Не хватает NCoins! Нужно {vip_price}", show_alert=True)
        return
    
    from datetime import datetime, timedelta
    new_until = (datetime.now() + timedelta(days=30)).isoformat()
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance - ?, vip_level = 1, vip_until = ? WHERE user_id = ?",
                   (vip_price, new_until, user_id))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        f"✅ *VIP статус активирован!*\n\n⭐ Действует до: {new_until[:10]}",
        parse_mode="Markdown"
    )
    await callback.answer()
