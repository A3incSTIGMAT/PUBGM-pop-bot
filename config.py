"""
config.py — Конфигурация бота Nexus
Загружает переменные окружения из .env или из системы
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ==================== TELEGRAM ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required")

ADMIN_IDS = [
    int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",")
    if id.strip()
]

# ==================== DATABASE ====================
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/nexus.db")

# ==================== GAMES ====================
MIN_BET = int(os.getenv("MIN_BET", "10"))
MAX_BET = int(os.getenv("MAX_BET", "10000"))
DUEL_TIMEOUT = int(os.getenv("DUEL_TIMEOUT", "60"))
RATE_LIMIT_GAMES = int(os.getenv("RATE_LIMIT_GAMES", "30"))

# ==================== MODERATION ====================
MAX_WARN_COUNT = int(os.getenv("MAX_WARN_COUNT", "3"))
MAX_CLEAR_MESSAGES = int(os.getenv("MAX_CLEAR_MESSAGES", "100"))
MAX_MUTE_DAYS = int(os.getenv("MAX_MUTE_DAYS", "30"))
RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", "3"))

# ==================== ENVIRONMENT ====================
BOT_ENV = os.getenv("BOT_ENV", "development")
IS_PRODUCTION = BOT_ENV == "production"

# ==================== OZON BANK ====================
OZON_CARD_LAST4 = os.getenv("OZON_CARD_LAST4", "")
OZON_BANK_NAME = os.getenv("OZON_BANK_NAME", "Озон Банк")
OZON_RECEIVER = os.getenv("OZON_RECEIVER", "")
OZON_SBP_QR_URL = os.getenv("OZON_SBP_QR_URL", "")

# ==================== AI ====================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_ENABLED = bool(OPENROUTER_API_KEY)
