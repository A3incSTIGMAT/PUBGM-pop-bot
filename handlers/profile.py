from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db

router = Router()


def get_main_menu():
    """Главное меню (для возврата)"""
    from utils.keyboards import main_menu
    return main_menu()


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
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main_menu")]
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


@router.callback_query(lambda c: c.data == "back_to_main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    from utils.keyboards import main_menu
    await callback.message.edit_text(
        "🏠 <b>Главное меню NEXUS Bot</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "view_my_profile")
async def view_my_profile(callback: types.CallbackQuery):
    """Просмотр своей анкеты"""
    from handlers.chat_manager import ensure_tables
    
    await ensure_tables()
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (callback.from_user.id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await callback.message.edit_text(
            "❌ Анкета не найдена!\n\nИспользуйте /setprofile для создания анкеты",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="back_to_profile")]
            ])
        )
        await callback.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")],
        [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="back_to_profile")]
    ])
    
    await callback.message.edit_text(
        f"👤 <b>Ваша анкета</b>\n\n"
        f"📛 Имя: {row[1]}\n"
        f"📅 Возраст: {row[2]}\n"
        f"🏙️ Город: {row[3]}\n"
        f"🕐 Часовой пояс: {row[4]}\n"
        f"📝 О себе: {row[5]}\n\n"
        f"📅 Создана: {row[6][:10] if row[6] else 'Неизвестно'}",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "fill_profile")
async def fill_profile(callback: types.CallbackQuery):
    """Заполнить анкету"""
    await callback.message.edit_text(
        "📝 <b>Создание анкеты</b>\n\n"
        "Используйте команду в чате:\n"
        "<code>/setprofile</code>\n\n"
        "Бот задаст вам 5 вопросов.\n\n"
        "❌ Для отмены: /cancel_profile",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="back_to_profile")]
        ])
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile(callback: types.CallbackQuery):
    """Редактировать анкету"""
    await callback.message.edit_text(
        "✏️ <b>Редактирование анкеты</b>\n\n"
        "Используйте команду <code>/setprofile</code>\n"
        "Это создаст новую анкету (старая будет заменена).",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К моей анкете", callback_data="view_my_profile")]
        ])
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile(callback: types.CallbackQuery):
    """Вернуться в профиль"""
    await cmd_profile(callback.message)
    await callback.answer()
