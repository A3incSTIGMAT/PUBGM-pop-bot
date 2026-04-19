FROM python:3.11-slim

# Переменные окружения для стабильной работы
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_PATH=/data/nexus.db

WORKDIR /app

# 1. Копируем зависимости и устанавливаем их (слой кэшируется)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Создаем папку для БД с правами на запись
RUN mkdir -p /data && chmod 777 /data

# 3. Копируем исходный код
COPY . .

# 4. Очищаем кэш компиляции, чтобы избежать конфликтов версий
RUN find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find . -name "*.pyc" -delete 2>/dev/null || true

# 5. Запускаем бота
CMD ["python", "bot.py"]

