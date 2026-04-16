import asyncio
import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from datetime import datetime, timedelta
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE, ADMIN_IDS
from utils.keyboards import back_button, finance_category_menu

router = Router()
logger = logging.getLogger(__name__)

# Настройки доната
DONATE_RATES = {
    10: 100,    # 10 руб = 100 NCoins
    50: 600,    # 50 руб = 600 NCoins
    100: 1500,  # 100 руб = 1500 NCoins
    200: 3500,  # 200 руб = 3500 NCoins
    500: 10000, # 500 руб = 10000 NCoins
}

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
async def cmd_balance(message: types.Message):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    await message.answer(
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{user['balance']}</b> NCoin\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ Побед: {user.get('wins', 0)}\n"
        f"└ Поражений: {user.get('losses', 0)}",
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "balance")
async def balance_callback(callback: types.CallbackQuery):
    """Обработчик кнопки БАЛАНС из меню"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    text = (
        f"💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"└ <b>{user['balance']}</b> NCoin\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ Побед: {user.get('wins', 0)}\n"
        f"└ Поражений: {user.get('losses', 0)}\n\n"
        f"💡 <i>Используйте /daily для получения бонуса!</i>"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_button()
    )
    await callback.answer()


# ==================== КОМАНДА /daily ====================

@router.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    
    # Авторегистрация если нужно
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    
    # Проверяем, можно ли получить бонус
    if last_daily:
        try:
            last_date = datetime.fromisoformat(last_daily).date()
            if last_date == datetime.now().date():
                # Уже получали сегодня
                await message.answer(
                    f"⏰ <b>БОНУС УЖЕ ПОЛУЧЕН!</b>\n\n"
                    f"Вы уже получали бонус сегодня.\n"
                    f"Возвращайтесь завтра за новым бонусом!\n\n"
                    f"🔥 Текущий стрик: <b>{user.get('daily_streak', 0)}</b> дней\n"
                    f"⏰ Следующий бонус: <b>завтра</b>",
                    parse_mode=ParseMode.HTML
                )
                return
        except:
            pass
    
    try:
        # Расчёт стрика
        streak = user.get("daily_streak", 0)
        
        if last_daily:
            try:
                last_date = datetime.fromisoformat(last_daily).date()
                days_diff = (datetime.now().date() - last_date).days
                
                if days_diff == 1:
                    # Прошёл ровно 1 день - увеличиваем стрик
                    streak += 1
                elif days_diff > 1:
                    # Пропустили день - сбрасываем стрик
                    streak = 1
                else:
                    # Меньше дня (не должно случиться из-за проверки выше)
                    streak = 1
            except:
                streak = 1
        else:
            # Первый бонус
            streak = 1
        
        # Расчёт бонуса
        base_bonus = 100 + (streak * 50)
        vip_level = user.get("vip_level", 0)
        vip_bonus = vip_level * 50 if vip_level > 0 else 0
        total_bonus = base_bonus + vip_bonus
        
        # Обновляем баланс и стрик
        await db.update_balance(user_id, total_bonus, f"Ежедневный бонус (стрик: {streak})")
        await db.update_daily_streak(user_id, streak)
        
        updated_user = await db.get_user(user_id)
        new_balance = updated_user["balance"] if updated_user else user['balance'] + total_bonus
        
        # Эмодзи для стрика
        if streak >= 30:
            streak_emoji = "🔥🔥🔥"
        elif streak >= 7:
            streak_emoji = "🔥🔥"
        elif streak >= 3:
            streak_emoji = "🔥"
        else:
            streak_emoji = "⭐"
        
        # Расчёт завтрашнего бонуса
        tomorrow_streak = streak + 1
        tomorrow_base = 100 + (tomorrow_streak * 50)
        tomorrow_vip = vip_level * 50 if vip_level > 0 else 0
        tomorrow_total = tomorrow_base + tomorrow_vip
        
        text = (
            f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС!</b>\n\n"
            f"💰 Получено: <b>+{total_bonus} NCoin</b>\n"
        )
        
        if vip_bonus > 0:
            text += f"   ├ Базовый: {base_bonus} NCoin\n"
            text += f"   └ VIP бонус: +{vip_bonus} NCoin\n"
        
        text += (
            f"\n{streak_emoji} Стрик: <b>{streak}</b> дней\n"
            f"💎 Новый баланс: <b>{new_balance} NCoin</b>\n\n"
            f"📅 Завтра бонус будет <b>{tomorrow_total} NCoin</b>!\n\n"
            f"💡 <i>Заходите каждый день для увеличения стрика!</i>"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Daily bonus failed for {user_id}: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при начислении бонуса. Попробуйте позже.")


@router.callback_query(F.data == "daily")
async def daily_callback(callback: types.CallbackQuery):
    """Обработчик кнопки ежедневного бонуса"""
    await cmd_daily(callback.message)
    await callback.answer()


# ==================== КОМАНДА /transfer ====================

@router.message(Command("transfer"))
async def cmd_transfer(message: types.Message):
    user_id = message.from_user.id
    
    args = message.text.strip().split()
    if len(args) != 3:
        await message.answer(
            "❌ <b>Неверный формат!</b>\n\n"
            "Использование: <code>/transfer @username 100</code>",
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
    except Exception as e:
        logger.error(f"Transfer error: {e}")
        await message.answer("❌ Ошибка перевода. Попробуйте позже.")


# ==================== ДОНАТ ====================

@router.message(Command("donate"))
async def cmd_donate(message: types.Message):
    """Информация о донате и начислении NCoins"""
    text = (
        f"❤️ <b>ПОДДЕРЖКА ПРОЕКТА NEXUS</b> ❤️\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>⚠️ ВАЖНО:</b>\n"
        f"Все функции бота <b>АБСОЛЮТНО БЕСПЛАТНЫ</b>!\n"
        f"Донат — это исключительно добровольная поддержка разработчика.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🎁 В ЗНАК БЛАГОДАРНОСТИ:</b>\n\n"
        f"За вашу поддержку мы начисляем NCoins на баланс:\n\n"
    )
    
    for rub, coins in DONATE_RATES.items():
        text += f"├ {rub} ₽ → <b>{coins} NCoin</b>\n"
    
    text += (
        f"\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>💳 СПОСОБЫ ПОДДЕРЖКИ:</b>\n\n"
        f"├ <b>СБП (Озон Банк)</b> — быстро и без комиссии\n"
        f"└ <b>Перевод на карту</b> — по запросу\n\n"
        f"<b>📝 КАК ПОЛУЧИТЬ NCOINS:</b>\n\n"
        f"1. Переведите любую сумму из списка выше\n"
        f"2. Отправьте скриншот перевода командой:\n"
        f"   <code>/donate_proof [сумма]</code>\n"
        f"3. Прикрепите скриншот к сообщению\n"
        f"4. Администратор проверит и начислит NCoins\n\n"
        f"Пример: <code>/donate_proof 100</code> + скриншот\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💝 <b>Спасибо за поддержку NEXUS!</b>\n"
        f"Ваша помощь делает бота лучше!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 РЕКВИЗИТЫ СБП", callback_data="donate_sbp")],
        [InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С РАЗРАБОТЧИКОМ", url="https://t.me/A3incSTIGMAT")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data == "donate_sbp")
async def donate_sbp_callback(callback: types.CallbackQuery):
    """Показать реквизиты СБП"""
    text = (
        "💳 <b>РЕКВИЗИТЫ СБП (ОЗОН БАНК)</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏦 Банк: <b>Озон Банк</b>\n"
        "👤 Получатель: <b>Александр Б.</b>\n\n"
        "📱 <b>Ссылка на оплату:</b>\n"
        "<code>https://finance.ozon.ru/apps/sbp/ozonbankpay/...</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📝 ИНСТРУКЦИЯ:</b>\n\n"
        "1. Перейдите по ссылке или отсканируйте QR\n"
        "2. Введите сумму из списка\n"
        "3. После оплаты отправьте скриншот командой:\n"
        "   <code>/donate_proof [сумма]</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💝 <i>Спасибо за поддержку!</i>"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate_menu")]
        ])
    )
    await callback.answer()


@router.message(Command("donate_proof"))
async def cmd_donate_proof(message: types.Message):
    """Отправка подтверждения доната"""
    args = message.text.strip().split()
    
    if len(args) < 2:
        await message.answer(
            "❌ <b>Укажите сумму доната!</b>\n\n"
            "Использование: <code>/donate_proof 100</code>\n"
            "И прикрепите скриншот перевода к этому сообщению.",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        amount_rub = int(args[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    if amount_rub not in DONATE_RATES:
        rates_text = ", ".join(str(r) for r in DONATE_RATES.keys())
        await message.answer(
            f"❌ <b>Неверная сумма!</b>\n\n"
            f"Доступные суммы: {rates_text} ₽\n\n"
            f"Если вы перевели другую сумму, свяжитесь с разработчиком.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not message.photo and not message.document:
        await message.answer(
            "❌ <b>Прикрепите скриншот перевода!</b>\n\n"
            "Отправьте команду вместе с фото:\n"
            "<code>/donate_proof 100</code> + скриншот",
            parse_mode=ParseMode.HTML
        )
        return
    
    coins = DONATE_RATES[amount_rub]
    
    # Отправляем админам
    if ADMIN_IDS:
        for admin_id in ADMIN_IDS:
            try:
                admin_text = (
                    f"💰 <b>НОВЫЙ ДОНАТ!</b>\n\n"
                    f"👤 От: {message.from_user.full_name}\n"
                    f"🆔 ID: <code>{message.from_user.id}</code>\n"
                    f"💵 Сумма: {amount_rub} ₽\n"
                    f"🪙 К начислению: {coins} NCoin\n\n"
                    f"<b>Действия:</b>"
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ ПОДТВЕРДИТЬ",
                            callback_data=f"confirm_donate_{message.from_user.id}_{amount_rub}_{coins}"
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
                    await message.bot.send_message(
                        admin_id,
                        admin_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard
                    )
            except Exception as e:
                logger.error(f"Failed to send donate proof to admin {admin_id}: {e}")
    
    await message.answer(
        f"✅ <b>ЗАЯВКА НА ДОНАТ ОТПРАВЛЕНА!</b>\n\n"
        f"💵 Сумма: {amount_rub} ₽\n"
        f"🪙 Ожидаемое начисление: {coins} NCoin\n\n"
        f"Администратор проверит платёж в ближайшее время.\n"
        f"Спасибо за поддержку! ❤️",
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data.startswith("confirm_donate_"))
async def confirm_donate_callback(callback: types.CallbackQuery):
    """Админ подтверждает донат"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    amount_rub = int(parts[3])
    coins = int(parts[4])
    
    # Начисляем NCoins
    await db.update_balance(user_id, coins, f"Донат {amount_rub} ₽")
    
    # Обновляем статистику донатера
    def _update_donor():
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO donors (user_id, total_donated, last_donate)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                total_donated = total_donated + ?,
                last_donate = CURRENT_TIMESTAMP
        """, (user_id, amount_rub, amount_rub))
        conn.commit()
        conn.close()
    
    await asyncio.to_thread(_update_donator)
    
    await callback.message.edit_caption(
        f"{callback.message.caption}\n\n✅ <b>ПОДТВЕРЖДЕНО!</b>\n"
        f"Начислено {coins} NCoin пользователю.",
        parse_mode=ParseMode.HTML
    )
    
    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            user_id,
            f"🎉 <b>ДОНАТ ПОДТВЕРЖДЁН!</b>\n\n"
            f"💵 Сумма: {amount_rub} ₽\n"
            f"🪙 Начислено: <b>{coins} NCoin</b>\n\n"
            f"Спасибо за поддержку проекта! ❤️",
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


# ==================== КНОПКИ МЕНЮ ====================

@router.callback_query(F.data == "finance_category")
async def finance_category_callback(callback: types.CallbackQuery):
    """Категория ФИНАНСЫ из главного меню"""
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    balance = user["balance"]
    daily_streak = user.get("daily_streak", 0)
    vip_level = user.get("vip_level", 0)
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    can_claim_daily = last_daily != today
    
    daily_status = "✅ ДОСТУПЕН" if can_claim_daily else "⏰ УЖЕ ПОЛУЧЕН"
    
    text = (
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
        f"├ ⭐ <b>VIP статус</b> — привилегии и бонусы\n"
        f"└ ❤️ <b>Поддержать</b> — донат\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 <i>Чем больше стрик — тем выше бонус!\n"
        f"VIP игроки получают +50 NCoin за уровень!</i>"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=finance_category_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "transfer_menu")
async def transfer_menu_callback(callback: types.CallbackQuery):
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


@router.callback_query(F.data == "donate_menu")
async def donate_menu_callback(callback: types.CallbackQuery):
    """Кнопка ПОДДЕРЖАТЬ"""
    await cmd_donate(callback.message)
    await callback.answer()
