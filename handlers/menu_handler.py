"""
Обработчик меню и callback-запросов
"""

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from handlers.roles import get_user_role
from keyboards.main_menu import (
    get_main_menu, get_profile_menu, get_economy_menu,
    get_games_menu, get_moderation_menu, get_stats_menu,
    get_social_menu, get_vip_menu, get_ai_menu, get_help_menu,
    get_back_menu, get_buy_menu, get_requisites_menu, get_requisites_text
)
from database.db import get_balance, get_user_stats
from config import OZON_CARD_LAST4, OZON_BANK_NAME, OZON_RECEIVER, OZON_SBP_QR_URL

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Открыть главное меню"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    role = await get_user_role(chat_id, user_id)
    
    await message.answer(
        "🏠 **Главное меню NEXUS**\n\n"
        "Выберите категорию:",
        reply_markup=get_main_menu(role)
    )

# ========== ОБРАБОТЧИКИ НАВИГАЦИИ ==========

@router.callback_query(lambda c: c.data == "menu_back_main")
async def menu_back_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    role = await get_user_role(chat_id, user_id)
    
    await callback.message.edit_text(
        "🏠 **Главное меню NEXUS**\n\n"
        "Выберите категорию:",
        reply_markup=get_main_menu(role)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    """Меню профиля"""
    await callback.message.edit_text(
        "👤 **Профиль**\n\n"
        "Выберите действие:",
        reply_markup=get_profile_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_economy")
async def menu_economy(callback: CallbackQuery):
    """Меню экономики"""
    await callback.message.edit_text(
        "💰 **Экономика NEXUS**\n\n"
        "Валюта: NCoin\n"
        "1 ₽ = 1 NCoin\n\n"
        "Выберите действие:",
        reply_markup=get_economy_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_games")
async def menu_games(callback: CallbackQuery):
    """Меню игр"""
    await callback.message.edit_text(
        "🎮 **Игры NEXUS**\n\n"
        "Выберите игру:",
        reply_markup=get_games_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_moderation")
async def menu_moderation(callback: CallbackQuery):
    """Меню модерации"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    role = await get_user_role(chat_id, user_id)
    is_admin = role in ['admin', 'creator', 'global_admin']
    
    await callback.message.edit_text(
        "🛡 **Модерация**\n\n"
        "Выберите действие:",
        reply_markup=get_moderation_menu(is_admin)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    """Меню статистики"""
    await callback.message.edit_text(
        "📊 **Статистика**\n\n"
        "Выберите тип статистики:",
        reply_markup=get_stats_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_social")
async def menu_social(callback: CallbackQuery):
    """Меню социальных функций"""
    await callback.message.edit_text(
        "🎁 **Социальные функции**\n\n"
        "Выберите действие:",
        reply_markup=get_social_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_vip")
async def menu_vip(callback: CallbackQuery):
    """Меню VIP-статуса"""
    await callback.message.edit_text(
        "👑 **VIP-статус NEXUS**\n\n"
        "💰 Цена: 500 NCoin\n"
        "⏱ Длительность: 30 дней\n\n"
        "💎 **Преимущества:**\n"
        "• +25% к ежедневному бонусу\n"
        "• Эксклюзивные подарки\n"
        "• Цветное имя в чате\n"
        "• Доступ к VIP-играм\n\n"
        "➡️ Для покупки используйте /vip",
        reply_markup=get_vip_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_ai")
async def menu_ai(callback: CallbackQuery):
    """Меню AI-помощника"""
    await callback.message.edit_text(
        "🤖 **AI-помощник NEXUS**\n\n"
        "Задайте любой вопрос!\n\n"
        "📌 **Команды:**\n"
        "• /ask [вопрос] — быстрый вопрос\n"
        "• /ai — диалог с AI\n\n"
        "💡 **Примеры:**\n"
        "/ask как получить VIP?\n"
        "/ask что такое NCoin?\n"
        "/ask как играть в рулетку?",
        reply_markup=get_ai_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_requisites")
async def menu_requisites(callback: CallbackQuery):
    """Показать реквизиты"""
    text = get_requisites_text()
    await callback.message.edit_text(
        text,
        reply_markup=get_requisites_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_buy")
async def menu_buy(callback: CallbackQuery):
    """Меню покупки NCoin"""
    await callback.message.edit_text(
        "💎 **Купить NCoin**\n\n"
        "Выберите сумму:\n"
        "💰 1 ₽ = 1 NCoin\n\n"
        "💳 После оплаты нажмите 'Я оплатил(а)'",
        reply_markup=get_buy_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    """Меню помощи"""
    await callback.message.edit_text(
        "❓ **Помощь NEXUS**\n\n"
        "Выберите раздел:",
        reply_markup=get_help_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "menu_about")
async def menu_about(callback: CallbackQuery):
    """Информация о боте"""
    await callback.message.edit_text(
        "ℹ️ **О NEXUS**\n\n"
        "🤖 NEXUS — интеллектуальный чат-менеджер для Telegram.\n\n"
        "✅ **Возможности:**\n"
        "• 🛡 Модерация\n"
        "• 💰 Экономика (NCoin)\n"
        "• 🎮 Игры\n"
        "• 📊 Статистика\n"
        "• 🤖 AI-помощник\n"
        "• 🔐 Защита от спама\n\n"
        "💳 **Реквизиты:**\n"
        f"🏦 {OZON_BANK_NAME}\n"
        f"💳 Карта: •••• {OZON_CARD_LAST4}\n"
        f"👤 {OZON_RECEIVER}\n\n"
        "🚀 **Разработчик:** @A3incSTIGMAT",
        reply_markup=get_back_menu()
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ПРОФИЛЯ ==========

@router.callback_query(lambda c: c.data == "profile_balance")
async def profile_balance(callback: CallbackQuery):
    """Показать баланс"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    await callback.message.edit_text(
        f"💰 **Ваш баланс:** {balance} NCoin\n\n"
        f"💡 Получить бонус: /daily\n"
        f"💳 Пополнить: /pay",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_stats")
async def profile_stats(callback: CallbackQuery):
    """Показать статистику"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    stats = get_user_stats(user_id, chat_id)
    
    if stats:
        text = (
            f"📊 **Ваша статистика**\n\n"
            f"💰 Баланс: {stats['balance']} NCoin\n"
            f"💬 Сообщений: {stats['total_messages']}\n"
            f"👑 VIP: {'Да' if stats['is_vip'] else 'Нет'}\n"
            f"⭐ Репутация: {stats['reputation']}\n"
            f"🎂 ДР: {stats['birthday'] or 'не указан'}"
        )
    else:
        text = "📊 Статистика пока пуста. Напишите несколько сообщений!"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_birthday")
async def profile_birthday(callback: CallbackQuery):
    """Установка дня рождения"""
    await callback.message.edit_text(
        "🎂 **Установка дня рождения**\n\n"
        "Используйте команду /setbirthday для открытия календаря",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_role")
async def profile_role(callback: CallbackQuery):
    """Показать роль"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    role = await get_user_role(chat_id, user_id)
    
    role_names = {
        'global_admin': '🌍 Глобальный супер-админ',
        'creator': '👑 Владелец чата',
        'admin': '🛡 Администратор Telegram',
        'moderator': '🔨 Модератор бота',
        'user': '👤 Обычный участник'
    }
    
    await callback.message.edit_text(
        f"👑 **Ваша роль:** {role_names.get(role, 'Обычный участник')}",
        reply_markup=get_back_menu()
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ЭКОНОМИКИ ==========

@router.callback_query(lambda c: c.data == "eco_balance")
async def eco_balance(callback: CallbackQuery):
    """Показать баланс"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    await callback.message.edit_text(
        f"💰 **Ваш баланс:** {balance} NCoin\n\n"
        f"💡 Получить бонус: /daily\n"
        f"💳 Пополнить: /pay",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_daily")
async def eco_daily(callback: CallbackQuery):
    """Ежедневный бонус"""
    await callback.message.edit_text(
        "🎁 **Ежедневный бонус**\n\n"
        "Используйте команду /daily для получения бонуса",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_gift")
async def eco_gift(callback: CallbackQuery):
    """Подарить NCoin"""
    await callback.message.edit_text(
        "🎁 **Подарить NCoin**\n\n"
        "Используйте команду /gift @username [сумма]\n"
        "Пример: /gift @ivan 50",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_top")
async def eco_top(callback: CallbackQuery):
    """Топ богачей"""
    await callback.message.edit_text(
        "🏆 **Топ богачей**\n\n"
        "Используйте команду /top для просмотра топа",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_buy")
async def eco_buy(callback: CallbackQuery):
    """Купить NCoin"""
    await callback.message.edit_text(
        "💎 **Купить NCoin**\n\n"
        "Выберите сумму:",
        reply_markup=get_buy_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "eco_requisites")
async def eco_requisites(callback: CallbackQuery):
    """Реквизиты"""
    text = get_requisites_text()
    await callback.message.edit_text(
        text,
        reply_markup=get_requisites_menu()
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ РЕКВИЗИТОВ ==========

@router.callback_query(lambda c: c.data == "copy_requisites")
async def copy_requisites(callback: CallbackQuery):
    """Копирование реквизитов"""
    text = f"Озон Банк, карта •••• {OZON_CARD_LAST4}, {OZON_RECEIVER}"
    await callback.answer(text, show_alert=True)

@router.callback_query(lambda c: c.data == "pay_qr")
async def pay_qr(callback: CallbackQuery):
    """Показать QR-код для оплаты"""
    if OZON_SBP_QR_URL:
        await callback.message.edit_text(
            f"📱 **Оплата по QR-коду**\n\n"
            f"Отсканируйте QR-код в приложении любого банка:\n\n"
            f"🔗 [Ссылка на QR-код]({OZON_SBP_QR_URL})\n\n"
            f"💳 После оплаты нажмите 'Я оплатил(а)'",
            reply_markup=get_requisites_menu(),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "❌ QR-код временно недоступен.\n"
            "Используйте реквизиты для перевода.",
            reply_markup=get_requisites_menu()
        )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ПОКУПКИ ==========

@router.callback_query(lambda c: c.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    """Обработка выбора суммы для покупки"""
    amount = int(callback.data.replace("buy_", ""))
    
    text = (
        f"💎 **Покупка {amount} NCoin**\n\n"
        f"💰 Сумма к оплате: {amount} ₽\n\n"
        f"🏦 **Реквизиты для оплаты:**\n"
        f"Банк: {OZON_BANK_NAME}\n"
        f"Карта: •••• {OZON_CARD_LAST4}\n"
        f"Получатель: {OZON_RECEIVER}\n\n"
        f"📝 **Назначение платежа:** Пополнение NEXUS\n\n"
        f"💡 **Инструкция:**\n"
        f"1. Переведите {amount} ₽ на указанную карту\n"
        f"2. В назначении платежа укажите: Пополнение NEXUS\n"
        f"3. Нажмите кнопку 'Я оплатил(а)'\n"
        f"4. Администратор проверит оплату и начислит NCoin"
    )
    
    if OZON_SBP_QR_URL:
        text += f"\n\n📱 Или оплатите по QR-коду: [Ссылка]({OZON_SBP_QR_URL})"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ПОМОЩИ ==========

@router.callback_query(lambda c: c.data == "help_commands")
async def help_commands(callback: CallbackQuery):
    """Справка по командам"""
    await callback.message.edit_text(
        "📖 **Список команд**\n\n"
        "👤 **Пользовательские:**\n"
        "/start — приветствие\n"
        "/help — справка\n"
        "/menu — главное меню\n"
        "/stats — моя статистика\n"
        "/balance — баланс NCoin\n"
        "/daily — ежедневный бонус\n"
        "/setbirthday — день рождения\n"
        "/report — анонимная жалоба\n\n"
        "🎮 **Игры:**\n"
        "/rps — камень-ножницы-бумага\n"
        "/roulette — рулетка\n\n"
        "🤖 **AI:**\n"
        "/ask — быстрый вопрос\n"
        "/ai — диалог с AI\n\n"
        "🛡 **Админ:**\n"
        "/all — отметить всех\n"
        "/ban — забанить\n"
        "/mute — заглушить\n"
        "/setup — настройка\n"
        "/setlogchannel — лог-канал",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "help_games")
async def help_games(callback: CallbackQuery):
    """Справка по играм"""
    await callback.message.edit_text(
        "🎮 **Игры NEXUS**\n\n"
        "🪨 **Камень-ножницы-бумага:** /rps\n"
        "• Выберите свой ход из кнопок\n"
        "• Бот выбирает случайно\n\n"
        "🎲 **Рулетка:** /roulette\n"
        "• Выберите сумму ставки\n"
        "• Выберите цвет (красное/черное)\n"
        "• Выигрыш x2\n\n"
        "⚔️ **Дуэль:** скоро\n"
        "🎰 **Слот-машина:** скоро",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "help_economy")
async def help_economy(callback: CallbackQuery):
    """Справка по экономике"""
    await callback.message.edit_text(
        "💰 **Экономика NEXUS**\n\n"
        "**Валюта:** NCoin\n\n"
        "📌 **Команды:**\n"
        "/balance — баланс\n"
        "/daily — бонус 50 NCoin (раз в 24ч)\n"
        "/gift — подарить NCoin\n"
        "/top — топ богачей\n\n"
        "💳 **Пополнение:**\n"
        "/pay [сумма] — реквизиты для оплаты\n"
        "1 ₽ = 1 NCoin",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "help_moderation")
async def help_moderation(callback: CallbackQuery):
    """Справка по модерации"""
    await callback.message.edit_text(
        "🛡 **Модерация NEXUS**\n\n"
        "📌 **Команды:**\n"
        "/all — отметить всех участников\n"
        "/ban — забанить (ответом на сообщение)\n"
        "/mute — заглушить на время\n"
        "/setup — мастер настройки\n"
        "/setlogchannel — установить лог-канал\n"
        "/setwelcome — настроить приветствие\n\n"
        "👥 **Модераторы:**\n"
        "/addmod — назначить модератора\n"
        "/removemod — удалить модератора\n"
        "/mods — список модераторов",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "help_requisites")
async def help_requisites(callback: CallbackQuery):
    """Справка по реквизитам"""
    text = get_requisites_text()
    await callback.message.edit_text(
        text,
        reply_markup=get_requisites_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "help_ai")
async def help_ai(callback: CallbackQuery):
    """Справка по AI помощнику"""
    await callback.message.edit_text(
        "🤖 **AI-помощник NEXUS**\n\n"
        "📌 **Команды:**\n"
        "/ask [вопрос] — быстрый вопрос\n"
        "/ai — диалог с AI\n\n"
        "💡 **Что умеет:**\n"
        "• Отвечать на вопросы о NEXUS\n"
        "• Помогать с настройкой бота\n"
        "• Давать советы\n"
        "• Рассказывать о функциях\n\n"
        "📝 **Примеры:**\n"
        "/ask как получить VIP?\n"
        "/ask что такое NCoin?\n"
        "/ask как играть в рулетку?\n\n"
        "❓ Вопросы задавайте на русском языке",
        reply_markup=get_back_menu()
    )
    await callback.answer()
