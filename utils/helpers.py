import re
from typing import Optional

def extract_username(text: str) -> Optional[str]:
    match = re.search(r'@(\w+)', text)
    return match.group(1) if match else None

def extract_amount(text: str) -> Optional[int]:
    matches = re.findall(r'\b(\d+)\b', text)
    return int(matches[0]) if matches else None

def extract_color(text: str) -> Optional[str]:
    text_lower = text.lower()
    if any(c in text_lower for c in ['красн', 'red']): return 'red'
    if any(c in text_lower for c in ['черн', 'black']): return 'black'
    if any(c in text_lower for c in ['зелен', 'green', 'зеро']): return 'green'
    return None

def extract_rps_choice(text: str) -> Optional[str]:
    text_lower = text.lower()
    if any(c in text_lower for c in ['камень', 'rock']): return 'rock'
    if any(c in text_lower for c in ['ножницы', 'scissors']): return 'scissors'
    if any(c in text_lower for c in ['бумага', 'paper']): return 'paper'
    return None
