"""
Модуль VIP статусов и преимуществ
Версия: 2.1 (Safe Strings + HTML Mode + Sync Balance)
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

# ==================== КОНФИГУРАЦИЯ ====================

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
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
    return user


def get_vip_privileges(vip_level: int) -> dict:
    return VIP_NAMES.get(vip_level, VIP_NAMES[1])


async def update_user_vip(user_id: int, vip_level: int, days: int = 30):
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
    return await asyncio.to_thread(_sync_update)


async def check_achievement_vip(user_id: int, wins: int):
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


# ==================== ФОРМАТТЕРЫ ТЕКСТА (БЕЗОПАСНЫЕ) ====================

def format_vip_active(user: dict, balance: int, privileges: dict, until_date: str) -> str:
    """Формирует текст для активного VIP (использует HTML, безопасную конкатенацию)"""
    vip_level = user.get("vip_level", 0) or 0
    return (
        f"{privileges['icon']} <b>ВАШ VIP СТАТУС</b> {privileges['icon']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Уровень: <b>{privileges['name']}</b> (Уровень {vip_level})\n"
        f"💰 Баланс: <b>{balance}</b> NCoins\n"
        f"📅 Действует до: {until_date}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>✨ ВАШИ ПРЕИМУЩЕСТВА:</b>\n\n"
        f"├ 🎮 +{privileges['win_bonus']}% к выигрышам\n"
        f"├ 🎁 +{privileges['daily_bonus']} NCoins к бонусу\n"
        f"├ 👑 Статус в чате\n"
        f"├ 💎 Доступ к VIP-комнатам\n"
        f"└ ⭐ Приоритетная поддержка"
    )


def format_vip_catalog(balance: int, wins: int) -> str:
    """Формирует текст каталога VIP статусов"""
    return (
        "⭐ <b>VIP СТАТУСЫ NEXUS</b> ⭐\n\n"
        "Получите эксклюзивные преимущества!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Ваш баланс: {balance} NCoins</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🥉 <b>БРОНЗА</b> (1 уровень) — 500 NCoins\n├ 🎮 +5% к выигрышам\n└ 🎁 +50 NCoins к бонусу\n\n"
        "🥈 <b>СЕРЕБРО</b> (2 уровень) — 1,000 NCoins\n├ 🎮 +10% к выигрышам\n└ 🎁 +100 NCoins к бонусу\n\n"
        "🥇 <b>ЗОЛОТО</b> (3 уровень) — 2,000 NCoins\n├ 🎮 +15% к выигрышам\n└ 🎁 +150 NCoins к бонусу\n\n"
        "💎 <b>ПЛАТИНА</b> (4 уровень) — 5,000 NCoins\n├ 🎮 +20% к выигрышам\n└ 🎁 +200 NCoins к бонусу\n\n"
        "💠 <b>АЛМАЗ</b> (5 уровень) — 10,000 NCoins\n├ 🎮 +30% к выигрышам\n└ 🎁 +300 NCoins к бонусу\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 <b>БЕСПЛАТНЫЙ VIP:</b>\n├ 10 побед → Бронза\n├ 50 побед → Серебро\n├ 100 побед → Золото\n└ 200 побед → Платина\n\n"
        f"📊 <b>Ваши победы: {wins}</b>"
    )


def format_achievements(balance: int, wins: int, current_vip: int, awarded_vip: int = None) -> str:
    """Формирует текст прогресса достижений"""
    # Расчёт прогресса
    next_level, next_wins, progress = None, 0, 0
    if wins < 10:
        next_level, next_wins, progress = "🥉 Бронза", 10, int((wins / 10) * 100) if wins > 0 else 0
    elif wins < 50:
        next_level, next_wins, progress = "🥈 Серебро", 50, int(((wins - 10) / 40) * 100)
    elif wins < 100:
        next_level, next_wins, progress = "🥇 Золото", 100, int(((wins - 50) / 50) * 100)
    elif wins < 200:
        next_level, next_wins, progress = "💎 Платина", 200, int(((wins - 100) / 100) * 100)
    else:
        progress = 100
    
    # Прогресс-бар
    bar_length = 10
    filled = int(bar_length * progress / 100)
    progress_bar = "█" * filled + "░" * (bar_length - filled)
    
    # Статус достижения
    status_msg = ""
    if wins >= 200:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ ПЛАТИНЫ!</b>\n\n"
    elif wins >= 100:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ ЗОЛОТА!</b>\n\n"
    elif wins >= 50:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ СЕРЕБРА!</b>\n\n"
    elif wins >= 10:
        status_msg = "🎉 <b>ВЫ ДОСТИГЛИ БРОНЗЫ!</b>\n\n"
    
    if awarded_vip:
        status_msg += f"✨ <b>Только что получен VIP {awarded_vip} уровня!</b>\n\n"
    
    # Сообщение о прогрессе
    progress_msg = ""
    if next_level and wins < 200:
        progress_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📈 <b>ДО СЛЕДУЮЩЕГО УРОВНЯ:</b>\n\n"
            f"Цель: <b>{next_level}</b>\n"
            f"Прогресс: {wins}/{next_wins} побед\n"
            f"[{progress_bar}] {progress}%\n\n"
            f"💪 Осталось <b>{next_wins - wins}</b> побед!\n"
        )
    
    return (
        f"🏆 <b>БЕСПЛАТНЫЙ VIP ЗА ДОСТИЖЕНИЯ</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>ВАШ ПРОГРЕСС:</b>\n\n"
        f"💰 Баланс: <b>{balance} NCoins</b>\n"
        f"🏆 Побед: <b>{wins}</b>\n"
        f"⭐ Текущий VIP: <b>{current_vip} уровень</b>\n\n"
        f"{status_msg}{progress_msg}"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>ДОСТУПНЫЕ НАГРАДЫ:</b>\n\n"
        f"🥉 10 побед → Бронза VIP\n"
        f"🥈 50 побед → Серебро VIP\n"
        f"🥇 100 побед → Золото VIP\n"
        f"💎 200 побед → Платина VIP"
    )


# ==================== ХЕНДЛЕРЫ ====================

@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    user_id = message.from_user.id
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    
    # 🔥 ВСЕГДА свежий баланс
    balance = await db.get_balance(user_id)
    
    vip_level = user.get("vip_level", 0) or 0
    vip_until = user.get("vip_until", "")
    wins = user.get("wins", 0) or 0
    
    # Проверка достижений
    achievement_vip = await check_achievement_vip(user_id, wins)
    if achievement_vip:
        vip_level = achievement_vip
        user = await db.get_user(user_id)
        balance = await db.get_balance(user_id)  # 🔥 Обновляем баланс после изменений
    
    # Парсинг даты
    try:
        until_date = datetime.fromisoformat(vip_until).strftime("%d.%m.%Y") if vip_until else "Бессрочно"
    except Exception:
        until_date = "Бессрочно"
    
    # Формирование текста
    if vip_level > 0:
        privileges = get_vip_privileges(vip_level)
        text = format_vip_active(user, balance, privileges, until_date)
    else:
        text = format_vip_catalog(balance, wins)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 КУПИТЬ VIP", callback_data="buy_vip")],
        [InlineKeyboardButton(text="🏆 МОИ ДОСТИЖЕНИЯ", callback_data="vip_achievements")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data == "vip")
@router.callback_query(F.data == "vip_menu")
async def vip_callback(callback: types.CallbackQuery):
    await cmd_vip(callback.message)
    await callback.answer()


@router.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    
    balance = await db.get_balance(user_id)  # 🔥 Свежий баланс
    current_vip = user.get('vip_level', 0) or 0
    
    buttons = []
    for level, price in VIP_PRICES.items():
        name = VIP_NAMES[level]['name']
        if level <= current_vip:
            name = f"✅ {name} (куплен)"
        buttons.append([
            InlineKeyboardButton(text=f"{name} ({price} NCoins)", callback_data=f"buy_vip_{level}")
        ])
    buttons.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")])
    
    await callback.message.edit_text(
        f"💎 <b>ПОКУПКА VIP СТАТУСА</b>\n\n"
        f"💰 Ваш баланс: <b>{balance} NCoins</b>\n"
        f"⭐ Текущий VIP: <b>{current_vip} уровень</b>\n\n"
        f"Выберите уровень VIP:\n\n"
        f"💡 <i>Совет:</i> VIP действует 30 дней",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_vip_"))
async def buy_vip(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    level = int(callback.data.split("_")[2])
    price = VIP_PRICES.get(level, 500)
    
    user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    current_vip = user.get('vip_level', 0) or 0
    
    if level <= current_vip:
        await callback.answer(f"❌ У вас уже есть VIP {current_vip} уровня!", show_alert=True)
        return
    
    balance = await db.get_balance(user_id)  # 🔥 Проверка по свежему балансу
    if balance < price:
        await callback.answer(
            f"❌ Недостаточно средств!\nНужно: {price} NCoins\nБаланс: {balance} NCoins",
            show_alert=True
        )
        return
    
    try:
        await db.update_balance(user_id, -price, f"Покупка VIP уровня {level}")
        await update_user_vip(user_id, level, 30)
        
        new_balance = await db.get_balance(user_id)  # 🔥 Получаем баланс ПОСЛЕ обновления
        privileges = get_vip_privileges(level)
        
        await callback.message.edit_text(
            f"🎉 <b>ПОЗДРАВЛЯЕМ С ПОКУПКОЙ VIP!</b>\n\n"
            f"{privileges['icon']} Новый уровень: <b>{privileges['name']}</b>\n"
            f"💰 Списано: <b>{price} NCoins</b>\n"
            f"💎 Новый баланс: <b>{new_balance} NCoins</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>✨ НОВЫЕ ПРЕИМУЩЕСТВА:</b>\n"
            f"├ 🎮 +{privileges['win_bonus']}% к выигрышам\n"
            f"├ 🎁 +{privileges['daily_bonus']} NCoins к бонусу\n"
            f"├ 👑 Статус в чате\n"
            f"└ ⭐ Приоритетная поддержка\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 Статус действует <b>30 дней</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ПОНЯТНО", callback_data="vip")]
            ])
        )
        logger.info(f"User {user_id} purchased VIP level {level}")
        
    except Exception as e:
        logger.error(f"VIP purchase failed: {e}")
        await callback.answer("❌ Ошибка при покупке", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data == "vip_achievements")
async def vip_achievements(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    
    wins = user.get("wins", 0) or 0
    current_vip = user.get("vip_level", 0) or 0
    balance = await db.get_balance(user_id)  # 🔥 Свежий баланс
    
    awarded_vip = await check_achievement_vip(user_id, wins)
    if awarded_vip:
        balance = await db.get_balance(user_id)  # 🔥 Обновляем после выдачи достижения
    
    text = format_achievements(balance, wins, current_vip, awarded_vip)
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="vip")]
        ])
    )
    await callback.answer()

