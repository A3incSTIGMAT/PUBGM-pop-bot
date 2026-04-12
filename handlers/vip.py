from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from utils.keyboards import back_button

router = Router()


@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    wins = user.get('wins', 0)
    vip_level = user.get('vip_level', 0)
    vip_until = user.get('vip_until', '')
    
    # Определяем следующий уровень
    if wins >= 100:
        next_level = "МАКСИМАЛЬНЫЙ ✅"
        needed = 0
    elif wins >= 50:
        next_level = "⭐ УРОВЕНЬ 3 (100 побед)"
        needed = 100 - wins
    elif wins >= 10:
        next_level = "⭐⭐ УРОВЕНЬ 2 (50 побед)"
        needed = 50 - wins
    else:
        next_level = "⭐ УРОВЕНЬ 1 (10 побед)"
        needed = 10 - wins
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 МОИ ДОСТИЖЕНИЯ", callback_data="achievements")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    text = f"""
⭐ *VIP СТАТУС*

━━━━━━━━━━━━━━━━━━━━━

📊 *ВАШ VIP УРОВЕНЬ:* {vip_level if vip_level > 0 else 'НЕТ'}

{f'📅 ДЕЙСТВУЕТ ДО: {vip_until[:10]}' if vip_level > 0 else ''}

━━━━━━━━━━━━━━━━━━━━━

*🏆 ПОЛУЧИТЕ VIP БЕСПЛАТНО!*

VIP даётся за победы в играх:

├ 10 побед → ⭐ УРОВЕНЬ 1
├ 50 побед → ⭐⭐ УРОВЕНЬ 2
├ 100 побед → ⭐⭐⭐ УРОВЕНЬ 3

━━━━━━━━━━━━━━━━━━━━━

*📊 ВАШ ПРОГРЕСС:*

🏆 Побед: {wins}
🎯 До следующего уровня: {needed} побед

━━━━━━━━━━━━━━━━━━━━━

*✨ ПРЕИМУЩЕСТВА VIP:*

├ +20% к выигрышам в играх
├ +100 NCoins к ежедневному бонусу
├ Эксклюзивные команды
└ Отдельный статус в профиле
"""
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "vip")
async def vip_callback(callback: types.CallbackQuery):
    await cmd_vip(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "achievements")
async def achievements(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    wins = user.get('wins', 0)
    losses = user.get('losses', 0)
    streak = user.get('daily_streak', 0)
    vip_level = user.get('vip_level', 0)
    
    text = f"""
🏆 *ВАШИ ДОСТИЖЕНИЯ*

━━━━━━━━━━━━━━━━━━━━━

⚔️ *ПОБЕДЫ:* {wins}
💀 *ПОРАЖЕНИЯ:* {losses}
📊 *ВСЕГО ИГР:* {wins + losses}
🔥 *СТРИК:* {streak} дней

━━━━━━━━━━━━━━━━━━━━━

⭐ *VIP СТАТУС:* {vip_level if vip_level > 0 else 'НЕТ'}

*КАК ПОВЫСИТЬ VIP:*
├ 10 побед → ⭐ Уровень 1
├ 50 побед → ⭐⭐ Уровень 2
└ 100 побед → ⭐⭐⭐ Уровень 3

━━━━━━━━━━━━━━━━━━━━━

💪 *ПРОДОЛЖАЙТЕ ИГРАТЬ!*
"""
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_button())
    await callback.answer()
