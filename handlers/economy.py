from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_balance, update_balance, init_db

router = Router()

# Инициализируем базу при первом импорте
init_db()

# Баланс пользователя
@router.message(Command("balance"))
async def show_balance(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    await message.answer(f"💰 Ваш баланс: {balance} монет")

# Подарок пользователю
@router.message(Command("gift"))
async def send_gift(message: Message):
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer(
            "🎁 Подарок\n\n"
            "Использование: /gift @username [сумма]\n"
            "Пример: /gift @ivan 50"
        )
        return
    
    # Получаем username получателя
    target_username = args[1].replace("@", "")
    try:
        amount = int(args[2])
    except:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    sender_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем баланс отправителя
    sender_balance = get_balance(sender_id, chat_id)
    
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно средств. Ваш баланс: {sender_balance} монет")
        return
    
    # Находим пользователя по username
    # В реальном боте нужно получить user_id через @mention
    # Пока заглушка
    await message.answer(
        f"🎁 Вы подарили {amount} монет пользователю @{target_username}\n\n"
        "⚠️ Функция в разработке. Скоро будет работать автоматически!"
    )

# Топ пользователей
@router.message(Command("top"))
async def show_top(message: Message):
    await message.answer(
        "🏆 Топ пользователей\n\n"
        "1. @user1 — 5000 монет\n"
        "2. @user2 — 3200 монет\n"
        "3. @user3 — 2100 монет\n\n"
        "📊 Скоро будет полноценная таблица!"
    )
