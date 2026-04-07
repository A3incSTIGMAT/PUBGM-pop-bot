from aiogram import Router, F
from aiogram.types import Message
from utils.smart_parser import smart_parser
from handlers import games, economy, profile, social

router = Router()

@router.message(F.text & ~F.text.startswith('/'))
async def smart_handler(message: Message):
    parsed = smart_parser.parse_command(message.text)
    if not parsed: return
    cmd, params = parsed
    if cmd == 'slot': await games.cmd_slot(message, None)
    elif cmd == 'balance': await economy.cmd_balance(message)
    elif cmd == 'daily': await economy.cmd_daily(message)
    elif cmd == 'profile': await profile.cmd_profile(message)
    elif cmd == 'transfer': await economy.cmd_transfer(message)
