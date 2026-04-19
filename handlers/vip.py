"""
Модуль VIP статусов и преимуществ — ИСПРАВЛЕННАЯ ВЕРСИЯ
Все отображения баланса используют ТОЛЬКО await db.get_balance()
"""

import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

router = Router()
logger = logging.getLogger(__name__)

# VIP конфигурация
VIP_PRICES = {1: 500, 2: 1000, 3: 2000, 4: 5000, 5: 10000}
VIP_NAMES = {
    1: {"name": "🥉 Бронза", "win_bonus": 5, "daily_bonus": 50, "icon": "🥉"},
    2: {"name": "🥈 Серебро", "win_bonus": 10, "daily_bonus": 100, "icon": "🥈"},
    3: {"name": "🥇 Золото", "win_bonus": 15, "daily_bonus": 150, "icon": "🥇"},
    4: {"name": "💎 Платина", "win_bonus": 20, "daily_bonus": 200, "icon": "💎"},
    5: {"name": "💠 Алмаз", "win_bonus": 30, "daily_bonus": 300, "icon": "💠"},
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Получить пользователя или создать если не существует"""
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Auto-registered user {user_id} in VIP module")
    return user


def get_vip_privileges(vip_level: int) -> dict:
    """Получить привилегии для уровня VIP"""
    return VIP_NAMES.get(vip_level, VIP_NAMES[1])


async def update_user_vip(user_id: int, vip_level: int, days: int = 30):
    """Обновить VIP статус пользователя"""
    def _sync_update():
        conn = db._get_connection()
        cursor = conn.cursor()
        new_until = (datetime.now() + timedelta(days=days)).isoformat()
        cursor.execute(
            "UPDATE users SET vip_level = ?, vip_until = ? WHERE user_id = ?",
            (vip_level, new_until, user_id)
        )
        conn.commit()
        conn.close()
        return True
    
    return await asyncio.to_thread(_sync_update)


async def check_achievement_vip(user_id: int, wins: int):
    """Проверить и выдать VIP за достижения"""
    vip_level = 0
    
    if wins >= 200:
        vip_level = 4
    elif wins >= 100:
        vip_level = 3
    elif wins >= 50:
        vip_level = 2
    elif wins >= 10:
        vip_level = 1
    
    if vip_level > 0:
        user = await db.get_user(user_id)
        current_vip = user.get("vip_level", 0) if user else 0
        
        if vip_level > current_vip:
            await update_user_vip(user_id, vip_level, 30)
            return vip_level
    
    return None


# ==================== КОМАНДА /vip ====================

@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    """Информация о VIP статусе — с актуальным балансом"""
    user_id = message.from_user.id
    
    # Получаем базовые данные пользователя
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    # 🔥 ВСЕГДА получаем свежий баланс непосредственно перед использованием
    balance = await db.get_balance(user_id)
    
    vip_level = user.get("vip_level", 0) or 0
    vip_until = user.get("vip_until", "")
    wins = user.get("wins", 0) or 0
    
    # Проверяем достижения (может изменить VIP)
    achievement_vip = await check_achievement_vip(user_id, wins)
    if achievement_vip:
        vip_level = achievement_vip
        # 🔥 После изменений в БД — обновляем данные пользователя и баланс
        user = await db.get_user(user_id)
        balance = await db.get_balance(user_id)
    
    if vip_level > 0:
        privileges = get_vip_privileges(vip_level)
        
        try:
            until_date = datetime.fromisoformat(vip_until).strftime("%d.%m.%Y") if vip_until else "Бессрочно"
        except:
            until_date = "Бессрочно"
        
        # 🔥 Используем ТОЛЬКО переменную balance, НЕ user['balance']
        text = f"""
{privileges['icon']} *ВАШ VIP СТАТУС* {privileges['icon']}

━━━━━━━━━━━━━━━━━━━━━

📛 Уровень: *{privileges['name']}* (Уровень {vip_level})
💰 Баланс: *{balance}* NCoins
📅 Действует до: {until_date}

━━━━━━━━━━━━━━━━━━━━━

*✨ ВАШИ ПРЕИМУЩЕСТВА:*

├ 🎮 +{privileges['win_bonus']}% к выигрышам
├ 🎁 +{privileges['daily_bonus']} NCoins к бонусу
├ 👑 Статус в чате
├ 💎 Доступ к VIP-комнатам
└ ⭐ Приоритетная поддержка
"""
    else:
        # 🔥 Здесь тоже используем balance, а не user['balance']
        text = f"""
⭐ *VIP СТАТУСЫ NEXUS* ⭐

Получите эксклюзивные преимущества!

━━━━━━━━━━━━━━━━━━━━━
💰 *Ваш баланс: {balance} NCoins*

━━━━━━━━━━━━━━━━━━━━━

🥉 *БРОНЗА* (1 уровень) — 500 NCoins
├ 🎮 +5% к выигрышам
└ 🎁 +50 NCoins к бонусу

🥈 *СЕРЕБРО* (2 уровень) — 1,000 NCoins
├ 🎮 +10% к выигрышам
└ 🎁 +100 NCoins к бонусу

🥇 *ЗОЛОТО* (3 уровень) — 2,000 NCoins
├ 🎮 +15% к выигрышам
└ 🎁 +150 NCoins к бонусу

💎 *ПЛАТИНА* (4 уровень) — 5,000 NCoins
├ 🎮 +20% к выигрышам
└ 🎁 +200 NCoins к бонусу

💠 *АЛМАЗ* (5 уровень) — 10,000 NCoins
├ 🎮 +30% к выигрышам
└ 🎁 +300 NCoins к бонусу

━━━━━━━━━━━━━━━━━━━━━

🎁 *БЕСПЛАТНЫЙ VIP:*
├ 10 побед → Бронза
├ 50 побед → Серебро
├ 100 побед → Золото
└ 200 побед → Платина

📊 *Ваши победы: {wins}*
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 КУПИТЬ VIP", callback_data="buy_vip")],
        [InlineKeyboardButton(text="🏆 МОИ ДОСТИЖЕНИЯ", callback_data="vip_achievements")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@router.callback_query(F.data == "vip")
@router.callback_query(F.data == "vip_menu")
async def vip_callback(callback: types.CallbackQuery):
    await cmd_vip(callback.message)
    await callback.answer()


# ==================== ПОКУПКА VIP ====================

@router.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: types.CallbackQuery):
    """Меню покупки VIP — с актуальным балансом"""
    user_id = callback.from_user.id
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    # 🔥 СВЕЖИЙ БАЛАНС перед отображением
    balance = await db.get_balance(user_id)
    current_vip = user.get('vip_level', 0) or 0
    
    buttons = []
    for level, price in VIP_PRICES.items():
        name = VIP_NAMES[level]['name']
        if level <= current_vip:
            name = f"✅ {name} (куплен)"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{name} ({price} NCoins)",
                callback_data=f"buy_vip_{level}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # 🔥 Используем balance, а не user['balance']
    await callback.message.edit_text(
        f"💎 *ПОКУПКА VIP СТАТУСА*\n\n"
        f"💰 Ваш баланс: *{balance} NCoins*\n"
        f"⭐ Текущий VIP: *{current_vip} уровень*\n\n"
        f"Выберите уровень VIP:\n\n"
        f"💡 *Совет:* VIP действует 30 дней",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_vip_"))
async def buy_vip(callback: types.CallbackQuery):
    """Покупка VIP уровня — с корректным обновлением баланса"""
    user_id = callback.from_user.id
    level = int(callback.data.split("_")[2])
    price = VIP_PRICES.get(level, 500)
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    current_vip = user.get('vip_level', 0) or 0
    
    if level <= current_vip:
        await callback.answer(f"❌ У вас уже есть VIP {current_vip} уровня!", show_alert=True)
        return
    
    # 🔥 СВЕЖИЙ БАЛАНС перед проверкой
    balance = await db.get_balance(user_id)
    
    if balance < price:
        await callback.answer(
            f"❌ Недостаточно средств!\nНужно: {price} NCoins\nБаланс: {balance} NCoins",
            show_alert=True
        )
        return
    
    try:
        # Списываем средства
        await db.update_balance(user_id, -price, f"Покупка VIP уровня {level}")
        await update_user_vip(user_id, level, 30)
        
        # 🔥 КРИТИЧНО: получаем баланс ПОСЛЕ обновления!
        new_balance = await db.get_balance(user_id)
        
        privileges = get_vip_privileges(level)
        
        # 🔥 Используем ТОЛЬКО new_balance в ответе
        await callback.message.edit_text(
            f"🎉 *ПОЗДРАВЛЯЕМ С ПОКУПКОЙ VIP!*\n\n"
            f"{privileges['icon']} Новый уровень: *{privileges['name']}*\n"
            f"💰 Списано: *{price} NCoins*\n"
            f"💎 Новый баланс: *{new_balance} NCoins*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✨ *НОВЫЕ ПРЕИМУЩЕСТВА:*\n"
            f"├ 🎮 +{privileges['win_bonus']}% к выигрышам\n"
            f"├ 🎁 +{privileges['daily_bonus']} NCoins к бонусу\n"
            f"├ 👑 Статус в чате\n"
            f"└ ⭐ Приоритетная поддержка\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 Статус действует *30 дней*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ПОНЯТНО", callback_data="vip")]
            ])
        )
        logger.info(f"User {user_id} purchased VIP level {level}")
        
    except Exception as e:
        logger.error(f"VIP purchase failed: {e}")
        await callback.answer("❌ Ошибка при покупке", show_alert=True)
    
    await callback.answer()


