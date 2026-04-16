import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime
from aiogram.enums import ParseMode

from database import db
from config import START_BALANCE
from utils.keyboards import back_button, finance_category_menu

router = Router()
logger = logging.getLogger(__name__)

# ⚠️ Импорт состояний анкеты
try:
    from handlers.profile import profile_states
except ImportError:
    profile_states = {}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Получить пользователя или создать если не существует"""
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Auto-registered user {user_id} in economy module")
    return user


async def get_daily_bonus_amount(user_id: int, base_bonus: int = 100) -> int:
    """Получить ежедневный бонус с учётом VIP"""
    user = await db.get_user(user_id)
    if not user or user.get("vip_level", 0) == 0:
        return base_bonus
    
    vip_bonus = user.get("vip_level", 0) * 50
    return base_bonus + vip_bonus


# ==================== КОМАНДА /balance ====================

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    await message.answer(
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{user['balance']}</b> NCoin\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ Побед: {user['wins']}\n"
        f"└ Поражений: {user['losses']}",
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "balance")
async def balance_callback(callback: CallbackQuery):
    """Обработчик кнопки БАЛАНС из меню"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    await callback.message.edit_text(
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{user['balance']}</b> NCoin\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ Побед: {user['wins']}\n"
        f"└ Поражений: {user['losses']}\n\n"
        f"💡 <i>Используйте /daily для получения бонуса!</i>",
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
    
    # Авторегистрация если нужно
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    
    if last_daily == today:
        await message.answer(
            "⏰ <b>БОНУС УЖЕ ПОЛУЧЕН!</b>\n\n"
            f"Вы уже получали бонус сегодня.\n"
            f"Возвращайтесь завтра за новым бонусом!\n\n"
            f"🔥 Текущий стрик: <b>{user.get('daily_streak', 0)}</b> дней",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        # Расчёт стрика и бонуса
        if last_daily:
            try:
                last_date = datetime.fromisoformat(last_daily).date()
                days_diff = (datetime.now().date() - last_date).days
                if days_diff == 1:
                    new_streak = user.get("daily_streak", 0) + 1
                else:
                    new_streak = 1
            except:
                new_streak = 1
        else:
            new_streak = 1
        
        base_bonus = 100 + (new_streak * 50)
        bonus = await get_daily_bonus_amount(user_id, base_bonus)
        
        # Атомарное обновление через database.py
        await db.update_balance(user_id, bonus, f"Ежедневный бонус (стрик: {new_streak})")
        await db.update_daily_streak(user_id, new_streak)
        
        updated_user = await db.get_user(user_id)
        new_balance = updated_user["balance"] if updated_user else user['balance'] + bonus
        
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
            f"📅 Завтра бонус будет <b>{100 + ((new_streak + 1) * 50)}</b> NCoin!\n\n"
            f"💡 <i>Продолжайте заходить каждый день для увеличения бонуса!</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Daily bonus failed for {user_id}: {e}")
        await message.answer("❌ Произошла ошибка при начислении бонуса. Попробуйте позже.")


