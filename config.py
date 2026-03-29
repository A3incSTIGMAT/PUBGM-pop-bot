"""
NEXUS AI — Конфигурация системы
Все переменные окружения загружаются из .env или Amvera
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# TELEGRAM
# ============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

# ============================================================================
# ОЗОН БАНК (платежи)
# ============================================================================
OZON_CARD_LAST4 = os.getenv("OZON_CARD_LAST4", "4436")
OZON_BANK_NAME = os.getenv("OZON_BANK_NAME", "Озон Банк")
OZON_RECEIVER = os.getenv("OZON_RECEIVER", "Александр Б.")
OZON_SBP_QR_URL = os.getenv("OZON_SBP_QR_URL")

# ============================================================================
# БАЗА ДАННЫХ
# ============================================================================
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/nexus.db")
MEMORY_DB_URL = os.getenv("MEMORY_DB_URL", "/data/nexus_memory.db")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

# ============================================================================
# REDIS (для rate limiting и кэширования)
# ============================================================================
REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# ============================================================================
# AI (OpenRouter / Hugging Face)
# ============================================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1000"))

# ============================================================================
# ИГРЫ (games_interactive.py)
# ============================================================================
MIN_BET = int(os.getenv("MIN_BET", "10"))
MAX_BET = int(os.getenv("MAX_BET", "10000"))
DUEL_TIMEOUT = int(os.getenv("DUEL_TIMEOUT", "60"))
RATE_LIMIT_GAMES = int(os.getenv("RATE_LIMIT_GAMES", "30"))
MAX_BET_CONFIRMATION = int(os.getenv("MAX_BET_CONFIRMATION", "1000"))

# ============================================================================
# БЕЗОПАСНОСТЬ
# ============================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "nexus-super-secret-key-2026-change-this-in-production")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# ============================================================================
# МЕТРИКИ (Prometheus)
# ============================================================================
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))

# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "/data/nexus.log")

# ============================================================================
# СТАРЫЕ ПЕРЕМЕННЫЕ (для совместимости)
# ============================================================================
DATABASE_URL = DATABASE_PATH
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
AI_MAX_TOKENS_OLD = int(os.getenv("AI_MAX_TOKENS", "2000"))

# ============================================================================
# ПРОВЕРКИ
# ============================================================================
if not SECRET_KEY or SECRET_KEY == "nexus-super-secret-key-2026-change-this-in-production":
    print("⚠️ WARNING: SECRET_KEY не задан! Используется значение по умолчанию. Это небезопасно!")

if not REDIS_URL:
    print("⚠️ WARNING: REDIS_URL не задан. Rate limiting будет работать в памяти (in-memory).")

# ============================================================================
# ВЫВОД ИНФОРМАЦИИ О КОНФИГУРАЦИИ
# ============================================================================
print("✅ Конфигурация загружена")
print(f"🤖 AI: {'OpenRouter' if OPENROUTER_API_KEY else 'Hugging Face' if HUGGINGFACE_TOKEN else 'DeepSeek' if DEEPSEEK_API_KEY else 'не настроен'}")
print(f"💳 Платежи: Озон Банк (карта •••• {OZON_CARD_LAST4})")
print(f"🎮 Игры: слоты, дуэли, рулетка, RPS")
print(f"🗄️ База данных: {DATABASE_PATH}")
print(f"🔄 Redis: {'подключен' if REDIS_URL else 'не настроен (in-memory mode)'}")
print(f"🔒 SECRET_KEY: {'установлен' if SECRET_KEY != 'nexus-super-secret-key-2026-change-this-in-production' else '⚠️ используйте свой!'}")
