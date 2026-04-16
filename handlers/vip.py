"""
Модуль VIP статусов и преимуществ
"""

import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()
logger = logging.getLogger(__name__)


async def get_vip_privileges(vip_level: int) -> dict:
    """Получить привилегии для уровня VIP"""
    # Временная заглушка, пока нет таблицы в БД
    privileges = {
        1: {"name": "🥉 Бронза", "win_bonus": 5, "daily_bonus": 50, "icon": "🥉"},
        2: {"name": "🥈 Серебро", "win_bonus": 10, "daily_bonus": 100, "icon": "🥈"},
        3: {"name": "🥇 Золото", "win_bonus": 15, "daily_bonus": 150, "icon": "🥇"},
        4: {"name": "💎 Платина", "win_bonus": 20, "daily_bonus": 200, "icon": "💎"},
        5: {"name": "💠 Алмаз", "win_bonus": 30, "daily_bonus": 300, "icon": "💠"},
    }
    return privileges.get(vip_level, privileges.get(1))


@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    """Информация о VIP статусе"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return

    vip_level = user.get("vip_level", 0)
    vip_until = user.get("vip_until", "")

    if vip_level > 0:
        privileges = await get_vip_privileges(vip_level)
        text = f"""
{privileges['icon']} *ВАШ VIP СТАТУС* {privileges['icon']}

━━━━━━━━━━━━━━━━━━━━━

📛 Уровень: *{privileges['name']}* (Уровень {vip_level})
📅 Действует до: {vip_until[:10] if vip_until else 'Неизвестно'}

*✨ ПРЕИМУЩЕСТВА:*

├ 🎮 +{privileges['win_bonus']}% к выигрышам в играх
├ 🎁 +{privileges['daily_bonus']} NCoins к ежедневному бонусу
├ 👑 Эксклюзивный статус в чате
└ 💎 Доступ к VIP-командам
"""
    else:
        text = """
⭐ *VIP СТАТУСЫ NEXUS* ⭐

Получите эксклюзивные преимущества:

━━━━━━━━━━━━━━━━━━━━━

🥉 *Бронза* (1 уровень)
├ 🎮 +5% к выигрышам
├ 🎁 +50 NCoins к бонусу
└ 💰 Цена: 500 NCoins

🥈 *Серебро* (2 уровень)
├ 🎮 +10% к выигрышам
├ 🎁 +100 NCoins к бонусу
└ 💰 Цена: 1000 NCoins

🥇 *Золото* (3 уровень)
├ 🎮 +15% к выигрышам
├ 🎁 +150 NCoins к бонусу
└ 💰 Цена: 2000 NCoins

💎 *Платина* (4 уровень)
├ 🎮 +20% к выигрышам
├ 🎁 +200 NCoins к бонусу
└ 💰 Цена: 5000 NCoins

💠 *Алмаз* (5 уровень)
├ 🎮 +30% к выигрышам
├ 🎁 +300 NCoins к бонусу
└ 💰 Цена: 10000 NCoins

━━━━━━━━━━━━━━━━━━━━━

