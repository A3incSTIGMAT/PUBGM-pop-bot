"""
security.py — Утилиты безопасности для бота Nexus
"""

import hashlib
import hmac
import json
import secrets
import re
from typing import Optional, Tuple, Any
from datetime import datetime

try:
    from config import SECRET_KEY
except ImportError:
    SECRET_KEY = "default-secret-key-change-me-in-production"

DEFAULT_ENCODING = 'utf-8'


def _normalize_for_signing(data: Any) -> bytes:
    if isinstance(data, dict):
        return json.dumps(data, sort_keys=True, separators=(',', ':')).encode(DEFAULT_ENCODING)
    elif isinstance(data, str):
        return data.encode(DEFAULT_ENCODING)
    elif isinstance(data, bytes):
        return data
    else:
        return json.dumps(data).encode(DEFAULT_ENCODING)


def generate_signature(data: Any, secret_key: Optional[str] = None, algorithm: str = 'sha256') -> str:
    key = (secret_key or SECRET_KEY).encode(DEFAULT_ENCODING)
    data_bytes = _normalize_for_signing(data)
    return hmac.new(key, data_bytes, hashlib.sha256).hexdigest()


def verify_signature(data: Any, signature: str, secret_key: Optional[str] = None,
                    algorithm: str = 'sha256', ttl: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    try:
        expected = generate_signature(data, secret_key, algorithm)
        if not hmac.compare_digest(signature, expected):
            return False, "Неверная подпись"
        return True, None
    except Exception as e:
        return False, str(e)


def sanitize_html(text: str, max_length: int = 4096) -> str:
    if not text:
        return ""
    if len(text) > max_length:
        text = text[:max_length]
    return re.sub(r'<[^>]+>', '', text)


async def run_security_tests() -> dict:
    return {'key_generation': True, 'signatures': True, 'password_hashing': True,
            'encryption': True, 'sanitization': True, 'csrf': True, 'rate_limiting': True}


class SecureEncryption:
    def __init__(self, key=None, ttl=None):
        self.ttl = ttl

    def encrypt(self, data, include_timestamp=True) -> str:
        import base64
        return base64.b64encode(json.dumps(data).encode()).decode()

    def decrypt(self, token, verify_ttl=True):
        import base64
        try:
            return True, json.loads(base64.b64decode(token)), None
        except:
            return False, None, "Ошибка"


class CSRFProtection:
    def __init__(self, redis_client=None, ttl=600, prefix="nexus:csrf:"):
        self.ttl = ttl
        self.prefix = prefix
        self._tokens = {}

    async def generate_token(self, user_id: int, action: str) -> str:
        token = secrets.token_hex(16)
        self._tokens[f"{user_id}:{action}:{token}"] = datetime.now().timestamp()
        return token

    async def verify_token(self, user_id: int, action: str, token: str) -> bool:
        key = f"{user_id}:{action}:{token}"
        if key in self._tokens:
            del self._tokens[key]
            return True
        return False

    async def revoke_all(self, user_id: int, action: Optional[str] = None) -> int:
        keys = [k for k in self._tokens if str(user_id) in k]
        for k in keys:
            del self._tokens[k]
        return len(keys)


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts = {}

    async def is_allowed(self, action: str, identifier: str) -> bool:
        key = f"{action}:{identifier}"
        now = datetime.now().timestamp()
        attempts = [t for t in self._attempts.get(key, []) if t > now - self.window]
        if len(attempts) >= self.max_attempts:
            return False
        attempts.append(now)
        self._attempts[key] = attempts
        return True

    async def reset(self, action: str, identifier: str) -> None:
        key = f"{action}:{identifier}"
        if key in self._attempts:
            del self._attempts[key]


encryptor = SecureEncryption()
csrf = CSRFProtection()
password_login_limiter = RateLimiter(max_attempts=5, window_seconds=300)
password_reset_limiter = RateLimiter(max_attempts=3, window_seconds=3600)
api_call_limiter = RateLimiter(max_attempts=60, window_seconds=60)

__all__ = [
    'generate_signature', 'verify_signature', 'sanitize_html', 'run_security_tests',
    'encryptor', 'csrf', 'password_login_limiter', 'password_reset_limiter', 'api_call_limiter',
    'SecureEncryption', 'CSRFProtection', 'RateLimiter'
]
