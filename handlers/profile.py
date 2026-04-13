import asyncio
import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from database import db
from utils.keyboards import main_menu

router = Router()
logger = logging.getLogger(__name__)

# ⚠️ В продакшене замените на aiogram.fsm (SQLiteStorage/RedisStorage)
profile_states = {}

def _generate_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 МОЯ АНКЕТА", callback_data="view_profile"),
         InlineKeyboardButton(text="📝 ЗАПОЛНИТЬ АНКЕТУ", callback_data="fill_profile")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])

def _format_profile_text(user: dict, user_id: int) -> str:
    reg_date = (user.get("register_date") or "Неизвестно")[:10]
    vip = "✅ АКТИВИРОВАН" if (user.get("vip_level") or 0) > 0 else "❌ НЕТ"
    wins = user.get("wins", 0)
    losses = user.get("losses", 0)
    streak = user.get("daily_streak", 0)
    
    return f"""
👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>

━━━━━━━━━━━━━━━━━━━━━
📛 Имя: {user.get("first_name", "Не указано")}
🆔 ID: {user_id}
📅 Регистрация: {reg_date}
━━━━━━━━━━━━━━━━━━━━━

💰 Баланс: {user.get("balance", 0)} NCoins

⭐ VIP статус: {vip}

🏆 СТАТИСТИКА:
├ Побед: {wins}
├ Поражений: {losses}
└ Всего игр: {wins + losses}

🔥 Стрик: {streak} дней

━━━━━━━━━━━━━━━━━━━━━
"""

async def _exec_db_sync(query: str, params: tuple = ()):
    """Безопасный вызов синхронной БД в асинхронном потоке"""
    def _run():
        conn = db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            conn.commit()
            return cur.fetchall() if cur.description else None
        finally:
            conn.close()
    return await asyncio.to_thread(_run)


@router.message(Command("profile"))
@router.callback_query(lambda c: c.data == "profile")
async def handle_profile(message_or_cb: types.Message | types.CallbackQuery):
    user_id = message_or_cb.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        response = "❌ Используйте /start для регистрации"
        kb = main_menu()
        if isinstance(message_or_cb, types.CallbackQuery):
            await message_or_cb.message.edit_text(response, reply_markup=kb)
            await message_or_cb.answer()
        else:
            await message_or_cb.answer(response, reply_markup=kb)
        return

    text = _format_profile_text(user, user_id)
    kb = _generate_profile_keyboard()
    
    if isinstance(message_or_cb, types.CallbackQuery):
        await message_or_cb.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        await message_or_cb.answer()
    else:
        await message_or_cb.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(lambda c: c.data == "view_profile")
async def view_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        rows = await _exec_db_sync(
            "SELECT full_name, age, city, timezone, about, created_at FROM user_profiles WHERE user_id = ?", 
            (user_id,)
        )
    except Exception as e:
        logger.error(f"DB error in view_profile: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    if not rows:
        await callback.message.edit_text(
            "❌ <b>АНКЕТА НЕ НАЙДЕНА!</b>\n\nНажмите 'ЗАПОЛНИТЬ АНКЕТУ', чтобы создать её.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 ЗАПОЛНИТЬ", callback_data="fill_profile")],
                [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="profile")]
            ])
        )
        await callback.answer()
        return

    row = rows[0]
    created = (row[5] or "Неизвестно")[:10]
    
    await callback.message.edit_text(
        f"👤 <b>ВАША АНКЕТА</b>\n\n"
        f"📛 Имя: {row[0]}\n"
        f"📅 Возраст: {row[1]}\n"
        f"🏙️ Город: {row[2]}\n"
        f"🕐 Часовой пояс: {row[3]}\n"
        f"📝 О себе: {row[4]}\n\n"
        f"📅 Создана: {created}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ РЕДАКТИРОВАТЬ", callback_data="fill_profile")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="profile")]
        ])
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "fill_profile")
async def fill_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    profile_states[user_id] = {"step": 1}
    
    await callback.message.answer(
        "📝 <b>СОЗДАНИЕ АНКЕТЫ</b>\n\n"
        "<b>Шаг 1 из 5:</b> Введите ваше имя\n\n"
        "Пример: <code>Александр</code>\n\n"
        "❌ Отмена: /cancel_profile",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.message(Command("cancel_profile"))
async def cancel_profile(message: types.Message):
    user_id = message.from_user.id
    profile_states.pop(user_id, None)
    await message.answer("❌ Заполнение анкеты отменено.")


# ⚠️ ВАЖНО: этот хендлер должен быть ПОСЛЕДНИМ в файле/роутере
@router.message()
async def process_profile_step(message: types.Message):
    user_id = message.from_user.id
    
    # Игнорируем не-текст и команды
    if not message.text or message.text.startswith("/"):
        return
        
    if user_id not in profile_states:
        return

    state = profile_states[user_id]
    step = state.get("step", 1)

    if step == 1:
        state["full_name"] = message.text.strip()
        state["step"] = 2
        await message.answer("📝 <b>Шаг 2 из 5</b>\n\nВведите ваш возраст (число):\n\nПример: <code>25</code>", parse_mode=ParseMode.HTML)

    elif step == 2:
        try:
            age = int(message.text.strip())
            if not (1 <= age <= 150):
                raise ValueError
            state["age"] = age
            state["step"] = 3
            await message.answer("📝 <b>Шаг 3 из 5</b>\n\nВведите ваш город:\n\nПример: <code>Москва</code>", parse_mode=ParseMode.HTML)
        except ValueError:
            await message.answer("❌ Введите корректный возраст (число от 1 до 150)")

    elif step == 3:
        state["city"] = message.text.strip()
        state["step"] = 4
        await message.answer("📝 <b>Шаг 4 из 5</b>\n\nВведите ваш часовой пояс (UTC):\n\nПример: <code>UTC+3</code> или <code>+3</code>", parse_mode=ParseMode.HTML)

    elif step == 4:
        state["timezone"] = message.text.strip()
        state["step"] = 5
        await message.answer("📝 <b>Шаг 5 из 5</b>\n\nРасскажите немного о себе:\n\nПример: <code>Люблю игры и программирование</code>", parse_mode=ParseMode.HTML)

    elif step == 5:
        state["about"] = message.text.strip()
        try:
            await _exec_db_sync(
                """INSERT OR REPLACE INTO user_profiles 
                   (user_id, full_name, age, city, timezone, about, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 
                           COALESCE((SELECT created_at FROM user_profiles WHERE user_id = ?), ?), ?)""",
                (user_id, state["full_name"], state["age"], state["city"], 
                 state["timezone"], state["about"], user_id, datetime.now().isoformat(), datetime.now().isoformat())
            )
            await message.answer(
                "✅ <b>АНКЕТА СОХРАНЕНА!</b>\n\n"
                f"📛 Имя: {state['full_name']}\n"
                f"📅 Возраст: {state['age']}\n"
                f"🏙️ Город: {state['city']}\n"
                f"🕐 Часовой пояс: {state['timezone']}\n"
                f"📝 О себе: {state['about']}\n\n"
                "Используйте /profile для просмотра анкеты",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to save profile for {user_id}: {e}")
            await message.answer("❌ Произошла ошибка при сохранении. Попробуйте позже.")
        finally:
            del profile_states[user_id]