@router.callback_query(F.data == "daily")
async def daily_callback(callback: CallbackQuery):
    """Обработчик кнопки ежедневного бонуса"""
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
            "❌ <b>Неверный формат!</b>\n\n"
            "Использование: <code>/transfer @username 100</code>\n\n"
            "Пример: <code>/transfer @user 500</code>",
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
    
    if amount < 10:
        await message.answer("❌ Минимальная сумма перевода: 10 NCoin")
        return
    
    # Авторегистрация отправителя
    sender = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    if sender["balance"] < amount:
        await message.answer(
            f"❌ <b>Недостаточно средств!</b>\n\n"
            f"Ваш баланс: <b>{sender['balance']}</b> NCoin\n"
            f"Не хватает: <b>{amount - sender['balance']}</b> NCoin",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        # Используем новый атомарный метод из database.py
        success = await db.transfer_coins(user_id, target_username, amount, "transfer")
        
        if not success:
            await message.answer(
                f"❌ <b>Пользователь @{target_username} не найден!</b>\n\n"
                f"Убедитесь, что пользователь активировал бота командой /start",
                parse_mode=ParseMode.HTML
            )
            return
        
        updated_sender = await db.get_user(user_id)
        
        await message.answer(
            f"✅ <b>ПЕРЕВОД ВЫПОЛНЕН!</b>\n\n"
            f"📤 Отправлено: <b>{amount} NCoin</b>\n"
            f"📥 Получатель: @{target_username}\n"
            f"💰 Ваш новый баланс: <b>{updated_sender['balance']}</b> NCoin",
            parse_mode=ParseMode.HTML
        )
    except ValueError as e:
        await message.answer(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Transfer error: {e}")
        await message.answer("❌ Ошибка перевода. Попробуйте позже.")


# ==================== КНОПКА ЭКОНОМИКИ ====================

@router.callback_query(F.data == "economy")
async def economy_menu(callback: CallbackQuery):
    """Обработчик кнопки ЭКОНОМИКА (старая)"""
    await finance_category_callback(callback)


@router.callback_query(F.data == "finance_category")
async def finance_category_callback(callback: CallbackQuery):
    """Категория ФИНАНСЫ из главного меню"""
    user_id = callback.from_user.id
    
    if user_id in profile_states:
        await callback.answer("❌ Сначала завершите заполнение анкеты", show_alert=True)
        return
    
    user = await get_or_create_user(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    balance = user["balance"]
    daily_streak = user.get("daily_streak", 0)
    vip_level = user.get("vip_level", 0)
    
    # Проверяем, можно ли получить daily сегодня
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    can_claim_daily = last_daily != today
    
    daily_status = "✅ ДОСТУПЕН" if can_claim_daily else "⏰ УЖЕ ПОЛУЧЕН"
    
    await callback.message.edit_text(
        f"💰 <b>ФИНАНСЫ И ЭКОНОМИКА</b>\n\n"
        f"💎 Баланс: <b>{balance} NCoin</b>\n"
        f"⭐ VIP уровень: <b>{vip_level}</b>\n"
        f"🔥 Стрик: <b>{daily_streak}</b> дней\n"
        f"🎁 Ежедневный бонус: {daily_status}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 <b>Доступные действия:</b>\n\n"
        f"├ 💰 <b>Баланс</b> — проверить счёт\n"
        f"├ 🎁 <b>Ежедневный бонус</b> — +100-500 NCoin\n"
        f"├ 💸 <b>Перевести</b> — отправить монеты\n"
        f"├ 🔗 <b>Рефералка</b> — приглашай друзей\n"
        f"└ ⭐ <b>VIP статус</b> — привилегии и бонусы\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 <i>Чем больше стрик — тем выше бонус!\n"
        f"VIP игроки получают +50 NCoin за уровень!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=finance_category_menu()
    )
    await callback.answer()


# ==================== ДОПОЛНИТЕЛЬНЫЕ КНОПКИ ====================

@router.callback_query(F.data == "transfer_menu")
async def transfer_menu_callback(callback: CallbackQuery):
    """Кнопка ПЕРЕВЕСТИ — показывает инструкцию"""
    await callback.message.edit_text(
        "💸 <b>ПЕРЕВОД МОНЕТ</b>\n\n"
        "Используйте команду:\n"
        "<code>/transfer @username сумма</code>\n\n"
        "📌 <b>Примеры:</b>\n"
        "• <code>/transfer @user 100</code>\n"
        "• <code>/transfer @friend 500</code>\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Минимальная сумма: 10 NCoin\n"
        "• Получатель должен активировать бота\n"
        "• Комиссия отсутствует\n\n"
        "💡 <i>Переводы между пользователями мгновенные!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()
