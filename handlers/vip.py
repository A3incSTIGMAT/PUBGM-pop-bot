from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import VIP_PRICE

router = Router()

@router.message(Command("vip"))
async def cmd_vip(message: types.Message):
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ Используйте /start")
        return
    
    if user.get("vip_level", 0) > 0:
        await message.answer(
            f"⭐ *Ваш VIP статус*\n\n"
            f"Уровень: {user['vip_level']}\n"
            f"Действует до: {user['vip_until']}",
            parse_mode="Markdown"
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить VIP", callback_data="buy_vip")]
        ])
        await message.answer(
            f"⭐ *VIP статус*\n\n"
            f"💰 Цена: {VIP_PRICE} монет за 30 дней",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@router.callback_query(lambda c: c.data == "buy_vip")
async def buy_vip(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    if user["balance"] < VIP_PRICE:
        await callback.answer(f"❌ Не хватает! Нужно {VIP_PRICE} монет", show_alert=True)
        return
    
    await db.update_balance(user_id, -VIP_PRICE, "Покупка VIP")
    
    from datetime import datetime, timedelta
    new_until = (datetime.now() + timedelta(days=30)).isoformat()
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET vip_level = 1, vip_until = ? WHERE user_id = ?", (new_until, user_id))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ VIP куплен! Действует до {new_until[:10]}")
    await callback.answer()
