"""
social.py — Социальные команды (обнять, поцеловать, ударить)
"""

import random
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from utils.helpers import extract_username

router = Router()


async def social_action(message: Message, action: str, emoji: str, messages: dict):
    """Общая функция для социальных действий"""
    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        username = extract_username(message.text)
        if username:
            target = username

    if not target:
        await message.answer(f"{emoji} {messages['no_target']}")
        return

    if isinstance(target, str):
        # Это username
        result = random.choice(messages['actions'])
        await message.answer(f"{emoji} {message.from_user.full_name} {result} @{target}")
    else:
        # Это пользователь
        if target.id == message.from_user.id:
            await message.answer(f"{emoji} {messages['self']}")
            return
        result = random.choice(messages['actions'])
        await message.answer(f"{emoji} {message.from_user.full_name} {result} {target.full_name}")


@router.message(Command("hug"))
async def cmd_hug(message: Message):
    await social_action(message, "hug", "🤗", {
        'no_target': "Кого обнять? Ответьте на сообщение или укажите @username",
        'self': "Нельзя обнять самого себя",
        'actions': ["обнимает", "крепко обнимает", "нежно обнимает", "обнимает со всей силы"]
    })


@router.message(Command("kiss"))
async def cmd_kiss(message: Message):
    await social_action(message, "kiss", "😘", {
        'no_target': "Кого поцеловать? Ответьте на сообщение или укажите @username",
        'self': "Нельзя поцеловать самого себя",
        'actions': ["целует", "нежно целует", "страстно целует", "целует в щёчку"]
    })


@router.message(Command("hit"))
async def cmd_hit(message: Message):
    await social_action(message, "hit", "👊", {
        'no_target': "Кого ударить? Ответьте на сообщение или укажите @username",
        'self': "Нельзя ударить самого себя",
        'actions': ["ударил", "сильно ударил", "дал подзатыльник", "пнул"]
    })
