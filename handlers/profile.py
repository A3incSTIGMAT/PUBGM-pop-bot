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
        [InlineKeyboardButton(text="👤 Моя анкета", callback_data="view_profile"),
         InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")]
    ])
    
    profile_text = f"""
👤 *Профиль пользователя*

━━━━━━━━━━━━━━━━━━━━━
📛 Имя: {user.get('first_name', 'Не указано')}
🆔 ID: {user_id}
📅 Регистрация: {user.get('register_date', 'Неизвестно')[:10]}
━━━━━━━━━━━━━━━━━━━━━

💰 Баланс: {user.get('balance', 0)} NCoins

⭐ VIP статус: {'✅ Активирован' if user.get('vip_level', 0) > 0 else '❌ Нет'}

🏆 Статистика:
├ Побед: {user.get('wins', 0)}
├ Поражений: {user.get('losses', 0)}
└ Всего игр: {user.get('wins', 0) + user.get('losses', 0)}

🔥 Стрик: {user.get('daily_streak', 0)} дней

━━━━━━━━━━━━━━━━━━━━━
"""
    await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    await cmd_profile(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "view_profile")
async def view_profile(callback: types.CallbackQuery):
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, age, city, timezone, about FROM user_profiles WHERE user_id = ?", 
                   (callback.from_user.id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await callback.message.edit_text(
            "❌ Анкета не найдена!\n\nИспользуйте /setprofile для создания",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"👤 *Ваша анкета*\n\n"
        f"📛 Имя: {row[0]}\n"
        f"📅 Возраст: {row[1]}\n"
        f"🏙️ Город: {row[2]}\n"
        f"🕐 Часовой пояс: {row[3]}\n"
        f"📝 О себе: {row[4]}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
        ])
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "fill_profile")
async def fill_profile(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📝 *Создание анкеты*\n\n"
        "Используйте команду `/setprofile` в чате.\n\n"
        "Бот задаст 5 вопросов для создания анкеты.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
        ])
    )
    await callback.answer()
