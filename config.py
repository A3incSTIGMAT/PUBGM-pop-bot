import os
from dotenv import load_dotenv

# Пытаемся загрузить .env только локально
try:
    load_dotenv()
except:
    pass

# ========== TELEGRAM ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# ========== AI AGENT ==========
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2000"))

# ========== ПРОВЕРКИ ==========
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан! Установите переменную окружения.")

if not DEEPSEEK_API_KEY:
    print("⚠️ DEEPSEEK_API_KEY не задан. AI-функции будут недоступны.")
