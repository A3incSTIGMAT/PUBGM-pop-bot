import re
from typing import Optional, Tuple

class SmartParser:
    def __init__(self):
        self.bot_names = ['nexus', 'nex', 'нексус', 'некс', 'бот', 'bot']
        self.commands = {
            'slot': {'ru': ['слот', 'слоты', 'играть слот'], 'en': ['slot', 'play slot']},
            'duel': {'ru': ['дуэль', 'вызов'], 'en': ['duel', 'fight']},
            'roulette': {'ru': ['рулетка', 'казино'], 'en': ['roulette', 'spin']},
            'rps': {'ru': ['камень ножницы бумага', 'кнб'], 'en': ['rock paper scissors', 'rps']},
            'balance': {'ru': ['баланс', 'сколько денег'], 'en': ['balance', 'money']},
            'daily': {'ru': ['бонус', 'ежедневный бонус'], 'en': ['daily', 'bonus']},
            'transfer': {'ru': ['перевести', 'отправить'], 'en': ['transfer', 'send']},
            'profile': {'ru': ['профиль', 'статистика'], 'en': ['profile', 'stats']},
            'help': {'ru': ['помощь', 'команды'], 'en': ['help', 'commands']},
            'hug': {'ru': ['обнять'], 'en': ['hug']},
            'kiss': {'ru': ['поцеловать'], 'en': ['kiss']},
            'hit': {'ru': ['ударить'], 'en': ['hit']},
        }

    def parse_command(self, text: str) -> Optional[Tuple[str, dict]]:
        text_lower = text.lower().strip()
        for cmd, variants in self.commands.items():
            for lang in variants.values():
                for variant in lang:
                    if variant in text_lower:
                        params = self._extract_params(cmd, text_lower)
                        return (cmd, params)
        return None

    def _extract_params(self, command: str, text: str) -> dict:
        params = {}
        if command in ['duel', 'transfer']:
            amounts = re.findall(r'\b(\d+)\b', text)
            if amounts: params['amount'] = int(amounts[0])
            mentions = re.findall(r'@(\w+)', text)
            if mentions: params['target'] = mentions[0] if command == 'duel' else mentions[0]
        elif command == 'roulette':
            amounts = re.findall(r'\b(\d+)\b', text)
            if amounts: params['amount'] = int(amounts[0])
            if 'красн' in text or 'red' in text: params['color'] = 'red'
            elif 'черн' in text or 'black' in text: params['color'] = 'black'
            elif 'зелен' in text or 'green' in text: params['color'] = 'green'
        elif command == 'rps':
            if 'камень' in text or 'rock' in text: params['choice'] = 'rock'
            elif 'ножницы' in text or 'scissors' in text: params['choice'] = 'scissors'
            elif 'бумага' in text or 'paper' in text: params['choice'] = 'paper'
        return params

smart_parser = SmartParser()
