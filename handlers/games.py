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
            "Пример: /rps камень"
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
            "🎲 Рулетка\n\n"
            "Использование: /roulette [сумма] [red/black]\n"
            "Пример: /roulette 100 red"
        )
        return
    
    try:
        bet = int(args[1])
        color = args[2].lower()
    except:
        await message.answer("❌ Неверный формат. Используйте: /roulette 100 red")
        return
    
    if color not in ["red", "black"]:
        await message.answer("❌ Ставить можно только на red или black")
        return
    
    result = random.choice(["red", "black"])
    
    if result == color:
        win = bet * 2
        await message.answer(f"🎲 Выпало {result}! Поздравляю! Вы выиграли {win} монет!")
    else:
        await message.answer(f"🎲 Выпало {result}. Вы проиграли {bet} монет.")

# Дуэль (заглушка)
@router.message(Command("duel"))
async def duel(message: Message):
    await message.answer(
        "⚔️ Дуэль\n\n"
        "Использование: /duel @username [сумма]\n"
        "Пример: /duel @ivan 100\n\n"
        "💰 Экономика еще настраивается. Скоро будет доступно!"
    )
