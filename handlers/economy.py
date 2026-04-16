import asyncio
import logging
import sqlite3
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime
from aiogram.enums import ParseMode

from database import db
from utils.keyboards import back_button

router = Router()
logger = logging.getLogger(__name__)

# ⚠️ Импорт состояний анкеты
try:
    from handlers.profile import profile_states
except ImportError:
    profile_states = {}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_daily_bonus_amount(user_id: int, base_bonus: int = 100) -> int:
    """Получить ежедневный бонус с учётом VIP"""
    user = await db.get_user(user_id)
    if not user or user.get("vip_level", 0) == 0:
        return base_bonus
    
    vip_bonus = user.get("vip_level", 0) * 50
    return base_bonus + vip_bonus


async def _exec_sync(query: str, params: tuple = ()):
    """Выполнить синхронный SQL-запрос в отдельном потоке"""
    def _run():
        conn = sqlite3.connect(db.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.fetchall() if cursor.description else cursor.rowcount
        finally:
            conn.close()
    return await asyncio.to_thread(_run)


# ==================== КОМАНДА /balance ====================

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала используйте /start")
        return
    await message.answer(
        f"💰 Баланс: <b>{user['balance']} NCoin</b>\n\n"
        f"📊 Побед: {user['wins']} | Поражений: {user['losses']}",
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "balance")
async def balance_callback(callback: CallbackQuery):
    """Обработчик кнопки БАЛАНС из меню"""
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Сначала используйте /start", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"💰 <b>Ваш баланс:</b> {user['balance']} NCoin\n\n"
        f"📊 Побед: {user['wins']} | Поражений: {user['losses']}",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()


# ==================== КОМАНДА /daily ====================

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    user_id = message.from_user.id
    
    if user_id in profile_states:
        await message.answer("❌ Сначала завершите заполнение анкеты командой /cancel_profile")
        return
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Сначала используйте /start")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    
    if last_daily == today:
        await message.answer("⏰ Вы уже получали бонус сегодня! Возвращайтесь завтра.")
        return
    
    try:
        # Расчёт стрика и бонуса
        if last_daily and (datetime.now().date() - datetime.fromisoformat(last_daily).date()).days == 1:
            new_streak = user.get("daily_streak", 0) + 1
        else:
            new_streak = 1
        
        base_bonus = 100 + (new_streak * 50)
        bonus = await get_daily_bonus_amount(user_id, base_bonus)
        
        # Обновляем баланс и стрик атомарно
        await db.update_balance(user_id, bonus, f"Ежедневный бонус (стрик: {new_streak})")
        await _exec_sync(
            "UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
            (new_streak, today, user_id)
        )
        
        updated_user = await db.get_user(user_id)
        new_balance = updated_user["balance"] if updated_user else 0
        
        # Эмодзи для стрика
        if new_streak >= 30:
            streak_emoji = "🔥🔥🔥"
        elif new_streak >= 7:
            streak_emoji = "🔥🔥"
        elif new_streak >= 3:
            streak_emoji = "🔥"
        else:
            streak_emoji = "⭐"
        
        await message.answer(
            f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС!</b>\n\n"
            f"💰 Получено: <b>+{bonus} NCoin</b>\n"
            f"{streak_emoji} Стрик: <b>{new_streak}</b> дней\n"
            f"💎 Новый баланс: <b>{new_balance} NCoin</b>\n\n"
            f"📅 Завтра бонус будет <b>{100 + ((new_streak + 1) * 50)}</b> NCoin!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Daily bonus failed for {user_id}: {e}")
        await message.answer("❌ Произошла ошибка при начислении бонуса. Попробуйте позже.")


@router.callback_query(F.data == "daily")
async def daily_callback(callback: CallbackQuery):
    """Обработчик кнопки ежедневного бонуса (если добавите в меню)"""
    await cmd_daily(callback.message)
    await callback.answer()


# ==================== КОМАНДА /transfer ====================

@router.message(Command("transfer"))
async def cmd_transfer(message: Message):
    user_id = message.from_user.id
    
    if user_id in profile_states:
        await message.answer("❌ Сначала завершите заполнение анкеты командой /cancel_profile")
        return
    
    args = message.text.strip().split()
    if len(args) != 3:
        await message.answer(
            "❌ Использование: <code>/transfer @username 100</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    target_username = args[1].lstrip("@")
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть целым числом")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной")
        return
    
    sender = await db.get_user(user_id)
    if not sender:
        await message.answer("❌ Сначала используйте /start")
        return
    
    if sender["balance"] < amount:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {sender['balance']} NCoin")
        return
    
    # Атомарный перевод
    def _perform_transfer():
        conn = sqlite3.connect(db.db_path)
        conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE username = ?", (target_username,))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return False, "user_not_found"
            
            target_id = row[0]
            if target_id == user_id:
                conn.rollback()
                return False, "self_transfer"
            
            cursor.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                (amount, user_id, amount)
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False, "insufficient_balance"
            
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
            conn.commit()
            return True, target_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Transfer DB error: {e}")
            return False, "db_error"
        finally:
            conn.close()
    
    success, result = await asyncio.to_thread(_perform_transfer)
    
    if not success:
        messages = {
            "user_not_found": f"❌ Пользователь @{target_username} не найден в базе",
            "self_transfer": "❌ Нельзя перевести монеты самому себе",
            "insufficient_balance": "❌ Баланс изменился во время операции. Попробуйте снова",
            "db_error": "❌ Ошибка базы данных. Попробуйте позже"
        }
        await message.answer(messages.get(result, "❌ Ошибка перевода"))
        return
    
    updated_sender = await db.get_user(user_id)
    await message.answer(
        f"✅ <b>Перевод выполнен!</b>\n\n"
        f"📤 Отправлено: <b>{amount} NCoin</b>\n"
        f"📥 Получатель: @{target_username}\n"
        f"💰 Ваш новый баланс: <b>{updated_sender['balance']} NCoin</b>",
        parse_mode=ParseMode.HTML
    )


# ==================== КНОПКА ЭКОНОМИКИ ====================

@router.callback_query(F.data == "economy")
async def economy_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id in profile_states:
        await callback.answer("❌ Сначала завершите заполнение анкеты", show_alert=True)
        return
    
    user = await db.get_user(user_id)
    balance = user["balance"] if user else 0
    
    await callback.message.edit_text(
        f"💰 <b>ЭКОНОМИКА</b>\n\n"
        f"💎 Ваш баланс: <b>{balance} NCoin</b>\n\n"
        f"📌 <b>Доступные команды:</b>\n"
        f"├ /balance — проверить баланс\n"
        f"├ /daily — получить бонус (+100 NCoin)\n"
        f"└ /transfer @user 100 — перевести монеты\n\n"
        f"✨ <b>Совет:</b> Чем больше стрик — тем выше бонус!",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()
