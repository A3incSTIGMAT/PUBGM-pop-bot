import random
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from utils.helpers import delete_after_response

router = Router()

@router.message(Command("rps"))
async def cmd_rps(message: Message):
    """Команда /rps - камень-ножницы-бумага"""
    args = message.text.split()
    if len(args) < 2:
        response = await message.answer(
            "🎮 **Камень-ножницы-бумага**\n\n"
            "Использование: /rps [камень|ножницы|бумага]\n"
            "Пример: /rps камень"
        )
        await delete_after_response(response, message, delay=15)
        return
    
    choices = {"камень": "🪨", "ножницы": "✂️", "бумага": "📄"}
    user_choice = args[1].lower()
    
    if user_choice not in choices:
        response = await message.answer("❌ Выберите: камень, ножницы или бумага")
        await delete_after_response(response, message, delay=10)
        return
    
    bot_choice = random.choice(list(choices.keys()))
    
    if user_choice == bot_choice:
        result = "🤝 Ничья!"
    elif (user_choice == "камень" and bot_choice == "ножницы") or \
         (user_choice == "ножницы" and bot_choice == "бумага") or \
         (user_choice == "бумага" and bot_choice == "камень"):
        result = "🎉 Вы выиграли!"
    else:
        result = "😔 Вы проиграли!"
    
    response = await message.answer(
        f"{choices[user_choice]} Вы: {user_choice}\n"
        f"{choices[bot_choice]} Бот: {bot_choice}\n\n"
        f"{result}"
    )
    await delete_after_response(response, message, delay=15)

@router.message(Command("roulette"))
async def cmd_roulette(message: Message):
    """Команда /roulette - рулетка"""
    args = message.text.split()
    if len(args) < 3:
        response = await message.answer(
            "🎲 **Рулетка**\n\n"
            "Использование: /roulette [сумма] [red/black]\n"
            "Пример: /roulette 100 red\n\n"
            "💰 Ставка в NCoin, выигрыш x2"
        )
        await delete_after_response(response, message, delay=15)
        return
    
    try:
        bet = int(args[1])
        color = args[2].lower()
    except:
        response = await message.answer("❌ Неверный формат. Используйте: /roulette 100 red")
        await delete_after_response(response, message, delay=10)
        return
    
    if bet <= 0:
        response = await message.answer("❌ Сумма ставки должна быть больше 0")
        await delete_after_response(response, message, delay=10)
        return
    
    if color not in ["red", "black"]:
        response = await message.answer("❌ Ставить можно только на red или black")
        await delete_after_response(response, message, delay=10)
        return
    
    result = random.choice(["red", "black"])
    
    if result == color:
        win = bet * 2
        response = await message.answer(
            f"🎲 Колесо остановилось на **{result.upper()}**!\n\n"
            f"🎉 **ПОБЕДА!** Вы выиграли {win} NCoin!"
        )
    else:
        response = await message.answer(
            f"🎲 Колесо остановилось на **{result.upper()}**!\n\n"
            f"😔 Вы проиграли {bet} NCoin."
        )
    await delete_after_response(response, message, delay=15)
