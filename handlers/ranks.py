"""
Модуль системы рангов и глобального рейтинга
Данные привязаны к пользователю (user_id), а не к чату
"""

import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)


# ==================== ТАБЛИЦА РАНГОВ (32 уровня) ====================

RANKS = [
    # Обычные участники (0-5)
    {"level": 0, "name": "🌱 Дерево", "xp": 0, "bonus": 0},
    {"level": 1, "name": "🍃 Лист", "xp": 50, "bonus": 0},
    {"level": 2, "name": "🌿 Куст", "xp": 150, "bonus": 0},
    {"level": 3, "name": "🌲 Сосна", "xp": 300, "bonus": 0},
    {"level": 4, "name": "🌳 Дуб", "xp": 500, "bonus": 0},
    {"level": 5, "name": "🔥 Кедр", "xp": 800, "bonus": 0},
    
    # VIP подписчики (6-14)
    {"level": 6, "name": "⭐ Бронза", "xp": 1200, "bonus": 5},
    {"level": 7, "name": "⭐⭐ Серебро", "xp": 1700, "bonus": 10},
    {"level": 8, "name": "⭐⭐⭐ Золото", "xp": 2300, "bonus": 15},
    {"level": 9, "name": "💎 Платина", "xp": 3000, "bonus": 20},
    {"level": 10, "name": "💎💎 Изумруд", "xp": 4000, "bonus": 25},
    {"level": 11, "name": "💎💎💎 Сапфир", "xp": 5200, "bonus": 30},
    {"level": 12, "name": "🔹 Рубин", "xp": 6600, "bonus": 35},
    {"level": 13, "name": "🔹🔹 Алмаз", "xp": 8200, "bonus": 40},
    {"level": 14, "name": "🔹🔹🔹 Аметист", "xp": 10000, "bonus": 45},
    
    # Премиум подписчики (15-20)
    {"level": 15, "name": "🪙 Топаз", "xp": 12500, "bonus": 50},
    {"level": 16, "name": "🪙🪙 Опал", "xp": 15500, "bonus": 60},
    {"level": 17, "name": "🪙🪙🪙 Янтарь", "xp": 19000, "bonus": 70},
    {"level": 18, "name": "✨ Жемчуг", "xp": 23000, "bonus": 80},
    {"level": 19, "name": "✨✨ Коралл", "xp": 28000, "bonus": 90},
    {"level": 20, "name": "✨✨✨ Малахит", "xp": 34000, "bonus": 100},
    
    # Легендарные подписчики (21-26)
    {"level": 21, "name": "🌌 Нефрит", "xp": 41000, "bonus": 120},
    {"level": 22, "name": "🌌🌌 Оникс", "xp": 49000, "bonus": 150},
    {"level": 23, "name": "🌌🌌🌌 Лазурит", "xp": 58000, "bonus": 180},
    {"level": 24, "name": "👑 Танзанит", "xp": 68000, "bonus": 220},
    {"level": 25, "name": "👑👑 Циркон", "xp": 79000, "bonus": 260},
    {"level": 26, "name": "👑👑👑 Гранат", "xp": 91000, "bonus": 300},
    
    # Топ донатеры (27-32)
    {"level": 27, "name": "🏅 Бриллиант", "xp": 105000, "bonus": 350},
    {"level": 28, "name": "🏅🏅 Корунд", "xp": 120000, "bonus": 400},
    {"level": 29, "name": "🏅🏅🏅 Шпинель", "xp": 136000, "bonus": 450},
    {"level": 30, "name": "🔮 Александрит", "xp": 153000, "bonus": 500},
    {"level": 31, "name": "🔮🔮 Хризолит", "xp": 171000, "bonus": 550},
    {"level": 32, "name": "🔮🔮🔮 Цоизит", "xp": 190000, "bonus": 600},
    
    # Глобальные лидеры (33-38)
    {"level": 33, "name": "🌍 Танзанит", "xp": 210000, "bonus": 700},
    {"level": 34, "name": "🌍🌍 Рубин", "xp": 231000, "bonus": 800},
    {"level": 35, "name": "🌍🌍🌍 Изумруд", "xp": 253000, "bonus": 900},
    {"level": 36, "name": "🌎 Сапфир", "xp": 276000, "bonus": 1000},
    {"level": 37, "name": "🌎🌎 Алмаз", "xp": 300000, "bonus": 1200},
    {"level": 38, "name": "🌎🌎🌎 Александрит", "xp": 325000, "bonus": 1500},
    
    # Легенды (39)
    {"level": 39, "name": "⭐ Чёрный Бриллиант", "xp": 351000, "bonus": 2000},
]


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

