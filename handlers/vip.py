from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()


@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    wins = user.get("wins", 0)
    current_vip = user.get("vip_level", 0)
    vip_until = user.get("vip_until", "")
    
    # Определяем следующий уровень
    next_level_wins = 0
    if current_vip == 0:
        next_level_wins = 10
    elif current_vip == 1:
        next_level_wins = 50
    elif current_vip == 2:
        next_level_wins = 100
    
    text = f"""
⭐ *VIP СТАТУС* — БЕСПЛАТНО!

━━━━━━━━━━━━━━━━━━━━━

*Ваш уровень:* {current_vip} / 3
*Побед:* {wins}
*Действует до:* {vip_until[:10] if vip_until else 'Не активирован'}

━━━━━━━━━━━━━━━━━━━━━

*Как получить VIP:*
├ 10 побед → ⭐ Уровень 1
├ 50 побед → ⭐⭐ Уровень 2
└ 100 побед → ⭐⭐⭐ Уровень 3

*До следующего уровня:* {next_level_wins - wins if next_level_wins > wins else 'Максимальный!'} побед

━━━━━━━━━━━━━━━━━━━━━

*Преимущества VIP:*
├ +20% к выигрышам в играх
├ +100 монет к /daily
└ Эксклюзивный статус в профиле
"""
    
    if current_vip == 0:
        text += "\n🔥 *Начните играть, чтобы получить VIP бесплатно!*"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)
