"""
Модуль экономики NEXUS Bot
Баланс, ежедневный бонус, переводы, ДОНАТ С АВТОРАСЧЁТОМ
ПОЛНОСТЬЮ ИСПРАВЛЕН — ВСЕ БАЛАНСЫ ЧЕРЕЗ db.get_balance()
"""

import asyncio
import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from datetime import datetime, timedelta
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from config import START_BALANCE, ADMIN_IDS, DONATE_URL, DONATE_BANK, DONATE_RECEIVER
from utils.keyboards import back_button, finance_category_menu

router = Router()
logger = logging.getLogger(__name__)


# ==================== НАСТРОЙКИ ДОНАТА ====================

DONATE_RATES = {
    10: 100,
    50: 600,
    100: 1500,
    200: 3500,
    500: 10000,
    1000: 22000,
    2000: 48000,
    5000: 130000,
    10000: 300000,
}


def calculate_donate_coins(amount_rub: int) -> int:
    """Автоматический расчёт NCoin за любую сумму"""
    base_coins = amount_rub * 10
    
    if amount_rub >= 10000:
        bonus = 30000
    elif amount_rub >= 5000:
        bonus = 15000
    elif amount_rub >= 2000:
        bonus = 5000
    elif amount_rub >= 1000:
        bonus = 2000
    elif amount_rub >= 500:
        bonus = 800
    elif amount_rub >= 200:
        bonus = 300
    elif amount_rub >= 100:
        bonus = 100
    elif amount_rub >= 50:
        bonus = 30
    else:
        bonus = 0
    
    return base_coins + bonus


class DonateState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_proof = State()


try:
    from handlers.profile import profile_states
except ImportError:
    profile_states = {}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
    return user


# ==================== КОМАНДА /balance ====================

@router.message(Command("balance"))
async def cmd_balance(message: types.Message):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(message.from_user.id)
    
    await message.answer(
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{balance}</b> NCoin\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ Побед: {user.get('wins', 0)}\n"
        f"└ Поражений: {user.get('losses', 0)}",
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "balance")
async def balance_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(user_id)
    user = await db.get_user(user_id)
    
    text = (
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{balance}</b> NCoin\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ Побед: {user.get('wins', 0)}\n"
        f"└ Поражений: {user.get('losses', 0)}\n\n"
        f"💡 <i>Используйте /daily для получения бонуса!</i>"
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_button())
    await callback.answer()


# ==================== КОМАНДА /daily ====================

