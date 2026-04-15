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
import logging

from database import db
from handlers.ranks import update_user_xp

router = Router()
logger = logging.getLogger(__name__)


def generate_ref_code() -> str:
    """Генерирует уникальный реферальный код"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


# ==================== НАГРАДЫ ЗА ДОСТИЖЕНИЯ ====================

REWARDS = {
    1: 100,      # 1 приглашённый
    5: 500,      # 5 приглашённых
    10: 1000,    # 10 приглашённых
    25: 3000,    # 25 приглашённых
    50: 7000,    # 50 приглашённых
    100: 15000,  # 100 приглашённых
    250: 50000,  # 250 приглашённых
    500: 150000, # 500 приглашённых
    1000: 500000 # 1000 приглашённых
}


async def check_milestone_reward(inviter_id: int, invited_count: int, chat_id: int):
    """Проверить и выдать награду за достижение"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ref_milestones (
            user_id INTEGER,
            chat_id INTEGER,
            milestone INTEGER,
            awarded BOOLEAN DEFAULT 0,
            awarded_at TIMESTAMP,
            PRIMARY KEY (user_id, chat_id, milestone)
        )
    """)
    
    for milestone, reward in REWARDS.items():
        if invited_count >= milestone:
            cursor.execute("""
                SELECT awarded FROM ref_milestones 
                WHERE user_id = ? AND chat_id = ? AND milestone = ?
            """, (inviter_id, chat_id, milestone))
            row = cursor.fetchone()
            
            if not row or not row[0]:
                cursor.execute("""
                    INSERT OR REPLACE INTO ref_milestones (user_id, chat_id, milestone, awarded, awarded_at)
                    VALUES (?, ?, ?, 1, ?)
                """, (inviter_id, chat_id, milestone, datetime.now().isoformat()))
                conn.commit()
                
                from database import update_balance
                await update_balance(inviter_id, reward, f"Реферальная награда за {milestone} приглашений")
                await update_user_xp(inviter_id, reward, f"Реферальный бонус {milestone}")
                
                try:
                    await router.bot.send_message(
                        inviter_id,
                        f"🎉 *ПОЗДРАВЛЯЕМ!*\n\n"
                        f"Вы пригласили {milestone} друзей!\n"
                        f"💰 Получена награда: +{reward} NCoins!\n"
                        f"⭐ +{reward} XP к рангу!\n\n"
                        f"📊 Следующая цель: {list(REWARDS.keys())[list(REWARDS.keys()).index(milestone) + 1] if milestone < 1000 else 'МАКСИМУМ'} приглашений",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to send milestone message: {e}")
    
    conn.close()


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
    
    # Формируем текст с наградами
    rewards_text = ""
    for milestone, reward in REWARDS.items():
        rewards_text += f"├ {milestone} приглашений → +{reward} NCoins\n"
    
    await message.answer(
        f"✅ *Реферальная система ВКЛЮЧЕНА!*\n\n"
        f"🔗 Ссылка чата: `{ref_link}`\n\n"
        f"📌 Участники используют /my_ref для получения своей ссылки.\n"
        f"💰 За каждого приглашённого: +100 NCoins\n\n"
        f"*🏆 БОНУСЫ ЗА ДОСТИЖЕНИЯ:*\n{rewards_text}",
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
    
    # Получаем общее количество наград
    cursor.execute("SELECT COUNT(*) FROM ref_milestones WHERE chat_id = ?", (chat_id,))
    total_milestones = cursor.fetchone()[0]
    
    conn.close()
    
    text = f"📊 *СТАТИСТИКА РЕФЕРАЛЬНОЙ СИСТЕМЫ*\n\n"
    text += f"📢 Статус: {'✅ ВКЛЮЧЕНА' if setting and setting[0] else '❌ ВЫКЛЮЧЕНА'}\n"
    text += f"💰 Бонус за приглашение: {setting[1] if setting else 100} NCoins\n"
    text += f"👥 Всего приглашений: {total_invites}\n"
    text += f"🏆 Выдано наград: {total_milestones}\n\n"
    
    if top_inviters:
        text += "*🏆 ТОП ПРИГЛАСИТЕЛЕЙ:*\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, (uid, count, earned) in enumerate(top_inviters[:5], 1):
            medal = medals[i-1] if i-1 < len(medals) else f"{i}️⃣"
            
            # Получаем имя пользователя
            user = await db.get_user(uid)
            name = f"@{user['username']}" if user and user['username'] else f"Пользователь {uid}"
            
            text += f"{medal} {name} — {count} приглашений (+{earned} NCoins)\n"
    
    await message.answer(text, parse_mode="Markdown")


# ==================== КОМАНДЫ ДЛЯ УЧАСТНИКОВ ====================

@router.message(Command("my_ref"))
async def my_referral_link(message: types.Message):
    """Получить свою реферальную ссылку и статистику"""
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
    
    # Получаем полученные награды
    cursor.execute("""
        SELECT milestone FROM ref_milestones 
        WHERE user_id = ? AND chat_id = ? AND awarded = 1
        ORDER BY milestone
    """, (user_id, chat_id))
    milestones = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    bot_username = (await router.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}_{ref_code}"
    
    # Формируем текст с наградами
    rewards_text = ""
    for milestone, reward in REWARDS.items():
        if milestone in milestones:
            rewards_text += f"✅ {milestone} приглашений — +{reward} NCoins (получено)\n"
        elif user_ref[1] >= milestone:
            rewards_text += f"🎉 {milestone} приглашений — +{reward} NCoins (доступно!)\n"
        else:
            rewards_text += f"🔜 {milestone} приглашений — +{reward} NCoins (осталось {milestone - user_ref[1]})\n"
    
    text = f"""
