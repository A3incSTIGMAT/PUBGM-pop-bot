# bot.py — PUBG Popularity Bot
import sqlite3
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)
import hashlib
import urllib.parse

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Подключаем настройки
try:
    from config import BOT_TOKEN, MERCHANT_ID, SECRET_1, SECRET_2
except ImportError:
    logger.error("❌ Не найден config.py — используй config.example.py как образец")
    exit()

# Имя базы
DB_NAME = "users.db"

def get_db():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            popular_points INTEGER DEFAULT 0,
            referrer_id INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_rewards (
            user_id INTEGER PRIMARY KEY,
            last_chicken DATE,
            last_motorcycle DATE
        )
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

def get_or_create_user(user_id, username, referrer_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)",
            (user_id, username, referrer_id)
        )
        if referrer_id:
            cursor.execute(
                "UPDATE users SET popular_points = popular_points + 10 WHERE user_id = ?",
                (referrer_id,)
            )
    conn.commit()
    conn.close()

def add_points(user_id, points):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET popular_points = popular_points + ? WHERE user_id = ?",
        (points, user_id)
    )
    conn.commit()
    conn.close()

def get_points(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT popular_points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def get_last_rewards(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT last_chicken, last_motorcycle FROM daily_rewards WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"chicken": row[0], "motorcycle": row[1]}
    return {"chicken": None, "motorcycle": None}

def update_last_reward(user_id, reward_type):
    today = date.today().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO daily_rewards (user_id, last_chicken, last_motorcycle)
        VALUES (?, 
                CASE WHEN ? = 'chicken' THEN ? ELSE COALESCE((SELECT last_chicken FROM daily_rewards WHERE user_id = ?), NULL) END,
                CASE WHEN ? = 'motorcycle' THEN ? ELSE COALESCE((SELECT last_motorcycle FROM daily_rewards WHERE user_id = ?), NULL) END
        )
    """, (user_id, reward_type, today, user_id, reward_type, today, user_id))
    conn.commit()
    conn.close()

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer_id = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].split("_")[1])
            if referrer_id == user.id:
                referrer_id = None
        except:
            referrer_id = None

    get_or_create_user(user.id, user.username, referrer_id)

    keyboard = [
        [InlineKeyboardButton("📊 Моя популярность", callback_data="popular")],
        [InlineKeyboardButton("🎁 Ежедневные награды", callback_data="daily")],
        [InlineKeyboardButton("📨 Рефералы", callback_data="ref")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="shop")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🎮 Привет, {user.first_name}! Добро пожаловать в битву популярности!",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "popular":
        points = get_points(user_id)
        await query.edit_message_text(f"🌟 Ваша популярность: {points} очков")

    elif query.data == "daily":
        status = get_last_rewards(user_id)
        today = date.today().isoformat()
        buttons = []
        if status["chicken"] != today:
            buttons.append(InlineKeyboardButton("🍗 Получить курицу (+10)", callback_data="get_chicken"))
        if status["motorcycle"] != today:
            buttons.append(InlineKeyboardButton("🏍 Получить мотоцикл (+200)", callback_data="get_motorcycle"))
        if not buttons:
            await query.edit_message_text("⏳ Вы уже получили все награды сегодня.")
            return
        reply_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text("🎁 Ежедневные награды:", reply_markup=reply_markup)

    elif query.data == "get_chicken":
        update_last_reward(user_id, "chicken")
        add_points(user_id, 10)
        await query.edit_message_text("✅ Вы получили курицу! +10 популярности")

    elif query.data == "get_motorcycle":
        update_last_reward(user_id, "motorcycle")
        add_points(user_id, 200)
        await query.edit_message_text("✅ Вы получили мотоцикл! +200 популярности")

    elif query.data == "ref":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        ref_link = f"https://t.me/PUBGPopBattleBot?start=ref_{user_id}"
        await query.edit_message_text(
            f"👥 Вы пригласили: {count} человек\n"
            f"🔗 Ваша реферальная ссылка:\n{ref_link}\n"
            f"🎁 Получаете 10 очков за каждого приглашённого!"
        )

    elif query.data == "shop":
        shop_text = """
🛒 **Магазин подарков:**
- 🏍 Мотоцикл: 10₽ → 200 очков
- 🏵 Слиток золота: 50₽ → 800 очков
- 🚗 Машинка: 100₽ → 2000 очков
- 💰 Денежная пушка: 150₽ → 3000 очков
- 💋 Воздушный поцелуй: 200₽ → 4000 очков
"""
        keyboard = [
            [InlineKeyboardButton("🏍 Мотоцикл (10₽)", callback_data="buy_motorcycle")],
            [InlineKeyboardButton("🏵 Слиток золота (50₽)", callback_data="buy_gold")],
            [InlineKeyboardButton("🚗 Машинка (100₽)", callback_data="buy_car")],
            [InlineKeyboardButton("💰 Денежная пушка (150₽)", callback_data="buy_money_gun")],
            [InlineKeyboardButton("💋 Воздушный поцелуй (200₽)", callback_data="buy_kiss")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(shop_text, reply_markup=reply_markup, parse_mode="Markdown")

    elif query.data.startswith("buy_"):
        item = query.data.split("_")[1]
        prices = {
            "motorcycle": 10,
            "gold": 50,
            "car": 100,
            "money_gun": 150,
            "kiss": 200
        }
        if item in prices:
            price = prices[item]
            payload = f"{user_id}_{item}"
            sign = hashlib.md5(f"{MERCHANT_ID}:{price}:{SECRET_1}:{payload}".encode()).hexdigest()
            url = f"https://free-kassa.ru/merchant/cash.php?m={MERCHANT_ID}&oa={price}&o={payload}&s={sign}&lang=ru"
            keyboard = [[InlineKeyboardButton("💳 Оплатить", url=url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Оплатите {price}₽ за {item}\n"
                "После оплаты очки будут начислены автоматически.",
                reply_markup=reply_markup
            )

# === ЗАПУСК ===
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("✅ Бот запущен и работает!")
    app.run_polling()

if __name__ == "__main__":
    main()
