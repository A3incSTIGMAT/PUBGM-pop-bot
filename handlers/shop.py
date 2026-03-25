"""
Магазин подарков
"""

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import get_balance, spend_balance, add_free_balance
from utils.logger import log_economy
from utils.helpers import delete_after_response

router = Router()
bot: Bot = None

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

# Состояния для покупки
class GiftState(StatesGroup):
    waiting_for_target = State()
    waiting_for_gift = State()

# Список подарков
GIFTS = {
    "rose": {"name": "🌹 Роза", "price": 10, "emoji": "🌹", "description": "Красивая роза"},
    "cake": {"name": "🍰 Торт", "price": 50, "emoji": "🍰", "description": "Вкусный торт"},
    "heart": {"name": "❤️ Сердце", "price": 100, "emoji": "❤️", "description": "Символ любви"},
    "star": {"name": "⭐ Звезда", "price": 200, "emoji": "⭐", "description": "Сияющая звезда"},
    "gift_box": {"name": "🎁 Подарок", "price": 300, "emoji": "🎁", "description": "Загадочный подарок"},
    "diamond": {"name": "💎 Алмаз", "price": 500, "emoji": "💎", "description": "Драгоценный алмаз"},
    "crown": {"name": "👑 Корона", "price": 1000, "emoji": "👑", "description": "Королевская корона"},
    "rocket": {"name": "🚀 Ракета", "price": 5000, "emoji": "🚀", "description": "Космическая ракета"}
}

def get_shop_menu() -> InlineKeyboardMarkup:
    """Клавиатура магазина"""
    buttons = []
    row = []
    
    for gift_id, gift in GIFTS.items():
        row.append(InlineKeyboardButton(
            text=f"{gift['emoji']} {gift['name']} - {gift['price']} NCoin",
            callback_data=f"shop_select_{gift_id}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_gift_confirm_menu(gift_id: str, gift_name: str, gift_price: int, target: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения покупки"""
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"shop_confirm_{gift_id}_{target}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="shop_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("shop"))
async def cmd_shop(message: Message):
    """Открыть магазин подарков"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = get_balance(user_id, chat_id)
    
    response = await message.answer(
        f"🎁 **Магазин подарков NEXUS**\n\n"
        f"💰 Ваш баланс: {balance} NCoin\n\n"
        f"Выберите подарок:",
        reply_markup=get_shop_menu()
    )
    await delete_after_response(response, message, delay=60)

@router.callback_query(lambda c: c.data == "shop_back")
async def shop_back(callback: CallbackQuery):
    """Назад в магазин"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    await callback.message.edit_text(
        f"🎁 **Магазин подарков NEXUS**\n\n"
        f"💰 Ваш баланс: {balance} NCoin\n\n"
        f"Выберите подарок:",
        reply_markup=get_shop_menu()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("shop_select_"))
async def shop_select(callback: CallbackQuery, state: FSMContext):
    """Выбор подарка"""
    gift_id = callback.data.replace("shop_select_", "")
    gift = GIFTS.get(gift_id)
    
    if not gift:
        await callback.answer("❌ Подарок не найден")
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    balance = get_balance(user_id, chat_id)
    
    if balance < gift["price"]:
        await callback.message.edit_text(
            f"❌ **Недостаточно NCoin!**\n\n"
            f"💰 Ваш баланс: {balance} NCoin\n"
            f"🎁 Стоимость: {gift['price']} NCoin\n\n"
            f"💡 Получите бонус: /daily\n"
            f"⭐ Пополните баланс: /buy",
            reply_markup=get_shop_menu()
        )
        await callback.answer()
        return
    
    await state.update_data(selected_gift=gift_id)
    await state.set_state(GiftState.waiting_for_target)
    
    await callback.message.edit_text(
        f"🎁 **Вы выбрали:** {gift['emoji']} {gift['name']}\n"
        f"💰 Стоимость: {gift['price']} NCoin\n\n"
        f"📝 **Введите @username получателя:**\n"
        f"Пример: @ivan\n\n"
        f"❌ Для отмены напишите /cancel",
        reply_markup=None
    )
    await callback.answer()