async def init_ranks():
    """Инициализация таблиц рангов"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Таблица рангов пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ranks (
            user_id INTEGER PRIMARY KEY,
            rank_level INTEGER DEFAULT 0,
            rank_name TEXT DEFAULT '🌱 Дерево',
            rank_xp INTEGER DEFAULT 0,
            rank_bonus INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица донатеров
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            user_id INTEGER PRIMARY KEY,
            total_donated INTEGER DEFAULT 0,
            last_donate TIMESTAMP,
            donor_rank TEXT DEFAULT '💎 Поддерживающий'
        )
    """)
    
    # Таблица глобального рейтинга
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_rating (
            user_id INTEGER PRIMARY KEY,
            total_xp INTEGER DEFAULT 0,
            rating_position INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ Таблицы рангов инициализированы")


# ==================== РАБОТА С РАНГАМИ ====================

async def get_user_rank(user_id: int) -> dict:
    """Получить ранг пользователя"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_ranks WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "user_id": row[0],
            "rank_level": row[1],
            "rank_name": row[2],
            "rank_xp": row[3],
            "rank_bonus": row[4],
            "updated_at": row[5]
        }
    
    # Создаём запись по умолчанию
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_ranks (user_id, rank_level, rank_name, rank_xp, rank_bonus)
        VALUES (?, 0, '🌱 Дерево', 0, 0)
    """, (user_id,))
    conn.commit()
    conn.close()
    
    return {
        "user_id": user_id,
        "rank_level": 0,
        "rank_name": "🌱 Дерево",
        "rank_xp": 0,
        "rank_bonus": 0,
        "updated_at": None
    }


async def update_user_xp(user_id: int, xp_gain: int, source: str) -> bool:
    """
    Обновить XP пользователя
    Возвращает True, если уровень повысился
    """
    rank_data = await get_user_rank(user_id)
    old_level = rank_data["rank_level"]
    new_xp = rank_data["rank_xp"] + xp_gain
    
    # Определяем новый уровень
    new_level = old_level
    new_name = rank_data["rank_name"]
    new_bonus = rank_data["rank_bonus"]
    
    for i, rank in enumerate(RANKS):
        if new_xp >= rank["xp"] and i > new_level:
            new_level = i
            new_name = rank["name"]
            new_bonus = rank["bonus"]
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_ranks 
        SET rank_xp = ?, rank_level = ?, rank_name = ?, rank_bonus = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (new_xp, new_level, new_name, new_bonus, user_id))
    conn.commit()
    conn.close()
    
    # Обновляем глобальный рейтинг
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO global_rating (user_id, total_xp, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (user_id, new_xp))
    conn.commit()
    conn.close()
    
    return new_level > old_level


async def get_next_rank_info(current_xp: int, current_level: int) -> dict:
    """Получить информацию о следующем ранге"""
    if current_level >= len(RANKS) - 1:
        return None
    
    next_rank = RANKS[current_level + 1]
    xp_needed = next_rank["xp"] - current_xp
    
    return {
        "level": next_rank["level"],
        "name": next_rank["name"],
        "xp_needed": xp_needed,
        "bonus": next_rank["bonus"]
    }


async def add_donate(user_id: int, amount: int):
    """Добавить донат (для глобального рейтинга донатеров)"""
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO donors (user_id, total_donated, last_donate)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            total_donated = total_donated + excluded.total_donated,
            last_donate = excluded.last_donate
    """, (user_id, amount))
    
    # Определяем ранг донатера
    cursor.execute("SELECT total_donated FROM donors WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    total = row[0] if row else amount
    
    if total >= 100000:
        donor_rank = "👑 Легендарный меценат"
    elif total >= 50000:
        donor_rank = "💎 Платиновый меценат"
    elif total >= 25000:
        donor_rank = "🥇 Золотой меценат"
    elif total >= 10000:
        donor_rank = "🥈 Серебряный меценат"
    elif total >= 5000:
        donor_rank = "🥉 Бронзовый меценат"
    elif total >= 1000:
        donor_rank = "💎 Поддерживающий"
    else:
        donor_rank = "💝 Добрый человек"
    
    cursor.execute("UPDATE donors SET donor_rank = ? WHERE user_id = ?", (donor_rank, user_id))
    conn.commit()
    conn.close()


async def get_top_donors(limit: int = 10) -> list:
    """Получить топ донатеров"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.user_id, u.username, u.first_name, d.total_donated, d.donor_rank
        FROM donors d
        JOIN users u ON u.user_id = d.user_id
        ORDER BY d.total_donated DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "user_id": row[0],
            "username": row[1],
            "name": row[2],
            "total": row[3],
            "rank": row[4]
        }
        for row in rows
    ]


