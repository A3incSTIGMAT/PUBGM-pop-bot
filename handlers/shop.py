from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import VIP_PRICE

router = Router()

@router.message(Command("shop"))
async def cmd_shop(message: types.Message):
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, description FROM shop_items")
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await message.answer("🛒 Магазин временно пуст!")
        return
    
    text = "🛒 *Магазин NEXUS*\n\n"
    keyboard = []
    
    for item in items:
        text += f"📦 {item[1]}\n💰 {item[2]} монет\n📝 {item[3]}\n\n"
        keyboard.append([InlineKeyboardButton(f"Купить {item[1]}", callback_data=f"buy_{item[0]}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(lambda c: c.data and c.data.startswith("buy_"))
async def buy_item(callback: types.CallbackQuery):
    item_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, price FROM shop_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    
    if not item:
        await callback.answer("❌ Товар не найден!", show_alert=True)
        return
    
    name, price = item
    
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Используйте /start", show_alert=True)
        return
    
    if user["balance"] < price:
        await callback.answer(f"❌ Не хватает! Нужно {price} монет", show_alert=True)
        return
    
    await db.update_balance(user_id, -price, f"Покупка: {name}")
    
    if "VIP" in name:
        from datetime import datetime, timedelta
        new_until = (datetime.now() + timedelta(days=30)).isoformat()
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET vip_level = 1, vip_until = ? WHERE user_id = ?", (new_until, user_id))
        conn.commit()
        conn.close()
        await callback.message.edit_text(f"✅ Куплено {name}!\n⭐ VIP до {new_until[:10]}")
    elif "Случайный" in name:
        import random
        bonus = random.randint(100, 1000)
        await db.update_balance(user_id, bonus, "Случайный подарок")
        await callback.message.edit_text(f"🎁 Куплено {name}!\n✨ Выпало +{bonus} монет!")
    else:
        await callback.message.edit_text(f"✅ Куплено {name}!\n💰 Списано {price} монет")
    
    await callback.answer()
