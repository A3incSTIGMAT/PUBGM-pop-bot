from aiogram import Router, Bot
from aiogram.types import CallbackQuery

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

@router.callback_query(lambda c: c.data == "menu_back_main")
async def menu_back_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        "🏠 **Главное меню NEXUS**\n\n"
        "Для открытия меню используйте /menu",
        reply_markup=None
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_close")
async def menu_close(callback: CallbackQuery):
    """Закрыть меню"""
    await callback.message.delete()
    await callback.answer()
