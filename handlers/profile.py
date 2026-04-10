from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден! Используйте /start для регистрации")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Моя анкета", callback_data="view_my_profile")],
        [InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    profile_text = f"""
👤 <b>Профиль пользователя</b>

━━━━━━━━━━━━━━━━━━━━━
📛 <b>Имя:</b> {user.get('first_name', 'Не указано')}
🆔 <b>ID:</b> {user_id}
📅 <b>Регистрация:</b> {user.get('register_date', 'Неизвестно')[:10]}
━━━━━━━━━━━━━━━━━━━━━

💰 <b>Баланс:</b> {user.get('balance', 0)} монет

⭐ <b>VIP статус:</b> {'✅ Активирован' if user.get('vip_level', 0) > 0 else '❌ Нет'}

🏆 <b>Статистика:</b>
├ Побед: {user.get('wins', 0)}
├ Поражений: {user.get('losses', 0)}
└ Всего игр: {user.get('wins', 0) + user.get('losses', 0)}

━━━━━━━━━━━━━━━━━━━━━
<i>Нажмите на кнопку ниже, чтобы заполнить анкету</i>
"""
    await message.answer(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
