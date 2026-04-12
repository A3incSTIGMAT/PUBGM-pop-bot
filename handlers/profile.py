from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from database import db
from utils.keyboards import main_menu

router = Router()

# Хранилище состояний для анкеты
profile_states = {}


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


@router.callback_query(lambda c: c.data == "view_profile")
async def view_profile(callback: types.CallbackQuery):
    """Просмотр анкеты"""
    user_id = callback.from_user.id
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, age, city, timezone, about, created_at FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await callback.message.edit_text(
            "❌ *АНКЕТА НЕ НАЙДЕНА!*\n\n"
            "Нажмите 'ЗАПОЛНИТЬ АНКЕТУ', чтобы создать её.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 ЗАПОЛНИТЬ", callback_data="fill_profile")],
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="profile")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"👤 *ВАША АНКЕТА*\n\n"
        f"📛 Имя: {row[0]}\n"
        f"📅 Возраст: {row[1]}\n"
        f"🏙️ Город: {row[2]}\n"
        f"🕐 Часовой пояс: {row[3]}\n"
        f"📝 О себе: {row[4]}\n\n"
        f"📅 Создана: {row[5][:10] if row[5] else 'Неизвестно'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ РЕДАКТИРОВАТЬ", callback_data="fill_profile")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="profile")]
        ])
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "fill_profile")
async def fill_profile(callback: types.CallbackQuery):
    """Начать заполнение анкеты"""
    user_id = callback.from_user.id
    profile_states[user_id] = {'step': 1}
    
    await callback.message.edit_text(
        "📝 *СОЗДАНИЕ АНКЕТЫ*\n\n"
        "*Шаг 1 из 5:* Введите ваше имя\n\n"
        "Пример: `Александр`\n\n"
        "❌ Отмена: /cancel_profile",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@router.message(Command("cancel_profile"))
async def cancel_profile(message: types.Message):
    """Отмена заполнения анкеты"""
    user_id = message.from_user.id
    if user_id in profile_states:
        del profile_states[user_id]
    await message.answer("❌ Заполнение анкеты отменено.")


@router.message(lambda message: message.from_user.id in profile_states)
async def process_profile_step(message: types.Message):
    """Обработка шагов анкеты"""
    user_id = message.from_user.id
    state = profile_states[user_id]
    step = state['step']
    
    if step == 1:
        state['full_name'] = message.text
        state['step'] = 2
        await message.answer(
            "📝 *Шаг 2 из 5*\n\n"
            "Введите ваш возраст (число):\n\n"
            "Пример: `25`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 2:
        try:
            age = int(message.text)
            if age < 1 or age > 150:
                raise ValueError
            state['age'] = age
            state['step'] = 3
            await message.answer(
                "📝 *Шаг 3 из 5*\n\n"
                "Введите ваш город:\n\n"
                "Пример: `Москва`",
                parse_mode=ParseMode.MARKDOWN
            )
        except ValueError:
            await message.answer("❌ Введите корректный возраст (число от 1 до 150)")
    
    elif step == 3:
        state['city'] = message.text
        state['step'] = 4
        await message.answer(
            "📝 *Шаг 4 из 5*\n\n"
            "Введите ваш часовой пояс (UTC):\n\n"
            "Пример: `UTC+3` или `+3`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 4:
        state['timezone'] = message.text
        state['step'] = 5
        await message.answer(
            "📝 *Шаг 5 из 5*\n\n"
            "Расскажите немного о себе:\n\n"
            "Пример: `Люблю игры и программирование`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif step == 5:
        state['about'] = message.text
        
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_profiles 
            (user_id, full_name, age, city, timezone, about, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM user_profiles WHERE user_id = ?), ?), ?)
        """, (
            user_id, state['full_name'], state['age'], state['city'], 
            state['timezone'], state['about'], user_id, datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        
        await message.answer(
            "✅ *АНКЕТА СОХРАНЕНА!*\n\n"
            f"📛 Имя: {state['full_name']}\n"
            f"📅 Возраст: {state['age']}\n"
            f"🏙️ Город: {state['city']}\n"
            f"🕐 Часовой пояс: {state['timezone']}\n"
            f"📝 О себе: {state['about']}\n\n"
            "Используйте /profile для просмотра анкеты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        del profile_states[user_id]
