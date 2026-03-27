import aiohttp
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from core.brain import NexusBrain

router = Router()
brain = NexusBrain()

@router.message(Command("ask"))
async def cmd_ask(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("🤖 /ask [вопрос]")
        return
    
    status = await message.answer("🤔 Думаю...")
    answer = await brain.ask(args[1])
    await status.delete()
    await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")

@router.message()
async def handle_mention(message: Message):
    if not message.text or f"@{message.bot.username}" not in message.text:
        return
    
    question = message.text.replace(f"@{message.bot.username}", "").strip()
    if question:
        status = await message.answer("🤔 Думаю...")
        answer = await brain.ask(question)
        await status.delete()
        await message.answer(f"🤖 **NEXUS AI:**\n\n{answer}")
