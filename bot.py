from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import time
import database
from config import BOT_TOKEN

database.init_db()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

GIFTS = {
    "мотоцикл": (10, 200),
    "слиток": (20, 800),
    "машинка": (50, 2000),
    "пушка": (70, 3000),
    "поцелуй": (90, 4000),
    "кубок": (120, 6000),
    "самолет": (500, 25000),
    "дирижабль": (750, 50000),
    "вертолет": (1500, 125000),
    "частный": (3000, 300000)
}

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    args = message.text.split()
    ref_id = int(args[1][3:]) if len(args) > 1 and args[1].startswith("ref") else None

    result = database.add_user(user_id, username, full_name, ref_id)
    text = f"🎮 Привет, {full_name}!\n\nТы в PUBG Popularity Battle!\nСобирай очки, дари подарки, побеждай в топах!"

    if result:
        referrer_id, bonus = result
        await bot.send_message(referrer_id, f"🎁 Новый реферал! Ты получил +{bonus} очков популярности!")

    await message.answer(text, reply_markup=main_menu())

def main_menu():
    kb = [
        [InlineKeyboardButton(text="🎁 Магазин", callback_data="shop")],
        [InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top")],
        [InlineKeyboardButton(text="🐔 Получить курицу", callback_data="chicken")],
        [InlineKeyboardButton(text="🏍 Получить мотоцикл", callback_data="bike")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data == "top")
async def show_top(call: types.CallbackQuery):
    top_users = database.get_top_users(10)
    text = "🏆 Топ 10 игроков:\n\n"
    for i, u in enumerate(top_users, 1):
        name = u[0] or u[1]
        text += f"{i}. @{name} — {u[2]} очков\n"
    await call.message.answer(text)

@dp.callback_query(F.data == "chicken")
async def daily_chicken(call: types.CallbackQuery):
    user = database.get_user(call.from_user.id)
    now = int(time.time())
    if user and user["last_daily_chicken"] and now - user["last_daily_chicken"] < 86400:
        await call.answer("Курица доступна раз в день!")
        return
    database.update_popularity(call.from_user.id, 10)
    conn = sqlite3.connect("db.sqlite3")
    conn.execute("UPDATE users SET last_daily_chicken = ? WHERE user_id = ?", (now, call.from_user.id))
    conn.commit()
    conn.close()
    await call.answer("🎉 +10 очков популярности! Курица получена.")
    await call.message.answer("🐔 Вы получили курицу! +10 популярности")

@dp.callback_query(F.data == "bike")
async def daily_bike(call: types.CallbackQuery):
    user = database.get_user(call.from_user.id)
    now = int(time.time())
    if user and user["last_daily_bike"] and now - user["last_daily_bike"] < 86400:
        await call.answer("Мотоцикл доступен раз в день!")
        return
    database.update_popularity(call.from_user.id, 200)
    conn = sqlite3.connect("db.sqlite3")
    conn.execute("UPDATE users SET last_daily_bike = ? WHERE user_id = ?", (now, call.from_user.id))
    conn.commit()
    conn.close()
    await call.answer("🎉 +200 очков популярности! Мотоцикл получен.")
    await call.message.answer("🏍 Вы получили мотоцикл! +200 популярности")

@dp.callback_query(F.data == "shop")
async def shop(call: types.CallbackQuery):
    text = "🛒 Магазин подарков:\n\n"
    for name, (price, pop) in GIFTS.items():
        text += f"• {name}: {price}₽ → {pop} очков\n"
    text += "\nЧтобы купить: /buy мотоцикл"
    await call.message.answer(text)

@dp.message(F.text.startswith("/buy"))
async def buy_item(message: types.Message):
    try:
        _, item = message.text.split(" ", 1)
        if item not in GIFTS:
            await message.answer("❌ Нет такого предмета.")
            return
        price, pop = GIFTS[item]
        user_id = message.from_user.id
        order_id = f"pop_{user_id}_{int(time.time())}"
        sign = __import__('hashlib').md5(f"{FK_ID}:{price}:Байкал:{order_id}".encode()).hexdigest()
        url = f"https://pay.freekassa.ru/?m={FK_ID}&oa={price}&o={order_id}&s={sign}&us_user_id={user_id}&us_popularity={pop}"
        database.add_payment(user_id, price, pop, "freekassa")
        await message.answer(f"💳 Оплатите {price}₽:\n{url}")
    except Exception as e:
        await message.answer("❌ Используйте: /buy мотоцикл")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
