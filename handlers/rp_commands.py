"""
Ролевые команды (обнять, поцеловать, ударить)
"""

import random
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

# Список действий с разными вариациями
RP_ACTIONS = {
    "hug": {
        "name": "обнял",
        "emoji": "🤗",
        "variations": [
            "нежно обнял(а) {target}",
            "крепко обнял(а) {target}",
            "обнял(а) {target} с теплотой",
            "заключил(а) {target} в объятия",
            "обнял(а) {target} и не отпускает"
        ]
    },
    "kiss": {
        "name": "поцеловал",
        "emoji": "😘",
        "variations": [
            "нежно поцеловал(а) {target}",
            "чмокнул(а) {target} в щёчку",
            "поцеловал(а) {target} в лоб",
            "страстно поцеловал(а) {target}",
            "легко коснулся(лась) губ {target}"
        ]
    },
    "slap": {
        "name": "шлёпнул",
        "emoji": "👋",
        "variations": [
            "шлёпнул(а) {target} по плечу",
            "легко шлёпнул(а) {target}",
            "дал(а) подзатыльник {target}",
            "шутливо шлёпнул(а) {target}",
            "хлопнул(а) {target} по спине"
        ]
    },
    "pat": {
        "name": "погладил",
        "emoji": "🫳",
        "variations": [
            "погладил(а) {target} по голове",
            "мягко потрепал(а) {target} по волосам",
            "погладил(а) {target} по спине",
            "ласково прикоснулся(лась) к {target}",
            "похлопал(а) {target} по плечу"
        ]
    },
    "poke": {
        "name": "ткнул",
        "emoji": "👉",
        "variations": [
            "ткнул(а) {target} пальцем",
            "подколол(а) {target}",
            "легко толкнул(а) {target}",
            "дёрнул(а) {target} за рукав",
            "привлёк(ла) внимание {target}"
        ]
    }
}

@router.message(Command("hug"))
async def cmd_hug(message: Message):
    await process_rp_command(message, "hug")

@router.message(Command("kiss"))
async def cmd_kiss(message: Message):
    await process_rp_command(message, "kiss")

@router.message(Command("slap"))
async def cmd_slap(message: Message):
    await process_rp_command(message, "slap")

@router.message(Command("pat"))
async def cmd_pat(message: Message):
    await process_rp_command(message, "pat")

@router.message(Command("poke"))
async def cmd_poke(message: Message):
    await process_rp_command(message, "poke")

async def process_rp_command(message: Message, action_key: str):
    """Обработка РП-команд"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            f"{RP_ACTIONS[action_key]['emoji']} **{RP_ACTIONS[action_key]['name']}**\n\n"
            f"Использование: /{action_key} @username\n"
            f"Пример: /{action_key} @ivan"
        )
        return
    
    target_username = args[1].replace("@", "")
    action = RP_ACTIONS[action_key]
    
    # Ищем пользователя в чате
    target_id = None
    target_name = target_username
    
    try:
        async for member in message.chat.get_members():
            if member.user.username and member.user.username.lower() == target_username.lower():
                target_id = member.user.id
                target_name = member.user.full_name
                break
    except:
        pass
    
    if not target_id:
        await message.answer(f"❌ Пользователь @{target_username} не найден в чате.")
        return
    
    # Выбираем случайную вариацию
    variation = random.choice(action["variations"])
    text = variation.format(target=f"@{target_username}")
    
    await message.answer(
        f"{action['emoji']} **{message.from_user.full_name}** {text}"
    )
