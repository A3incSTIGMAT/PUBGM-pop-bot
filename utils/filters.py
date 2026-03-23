import re

# Список запрещенных слов (мат)
BAD_WORDS = [
    "хуй", "пизда", "бля", "еба", "пидор", "мудак",
    "сука", "залупа", "говно", "долбаеб"
]

def contains_bad_words(text: str) -> bool:
    """Проверяет, содержит ли текст запрещенные слова"""
    text_lower = text.lower()
    for word in BAD_WORDS:
        if word in text_lower:
            return True
    return False

def censor_text(text: str) -> str:
    """Заменяет матерные слова звездочками"""
    result = text
    for word in BAD_WORDS:
        result = re.sub(rf'\b{word}\b', '*' * len(word), result, flags=re.IGNORECASE)
    return result
