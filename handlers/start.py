from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from datetime import datetime
import json

from database import db
from config import START_BALANCE

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Проверяем, существует ли пользователь
    user = await db.get_user(user_id)
    
    if not user:
        # Создаём нового пользователя
        await db.create_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
            balance=START_BALANCE
        )
        
        # Приветствие для нового пользователя
        welcome_text = f"""
✨ <b>Добро пожаловать в NEXUS Bot, {first_name}!</b> ✨

🎁 <b>Вам начислено {START_BALANCE} монет</b> в подарок!

🤖 <b>NEXUS Bot v5.0</b> — это:
├ 🎮 Игры на монеты
├ 💰 Экономическая система
├ 🛒 Магазин и транзакции
├ ⭐ VIP статус
├ 🤖 AI помощник
└ 💳 Платежи через Озон Банк

📌 <b>Быстрый старт:</b>
• /daily — получить ежедневный бонус
• /slot 100 — сыграть в слот
• /balance — проверить баланс
• /help — все команды

Приятной игры! 🎯
"""
        await message.answer(welcome_text, parse_mode=ParseMode.HTML)
    
    else:
        # Приветствие для существующего пользователя
        welcome_back = f"""
👋 <b>С возвращением, {first_name}!</b>

💰 <b>Ваш баланс:</b> {user['balance']} монет
⭐ <b>VIP статус:</b> {'Да' if user.get('vip_level', 0) > 0 else 'Нет'}
🔥 <b>Daily стрик:</b> {user.get('daily_streak', 0)} дней

📌 <b>Доступные команды:</b>
• /daily — бонус дня
• /slot — слот-машина
• /roulette — рулетка
• /duel — дуэль с игроком
• /shop — магазин
• /balance — баланс
• /profile — профиль
• /help — помощь

Выберите действие в меню 👇
"""
        await message.answer(welcome_back, parse_mode=ParseMode.HTML)
    
    # Отправляем клавиатуру (если есть функция)
    try:
        from utils.keyboards import main_keyboard
        await message.answer("📱 <b>Главное меню:</b>", 
                            reply_markup=main_keyboard(),
                            parse_mode=ParseMode.HTML)
    except ImportError:
        pass  # Клавиатура не подключена, игнорируем


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """
🤖 <b>NEXUS Bot v5.0 — Справка</b>

━━━━━━━━━━━━━━━━━━━━━
💰 <b>ЭКОНОМИКА</b>
━━━━━━━━━━━━━━━━━━━━━
/balance — Проверить баланс
/daily — Ежедневный бонус
/transfer @user 100 — Перевести монеты

━━━━━━━━━━━━━━━━━━━━━
🎮 <b>ИГРЫ</b>
━━━━━━━━━━━━━━━━━━━━━
/slot 100 — Слот-машина (x3, x5, x10)
/roulette 100 красный — Рулетка
/rps камень — Камень-ножницы-бумага
/duel @user 100 — Дуэль с игроком

━━━━━━━━━━━━━━━━━━━━━
👤 <b>ПРОФИЛЬ И ПРОГРЕСС</b>
━━━━━━━━━━━━━━━━━━━━━
/profile — Ваш профиль
/stats — Статистика бота
/vip — Информация о VIP

━━━━━━━━━━━━━━━━━━━━━
🛒 <b>МАГАЗИН И ПЛАТЕЖИ</b>
━━━━━━━━━━━━━━━━━━━━━
/shop — Магазин товаров
/add_ncoin — Пополнить баланс через Озон Банк

━━━━━━━━━━━━━━━━━━━━━
🤖 <b>ПРОЧЕЕ</b>
━━━━━━━━━━━━━━━━━━━━━
/ask вопрос — AI помощник
/about — О боте
/help — Эта справка

━━━━━━━━━━━━━━━━━━━━━
<i>Разработано с ❤️ для NEXUS Community</i>
"""
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@router.message(Command("about"))
async def cmd_about(message: types.Message):
    about_text = """
🤖 <b>NEXUS Bot v5.0</b>

<b>Версия:</b> 5.0
<b>Статус:</b> ✅ Активен

<b>Возможности:</b>
├ 🎮 Игровая система
├ 💰 Экономика
├ 🛒 Магазин
├ ⭐ VIP статусы
├ 🤖 AI помощник
├ 💳 Озон Банк платежи
└ 📊 Статистика

<b>Технологии:</b>
├ Python 3.11
├ Aiogram 3.x
├ SQLite
└ Docker

<b>Разработчик:</b> @A3incSTIGMAT

Спасибо, что используете NEXUS Bot! 🎯
"""
    await message.answer(about_text, parse_mode=ParseMode.HTML)


@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден! Используйте /start для регистрации")
        return
    
    profile_text = f"""
👤 <b>Профиль пользователя</b>

━━━━━━━━━━━━━━━━━━━━━
📛 <b>Имя:</b> {user.get('first_name', 'Не указано')}
🆔 <b>ID:</b> {user_id}
📅 <b>Регистрация:</b> {user.get('register_date', 'Неизвестно')[:10]}
━━━━━━━━━━━━━━━━━━━━━

💰 <b>Баланс:</b> {user.get('balance', 0)} монет

⭐ <b>VIP статус:</b> {'✅ Активирован' if user.get('vip_level', 0) > 0 else '❌ Нет'}
{f'📅 VIP до: {user.get("vip_until", "")[:10]}' if user.get('vip_level', 0) > 0 else ''}

🏆 <b>Статистика:</b>
├ Побед: {user.get('wins', 0)}
├ Поражений: {user.get('losses', 0)}
└ Всего игр: {user.get('wins', 0) + user.get('losses', 0)}

🔥 <b>Daily стрик:</b> {user.get('daily_streak', 0)} дней

━━━━━━━━━━━━━━━━━━━━━
<i>Продолжайте играть и повышайте свой статус!</i>
"""
    await message.answer(profile_text, parse_mode=ParseMode.HTML)
