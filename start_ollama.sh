#!/bin/bash
# Ждём, пока Ollama запустится
sleep 15

# Загружаем лёгкую модель (работает на 1GB RAM)
ollama pull tinyllama

# Для более мощной модели (если хватит ресурсов):
# ollama pull mistral

echo "✅ Модель загружена"
