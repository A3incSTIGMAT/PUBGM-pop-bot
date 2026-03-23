import random
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

# Камень-ножницы-бумага
@router.message(Command("rps"))
async def rps_game(message: Message):
    choices = {
        "камень": "🪨",
        "ножницы": "✂️",
        "бумага": "📄"
    }
    
    # Разбираем выбор пользователя
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "🎮 Камень-ножницы-бумага\n\n"
            "Использование: /rps [камень|ножницы|бумага]\n"
            "Пример: /rps камень\n\n"
            "💰 Ставка: игра бесплатная"
        )
        return
    
    user_choice = args[1].lower()
    if user_choice not in choices:
        await message.answer("❌ Выберите: камень, ножницы или бумага")
        return
    
    bot_choice = random.choice(list(choices.keys()))
    
    # Определяем победителя
    if user_choice == bot_choice:
        result = "🤝 Ничья!"
    elif (user_choice == "камень" and bot_choice == "ножницы") or \
         (user_choice == "ножницы" and bot_choice == "бумага") or \
         (user_choice == "бумага" and bot_choice == "камень"):
        result = "🎉 Вы выиграли!"
    else:
        result = "😔 Вы проиграли!"
    
    await message.answer(
        f"{choices[user_choice]} Вы выбрали: {user_choice}\n"
        f"{choices[bot_choice]} Бот выбрал: {bot_choice}\n\n"
        f"{result}"
    )

# Рулетка
@router.message(Command("roulette"))
async def roulette(message: Message):
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer(
            "🎲 РУЛЕТКА NEXUS\n\n"
            "Использование: /roulette [сумма] [red/black]\n"
            "Пример: /roulette 100 red\n\n"
            "💰 Ставка в NCoin\n"
            "🎯 Выигрыш: x2 от ставки"
        )
        return
    
    try:
        bet = int(args[1])
        color = args[2].lower()
    except:
        await message.answer("❌ Неверный формат. Используйте: /roulette 100 red")
        return
    
    if bet <= 0:
        await message.answer("❌ Сумма ставки должна быть больше 0")
        return
    
    if color not in ["red", "black"]:
        await message.answer("❌ Ставить можно только на red или black")
        return
    
    result = random.choice(["red", "black"])
    
    if result == color:
        win = bet * 2
        await message.answer(
            f"🎲 Колесо остановилось на {result.upper()}!\n\n"
            f"🎉 ПОБЕДА! Вы выиграли {win} NCoin!"
        )
    else:
        await message.answer(
            f"🎲 Колесо остановилось на {result.upper()}!\n\n"
            f"😔 Вы проиграли {bet} NCoin."
        )

# Дуэль (заглушка, будет доработана)
@router.message(Command("duel"))
async def duel(message: Message):
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "⚔️ ДУЭЛЬ\n\n"
            "Использование: /duel @username [сумма]\n"
            "Пример: /duel @ivan 100\n\n"
            "💰 Ставка в NCoin\n"
            "🎯 Победитель забирает банк"
        )
        return
    
    target = args[1]
    amount = args[2] if len(args) > 2 else 50
    
    await message.answer(
        f"⚔️ Вызов на дуэль!\n\n"
        f"{message.from_user.full_name} вызывает @{target.replace('@', '')} на дуэль!\n"
        f"💰 Ставка: {amount} NCoin\n\n"
        f"✅ Скоро будет доступно полноценное PvP!"
    )
