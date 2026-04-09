import os
from dotenv import load_dotenv

load_dotenv()

# Обязательные переменные
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Администраторы (через запятую)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Пути для Amvera (ОБЯЗАТЕЛЬНО)
DATA_DIR = "/data"
DB_PATH = os.getenv("DATABASE_PATH", f"{DATA_DIR}/nexus.db")
LOG_FILE = os.getenv("LOG_FILE", f"{DATA_DIR}/nexus.log")

# Экономика (опционально)
START_BALANCE = int(os.getenv("START_BALANCE", "1000"))
DAILY_BONUS = int(os.getenv("DAILY_BONUS", "500"))
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "250"))

# Уровень логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Безопасность
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-me")
