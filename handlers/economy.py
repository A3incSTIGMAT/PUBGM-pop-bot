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
    10: 100,
    50: 600,
    100: 1500,
    200: 3500,
    500: 10000,
}

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


# ==================== BALANCE ====================

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


# ==================== DAILY (ПОЛНОСТЬЮ ПЕРЕПИСАНО С ПРОВЕРКОЙ NULL) ====================

@router.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    
    # Авторегистрация
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 🔥 ПРОВЕРКА НА NULL
    last_daily = user.get("last_daily")
    daily_streak = user.get("daily_streak") or 0
    
    # Если last_daily None или пустая строка
    if not last_daily:
        last_daily = None
    
    # Проверяем, получал ли уже сегодня
    if last_daily == today_str:
        await message.answer(
            f"⏰ <b>БОНУС УЖЕ ПОЛУЧЕН!</b>\n\n"
            f"🔥 Стрик: <b>{daily_streak}</b> дней\n"
            f"⏰ Следующий бонус: <b>завтра</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        # Расчёт стрика
        streak = daily_streak
        
        if last_daily:
            try:
                # Парсим дату из строки
                last_date = datetime.strptime(last_daily, "%Y-%m-%d").date()
                yesterday = datetime.now().date() - timedelta(days=1)
                
                if last_date == yesterday:
                    streak += 1  # Вчера получал — увеличиваем
                elif last_date < yesterday:
                    streak = 1   # Пропустил день — сбрасываем
                else:
                    streak = 1   # Будущая дата (ошибка) — сбрасываем
            except Exception as e:
                logger.warning(f"Error parsing last_daily '{last_daily}': {e}")
                streak = 1
        else:
            # Первый раз
            streak = 1
        
        # Расчёт бонуса
        base_bonus = 100 + (streak * 50)
        vip_level = user.get("vip_level") or 0
        vip_bonus = vip_level * 50 if vip_level > 0 else 0
        total_bonus = base_bonus + vip_bonus
        
        # АТОМАРНОЕ ОБНОВЛЕНИЕ ВСЕГО В ОДНОЙ ТРАНЗАКЦИИ
        def _sync_update_all():
            conn = db._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                # Проверяем текущий баланс
                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError("User not found")
                
                old_balance = row[0]
                new_balance = old_balance + total_bonus
                
                # Обновляем баланс
                cursor.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (new_balance, user_id)
                )
                
                # Обновляем стрик и дату
                cursor.execute(
                    "UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
                    (streak, today_str, user_id)
                )
                
                # Записываем транзакцию
                cursor.execute("""
                    INSERT INTO transactions (from_id, to_id, amount, reason, date)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, user_id, total_bonus, f"Ежедневный бонус (стрик: {streak})", datetime.now().isoformat()))
                
                conn.commit()
                return new_balance
                
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        new_balance = await asyncio.to_thread(_sync_update_all)
        
        # Эмодзи для стрика
        if streak >= 30:
            streak_emoji = "🔥🔥🔥"
        elif streak >= 7:
            streak_emoji = "🔥🔥"
        elif streak >= 3:
            streak_emoji = "🔥"
        else:
            streak_emoji = "⭐"
        
        # Завтрашний бонус
        tomorrow_total = 100 + ((streak + 1) * 50) + vip_bonus
        
        text = (
            f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС ПОЛУЧЕН!</b>\n\n"
            f"💰 Начислено: <b>+{total_bonus} NCoin</b>\n"
        )
        
        if vip_bonus > 0:
            text += f"   ├ Базовый: {base_bonus} NCoin\n"
            text += f"   └ VIP бонус: +{vip_bonus} NCoin\n"
        
        text += (
            f"\n{streak_emoji} Стрик: <b>{streak}</b> дней\n"
            f"💎 Новый баланс: <b>{new_balance} NCoin</b>\n\n"
            f"📅 Завтра получите: <b>{tomorrow_total} NCoin</b>!\n\n"
            f"💡 <i>Заходите каждый день — стрик растёт!</i>"
        )
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        logger.info(f"✅ DAILY: user={user_id}, bonus={total_bonus}, streak={streak}, balance={new_balance}")
        
    except Exception as e:
        logger.error(f"❌ DAILY FAILED for {user_id}: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Произошла ошибка при начислении бонуса</b>\n\n"
            "Попробуйте позже или сообщите администратору.",
            parse_mode=ParseMode.HTML
        )


@router.callback_query(F.data == "daily")
async def daily_callback(callback: types.CallbackQuery):
    await cmd_daily(callback.message)
    await callback.answer()


# ==================== TRANSFER ====================

@router.message(Command("transfer"))
async def cmd_transfer(message: types.Message):
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
    
    if amount < 10:
        await message.answer("❌ Минимальная сумма: 10 NCoin")
        return
    
    sender = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    if sender["balance"] < amount:
        await message.answer(f"❌ Недостаточно средств! Баланс: {sender['balance']} NCoin")
        return
    
    try:
        success = await db.transfer_coins(message.from_user.id, target_username, amount, "transfer")
        
        if not success:
            await message.answer(f"❌ @{target_username} не найден!")
            return
        
        updated = await db.get_user(message.from_user.id)
        await message.answer(
            f"✅ Перевод {amount} NCoin для @{target_username}\n"
            f"💰 Новый баланс: {updated['balance']} NCoin",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Transfer error: {e}")
        await message.answer(f"❌ Ошибка: {e}")


# ==================== ДОНАТ ====================

@router.message(Command("donate"))
async def cmd_donate(message: types.Message):
    text = (
        f"❤️ <b>ПОДДЕРЖКА ПРОЕКТА NEXUS</b> ❤️\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>⚠️ ВАЖНО:</b>\n"
        f"Все функции бота <b>АБСОЛЮТНО БЕСПЛАТНЫ</b>!\n"
        f"Донат — это исключительно добровольная поддержка.\n\n"
        f"<b>🎁 В ЗНАК БЛАГОДАРНОСТИ:</b>\n\n"
    )
    for rub, coins in DONATE_RATES.items():
        text += f"├ {rub} ₽ → <b>{coins} NCoin</b>\n"
    
    text += (
        f"\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📝 КАК ПОЛУЧИТЬ NCOINS:</b>\n"
        f"1. Переведите сумму из списка\n"
        f"2. Отправьте скриншот: <code>/donate_proof 100</code>\n"
        f"3. Администратор проверит и начислит\n\n"
        f"💝 <b>Спасибо за поддержку!</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 РЕКВИЗИТЫ СБП", callback_data="donate_sbp")],
        [InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ", url="https://t.me/A3incSTIGMAT")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data == "donate_sbp")
async def donate_sbp_callback(callback: types.CallbackQuery):
    from config import DONATE_URL, DONATE_BANK, DONATE_RECEIVER
    
    text = (
        "💳 <b>РЕКВИЗИТЫ СБП</b>\n\n"
        f"🏦 Банк: <b>{DONATE_BANK}</b>\n"
        f"👤 Получатель: <b>{DONATE_RECEIVER}</b>\n\n"
        f"📱 Ссылка:\n<code>{DONATE_URL}</code>\n\n"
        "После оплаты: <code>/donate_proof [сумма]</code>"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="donate")]
        ])
    )
    await callback.answer()


@router.message(Command("donate_proof"))
async def cmd_donate_proof(message: types.Message):
    args = message.text.strip().split()
    
    if len(args) < 2:
        await message.answer("❌ Укажите сумму: <code>/donate_proof 100</code>", parse_mode=ParseMode.HTML)
        return
    
    try:
        amount_rub = int(args[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    if amount_rub not in DONATE_RATES:
        rates = ", ".join(str(r) for r in DONATE_RATES.keys())
        await message.answer(f"❌ Доступные суммы: {rates} ₽")
        return
    
    if not message.photo:
        await message.answer("❌ Прикрепите скриншот перевода!")
        return
    
    coins = DONATE_RATES[amount_rub]
    
    if ADMIN_IDS:
        for admin_id in ADMIN_IDS:
            try:
                admin_text = (
                    f"💰 <b>НОВЫЙ ДОНАТ!</b>\n\n"
                    f"👤 {message.from_user.full_name}\n"
                    f"🆔 <code>{message.from_user.id}</code>\n"
                    f"💵 {amount_rub} ₽ → {coins} NCoin"
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
                
                await message.bot.send_photo(
                    admin_id,
                    photo=message.photo[-1].file_id,
                    caption=admin_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Failed to send to admin {admin_id}: {e}")
    
    await message.answer(
        f"✅ Заявка отправлена!\n"
        f"💵 {amount_rub} ₽ → {coins} NCoin\n"
        f"Ожидайте подтверждения.",
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data.startswith("confirm_donate_"))
async def confirm_donate_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    amount_rub = int(parts[3])
    coins = int(parts[4])
    
    await db.update_balance(user_id, coins, f"Донат {amount_rub} ₽")
    await db.update_donor_stats(user_id, amount_rub)
    
    await callback.message.edit_caption(
        f"{callback.message.caption}\n\n✅ <b>ПОДТВЕРЖДЕНО!</b>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        await callback.bot.send_message(
            user_id,
            f"🎉 <b>ДОНАТ ПОДТВЕРЖДЁН!</b>\n\n"
            f"💵 {amount_rub} ₽\n"
            f"🪙 +{coins} NCoin\n\n"
            f"Спасибо за поддержку! ❤️",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await callback.answer("✅ Подтверждено!")


@router.callback_query(F.data.startswith("reject_donate_"))
async def reject_donate_callback(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_caption(
        f"{callback.message.caption}\n\n❌ <b>ОТКЛОНЕНО</b>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        await callback.bot.send_message(
            user_id,
            "❌ Донат не подтверждён. Свяжитесь с разработчиком.",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await callback.answer("❌ Отклонено")


# ==================== МЕНЮ ====================

@router.callback_query(F.data == "finance_category")
async def finance_category_callback(callback: types.CallbackQuery):
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_daily = user.get("last_daily")
    can_claim = not last_daily or last_daily != today
    daily_status = "✅ ДОСТУПЕН" if can_claim else "⏰ УЖЕ ПОЛУЧЕН"
    
    text = (
        f"💰 <b>ФИНАНСЫ</b>\n\n"
        f"💎 Баланс: <b>{user['balance']} NCoin</b>\n"
        f"⭐ VIP: <b>{user.get('vip_level') or 0}</b>\n"
        f"🔥 Стрик: <b>{user.get('daily_streak') or 0}</b>\n"
        f"🎁 Бонус: {daily_status}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Действия:</b>\n"
        f"/balance — баланс\n"
        f"/daily — бонус\n"
        f"/transfer — перевод\n"
        f"/donate — поддержать"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=finance_category_menu()
    )
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


@router.callback_query(F.data == "donate_menu")
async def donate_menu_callback(callback: types.CallbackQuery):
    await cmd_donate(callback.message)
    await callback.answer()
