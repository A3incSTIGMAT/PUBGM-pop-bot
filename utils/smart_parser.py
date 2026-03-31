"""
smart_parser.py — Умный парсер команд
"""

import re
from typing import Optional, Tuple, Dict, List


class SmartParser:
    """Умный парсер текстовых команд"""

    def __init__(self):
        self.bot_names = [
            'nexus', 'nex', 'нексус', 'некс', 'нейксус', 'нейкс',
            'бот', 'bot', 'никс', 'никсус', 'nix'
        ]

        self.commands = {
            'slot': {
                'ru': ['слот', 'слоты', 'слот машина', 'слот-машина', 'играть слот', 'покрути слот'],
                'en': ['slot', 'slots', 'slot machine', 'play slot']
            },
            'duel': {
                'ru': ['дуэль', 'дуэля', 'вызов', 'поединок', 'сразиться'],
                'en': ['duel', 'fight', 'battle']
            },
            'roulette': {
                'ru': ['рулетка', 'рулетку', 'казино', 'покрути рулетку', 'сыграй в рулетку'],
                'en': ['roulette', 'spin', 'casino']
            },
            'rps': {
                'ru': ['камень ножницы бумага', 'кнб', 'камень-ножницы-бумага', 'поиграем в кнб'],
                'en': ['rock paper scissors', 'rps', 'play rps']
            },
            'balance': {
                'ru': ['баланс', 'сколько денег', 'мой баланс', 'сколько у меня', 'кошелек', 'кошелёк'],
                'en': ['balance', 'money', 'wallet']
            },
            'daily': {
                'ru': ['бонус', 'ежедневный бонус', 'забрать бонус', 'дейлик'],
                'en': ['daily', 'bonus', 'claim']
            },
            'transfer': {
                'ru': ['перевести', 'отправить', 'перевод', 'дать'],
                'en': ['transfer', 'send', 'give']
            },
            'profile': {
                'ru': ['профиль', 'мой профиль', 'статистика', 'моя статистика'],
                'en': ['profile', 'stats', 'my stats']
            },
            'help': {
                'ru': ['помощь', 'команды', 'что умеешь', 'помоги'],
                'en': ['help', 'commands', 'what can you do']
            },
            'vip': {
                'ru': ['вип', 'вип статус', 'купить вип'],
                'en': ['vip', 'premium']
            },
            'hug': {
                'ru': ['обнять', 'обними', 'хуг'],
                'en': ['hug']
            },
            'kiss': {
                'ru': ['поцеловать', 'поцелуй', 'кисс'],
                'en': ['kiss']
            },
            'hit': {
                'ru': ['ударить', 'бить', 'хит'],
                'en': ['hit', 'punch']
            },
        }

        self.roulette_colors = {
            'red': {'ru': ['красный', 'красное', 'red'], 'en': ['red']},
            'black': {'ru': ['черный', 'черное', 'black'], 'en': ['black']},
            'green': {'ru': ['зеленый', 'зеленое', 'green', 'зеро'], 'en': ['green', 'zero']},
        }

        self.rps_choices = {
            'rock': {'ru': ['камень', 'камень!', '✊'], 'en': ['rock', 'stone']},
            'scissors': {'ru': ['ножницы', 'ножницы!', '✌️'], 'en': ['scissors']},
            'paper': {'ru': ['бумага', 'бумага!', '✋'], 'en': ['paper']},
        }

    def extract_bot_name(self, text: str) -> Optional[str]:
        """Извлекает обращение к боту"""
        text_lower = text.lower()
        for name in self.bot_names:
            if name in text_lower:
                return name
        return None

    def remove_bot_name(self, text: str) -> str:
        """Удаляет обращение к боту"""
        text_lower = text.lower()
        for name in self.bot_names:
            text_lower = text_lower.replace(name, '')
        return text_lower.strip()

    def parse_command(self, text: str) -> Optional[Tuple[str, dict]]:
        """Парсит текстовую команду"""
        original_text = text
        text_lower = text.lower().strip()

        # Удаляем обращение к боту
        bot_name = self.extract_bot_name(text_lower)
        if bot_name:
            text_lower = self.remove_bot_name(text_lower)

        # Проверяем команды
        for cmd, variants in self.commands.items():
            for lang_variants in variants.values():
                for variant in lang_variants:
                    if variant in text_lower or text_lower.startswith(variant):
                        params = self._extract_params(cmd, text_lower)
                        return (cmd, params)

        return None

    def _extract_params(self, command: str, text: str) -> dict:
        """Извлекает параметры команды"""
        params = {}

        if command == 'duel':
            amounts = re.findall(r'\b(\d+)\b', text)
            if amounts:
                params['amount'] = int(amounts[0])
            mentions = re.findall(r'@(\w+)', text)
            if mentions:
                params['target'] = mentions[0]

        elif command == 'roulette':
            amounts = re.findall(r'\b(\d+)\b', text)
            if amounts:
                params['amount'] = int(amounts[0])
            for color, variants in self.roulette_colors.items():
                for lang_variants in variants.values():
                    for variant in lang_variants:
                        if variant in text.lower():
                            params['color'] = color
                            break

        elif command == 'rps':
            for choice, variants in self.rps_choices.items():
                for lang_variants in variants.values():
                    for variant in lang_variants:
                        if variant in text.lower():
                            params['choice'] = choice
                            break

        elif command == 'transfer':
            amounts = re.findall(r'\b(\d+)\b', text)
            if amounts:
                params['amount'] = int(amounts[0])
            mentions = re.findall(r'@(\w+)', text)
            if mentions:
                params['to'] = mentions[0]

        return params

    def parse_bet_amount(self, text: str) -> Optional[int]:
        """Извлекает сумму ставки"""
        amounts = re.findall(r'\b(\d+)\b', text)
        return int(amounts[0]) if amounts else None

    def parse_username(self, text: str) -> Optional[str]:
        """Извлекает username"""
        mentions = re.findall(r'@(\w+)', text)
        return mentions[0] if mentions else None


smart_parser = SmartParser()
