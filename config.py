import os
from dotenv import load_dotenv

load_dotenv()

# ==================== ОБЯЗАТЕЛЬНЫЕ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required!")

# ==================== АДМИНИСТРИРОВАНИЕ ====================
# Обычные администраторы (могут быть пустыми)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# 🔥 СУПЕР-АДМИН — ТОЛЬКО ТЫ (ВЛАДЕЛЕЦ)
SUPER_ADMIN_IDS = [895844198]  # Жёсткий хардкод твоего ID

# ==================== ПУТИ ====================
DATA_DIR = "/data"
DATABASE_PATH = os.getenv("DATABASE_PATH", f"{DATA_DIR}/nexus.db")
DB_PATH = DATABASE_PATH
LOG_FILE = os.getenv("LOG_FILE", f"{DATA_DIR}/nexus.log")

# ==================== ЭКОНОМИКА ====================
START_BALANCE = int(os.getenv("START_BALANCE", "1000"))
DAILY_BONUS = int(os.getenv("DAILY_BONUS", "500"))
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "250"))

# ==================== ИГРЫ ====================
SLOT_COST = int(os.getenv("SLOT_COST", "50"))
ROULETTE_MIN = int(os.getenv("ROULETTE_MIN", "50"))
DUEL_MIN = int(os.getenv("DUEL_MIN", "100"))
GAME_COMMISSION = float(os.getenv("GAME_COMMISSION", "0.05"))

# ==================== МОДЕРАЦИЯ ====================
MAX_WARN_COUNT = int(os.getenv("MAX_WARN_COUNT", "3"))

# ==================== VIP ====================
VIP_PRICE = int(os.getenv("VIP_PRICE", "5000"))
VIP_DURATION_DAYS = int(os.getenv("VIP_DURATION_DAYS", "30"))

# ==================== AI ====================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_ENABLED = os.getenv("AI_ENABLED", "False").lower() == "true"

# ==================== ДОНАТ ====================
DONATE_URL = os.getenv("DONATE_URL", "https://finance.ozon.ru/apps/sbp/ozonbankpay/019d2edd-64d5-7781-87ea-fea6bf40d6cf")
DONATE_RECEIVER = os.getenv("DONATE_RECEIVER", "Александр Б.")
DONATE_BANK = os.getenv("DONATE_BANK", "Озон Банк")

# ==================== ЛОГИРОВАНИЕ ====================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ==================== БЕЗОПАСНОСТЬ ====================
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-me")

# ==================== ОЗОН БАНК ====================
OZON_BANK_API_KEY = os.getenv("OZON_BANK_API_KEY", "")
OZON_BANK_NAME = os.getenv("OZON_BANK_NAME", "Озон Банк")
OZON_RECEIVER = os.getenv("OZON_RECEIVER", "")
OZON_CARD_LAST4 = os.getenv("OZON_CARD_LAST4", "")
OZON_SBP_QR_URL = os.getenv("OZON_SBP_QR_URL", "")

# ==================== СОЦСЕТИ ====================
TWITCH_URL = os.getenv("TWITCH_URL", "")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")

# ==================== БОТ ====================
BOT_USERNAME = os.getenv("BOT_USERNAME", "NEXUS_Manager_Official_bot")
MORNING_CLEANUP_HOUR = int(os.getenv("MORNING_CLEANUP_HOUR", "10"))
