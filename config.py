import os

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/nexus.db")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

# Redis (опционально)
REDIS_URL = os.getenv("REDIS_URL", None)

# Game settings
MIN_BET = int(os.getenv("MIN_BET", "10"))
MAX_BET = int(os.getenv("MAX_BET", "10000"))
DUEL_TIMEOUT = int(os.getenv("DUEL_TIMEOUT", "60"))
RATE_LIMIT_GAMES = int(os.getenv("RATE_LIMIT_GAMES", "30"))
MAX_BET_CONFIRMATION = int(os.getenv("MAX_BET_CONFIRMATION", "1000"))

# Admin
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-me")

# Prometheus
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "/data/nexus.log")

# OZON payment
OZON_CARD_LAST4 = os.getenv("OZON_CARD_LAST4", "")
OZON_BANK_NAME = os.getenv("OZON_BANK_NAME", "Озон Банк")
OZON_RECEIVER = os.getenv("OZON_RECEIVER", "")
OZON_SBP_QR_URL = os.getenv("OZON_SBP_QR_URL", "")
