import os
from dotenv import load_dotenv

load_dotenv()

# ==================== ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================== АДМИНИСТРИРОВАНИЕ ====================
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ==================== ПУТИ ДЛЯ AMVERA ====================
DATA_DIR = "/data"
DB_PATH = os.getenv("DATABASE_PATH", f"{DATA_DIR}/nexus.db")
LOG_FILE = os.getenv("LOG_FILE", f"{DATA_DIR}/nexus.log")

# ==================== ЭКОНОМИКА ====================
START_BALANCE = int(os.getenv("START_BALANCE", "1000"))
DAILY_BONUS = int(os.getenv("DAILY_BONUS", "500"))
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "250"))

# ==================== ИГРЫ ====================
SLOT_COST = int(os.getenv("SLOT_COST", "50"))
ROULETTE_MIN = int(os.getenv("ROULETTE_MIN", "50"))
DUEL_MIN = int(os.getenv("DUEL_MIN", "100"))

# ==================== МОДЕРАЦИЯ ====================
MAX_WARN_COUNT = int(os.getenv("MAX_WARN_COUNT", "3"))

# ==================== VIP ====================
VIP_PRICE = int(os.getenv("VIP_PRICE", "5000"))
VIP_DURATION_DAYS = int(os.getenv("VIP_DURATION_DAYS", "30"))

# ==================== ЛОГИРОВАНИЕ ====================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ==================== БЕЗОПАСНОСТЬ ====================
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-me")

# ==================== ОЗОН БАНК (опционально) ====================
OZON_BANK_API_KEY = os.getenv("OZON_BANK_API_KEY", "")
OZON_BANK_NAME = os.getenv("OZON_BANK_NAME", "Озон Банк")
OZON_RECEIVER = os.getenv("OZON_RECEIVER", "")
OZON_CARD_LAST4 = os.getenv("OZON_CARD_LAST4", "")
OZON_SBP_QR_URL = os.getenv("OZON_SBP_QR_URL", "")

# ==================== AI (опционально) ====================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ==================== ПРОВЕРКА ТОКЕНА ====================
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required! Add it to environment variables.")