@router.message(Command("cancel"), GiftState.waiting_for_target)
async def cancel_gift(message: Message, state: FSMContext):
    """Отмена покупки"""
    await state.clear()
    await message.answer("❌ Покупка подарка отменена.")

@router.message(GiftState.waiting_for_target)
async def process_gift_target(message: Message, state: FSMContext):
    """Обработка ввода получателя"""
    if not message.text:
        return
    
    target_username = message.text.strip().replace("@", "")
    if not target_username:
        await message.answer("❌ Введите корректный @username получателя")
        return
    
    data = await state.get_data()
    gift_id = data.get("selected_gift")
    
    if not gift_id:
        await state.clear()
        await message.answer("❌ Ошибка. Попробуйте снова /shop")
        return
    
    gift = GIFTS.get(gift_id)
    if not gift:
        await state.clear()
        await message.answer("❌ Ошибка. Подарок не найден")
        return
    
    # Находим пользователя в чате
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
        await message.answer(f"❌ Пользователь @{target_username} не найден в чате.\n\nПопробуйте ещё раз или введите /cancel для отмены.")
        return
    
    # Сохраняем получателя
    await state.update_data(target_id=target_id, target_name=target_name, target_username=target_username)
    
    # Отправляем подтверждение
    keyboard = get_gift_confirm_menu(gift_id, gift["name"], gift["price"], target_username)
    await message.answer(
        f"🎁 **Подтверждение покупки**\n\n"
        f"Подарок: {gift['emoji']} {gift['name']}\n"
        f"Получатель: @{target_username}\n"
        f"💰 Стоимость: {gift['price']} NCoin\n\n"
        f"✅ Подтвердите покупку:",
        reply_markup=keyboard
    )

@router.callback_query(lambda c: c.data.startswith("shop_confirm_"))
async def shop_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение покупки"""
    parts = callback.data.replace("shop_confirm_", "").split("_")
    gift_id = parts[0]
    target_username = "_".join(parts[1:]) if len(parts) > 1 else ""
    
    data = await state.get_data()
    target_id = data.get("target_id")
    gift = GIFTS.get(gift_id)
    
    if not gift or not target_id:
        await callback.message.edit_text("❌ Ошибка. Попробуйте снова /shop")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # Проверяем баланс
    balance = get_balance(user_id, chat_id)
    if balance < gift["price"]:
        await callback.message.edit_text(
            f"❌ **Недостаточно NCoin!**\n\n"
            f"💰 Ваш баланс: {balance} NCoin\n"
            f"🎁 Стоимость: {gift['price']} NCoin",
            reply_markup=get_shop_menu()
        )
        await state.clear()
        await callback.answer()
        return
    
    # Списываем средства
    if not spend_balance(user_id, chat_id, gift["price"]):
        await callback.message.edit_text("❌ Ошибка при списании средств")
        await state.clear()
        await callback.answer()
        return
    
    # Отправляем уведомление отправителю
    await callback.message.edit_text(
        f"✅ **Подарок отправлен!**\n\n"
        f"{gift['emoji']} {gift['name']} → @{target_username}\n"
        f"💰 С вас списано: {gift['price']} NCoin\n"
        f"💎 Ваш баланс: {get_balance(user_id, chat_id)} NCoin",
        reply_markup=get_shop_menu()
    )
    
    # Отправляем уведомление получателю
    try:
        await bot.send_message(
            target_id,
            f"🎁 **Вам подарили подарок!**\n\n"
            f"{gift['emoji']} {gift['name']} от {callback.from_user.full_name}\n"
            f"💝 Наслаждайтесь!"
        )
    except:
        pass
    
    log_economy(callback.from_user.full_name, f"подарил {gift['name']}", gift["price"], target_username)
    
    await state.clear()
    await callback.answer()
