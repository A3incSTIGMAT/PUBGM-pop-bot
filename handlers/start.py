from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    user = await db.get_user(user_id)
    
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
    
    # Красивая презентация бота
    presentation_text = f"""
🤖 *ВЕЛКОМ ТО NEXUS ЧАТ МЕНЕДЖЕР!* 🤖

✨ *Привет, {first_name}!*

Я — *NEXUS Chat Manager* — твой личный помощник в управлении чатом!

━━━━━━━━━━━━━━━━━━━━━

*🎯 ЧТО Я УМЕЮ:*

├ 🎮 *Игры* — слоты, рулетка, КНБ, дуэли
├ 💰 *Экономика* — баланс, переводы, магазин
├ ⭐ *VIP статус* — бонусы и привилегии
├ 📢 *Общий сбор* — оповещение всех участников
├ 🛡️ *Модерация* — бан, мут, варны (для админов)
├ 🤖 *AI помощник* — отвечаю на вопросы
└ 💳 *Озон Банк* — пополнение баланса

━━━━━━━━━━━━━━━━━━━━━

*🗣️ КАК КО МНЕ ОБРАЩАТЬСЯ:*

Я понимаю любые формы обращения:

📝 *Текстовые команды:*
• `Нексус, оповести всех`
• `Nexus, общий сбор`
• `собери всех участников`
• `отметь всех в чате`
• `@username` — упомянуть пользователя

🎤 *Голосовые команды:*
• "Нексус, оповести всех"
• "Nexus, общий сбор"
• "Собери всех участников"

✨ *Достаточно просто сказать или написать — я пойму!*

━━━━━━━━━━━━━━━━━━━━━

*📌 БЫСТРЫЙ СТАРТ:*

├ /daily — получить бонус {START_BALANCE} монет
├ /slot 100 — сыграть в слот
├ /balance — проверить баланс
└ /all — оповестить всех участников

━━━━━━━━━━━━━━━━━━━━━

*🎁 ВАМ НАЧИСЛЕНО: {START_BALANCE} МОНЕТ!*

Нажми на кнопку ниже, чтобы начать 👇
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать использовать", callback_data="back_to_menu")],
        [InlineKeyboardButton(text="📢 Как оповестить всех?", callback_data="tag_help")]
    ])
    
    await message.answer(
        presentation_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """
🤖 *NEXUS Chat Manager — ПОМОЩЬ*

━━━━━━━━━━━━━━━━━━━━━

*🗣️ КАК ОБРАЩАТЬСЯ:*

Я понимаю команды без слеша!

📝 *Примеры текстовых команд:*
• `Нексус, оповести всех`
• `Nexus, общий сбор`
• `собери всех участников`
• `@username привет!`

🎤 *Голосовые команды:*
• Скажите "Нексус, оповести всех"
• Скажите "Nexus, общий сбор"

━━━━━━━━━━━━━━━━━━━━━

*📋 ОСНОВНЫЕ КОМАНДЫ:*

*💰 Экономика*
/balance — баланс
/daily — бонус дня
/transfer @user 100 — перевод

*🎮 Игры*
/slot 100 — слот
/roulette 100 красный — рулетка
/rps камень — КНБ
/duel @user 100 — дуэль

*👤 Профиль*
/profile — профиль
/shop — магазин
/vip — VIP статус

*📢 Оповещения*
/all — общий сбор
/tag @user — упомянуть
/tagrole админы — написать админам

━━━━━━━━━━━━━━━━━━━━━

*🤖 AI ПОМОЩНИК*
/ask вопрос — задай любой вопрос

━━━━━━━━━━━━━━━━━━━━━

✨ *Все команды работают и через меню!*
"""
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("about"))
async def cmd_about(message: types.Message):
    about_text = """
🤖 *NEXUS Chat Manager v5.0*

━━━━━━━━━━━━━━━━━━━━━

*📖 О БОТЕ:*

NEXUS Chat Manager — это многофункциональный бот для управления чатами, игр и экономики.

*🔧 ТЕХНОЛОГИИ:*
├ Python 3.11
├ Aiogram 3.x
├ SQLite
└ Docker

*👨‍💻 РАЗРАБОТЧИК:*
@A3incSTIGMAT

*🗣️ ОБРАЩЕНИЯ:*
• Нексус, Нэкс, Nexus
• Отметь, тэгни, упомяни, оповести
• Собери, созывай, общий сбор

*🎤 ГОЛОСОВЫЕ КОМАНДЫ:*
• "Нексус, оповести всех"
• "Nexus, общий сбор"

━━━━━━━━━━━━━━━━━━━━━

✨ *Спасибо, что используете NEXUS!*
"""
    await message.answer(about_text, parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    from utils.keyboards import main_menu
    await callback.message.edit_text(
        "🏠 *Главное меню NEXUS Chat Manager*\n\nВыберите действие:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )
    await callback.answer()
