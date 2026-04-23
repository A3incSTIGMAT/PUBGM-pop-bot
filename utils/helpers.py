#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: utils/helpers.py
# ВЕРСИЯ: 2.0.0-production
# ОПИСАНИЕ: Утилиты для извлечения данных и форматирования
# ============================================

import html
import re
from typing import Optional, List, Any


# ==================== ИЗВЛЕЧЕНИЕ ДАННЫХ ====================

def extract_username(text: Optional[str]) -> Optional[str]:
    """
    Извлекает Telegram username из текста.
    Поддерживает форматы: @username, username как отдельное слово.
    
    Telegram username правила: 5-32 символа, a-z, 0-9, underscore
    """
    if not text:
        return None
    
    text = text.strip()
    
    patterns = [
        r'@([a-zA-Z0-9_]{5,32})\b',           # @username
        r'(?:^|\s)([a-zA-Z0-9_]{5,32})(?:\s|$)',  # username как отдельное слово
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            username = match.group(1)
            if not username.isdigit():
                return username.lower()
    
    return None


def extract_amount(text: Optional[str], min_value: int = 1, max_value: int = 1_000_000) -> Optional[int]:
    """
    Извлекает числовое значение (сумму) из текста.
    
    Args:
        text: Исходный текст
        min_value: Минимально допустимое значение
        max_value: Максимально допустимое значение
    
    Returns:
        int или None, если число не найдено или вне диапазона
    """
    if not text:
        return None
    
    matches = re.findall(r'-?\b\d+(?:[\s,.]?\d{3})*\b', text)
    
    if not matches:
        return None
    
    for match in matches:
        try:
            cleaned = re.sub(r'[\s,.]', '', match)
            amount = int(cleaned)
            if min_value <= amount <= max_value:
                return amount
        except (ValueError, TypeError):
            continue
    
    return None


def extract_color(text: Optional[str]) -> Optional[str]:
    """
    Определяет цвет для рулетки по ключевым словам.
    
    Returns: 'red', 'black', 'green' или None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    color_keywords = {
        'red': ['красн', 'red', 'красный', 'алый', 'рубин'],
        'black': ['черн', 'black', 'чёрный', 'темный', 'уголь'],
        'green': ['зелен', 'green', 'зеро', 'ноль', '0', 'зелёный'],
    }
    
    for color, keywords in color_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            return color
    
    return None


def extract_rps_choice(text: Optional[str]) -> Optional[str]:
    """
    Определяет выбор для игры "Камень-Ножницы-Бумага".
    
    Returns: 'rock', 'scissors', 'paper' или None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    choice_keywords = {
        'rock': ['камень', 'rock', 'stone', 'кам', 'камен'],
        'scissors': ['ножницы', 'scissors', 'scissor', 'нож', 'лезвие'],
        'paper': ['бумага', 'paper', 'лист', 'бум', 'картон'],
    }
    
    scores = {}
    for choice, keywords in choice_keywords.items():
        scores[choice] = sum(1 for kw in keywords if kw in text_lower)
    
    if scores:
        best_choice = max(scores, key=scores.get)
        if scores[best_choice] > 0:
            return best_choice
    
    return None


def extract_numbers_range(text: Optional[str], min_val: int = 0, max_val: int = 999999) -> List[int]:
    """
    Извлекает ВСЕ числа из текста в заданном диапазоне.
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


# ==================== ФОРМАТИРОВАНИЕ ====================

def safe_html_escape(text: Optional[str]) -> str:
    """Безопасное экранирование HTML."""
    if text is None:
        return ""
    try:
        return html.escape(str(text))
    except Exception:
        return ""


def format_number(num: Any) -> str:
    """Форматирование числа с разделителями тысяч."""
    if num is None:
        return "0"
    try:
        return f"{int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def format_time_seconds(seconds: int) -> str:
    """Форматирует секунды в читаемый вид."""
    if seconds is None or seconds < 0:
        return "0 сек"
    
    minutes = seconds // 60
    secs = seconds % 60
    
    if minutes > 0:
        return f"{minutes} мин {secs} сек"
    return f"{secs} сек"


def format_date(date_str: Optional[str]) -> str:
    """Форматирование даты из ISO формата."""
    if not date_str:
        return "Неизвестно"
    try:
        if "T" in date_str:
            return date_str.split("T")[0]
        return date_str[:10] if len(date_str) >= 10 else date_str
    except Exception:
        return "Неизвестно"


def get_medal(position: Optional[int]) -> str:
    """Получить медаль для позиции в топе."""
    if position is None:
        return "—"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(position, f"{position}.")


def escape_name(user: Optional[dict]) -> str:
    """Безопасное получение имени пользователя."""
    if user is None:
        return "Пользователь"
    
    username = user.get("username")
    if username:
        return f"@{safe_html_escape(str(username))}"
    
    first_name = user.get("first_name")
    if first_name:
        name = str(first_name)[:20] if len(str(first_name)) > 20 else str(first_name)
        return safe_html_escape(name)
    
    return "Пользователь"


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

def normalize_text(text: Optional[str]) -> str:
    """Нормализует текст: удаляет лишние пробелы, приводит к нижнему регистру."""
    if not text:
        return ""
    return ' '.join(text.lower().split())


def contains_keyword(text: Optional[str], keywords: List[str], case_sensitive: bool = False) -> bool:
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


def truncate_text(text: Optional[str], max_length: int = 100) -> str:
    """Обрезает текст до заданной длины с многоточием."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def safe_int(value: Any, default: int = 0) -> int:
    """Безопасное преобразование в int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_get(obj: Optional[dict], key: str, default: Any = None) -> Any:
    """Безопасное получение значения из словаря."""
    if obj is None:
        return default
    return obj.get(key, default)


# ==================== ИГРОВЫЕ ====================

def extract_bet_params(text: Optional[str], game_type: str = 'generic') -> dict:
    """
    Универсальная функция для извлечения параметров ставки.
    
    Args:
        text: Текст сообщения
        game_type: Тип игры ('slot', 'roulette', 'duel', 'rps', 'generic')
    
    Returns:
        dict с параметрами
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
    
    result['amount'] = extract_amount(text)
    result['username'] = extract_username(text)
    
    if game_type in ('roulette', 'generic'):
        result['color'] = extract_color(text)
    
    if game_type in ('rps', 'generic'):
        result['choice'] = extract_rps_choice(text)
    
    # Определяем успешность
    if game_type == 'slot':
        result['success'] = result['amount'] is not None
    elif game_type == 'roulette':
        result['success'] = result['amount'] is not None and result['color'] is not None
    elif game_type == 'duel':
        result['success'] = result['amount'] is not None and result['username'] is not None
    elif game_type == 'rps':
        result['success'] = result['choice'] is not None
    else:
        result['success'] = any([
            result['amount'],
            result['username'],
            result['color'],
            result['choice']
        ])
    
    return result