💡 *Как получить VIP?*
├ Купить за NCoins в магазине
├ Получить за достижения (победы)
└ Выиграть в розыгрышах
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 КУПИТЬ VIP", callback_data="buy_vip")],
        [InlineKeyboardButton(text="🏆 МОИ ДОСТИЖЕНИЯ", callback_data="vip_achievements")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@router.callback_query(F.data == "vip")
async def vip_callback(callback: types.CallbackQuery):
    """Обработчик кнопки VIP из главного меню"""
    await cmd_vip(callback.message)
    await callback.answer()


@router.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: types.CallbackQuery):
    """Меню покупки VIP"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥉 БРОНЗА (500 NCoins)", callback_data="buy_vip_1")],
        [InlineKeyboardButton(text="🥈 СЕРЕБРО (1000 NCoins)", callback_data="buy_vip_2")],
        [InlineKeyboardButton(text="🥇 ЗОЛОТО (2000 NCoins)", callback_data="buy_vip_3")],
        [InlineKeyboardButton(text="💎 ПЛАТИНА (5000 NCoins)", callback_data="buy_vip_4")],
        [InlineKeyboardButton(text="💠 АЛМАЗ (10000 NCoins)", callback_data="buy_vip_5")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
    ])
    
    await callback.message.edit_text(
        f"💎 *ПОКУПКА VIP*\n\n"
        f"💰 Ваш баланс: {user['balance']} NCoins\n\n"
        "Выберите уровень VIP:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_vip_"))
async def buy_vip(callback: types.CallbackQuery):
    """Покупка VIP уровня"""
    user_id = callback.from_user.id
    level = int(callback.data.split("_")[2])
    
    prices = {1: 500, 2: 1000, 3: 2000, 4: 5000, 5: 10000}
    price = prices.get(level, 500)
    
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    if user["balance"] < price:
        await callback.answer(f"❌ Не хватает NCoins! Нужно {price}", show_alert=True)
        return
    
    # Списываем монеты
    await db.update_balance(user_id, -price, f"Покупка VIP уровня {level}")
    
    # Обновляем VIP уровень
    new_until = (datetime.now() + timedelta(days=30)).isoformat()
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET vip_level = ?, vip_until = ? WHERE user_id = ?",
                   (level, new_until, user_id))
    conn.commit()
    conn.close()
    
    privileges = await get_vip_privileges(level)
    
    await callback.message.edit_text(
        f"✅ *VIP СТАТУС ПОВЫШЕН!*\n\n"
        f"{privileges['icon']} Новый уровень: *{privileges['name']}*\n"
        f"💰 Списано: {price} NCoins\n\n"
        f"✨ *Новые преимущества:*\n"
        f"├ 🎮 +{privileges['win_bonus']}% к выигрышам\n"
        f"├ 🎁 +{privileges['daily_bonus']} NCoins к бонусу\n\n"
        f"📅 Действует 30 дней",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "vip_achievements")
async def vip_achievements(callback: types.CallbackQuery):
    """Достижения для получения VIP бесплатно"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    wins = user.get("wins", 0)
    
    text = f"""
🏆 *БЕСПЛАТНЫЙ VIP ЗА ДОСТИЖЕНИЯ*

Получите VIP статус бесплатно, выполняя достижения:

━━━━━━━━━━━━━━━━━━━━━

*ДОСТУПНЫЕ УРОВНИ:*

🥉 *Бронза* — 10 побед
   └ 🎮 +5% к выигрышам
   └ 🎁 +50 NCoins к бонусу

🥈 *Серебро* — 50 побед
   └ 🎮 +10% к выигрышам
   └ 🎁 +100 NCoins к бонусу

🥇 *Золото* — 100 побед
   └ 🎮 +15% к выигрышам
   └ 🎁 +150 NCoins к бонусу

💎 *Платина* — 200 побед
   └ 🎮 +20% к выигрышам
   └ 🎁 +200 NCoins к бонусу

━━━━━━━━━━━━━━━━━━━━━

📊 *ВАШ ПРОГРЕСС:*

🏆 Побед: {wins}
"""
    
    if wins >= 200:
        text += "\n🎉 *Вы достигли ПЛАТИНЫ!* VIP статус активирован!"
    elif wins >= 100:
        text += "\n🎉 *Вы достигли ЗОЛОТА!* VIP статус активирован!"
    elif wins >= 50:
        text += "\n🎉 *Вы достигли СЕРЕБРА!* VIP статус активирован!"
    elif wins >= 10:
        text += "\n🎉 *Вы достигли БРОНЗЫ!* VIP статус активирован!"
    else:
        text += f"\n💪 Осталось {10 - wins} побед до Бронзового VIP!"
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
    ]))
    await callback.answer()