async def get_top_ranked(limit: int = 10) -> list:
    """Получить топ по рангу"""
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.user_id, u.username, u.first_name, r.rank_level, r.rank_name, r.rank_xp
        FROM user_ranks r
        JOIN users u ON u.user_id = r.user_id
        ORDER BY r.rank_xp DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "user_id": row[0],
            "username": row[1],
            "name": row[2],
            "level": row[3],
            "rank": row[4],
            "xp": row[5]
        }
        for row in rows
    ]


# ==================== КОМАНДЫ ====================

@router.message(Command("rank"))
async def cmd_rank(message: types.Message):
    """Показать текущий ранг пользователя"""
    user_id = message.from_user.id
    rank_data = await get_user_rank(user_id)
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    next_rank = await get_next_rank_info(rank_data["rank_xp"], rank_data["rank_level"])
    
    # Прогресс-бар
    if next_rank:
        current_rank_xp = RANKS[rank_data["rank_level"]]["xp"]
        xp_in_current = rank_data["rank_xp"] - current_rank_xp
        xp_to_next = next_rank["xp_needed"]
        
        # Прогресс в процентах
        progress = int((xp_in_current / (current_rank_xp + xp_to_next)) * 20) if xp_to_next > 0 else 0
        progress_bar = "█" * progress + "░" * (20 - progress)
        
        text = f"""
🏆 *ВАШ РАНГ В NEXUS*

━━━━━━━━━━━━━━━━━━━━━

{rank_data['rank_name']}

📊 Уровень: {rank_data['rank_level']}
⭐ Бонус к выигрышам: +{rank_data['rank_bonus']}%
📈 Опыт: {rank_data['rank_xp']} XP

📊 *ПРОГРЕСС ДО {next_rank['name']}:*
{progress_bar}
{current_rank_xp} XP ━━━ {rank_data['rank_xp']} XP ━━━ {current_rank_xp + xp_to_next} XP

Осталось: {next_rank['xp_needed']} XP

━━━━━━━━━━━━━━━━━━━━━

💰 *КАК ПОЛУЧИТЬ XP?*

├ /daily — +100 XP
├ Выигрыши в играх — +50 XP
├ Приглашение друга — +200 XP
├ Донаты — +10 XP за 1 рубль

━━━━━━━━━━━━━━━━━━━━━

📊 *Глобальный рейтинг:* /top_ranked
🏅 *Топ донатеров:* /top_donors
"""
    else:
        text = f"""
🏆 *ВАШ РАНГ В NEXUS*

━━━━━━━━━━━━━━━━━━━━━

{rank_data['rank_name']}

📊 Уровень: {rank_data['rank_level']}
⭐ Бонус к выигрышам: +{rank_data['rank_bonus']}%
📈 Опыт: {rank_data['rank_xp']} XP

━━━━━━━━━━━━━━━━━━━━━

🎉 *ПОЗДРАВЛЯЕМ!*
Вы достигли МАКСИМАЛЬНОГО РАНГА!

━━━━━━━━━━━━━━━━━━━━━

📊 *Глобальный рейтинг:* /top_ranked
🏅 *Топ донатеров:* /top_donors
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 ТОП РЕЙТИНГА", callback_data="top_ranked_menu"),
         InlineKeyboardButton(text="🏅 ТОП ДОНАТЕРОВ", callback_data="top_donors_menu")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@router.message(Command("top_ranked"))
async def cmd_top_ranked(message: types.Message):
    """Топ пользователей по рангу"""
    top = await get_top_ranked(10)
    
    if not top:
        await message.answer("🏆 Пока нет участников в рейтинге!\n\nБудьте первыми!")
        return
    
    text = "🏆 *ТОП ПОЛЬЗОВАТЕЛЕЙ ПО РАНГУ*\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, user in enumerate(top):
        medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
        name = f"@{user['username']}" if user['username'] else user['name']
        text += f"{medal} {name} — {user['rank']} (уровень {user['level']})\n"
        text += f"   └ {user['xp']} XP\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@router.message(Command("top_donors"))
async def cmd_top_donors(message: types.Message):
    """Топ донатеров"""
    top = await get_top_donors(10)
    
    if not top:
        await message.answer("🏅 Пока нет донатеров в рейтинге!\n\nСтань первым — /donate")
        return
    
    text = "🏅 *ТОП ДОНАТЕРОВ NEXUS*\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, donor in enumerate(top):
        medal = medals[i] if i < len(medals) else f"{i+1}️⃣"
        name = f"@{donor['username']}" if donor['username'] else donor['name']
        text += f"{medal} {name} — {donor['rank']}\n"
        text += f"   └ {donor['total']} ₽\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ ПОДДЕРЖАТЬ", callback_data="donate")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data == "top_ranked_menu")
async def top_ranked_menu_callback(callback: types.CallbackQuery):
    await cmd_top_ranked(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "top_donors_menu")
async def top_donors_menu_callback(callback: types.CallbackQuery):
    await cmd_top_donors(callback.message)
    await callback.answer()