@router.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    
    if last_daily == today:
        await message.answer(
            f"⏰ <b>БОНУС УЖЕ ПОЛУЧЕН!</b>\n\n"
            f"🔥 Стрик: <b>{user.get('daily_streak', 0)}</b> дней\n"
            f"⏰ Следующий бонус: <b>завтра</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        streak = user.get("daily_streak", 0)
        
        if last_daily:
            try:
                last_date = datetime.strptime(last_daily, "%Y-%m-%d").date()
                yesterday = datetime.now().date() - timedelta(days=1)
                streak = streak + 1 if last_date == yesterday else 1
            except:
                streak = 1
        else:
            streak = 1
        
        base_bonus = 100 + (streak * 50)
        vip_level = user.get("vip_level", 0) or 0
        vip_bonus = vip_level * 50 if vip_level > 0 else 0
        total_bonus = base_bonus + vip_bonus
        
        def _sync_update():
            conn = db._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_bonus, user_id))
                cursor.execute("UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?", (streak, today, user_id))
                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                conn.commit()
                return row[0] if row else user['balance'] + total_bonus
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        new_balance = await asyncio.to_thread(_sync_update)
        
        if streak >= 30:
            emoji = "🔥🔥🔥"
        elif streak >= 7:
            emoji = "🔥🔥"
        elif streak >= 3:
            emoji = "🔥"
        else:
            emoji = "⭐"
        
        text = (
            f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС ПОЛУЧЕН!</b>\n\n"
            f"💰 Начислено: <b>+{total_bonus} NCoin</b>\n"
        )
        if vip_bonus > 0:
            text += f"   ├ Базовый: {base_bonus} NCoin\n"
            text += f"   └ VIP бонус: +{vip_bonus} NCoin\n"
        
        text += (
            f"\n{emoji} Стрик: <b>{streak}</b> дней\n"
            f"💎 Новый баланс: <b>{new_balance} NCoin</b>"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        logger.info(f"✅ DAILY: user={user_id}, bonus={total_bonus}, streak={streak}")
        
    except Exception as e:
        logger.error(f"❌ DAILY FAILED: {e}", exc_info=True)
        await message.answer("❌ Ошибка при начислении бонуса. Попробуйте позже.")


@router.callback_query(F.data == "daily")
async def daily_callback(callback: types.CallbackQuery):
    await cmd_daily(callback.message)
    await callback.answer()


# ==================== КОМАНДА /transfer ====================

@router.message(Command("transfer"))
async def cmd_transfer(message: types.Message):
    args = message.text.strip().split()
    if len(args) != 3:
        await message.answer("❌ Использование: <code>/transfer @username 100</code>", parse_mode=ParseMode.HTML)
        return
    
    target_username = args[1].lstrip("@")
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    if amount < 10:
        await message.answer("❌ Минимум 10 NCoin")
        return
    
    user_id = message.from_user.id
    sender = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(user_id)
    
    if balance < amount:
        await message.answer(f"❌ Недостаточно средств! Баланс: {balance} NCoin")
        return
    
    try:
        success = await db.transfer_coins(user_id, target_username, amount, "transfer")
        
        if not success:
            await message.answer(f"❌ @{target_username} не найден!")
            return
        
        new_balance = await db.get_balance(user_id)
        await message.answer(
            f"✅ Перевод {amount} NCoin для @{target_username}\n"
            f"💰 Новый баланс: {new_balance} NCoin",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==================== ДОНАТ (УДОБНЫЙ ИНТЕРФЕЙС) ====================

@router.message(Command("donate"))
async def cmd_donate(message: types.Message):
    """Главное меню доната"""
    text = (
        "❤️ <b>ПОДДЕРЖКА ПРОЕКТА NEXUS</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>⚠️ ВАЖНО:</b>\n"
        "Все функции бота <b>АБСОЛЮТНО БЕСПЛАТНЫ</b>!\n"
        "Донат — это добровольная поддержка.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎁 АВТОМАТИЧЕСКИЙ РАСЧЁТ:</b>\n"
        "• 1 ₽ = 10 NCoin\n"
        "• Бонусы за крупные суммы!\n\n"
        "<b>📊 ПРИМЕРЫ:</b>\n"
        "├ 10 ₽ → 100 NCoin\n"
        "├ 50 ₽ → 600 NCoin\n"
        "├ 100 ₽ → 1500 NCoin\n"
        "├ 500 ₽ → 10000 NCoin\n"
        "├ 1000 ₽ → 22000 NCoin\n"
        "└ 5000 ₽ → 130000 NCoin\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>Выберите действие:</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 ВЫБРАТЬ СУММУ", callback_data="donate_select_amount")],
        [InlineKeyboardButton(text="💰 ВВЕСТИ СВОЮ СУММУ", callback_data="donate_custom_amount")],
        [InlineKeyboardButton(text="💳 РЕКВИЗИТЫ СБП", callback_data="donate_sbp")],
        [InlineKeyboardButton(text="📋 КАК ПОЛУЧИТЬ NCOINS", callback_data="donate_help")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data == "donate_menu")
async def donate_menu_callback(callback: types.CallbackQuery):
    await cmd_donate(callback.message)
    await callback.answer()


@router.callback_query(F.data == "donate_select_amount")
async def donate_select_amount(callback: types.CallbackQuery):
    """Выбор из фиксированных сумм"""
    text = (
        "💎 <b>ВЫБЕРИТЕ СУММУ ДОНАТА</b>\n\n"
        "Нажмите на сумму ниже:\n\n"
        "💰 <i>После выбора вам нужно будет прикрепить скриншот</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10 ₽ → 100 NCoin", callback_data="donate_fixed_10")],
        [InlineKeyboardButton(text="50 ₽ → 600 NCoin", callback_data="donate_fixed_50")],
        [InlineKeyboardButton(text="100 ₽ → 1500 NCoin", callback_data="donate_fixed_100")],
        [InlineKeyboardButton(text="200 ₽ → 3500 NCoin", callback_data="donate_fixed_200")],
        [InlineKeyboardButton(text="500 ₽ → 10000 NCoin", callback_data="donate_fixed_500")],
        [InlineKeyboardButton(text="1000 ₽ → 22000 NCoin", callback_data="donate_fixed_1000")],
        [InlineKeyboardButton(text="2000 ₽ → 48000 NCoin", callback_data="donate_fixed_2000")],
        [InlineKeyboardButton(text="5000 ₽ → 130000 NCoin", callback_data="donate_fixed_5000")],
        [InlineKeyboardButton(text="10000 ₽ → 300000 NCoin", callback_data="donate_fixed_10000")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("donate_fixed_"))
