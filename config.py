"""
config.py — Конфигурация бота Nexus
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# ТЕЛЕГРАМ БОТ
# ============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_TOKEN = BOT_TOKEN  # Для обратной совместимости

# ============================================================================
# БАЗА ДАННЫХ
# ============================================================================

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/nexus.db")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

# Redis (опционально)
REDIS_URL = os.getenv("REDIS_URL", None)

# ============================================================================
# ИГРОВЫЕ НАСТРОЙКИ
# ============================================================================

MIN_BET = int(os.getenv("MIN_BET", "10"))
MAX_BET = int(os.getenv("MAX_BET", "10000"))
DUEL_TIMEOUT = int(os.getenv("DUEL_TIMEOUT", "60"))
RATE_LIMIT_GAMES = int(os.getenv("RATE_LIMIT_GAMES", "30"))
MAX_BET_CONFIRMATION = int(os.getenv("MAX_BET_CONFIRMATION", "1000"))

# ============================================================================
# АДМИНИСТРАТОРЫ
# ============================================================================

# ID глобальных администраторов (владельцев бота) через запятую
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# ============================================================================
# БЕЗОПАСНОСТЬ
# ============================================================================

SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-me")

# ============================================================================
# МЕТРИКИ
# ============================================================================

PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))

# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "/data/nexus.log")

# ============================================================================
# ПЛАТЕЖИ OZON
# ============================================================================

OZON_CARD_LAST4 = os.getenv("OZON_CARD_LAST4", "")
OZON_BANK_NAME = os.getenv("OZON_BANK_NAME", "Озон Банк")
OZON_RECEIVER = os.getenv("OZON_RECEIVER", "")
OZON_SBP_QR_URL = os.getenv("OZON_SBP_QR_URL", "")

# ============================================================================
# АДМИНИСТРАТИВНЫЕ НАСТРОЙКИ
# ============================================================================

# Rate limiting для команд (секунды между вызовами)
RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", "3"))

# Максимальное количество предупреждений до авто-бана
MAX_WARN_COUNT = int(os.getenv("MAX_WARN_COUNT", "3"))

# Максимальное количество сообщений для очистки
MAX_CLEAR_MESSAGES = int(os.getenv("MAX_CLEAR_MESSAGES", "100"))

# Максимальная длительность мута (дни)
MAX_MUTE_DAYS = int(os.getenv("MAX_MUTE_DAYS", "30"))

# Автоматическая модерация
AUTO_MODERATION_ENABLED = os.getenv("AUTO_MODERATION_ENABLED", "true").lower() == "true"

# Запрещённые паттерны для авто-модерации (через запятую)
FORBIDDEN_PATTERNS = os.getenv("FORBIDDEN_PATTERNS", "").split(",") if os.getenv("FORBIDDEN_PATTERNS") else []

# ============================================================================
# AI (OpenRouter)
# ============================================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_ENABLED = bool(OPENROUTER_API_KEY)