# ==================== ДОСТИЖЕНИЯ ====================

@router.callback_query(F.data == "vip_achievements")
async def vip_achievements(callback: types.CallbackQuery):
    """Достижения для получения VIP бесплатно — с актуальным балансом"""
    user_id = callback.from_user.id
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    wins = user.get("wins", 0) or 0
    current_vip = user.get("vip_level", 0) or 0
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(user_id)
    
    awarded_vip = await check_achievement_vip(user_id, wins)
    
    # Если VIP был выдан за достижения — обновляем баланс после этого
    if awarded_vip:
        balance = await db.get_balance(user_id)
    
    next_level = None
    next_wins = 0
    progress = 0
    
    if wins < 10:
        next_level = "🥉 Бронза"
        next_wins = 10
        progress = int((wins / 10) * 100) if wins > 0 else 0
    elif wins < 50:
        next_level = "🥈 Серебро"
        next_wins = 50
        progress = int(((wins - 10) / 40) * 100)
    elif wins < 100:
        next_level = "🥇 Золото"
        next_wins = 100
        progress = int(((wins - 50) / 50) * 100)
    elif wins < 200:
        next_level = "💎 Платина"
        next_wins = 200
        progress = int(((wins - 100) / 100) * 100)
    else:
        progress = 100
    
    bar_length = 10
    filled = int(bar_length * progress / 100)
    progress_bar = "█" * filled + "░" * (bar_length - filled)
    
    # 🔥 Используем balance, а не user['balance']
    text = f"""
🏆 *БЕСПЛАТНЫЙ VIP ЗА ДОСТИЖЕНИЯ*

━━━━━━━━━━━━━━━━━━━━━

📊 *ВАШ ПРОГРЕСС:*

💰 Баланс: *{balance} NCoins*
🏆 Побед: *{wins}*
⭐ Текущий VIP: *{current_vip} уровень*

"""
    
    if wins >= 200:
        text += "🎉 *ВЫ ДОСТИГЛИ ПЛАТИНЫ!*\n\n"
    elif wins >= 100:
        text += "🎉 *ВЫ ДОСТИГЛИ ЗОЛОТА!*\n\n"
    elif wins >= 50:
        text += "🎉 *ВЫ ДОСТИГЛИ СЕРЕБРА!*\n\n"
    elif wins >= 10:
        text += "🎉 *ВЫ ДОСТИГЛИ БРОНЗЫ!*\n\n"
    
    if awarded_vip:
        text += f"✨ *Только что получен VIP {awarded_vip} уровня!*\n\n"
    
    if next_level and wins < 200:
        text += f"""
━━━━━━━━━━━━━━━━━━━━━

📈 *ДО СЛЕДУЮЩЕГО УРОВНЯ:*

Цель: *{next_level}*
Прогресс: {wins}/{next_wins} побед
[{progress_bar}] {progress}%

💪 Осталось *{next_wins - wins}* побед!
"""
    
    text += """
━━━━━━━━━━━━━━━━━━━━━

*ДОСТУПНЫЕ НАГРАДЫ:*

🥉 10 побед → Бронза VIP
🥈 50 побед → Серебро VIP
🥇 100 побед → Золото VIP
💎 200 побед → Платина VIP
"""
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="
