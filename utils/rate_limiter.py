import time
from collections import defaultdict
from typing import Dict, List
from functools import wraps
from aiogram.types import Message

_rate_limits: Dict[str, List[float]] = defaultdict(list)

def rate_limit(limit: int = 30, period: int = 60, key: str = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(message: Message, *args, **kwargs):
            user_id = message.from_user.id
            limiter_key = f"{key or func.__name__}:{user_id}"
            now = time.time()
            _rate_limits[limiter_key] = [t for t in _rate_limits[limiter_key] if t > now - period]
            if len(_rate_limits[limiter_key]) >= limit:
                wait = int(period - (now - _rate_limits[limiter_key][0]))
                await message.answer(f"⏰ *Лимит!* Подождите *{wait} сек*", parse_mode="Markdown")
                return
            _rate_limits[limiter_key].append(now)
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator
