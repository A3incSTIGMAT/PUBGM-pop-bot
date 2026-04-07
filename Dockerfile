FROM python:3.11-slim

WORKDIR /app

# 1. Копируем только файл зависимостей
COPY requirements.txt .

# 2. Устанавливаем библиотеки в системную папку (игнорируем папку venv)
RUN pip install --no-cache-dir -r requirements.txt

# 3. Копируем весь код проекта
COPY . .

# 4. Запускаем бота
CMD ["python", "bot.py"]