🔗 *ВАША РЕФЕРАЛЬНАЯ ССЫЛКА*

`{ref_link}`

━━━━━━━━━━━━━━━━━━━━━

📊 *ВАША СТАТИСТИКА:*
├ 👥 Приглашено: {user_ref[1]}
└ 💰 Заработано: {user_ref[2]} NCoins

💰 *БОНУС ЗА ПРИГЛАШЕНИЕ:* +{setting[1]} NCoins

━━━━━━━━━━━━━━━━━━━━━

*🏆 ДОСТИЖЕНИЯ:*
{rewards_text}

━━━━━━━━━━━━━━━━━━━━━

💡 *Чем больше друзей пригласишь — тем выше награда!*
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ", url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся к нашему чату!")],
        [InlineKeyboardButton(text="💰 КУПИТЬ VIP", callback_data="buy_vip_ncoins")],
        [InlineKeyboardButton(text="📊 ТОП ПРИГЛАСИТЕЛЕЙ", callback_data="ref_top")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "ref_top")
async def ref_top_callback(callback: types.CallbackQuery):
    """Топ пригласителей чата"""
    chat_id = callback.message.chat.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, invited_count, earned_coins 
        FROM ref_links 
        WHERE chat_id = ? 
        ORDER BY invited_count DESC 
        LIMIT 10
    """, (chat_id,))
    top_inviters = cursor.fetchall()
    conn.close()
    
    if not top_inviters:
        await callback.answer("Пока нет приглашений!", show_alert=True)
        return
    
    text = "🏆 *ТОП ПРИГЛАСИТЕЛЕЙ ЧАТА*\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, (uid, count, earned) in enumerate(top_inviters):
        medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
        user = await db.get_user(uid)
        name = f"@{user['username']}" if user and user['username'] else f"Пользователь {uid}"
        text += f"{medal} {name} — {count} приглашений (+{earned} NCoins)\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="ref_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


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
    invited_id = message.from_user.id
    
    if inviter_id == invited_id:
        await message.answer("❌ Нельзя пригласить самого себя!")
        conn.close()
        return
    
    # Проверяем, не было ли уже приглашения
    cursor.execute("SELECT id FROM ref_invites WHERE inviter_id = ? AND invited_id = ? AND chat_id = ?",
                   (inviter_id, invited_id, chat_id))
    if cursor.fetchone():
        await message.answer("✅ Вы уже присоединялись по реферальной ссылке!")
        conn.close()
        return
    
    cursor.execute("SELECT bonus_amount FROM ref_settings WHERE chat_id = ?", (chat_id,))
    setting = cursor.fetchone()
    bonus_amount = setting[0] if setting else 100
    
    # Добавляем запись о приглашении
    cursor.execute("""
        INSERT INTO ref_invites (inviter_id, invited_id, chat_id, invited_at)
        VALUES (?, ?, ?, ?)
    """, (inviter_id, invited_id, chat_id, datetime.now().isoformat()))
    
    # Обновляем счётчик приглашений
    cursor.execute("""
        UPDATE ref_links 
        SET invited_count = invited_count + 1, earned_coins = earned_coins + ?
        WHERE user_id = ? AND chat_id = ?
    """, (bonus_amount, inviter_id, chat_id))
    conn.commit()
    
    # Получаем новое количество приглашений
    cursor.execute("SELECT invited_count FROM ref_links WHERE user_id = ? AND chat_id = ?", (inviter_id, chat_id))
    new_count = cursor.fetchone()[0]
    conn.close()
    
    from database import update_balance
    await update_balance(inviter_id, bonus_amount, f"Реферальный бонус")
    await update_user_xp(inviter_id, bonus_amount, "Реферальный бонус")
    
    # Проверяем награды за достижения
    await check_milestone_reward(inviter_id, new_count, chat_id)
    
    # Уведомляем пригласившего
    try:
        await router.bot.send_message(
            inviter_id,
            f"🎉 *НОВЫЙ УЧАСТНИК!*\n\n"
            f"По вашей реферальной ссылке присоединился новый участник!\n"
            f"💰 Вам начислено +{bonus_amount} NCoins!\n"
            f"⭐ +{bonus_amount} XP к рангу!\n"
            f"📊 Всего приглашений: {new_count}\n\n"
            f"✨ Осталось {10 - new_count if new_count < 10 else 0} приглашений до следующей награды!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to notify inviter: {e}")
    
    await message.answer(
        f"✅ *ДОБРО ПОЖАЛОВАТЬ!*\n\n"
        f"Вы присоединились по реферальной ссылке!\n"
        f"Пригласивший получил +{bonus_amount} NCoins.\n\n"
        f"📌 Используйте /my_ref, чтобы получить свою реферальную ссылку!\n"
        f"💰 Приглашайте друзей и получайте награды!",
        parse_mode="Markdown"
    )


# ==================== КНОПКИ ====================

@router.callback_query(lambda c: c.data == "ref_menu")
async def ref_menu(callback: types.CallbackQuery):
    """Меню реферальной системы"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 МОЯ ССЫЛКА", callback_data="my_ref")],
        [InlineKeyboardButton(text="📊 ТОП ПРИГЛАСИТЕЛЕЙ", callback_data="ref_top")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "📢 *РЕФЕРАЛЬНАЯ СИСТЕМА*\n\n"
        "Приглашайте друзей и получайте NCoins!\n\n"
        "💰 *БОНУСЫ:*\n"
        "├ За каждого друга: +100 NCoins\n"
        "├ 5 друзей: +500 NCoins\n"
        "├ 10 друзей: +1000 NCoins\n"
        "├ 25 друзей: +3000 NCoins\n"
        "├ 50 друзей: +7000 NCoins\n"
        "├ 100 друзей: +15000 NCoins\n"
        "└ 250+ друзей: огромные бонусы!\n\n"
        "✨ Чем больше друзей — тем выше награда!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "my_ref")
async def my_ref_callback(callback: types.CallbackQuery):
    """Обработчик кнопки 'Моя ссылка'"""
    await my_referral_link(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "buy_vip_ncoins")
async def buy_vip_ncoins(callback: types.CallbackQuery):
    """Купить VIP за NCoins"""
    user_id = callback.from_user.id
    vip_price = 500
    
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    if user["balance"] < vip_price:
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
        f"✅ *VIP СТАТУС АКТИВИРОВАН!*\n\n"
        f"⭐ Действует до: {new_until[:10]}\n"
        f"💰 Списано: {vip_price} NCoins",
        parse_mode="Markdown"
    )
    await callback.answer()
