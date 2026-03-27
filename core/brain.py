import aiohttp
from config import DEEPSEEK_API_KEY, AI_MODEL, AI_TEMPERATURE, AI_MAX_TOKENS

SYSTEM_PROMPT = """Ты — NEXUS AI, интеллектуальный ассистент для Telegram.
Ты понимаешь русский язык, отвечаешь кратко и полезно.
Ты помогаешь пользователям, отвечаешь на вопросы, даёшь советы.
"""

class NexusBrain:
    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        self.model = AI_MODEL
    
    async def ask(self, question: str) -> str:
        if not self.api_key:
            return "⚠️ AI недоступен"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": question}
                        ],
                        "temperature": AI_TEMPERATURE,
                        "max_tokens": AI_MAX_TOKENS
                    }
                ) as resp:
                    data = await resp.json()
                    if "choices" in data:
                        return data["choices"][0]["message"]["content"]
                    return f"❌ Ошибка: {data.get('error', {}).get('message', 'Неизвестная ошибка')}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
