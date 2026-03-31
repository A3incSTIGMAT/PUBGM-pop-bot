"""
smart_commands.py — Обработчик текстовых команд (без слэша)
"""

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from utils.smart_parser import smart_parser
from handlers import games, economy, profile, social, vip

router = Router()


@router.message(F.text & ~F.text.startswith('/'))
async def smart_command_handler(message: Message, state: FSMContext):
    """
    Обработчик текстовых команд (не слэш)
    Понимает обращения по имени и обычный текст
    """
    text = message.text.strip()
    if not text:
        return

    # Парсим команду
    parsed = smart_parser.parse_command(text)

    if not parsed:
        # Не распознано как команда, игнорируем
        return

    command, params = parsed

    # Перенаправляем в соответствующий хендлер
    if command == 'slot':
        await games.cmd_slot_smart(message, state, params.get('amount'))

    elif command == 'duel':
        await games.cmd_duel_smart(message, state, params.get('amount'), params.get('target'))

    elif command == 'roulette':
        await games.cmd_roulette_smart(message, state, params.get('amount'), params.get('color'))

    elif command == 'rps':
        await games.cmd_rps_smart(message, state, params.get('choice'))

    elif command == 'balance':
        await economy.cmd_balance_smart(message)

    elif command == 'daily':
        await economy.cmd_daily_smart(message)

    elif command == 'transfer':
        await economy.cmd_transfer_smart(message, params.get('to'), params.get('amount'))

    elif command == 'profile':
        await profile.cmd_profile_smart(message)

    elif command == 'help':
        await message.answer(
            "🤖 *Я умею:*\n\n"
            "🎮 *Игры:* слот, дуэль, рулетка, камень-ножницы-бумага\n"
            "💰 *Экономика:* баланс, бонус, перевод\n"
            "👤 *Профиль:* моя статистика\n"
            "🤝 *Социальные:* обнять, поцеловать, ударить\n\n"
            "📱 *Примеры:*\n"
            "• `сыграй в слот`\n"
            "• `рулетка 100 красный`\n"
            "• `перевести @username 100`\n"
            "• `обнять @username`",
            parse_mode="Markdown"
        )

    elif command == 'vip':
        await vip.buy_vip(message)

    elif command == 'hug':
        await social.cmd_hug(message)

    elif command == 'kiss':
        await social.cmd_kiss(message)

    elif command == 'hit':
        await social.cmd_hit(message)
