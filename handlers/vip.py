"""
VIP-статус и платные функции
"""

import time
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.db import spend_balance, get_balance, add_paid_balance
from utils.helpers import delete_after_response

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

# Стоимость VIP в NCoin
VIP_PRICE = 500
VIP_DURATION_DAYS = 30

def get_vip_menu() -> InlineKeyboardMarkup:
    """Меню покупки VIP"""
    buttons = [
        [InlineKeyboardButton(text="👑 Купить VIP (500 NCoin)", callback_data="vip_buy")],
        [InlineKeyboardButton(text="❓ Что даёт VIP?", callback_data="vip_info")],
        [InlineKeyboardButton(text="🤖 Спросить AI", callback_data="vip_ai")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def is_vip_active(user_id: int, chat_id: int) -> bool:
    """Проверить, активен ли VIP"""
    from database.db import get_db
    with get_db() as conn:
        result = conn.execute(
            "SELECT is_vip, vip_until FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        
        if not result or not result["is_vip"]:
            return False
        
        if result["vip_until"] and time.time() > result["vip_until"]:
            # VIP истёк
            conn.execute(
                "UPDATE users SET is_vip = 0, vip_until = 0 WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            return False
        
        return True

def set_vip(user_id: int, chat_id: int, days: int = VIP_DURATION_DAYS):
    """Активировать VIP статус"""
    from database.db import get_db
    with get_db() as conn:
        vip_until = int(time.time()) + days * 86400
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_until = ? WHERE user_id = ? AND chat_id = ?",
            (vip_until, user_id, chat_id)
        )

def get_vip_remaining_days(user_id: int, chat_id: int) -> int:
    """Получить оставшиеся дни VIP"""
    from database.db import get_db
    with get_db() as conn:
        result = conn.execute(
            "SELECT vip_until FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()
        
        if not result or not result["vip_until"]:
            return 0
        
        remaining = max(0, (result["vip_until"] - time.time()) // 86400)
        return int(remaining)

@router.message(Command("vip"))
async def cmd_vip(message: Message):
    """Открыть меню VIP"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if is_vip_active(user_id, chat_id):
        days_left = get_vip_remaining_days(user_id, chat_id)
        await message.answer(
            f"👑 **Ваш VIP статус активен!**\n\n"
            f"⏳ Осталось дней: {days_left}\n\n"
            f"💎 **Преимущества VIP:**\n"
            f"• +25% к ежедневному бонусу\n"
            f"• Эксклюзивные подарки\n"
            f"• Цветное имя в чате\n"
            f"• Доступ к VIP-играм\n"
            f"• Приоритетная поддержка\n\n"
            f"🤖 Вопросы о VIP: /ask",
            reply_markup=get_vip_menu()
        )
    else:
        balance = get_balance(user_id, chat_id)
        await message.answer(
            f"👑 **VIP-статус NEXUS**\n\n"
            f"💰 Цена: {VIP_PRICE} NCoin\n"
            f"⏱ Длительность: {VIP_DURATION_DAYS} дней\n\n"
            f"💎 **Что даёт VIP:**\n"
            f"• +25% к ежедневному бонусу\n"
            f"• Эксклюзивные подарки\n"
            f"• Цветное имя в чате\n"
            f"• Доступ к VIP-играм\n"
            f"• Приоритетная поддержка\n\n"
            f"💰 Ваш баланс: {balance} NCoin\n\n"
            f"🤖 Вопросы о VIP: /ask",
            reply_markup=get_vip_menu()
        )

@router.callback_query(lambda c: c.data == "vip_buy")
async def vip_buy(callback: CallbackQuery):
    """Покупка VIP статуса"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    if balance < VIP_PRICE:
        await callback.message.edit_text(
            f"❌ **Недостаточно NCoin!**\n\n"
            f"💰 Ваш баланс: {balance} NCoin\n"
            f"👑 Стоимость VIP: {VIP_PRICE} NCoin\n\n"
            f"💡 Получите бонус: /daily\n"
            f"⭐ Пополните баланс: /buy",
            reply_markup=get_vip_menu()
        )
        await callback.answer()
        return
    
    # Списываем NCoin
    if spend_balance(user_id, chat_id, VIP_PRICE):
        set_vip(user_id, chat_id)
        
        await callback.message.edit_text(
            f"✅ **Поздравляем! Вы приобрели VIP-статус!**\n\n"
            f"👑 Действует {VIP_DURATION_DAYS} дней\n\n"
            f"💎 **Теперь вам доступно:**\n"
            f"• +25% к ежедневному бонусу\n"
            f"• Эксклюзивные подарки\n"
            f"• Цветное имя в чате\n"
            f"• Доступ к VIP-играм\n"
            f"• Приоритетная поддержка\n\n"
            f"🤖 Вопросы о VIP: /ask",
            reply_markup=get_vip_menu()
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка при покупке VIP. Попробуйте позже.",
            reply_markup=get_vip_menu()
        )
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "vip_info")
async def vip_info(callback: CallbackQuery):
    """Информация о VIP"""
    await callback.message.edit_text(
        "👑 **VIP-статус NEXUS**\n\n"
        "💎 **Преимущества:**\n"
        "• 🎁 +25% к ежедневному бонусу\n"
        "• 🎁 Эксклюзивные подарки в магазине\n"
        "• 🎨 Цветное имя в сообщениях бота\n"
        "• 🎮 Доступ к VIP-играм с большими выигрышами\n"
        "• 💬 Приоритетная поддержка (ответ в течение часа)\n"
        "• 🏆 Особые достижения\n\n"
        f"💰 Стоимость: {VIP_PRICE} NCoin\n"
        f"⏱ Длительность: {VIP_DURATION_DAYS} дней\n\n"
        "💡 NCoin можно получить:\n"
        "• Бесплатно: /daily\n"
        "• Покупка: /buy\n\n"
        "🤖 Вопросы о VIP: /ask",
        reply_markup=get_vip_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "vip_ai")
async def vip_ai(callback: CallbackQuery):
    """Спросить AI о VIP"""
    await callback.message.edit_text(
        "🤖 **Спросите AI о VIP**\n\n"
        "Напишите свой вопрос в чат, используя:\n"
        "/ask Вопрос о VIP\n\n"
        "Например:\n"
        "• /ask как получить VIP?\n"
        "• /ask какие преимущества у VIP?\n"
        "• /ask стоит ли покупать VIP?\n\n"
        "Или используйте /ai для диалога.",
        reply_markup=get_vip_menu()
    )
    await callback.answer()
