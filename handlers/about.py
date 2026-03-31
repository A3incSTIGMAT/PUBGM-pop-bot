"""
about.py — Информация о боте
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from utils.keyboards import back_button

router = Router()


@router.message(Command("about"))
async def cmd_about(message: Message):
    """Команда /about"""
    text = get_about_text()
    await message.answer(text, parse_mode="Markdown")


@router.callback_query(F.data == "about")
async def about_menu(callback: CallbackQuery):
    """Меню о боте"""
    text = get_about_text()
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


def get_about_text() -> str:
    """Текст о боте"""
    return (
        "ℹ️ *О БОТЕ NEXUS*\n\n"
        "NEXUS Chat Manager — многофункциональный бот для чатов.\n\n"
        "🎮 *Игры:* слоты, дуэли, рулетка, камень-ножницы-бумага\n"
        "💰 *Экономика:* баланс, переводы, ежедневный бонус\n"
        "🛡️ *Модерация:* бан, мут, предупреждения\n"
        "⭐ *VIP:* повышенные лимиты и множители\n"
        "🤖 *AI:* помощь и ответы на вопросы\n"
        "💳 *Оплата:* Озон Банк, СБП\n\n"
        "📱 *Как играть:*\n"
        "• Слэш-команды: `/slot`\n"
        "• Текстовые команды: `сыграй в слот`\n"
        "• Обращение по имени: `Nexus, сыграй в слот`\n\n"
        "Версия: 3.0 (полная пересборка)\n"
        "Разработчик: @A3incSTIGMAT\n\n"
        "© 2025 NEXUS"
    )
