import os
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime, timedelta

# === НАСТРОЙКА ТОКЕНА ===
TOKEN = "8364745841:AAF2g6-4_GVxZRpDzUh-qtatfxp5_gH17QI"

# Хранилище данных (в реальном проекте — используй базу)
users = {}

# Товары в магазине
items = {
    "chicken": {"name": "🐔 Курица", "price": 10, "pop": 10},
    "motorcycle": {"name": "🏍️ Мотоцикл", "price": 10, "pop": 200},
    "gold": {"name": "🏅 Слиток золота", "price": 20, "pop": 800},
    "car": {"name": "🚗 Машинка", "price": 50, "pop": 2000},
    "gun": {"name": "💰 Денежная пушка", "price": 70, "pop": 3000},
    "kiss": {"name": "💋 Воздушный поцелуй", "price": 90, "pop": 4000},
    "cup": {"name": "🏆 Кубок победителя", "price": 120, "pop": 6000},
    "plane": {"name": "✈️ Самолёт", "price": 500, "pop": 25000},
    "blimp": {"name": "🎈 Дирижабль", "price": 750, "pop": 50000},
    "helicopter": {"name": "🚁 Вертолёт", "price": 1500, "pop": 125000},
    "private_jet": {"name": "🛩️ Частный самолёт", "price": 3000, "pop": 300000},
}

# Получить пользователя
def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "id": user_id,
            "username": "Игрок",
            "pop": 0,
            "last_daily": None,
            "last_motorcycle": None,
            "referrals": 0,
            "referred_by": None
        }
    return users[user_id]

# Главное меню
async def start(update: Update, context):
    user = update.effective_user
    db_user = get_user(user.id)
    db_user["username"] = user.username or user.first_name

    # Обработка реферала
    if context.args and context.args[0].startswith("ref_"):
        ref_id = int(context.args[0].split("_")[1])
        if ref_id != user.id and ref_id in users:
            if db_user["referred_by"] is None:
                users[ref_id]["pop"] += 50
                db_user["referred_by"] = ref_id
                await context.bot.send_message(ref_id, "🎉 У вас новый реферал! +50 очков популярности!")

    keyboard = [
        [InlineKeyboardButton("🔥 Моя популярность", callback_data="my_pop")],
        [InlineKeyboardButton("🏆 Рейтинги", callback_data="rating")],
        [InlineKeyboardButton("💰 Магазин", callback_data="shop")],
        [InlineKeyboardButton("🎁 Подарить", callback_data="gift")],
        [InlineKeyboardButton("🤝 Рефералка", callback_data="ref")],
        [InlineKeyboardButton("🎉 Розыгрыши", callback_data="giveaway")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🎮 Добро пожаловать, {user.first_name}!\n"
        "Соревнуйся за популярность, дари мощь, взлетай в топ!\n\n"
        "Нажми кнопку ниже:",
        reply_markup=reply_markup
    )

# Обработка кнопок
async def button_handler(update: Update, context):
    query = update.callback_query
    user = query.from_user
    db_user = get_user(user.id)

    if query.data == "my_pop":
        text = (
            f"📊 Твоя популярность: {db_user['pop']} очков\n"
            f"🆔 Твой ID: {user.id}\n"
            f"🎯 Юзернейм: @{user.username or 'нет'}\n\n"
        )
        if db_user["last_daily"]:
            next_daily = datetime.fromisoformat(db_user["last_daily"]) + timedelta(days=1)
            if datetime.now() < next_daily:
                text += "🐔 Курица: недоступна (через 23ч 59м)\n"
            else:
                text += "🐔 Курица: доступна! /daily\n"
        else:
            text += "🐔 Курица: доступна! /daily\n"

        if db_user["last_motorcycle"]:
            next_motor = datetime.fromisoformat(db_user["last_motorcycle"]) + timedelta(days=1)
            if datetime.now() < next_motor:
                text += "🏍️ Мотоцикл: недоступен (через 23ч 59м)\n"
            else:
                text += "🏍️ Мотоцикл: доступен! /motorcycle\n"
        else:
            text += "🏍️ Мотоцикл: доступен! /motorcycle\n"

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]))

    elif query.data == "rating":
        top = sorted(users.values(), key=lambda x: x["pop"], reverse=True)[:10]
        text = "🏆 Топ-10 игроков:\n\n"
        for i, u in enumerate(top, 1):
            username = u["username"]
            text += f"{i}. @{username} — {u['pop']} очков\n"
        text += "\nОбновлено: только что"
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]))

    elif query.data == "shop":
        text = "🛒 Магазин популярности:\n\n"
        for item_id, item in items.items():
            text += f"{item['name']} — {item['price']}₽ ({item['pop']} очков)\n"
        text += "\nОплата: TON (The Open Network)\n"
        text += "Отправь нужную сумму на кошелёк:\n"
        text += "`UQAx2c...xyz123` (вставь свой TON-адрес)\n"
        text += "После оплаты отправь хэш транзакции админу."
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]))

    elif query.data == "gift":
        await query.message.edit_text(
            "🎁 Чтобы подарить популярность:\n"
            "Напиши: `/gift @username 500`\n"
            "Где 500 — количество очков.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
            ])
        )

    elif query.data == "ref":
        ref_link = f"https://t.me/PUBGPopBattleBot?start=ref_{user.id}"
        text = (
            f"🤝 Рефералка\n\n"
            f"Приглашай друзей и получай +50 очков за каждого!\n\n"
            f"📌 Твоя ссылка:\n{ref_link}\n\n"
            f"👥 Приглашено: {db_user['referrals']} человек"
        )
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]))

    elif query.data == "giveaway":
        text = (
            "🎉 Еженедельный розыгрыш\n\n"
            "Каждый понедельник в 20:00 (МСК)\n\n"
            "Призы:\n"
            "1 место: +50 000 очков + вертолёт\n"
            "2 место: +30 000 очков\n"
            "3 место: +20 000 очков\n"
            "4–10: +10 000 очков\n\n"
            "Участвуют все, кто сделал хотя бы 1 покупку."
        )
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]))

    elif query.data == "back":
        await query.message.edit_text(
            "🎮 Главное меню:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔥 Моя популярность", callback_data="my_pop")],
                [InlineKeyboardButton("🏆 Рейтинги", callback_data="rating")],
                [InlineKeyboardButton("💰 Магазин", callback_data="shop")],
                [InlineKeyboardButton("🎁 Подарить", callback_data="gift")],
                [InlineKeyboardButton("🤝 Рефералка", callback_data="ref")],
                [InlineKeyboardButton("🎉 Розыгрыши", callback_data="giveaway")],
            ])
        )

