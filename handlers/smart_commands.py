from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from database import db

router = Router()

@router.message(Command("smart"))
async def cmd_smart(message: types.Message):
    """Умный парсер команд"""
    text = message.text.replace("/smart", "").strip().lower()
    
    if not text:
        await message.answer(
            "🤖 *Умный парсер команд*\n\n"
            "Примеры:\n"
            "• сыграй в слот на 100\n"
            "• рулетка 500 красный\n"
            "• переведи @user 200\n"
            "• мой баланс\n"
            "• помоги мне",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Парсим команды
    if "слот" in text or "slot" in text:
        await message.answer("🎰 Используйте команду: /slot 100")
    
    elif "рулетк" in text or "roulette" in text:
        await message.answer("🎡 Используйте команду: /roulette 100 красный")
    
    elif "кнб" in text or "rps" in text:
        await message.answer("✂️ Используйте команду: /rps камень")
    
    elif "дуэль" in text or "duel" in text:
        await message.answer("⚔️ Используйте команду: /duel @user 100")
    
    elif "баланс" in text or "balance" in text:
        user = await db.get_user(message.from_user.id)
        if user:
            await message.answer(f"💰 Ваш баланс: {user['balance']} монет")
        else:
            await message.answer("❌ Используйте /start для регистрации")
    
    elif "переведи" in text or "transfer" in text:
        await message.answer("💸 Используйте команду: /transfer @user 100")
    
    elif "помоги" in text or "help" in text:
        await message.answer("📚 Используйте /help для списка всех команд")
    
    else:
        await message.answer(
            "🤖 *Не понял команду*\n\n"
            "Доступные действия:\n"
            "• слот, рулетка, кнб, дуэль\n"
            "• баланс, перевод\n"
            "• помощь",
            parse_mode=ParseMode.MARKDOWN
        )
