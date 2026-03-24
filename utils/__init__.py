from . import antispam
from . import filters
from . import logger
# lock НЕ импортируем здесь, чтобы избежать циклических импортов
# lock будет импортироваться напрямую в bot.py
