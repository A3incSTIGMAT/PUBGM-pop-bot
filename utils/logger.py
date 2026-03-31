"""
logger.py — Логирование для бота Nexus
"""

import logging
import sys

# Форматирование
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Консольный обработчик
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Корневой логгер
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)

# Логгер бота
logger = logging.getLogger("nexus_bot")
