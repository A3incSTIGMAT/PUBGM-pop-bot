#!/bin/bash
# Запуск ZeroClaw с правильными переменными

export BOT_TOKEN="${BOT_TOKEN}"
export ADMIN_IDS="${ADMIN_IDS}"
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY}"

# Создаём папку для данных
mkdir -p /data/personas

# Копируем личность агента
cp /app/personas/nexus.md /data/personas/nexus.md

# Запускаем агента
zeroclaw daemon --config /app/0claw.toml
