#!/bin/bash

# Запускаем Ollama в фоне
ollama serve &

# Ждём загрузки Ollama
sleep 10

# Загружаем модель
ollama pull tinyllama

# Запускаем бота
python bot.py