# Ежедневная курица
async def daily(update: Update, context):
    user = update.effective_user
    db_user = get_user(user.id)
    now = datetime.now()

    if db_user["last_daily"]:
        last = datetime.fromisoformat(db_user["last_daily"])
        if now - last < timedelta(days=1):
            await update.message.reply_text("🐔 Курица доступна раз в день! Попробуй завтра.")
            return

    db_user["pop"] += 10
    db_user["last_daily"] = now.isoformat()
    await update.message.reply_text("🎉 Вы получили 10 очков популярности за курицу!")

# Мотоцикл
async def motorcycle(update: Update, context):
    user = update.effective_user
    db_user = get_user(user.id)
    now = datetime.now()

    if db_user["last_motorcycle"]:
        last = datetime.fromisoformat(db_user["last_motorcycle"])
        if now - last < timedelta(days=1):
            await update.message.reply_text("🏍️ Мотоцикл доступен раз в день! Попробуй завтра.")
            return

    db_user["pop"] += 200
    db_user["last_motorcycle"] = now.isoformat()
    await update.message.reply_text("🎉 Вы получили 200 очков популярности за мотоцикл!")

# Подарить популярность
async def gift(update: Update, context):
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /gift @username 500")
        return

    target_username = context.args[0].lstrip("@")
    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("Количество должно быть числом.")
        return

    user = update.effective_user
    db_user = get_user(user.id)

    if amount <= 0:
        await update.message.reply_text("Минимум — 1 очко.")
        return

    if db_user["pop"] < amount:
        await update.message.reply_text("❌ Недостаточно очков популярности.")
        return

    # Найти получателя
    target_id = None
    for uid, udata in users.items():
        if udata["username"] == target_username:
            target_id = uid
            break

    if not target_id:
        await update.message.reply_text(f"❌ Игрок @{target_username} не найден.")
        return

    # Перевод
    db_user["pop"] -= amount
    users[target_id]["pop"] += amount

    await update.message.reply_text(f"✅ Вы подарили {amount} очков игроку @{target_username}!")
    try:
        await context.bot.send_message(target_id, f"🎉 Вам подарили {amount} очков популярности от @{user.username or user.first_name}!")
    except:
        pass

# Рефералка
async def ref(update: Update, context):
    user = update.effective_user
    db_user = get_user(user.id)
    ref_link = f"https://t.me/PUBGPopBattleBot?start=ref_{user.id}"
    await update.message.reply_text(
        f"🤝 Рефералка\n\n"
        f"Приглашай друзей:\n{ref_link}\n\n"
        f"Приглашено: {db_user['referrals']} человек\n"
        f"Награда: +50 очков за каждого"
    )

# Топ
async def top(update: Update, context):
    top = sorted(users.values(), key=lambda x: x["pop"], reverse=True)[:10]
    text = "🏆 Топ-10 игроков:\n\n"
    for i, u in enumerate(top, 1):
        username = u["username"]
        text += f"{i}. @{username} — {u['pop']} очков\n"
    await update.message.reply_text(text)

# Запуск бота
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("motorcycle", motorcycle))
    app.add_handler(CommandHandler("gift", gift))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("top", top))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()
