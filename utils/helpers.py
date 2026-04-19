"""
Утилиты для извлечения данных из текстовых сообщений
Исправленная версия с улучшенной логикой и обработкой краевых случаев
"""

import re
from typing import Optional, List


def extract_username(text: str) -> Optional[str]:
    """
    Извлекает Telegram username из текста.
    Поддерживает форматы: @username, username@, упоминания в тексте.
    
    Telegram username правила: 5-32 символа, a-z, 0-9, underscore
    """
    if not text:
        return None
    
    # Очищаем текст от лишних пробелов
    text = text.strip()
    
    # Паттерн для Telegram username: @ + буквы/цифры/подчёркивания (5-32 символа)
    # Также ловим username без @ в начале, если он окружён пробелами
    patterns = [
        r'@([a-zA-Z0-9_]{5,32})\b',           # @username
        r'(?:^|\s)([a-zA-Z0-9_]{5,32})(?:\s|$)',  # username как отдельное слово
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            username = match.group(1)
            # Дополнительная валидация: не принимаем чисто цифровые "юзернеймы"
            if not username.isdigit():
                return username.lower()
    
    return None


def extract_amount(text: str, min_value: int = 1, max_value: int = 1_000_000) -> Optional[int]:
    """
    Извлекает числовое значение (сумму) из текста.
    
    Args:
        text: Исходный текст
        min_value: Минимально допустимое значение (по умолчанию 1)
        max_value: Максимально допустимое значение (по умолчанию 1_000_000)
    
    Returns:
        int или None, если число не найдено или вне диапазона
    """
    if not text:
        return None
    
    # Ищем все числа в тексте, включая возможные отрицательные
    # Паттерн: опциональный минус + цифры + опциональные пробелы + разделители тысяч
    matches = re.findall(r'-?\b\d+(?:[\s,.]?\d{3})*\b', text)
    
    if not matches:
        return None
    
    for match in matches:
        try:
            # Очищаем число от разделителей тысяч и пробелов
            cleaned = re.sub(r'[\s,.]', '', match)
            amount = int(cleaned)
            
            # Проверяем диапазон
            if min_value <= amount <= max_value:
                return amount
        except (ValueError, TypeError):
            continue
    
    return None


def extract_color(text: str) -> Optional[str]:
    """
    Определяет цвет для рулетки по ключевым словам.
    
    Поддерживаемые цвета: red, black, green (zero)
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Ключевые слова для каждого цвета
    color_keywords = {
        'red': ['красн', 'red', 'красный', 'алый', 'рубин'],
        'black': ['черн', 'black', 'чёрный', 'темный', 'уголь'],
        'green': ['зелен', 'green', 'зеро', 'ноль', '0', 'зелёный'],
    }
    
    for color, keywords in color_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            return color
    
    return None


def extract_rps_choice(text: str) -> Optional[str]:
    """
    Определяет выбор для игры "Камень-Ножницы-Бумага".
    
    Returns: 'rock', 'scissors', 'paper' или None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Ключевые слова для каждого выбора
    choice_keywords = {
        'rock': ['камень', 'rock', 'stone', 'кам', 'камен'],
        'scissors': ['ножницы', 'scissors', 'scissor', 'нож', 'лезвие'],
        'paper': ['бумага', 'paper', 'лист', 'бум', 'картон'],
    }
    
    # Считаем совпадения для каждого варианта
    scores = {}
    for choice, keywords in choice_keywords.items():
        scores[choice] = sum(1 for kw in keywords if kw in text_lower)
    
    # Возвращаем вариант с наибольшим количеством совпадений
    if scores:
        best_choice = max(scores, key=scores.get)
        if scores[best_choice] > 0:
            return best_choice
    
    return None


def extract_bet_params(text: str, game_type: str = 'generic') -> dict:
    """
    Универсальная функция для извлечения параметров ставки.
    
    Args:
        text: Текст сообщения
        game_type: Тип игры ('slot', 'roulette', 'duel', 'generic')
    
    Returns:
        dict с параметрами: {'amount': int, 'color': str, 'username': str, ...}
    """
    result = {
        'amount': None,
        'color': None,
        'username': None,
        'choice': None,
        'success': False
    }
    
    if not text:
        return result
    
    # Извлекаем базовые параметры
    result['amount'] = extract_amount(text)
    result['username'] = extract_username(text)
    
    # Извлекаем специфичные параметры в зависимости от игры
    if game_type in ('roulette', 'generic'):
        result['color'] = extract_color(text)
    
    if game_type in ('rps', 'generic'):
        result['choice'] = extract_rps_choice(text)
    
    # Определяем успешность извлечения
    if game_type == 'slot':
        result['success'] = result['amount'] is not None
    elif game_type == 'roulette':
        result['success'] = result['amount'] is not None and result['color'] is not None
    elif game_type == 'duel':
        result['success'] = result['amount'] is not None and result['username'] is not None
    elif game_type == 'rps':
        result['success'] = result['choice'] is not None
    else:  # generic
        result['success'] = any([
            result['amount'],
            result['username'],
            result['color'],
            result['choice']
        ])
    
    return result


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def normalize_text(text: str) -> str:
    """
    Нормализует текст: удаляет лишние пробелы, приводит к нижнему регистру.
    """
    if not text:
        return ""
    return ' '.join(text.lower().split())


def contains_keyword(text: str, keywords: List[str], case_sensitive: bool = False) -> bool:
    """
    Проверяет наличие любого из ключевых слов в тексте.
    
    Args:
        text: Исходный текст
        keywords: Список ключевых слов для поиска
        case_sensitive: Учитывать ли регистр (по умолчанию False)
    
    Returns:
        bool: True если найдено хотя бы одно совпадение
    """
    if not text or not keywords:
        return False
    
    search_text = text if case_sensitive else text.lower()
    search_keywords = keywords if case_sensitive else [kw.lower() for kw in keywords]
    
    return any(keyword in search_text for keyword in search_keywords)


def extract_numbers_range(text: str, min_val: int = 0, max_val: int = 999999) -> List[int]:
    """
    Извлекает ВСЕ числа из текста в заданном диапазоне.
    
    Полезно для команд вида: "перевести 100 200 300 монет"
    """
    if not text:
        return []
    
    numbers = []
    matches = re.findall(r'-?\b\d+\b', text)
    
    for match in matches:
        try:
            num = int(match)
            if min_val <= num <= max_val:
                numbers.append(num)
        except ValueError:
            continue
    
    return numbers

