from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from utils.keyboards import main_menu

router = Router()


@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Используйте /start для регистрации")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 МОЯ АНКЕТА", callback_data="view_profile"),
         InlineKeyboardButton(text="📝 ЗАПОЛНИТЬ АНКЕТУ", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    profile_text = f"""
👤 *ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ*

━━━━━━━━━━━━━━━━━━━━━
📛 Имя: {user.get('first_name', 'Не указано')}
🆔 ID: {user_id}
📅 Регистрация: {user.get('register_date', 'Неизвестно')[:10]}
━━━━━━━━━━━━━━━━━━━━━

💰 Баланс: {user.get('balance', 0)} NCoins

⭐ VIP статус: {'✅ АКТИВИРОВАН' if user.get('vip_level', 0) > 0 else '❌ НЕТ'}

🏆 СТАТИСТИКА:
├ Побед: {user.get('wins', 0)}
├ Поражений: {user.get('losses', 0)}
└ Всего игр: {user.get('wins', 0) + user.get('losses', 0)}

🔥 Стрик: {user.get('daily_streak', 0)} дней

━━━━━━━━━━━━━━━━━━━━━
"""
    await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    """Обработчик кнопки ПРОФИЛЬ из меню"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.message.edit_text(
            "❌ Вы не зарегистрированы!\n\nНажмите /start для регистрации",
            reply_markup=main_menu()
        )
        await callback.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 МОЯ АНКЕТА", callback_data="view_profile"),
         InlineKeyboardButton(text="📝 ЗАПОЛНИТЬ АНКЕТУ", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    profile_text = f"""
👤 *ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ*

━━━━━━━━━━━━━━━━━━━━━
📛 Имя: {user.get('first_name', 'Не указано')}
🆔 ID: {user_id}
📅 Регистрация: {user.get('register_date', 'Неизвестно')[:10]}
━━━━━━━━━━━━━━━━━━━━━

💰 Баланс: {user.get('balance', 0)} NCoins

⭐ VIP статус: {'✅ АКТИВИРОВАН' if user.get('vip_level', 0) > 0 else '❌ НЕТ'}

🏆 СТАТИСТИКА:
├ Побед: {user.get('wins', 0)}
├ Поражений: {user.get('losses', 0)}
└ Всего игр: {user.get('wins', 0) + user.get('losses', 0)}

🔥 Стрик: {user.get('daily_streak', 0)} дней

━━━━━━━━━━━━━━━━━━━━━
"""
    await callback.message.edit_text(profile_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()