async def donate_fixed_selected(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал фиксированную сумму"""
    amount = int(callback.data.split("_")[2])
    coins = calculate_donate_coins(amount)
    
    await state.update_data(donate_amount=amount, donate_coins=coins)
    await state.set_state(DonateState.waiting_for_proof)
    
    text = (
        f"💳 <b>ДОНАТ НА {amount} ₽</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Банк: <b>{DONATE_BANK}</b>\n"
        f"👤 Получатель: <b>{DONATE_RECEIVER}</b>\n\n"
        f"📱 <b>Ссылка СБП:</b>\n"
        f"<code>{DONATE_URL}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📸 ПРИКРЕПИТЕ СКРИНШОТ ПЕРЕВОДА:</b>\n\n"
        f"1. Переведите <b>{amount} ₽</b> по ссылке\n"
        f"2. Сделайте скриншот\n"
        f"3. <b>Отправьте скриншот прямо сейчас</b>\n\n"
        f"🪙 Вы получите: <b>{coins} NCoin</b>\n\n"
        f"❌ Для отмены: /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 ОТКРЫТЬ СБП", url=DONATE_URL)],
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="donate_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "donate_custom_amount")
async def donate_custom_amount(callback: types.CallbackQuery, state: FSMContext):
    """Ввод своей суммы"""
    await state.set_state(DonateState.waiting_for_amount)
    
    text = (
        "💰 <b>ВВЕДИТЕ СУММУ ДОНАТА</b>\n\n"
        "Напишите сумму в рублях (целое число):\n\n"
        "Пример: <code>1500</code>\n\n"
        "🪙 Расчёт: 1 ₽ = 10 NCoin + бонусы!\n\n"
        "❌ Для отмены: /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="donate_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.message(DonateState.waiting_for_amount)
async def process_custom_amount(message: types.Message, state: FSMContext):
    """Обработка введённой суммы"""
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число!\nПопробуйте ещё раз:")
        return
    
    if amount < 10:
        await message.answer("❌ Минимальная сумма доната: 10 ₽\nПопробуйте ещё раз:")
        return
    
    coins = calculate_donate_coins(amount)
    
    await state.update_data(donate_amount=amount, donate_coins=coins)
    await state.set_state(DonateState.waiting_for_proof)
    
    text = (
        f"💳 <b>ДОНАТ НА {amount} ₽</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Банк: <b>{DONATE_BANK}</b>\n"
        f"👤 Получатель: <b>{DONATE_RECEIVER}</b>\n\n"
        f"📱 <b>Ссылка СБП:</b>\n"
        f"<code>{DONATE_URL}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📸 ПРИКРЕПИТЕ СКРИНШОТ ПЕРЕВОДА:</b>\n\n"
        f"1. Переведите <b>{amount} ₽</b> по ссылке\n"
        f"2. Сделайте скриншот\n"
        f"3. <b>Отправьте скриншот прямо сейчас</b>\n\n"
        f"🪙 Вы получите: <b>{coins} NCoin</b>\n\n"
        f"❌ Для отмены: /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 ОТКРЫТЬ СБП", url=DONATE_URL)],
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="donate_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(DonateState.waiting_for_proof, F.photo | F.document)
async def process_donate_proof(message: types.Message, state: FSMContext):
    """Получение скриншота"""
    data = await state.get_data()
    amount = data.get("donate_amount", 0)
    coins = data.get("donate_coins", 0)
    
    await state.clear()
    
    if ADMIN_IDS:
        for admin_id in ADMIN_IDS:
            try:
                admin_text = (
                    f"💰 <b>НОВЫЙ ДОНАТ!</b>\n\n"
                    f"👤 От: {message.from_user.full_name}\n"
                    f"🆔 ID: <code>{message.from_user.id}</code>\n"
                    f"💵 Сумма: {amount} ₽\n"
                    f"🪙 К начислению: {coins} NCoin\n\n"
                    f"<b>Действия:</b>"
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ ПОДТВЕРДИТЬ",
                            callback_data=f"confirm_donate_{message.from_user.id}_{amount}_{coins}"
                        ),
                        InlineKeyboardButton(
                            text="❌ ОТКЛОНИТЬ",
                            callback_data=f"reject_donate_{message.from_user.id}"
                        )
                    ]
                ])
                
                if message.photo:
                    await message.bot.send_photo(
                        admin_id,
                        photo=message.photo[-1].file_id,
                        caption=admin_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard
                    )
                else:
                    await message.bot.send_document(
                        admin_id,
                        document=message.document.file_id,
                        caption=admin_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard
                    )
            except Exception as e:
                logger.error(f"Failed to send to admin {admin_id}: {e}")
    
    await message.answer(
        f"✅ <b>ЗАЯВКА ОТПРАВЛЕНА!</b>\n\n"
        f"💵 Сумма: {amount} ₽\n"
        f"🪙 Ожидаемое начисление: {coins} NCoin\n\n"
        f"Администратор проверит платёж в ближайшее время.\n"
        f"Спасибо за поддержку! ❤️",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
        ])
    )


@router.message(DonateState.waiting_for_proof)
async def donate_waiting_for_photo(message: types.Message):
    """Напоминание, что нужен скриншот"""
    await message.answer(
        "📸 <b>Прикрепите скриншот перевода!</b>\n\n"
        "Просто отправьте фото или файл.\n"
        "❌ Для отмены: /cancel",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("cancel"))
async def cancel_donate(message: types.Message, state: FSMContext):
    """Отмена доната"""
    current_state = await state.get_state()
    if current_state in [DonateState.waiting_for_amount, DonateState.waiting_for_proof]:
        await state.clear()
        await message.answer("❌ Донат отменён.")
    else:
        await message.answer("ℹ️ Нет активной операции.")


@router.callback_query(F.data == "donate_sbp")
async def donate_sbp_callback(callback: types.CallbackQuery):
    """Показать реквизиты СБП"""
    text = (
        "💳 <b>РЕКВИЗИТЫ СБП</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Банк: <b>{DONATE_BANK}</b>\n"
        f"👤 Получатель: <b>{DONATE_RECEIVER}</b>\n\n"
        f"📱 <b>Ссылка на оплату:</b>\n"
        f"<code>{DONATE_URL}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <i>Нажмите на ссылку или скопируйте её</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 ОТКРЫТЬ СБП", url=DONATE_URL)],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "donate_help")
async def donate_help_callback(callback: types.CallbackQuery):
    """Помощь по донату"""
    text = (
        "📋 <b>КАК ПОЛУЧИТЬ NCOINS ЗА ДОНАТ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>1️⃣ Выберите сумму</b>\n"
        "Нажмите на кнопку с суммой или введите свою\n\n"
        "<b>2️⃣ Переведите деньги</b>\n"
        "По реквизитам СБП (Озон Банк)\n\n"
        "<b>3️⃣ Сделайте скриншот</b>\n"
        "Подтверждения перевода\n\n"
        "<b>4️⃣ Отправьте скриншот</b>\n"
        "Прямо в чат с ботом\n\n"
        "<b>5️⃣ Ожидайте проверки</b>\n"
        "Администратор проверит и начислит NCoin\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>💰 АВТОРАСЧЁТ:</b>\n"
        "• 1 ₽ = 10 NCoin\n"
        "• Бонусы за крупные суммы!\n\n"
        "⏰ Обычно проверка занимает до 24 часов.\n"
        "💝 Спасибо за поддержку!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


# ==================== ПОДТВЕРЖДЕНИЕ ДОНАТА АДМИНОМ ====================

@router.callback_query(F.data.startswith("confirm_donate_"))
async def confirm_donate_callback(callback: types.CallbackQuery):
    """Админ подтверждает донат"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    amount_rub = int(parts[3])
    coins = int(parts[4])
    
    await db.update_balance(user_id, coins, f"Донат {amount_rub} ₽")
    await db.update_donor_stats(user_id, amount_rub)
    
    await callback.message.edit_caption(
        f"{callback.message.caption}\n\n✅ <b>ПОДТВЕРЖДЕНО!</b>\n"
        f"Начислено {coins} NCoin пользователю.",
        parse_mode=ParseMode.HTML
    )
    
    try:
        await callback.bot.send_message(
            user_id,
            f"🎉 <b>ДОНАТ ПОДТВЕРЖДЁН!</b>\n\n"
            f"💵 Сумма: {amount_rub} ₽\n"
            f"🪙 Начислено: <b>{coins} NCoin</b>\n\n"
            f"Спасибо за поддержку! ❤️",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await callback.answer("✅ Донат подтверждён!")


@router.callback_query(F.data.startswith("reject_donate_"))
async def reject_donate_callback(callback: types.CallbackQuery):
    """Админ отклоняет донат"""
    user_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_caption(
        f"{callback.message.caption}\n\n❌ <b>ОТКЛОНЕНО</b>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        await callback.bot.send_message(
            user_id,
            f"❌ <b>ДОНАТ НЕ ПОДТВЕРЖДЁН</b>\n\n"
            f"Платёж не найден или скриншот недействителен.\n"
            f"Свяжитесь с разработчиком для уточнения.",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await callback.answer("❌ Донат отклонён")


# ==================== МЕНЮ ФИНАНСОВ ====================

@router.callback_query(F.data == "finance_category")
async def finance_category_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    
    # 🔥 СВЕЖИЙ БАЛАНС
    balance = await db.get_balance(user_id)
    
    today = datetime.now().strftime("%Y-%m-%d")
    can_claim = user.get("last_daily") != today
    daily_status = "✅ ДОСТУПЕН" if can_claim else "⏰ УЖЕ ПОЛУЧЕН"
    
    text = (
        f"💰 <b>ФИНАНСЫ И ЭКОНОМИКА</b>\n\n"
        f"💎 Баланс: <b>{balance} NCoin</b>\n"
        f"⭐ VIP: <b>{user.get('vip_level', 0) or 0}</b>\n"
        f"🔥 Стрик: <b>{user.get('daily_streak', 0) or 0}</b> дней\n"
        f"🎁 Бонус: {daily_status}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Доступные действия:</b>\n"
        f"├ /balance — баланс\n"
        f"├ /daily — бонус\n"
        f"├ /transfer — перевод\n"
        f"└ /donate — поддержать"
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=finance_category_menu())
    await callback.answer()


@router.callback_query(F.data == "transfer_menu")
async def transfer_menu_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💸 <b>ПЕРЕВОД МОНЕТ</b>\n\n"
        "<code>/transfer @username 100</code>\n\n"
        "⚠️ Минимум: 10 NCoin",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()
