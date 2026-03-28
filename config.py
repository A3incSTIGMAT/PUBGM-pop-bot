import os
from dotenv import load_dotenv

load_dotenv()

# ========== TELEGRAM ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

# ========== AI (Ollama) ==========
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

# ========== ОЗОН БАНК (платежи) ==========
OZON_CARD_LAST4 = os.getenv("OZON_CARD_LAST4", "4436")
OZON_BANK_NAME = os.getenv("OZON_BANK_NAME", "Озон Банк")
OZON_RECEIVER = os.getenv("OZON_RECEIVER", "Александр Б.")
OZON_SBP_QR_URL = os.getenv("OZON_SBP_QR_URL")

# ========== БАЗА ДАННЫХ ==========
DATABASE_URL = os.getenv("DATABASE_URL", "/data/nexus.db")
MEMORY_DB_URL = os.getenv("MEMORY_DB_URL", "/data/nexus_memory.db")

# ========== ЛОГИРОВАНИЕ ==========
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "/data/nexus.log")

# ========== СТАРЫЕ ПЕРЕМЕННЫЕ (для совместимости) ==========
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.8"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2000"))

print("✅ Конфигурация загружена")
