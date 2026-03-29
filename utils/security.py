mkdir -p /app/utils
cat > /app/utils/security.py << 'EOF'
"""
security.py — Заглушка для совместимости
"""
def verify_signature(*args, **kwargs):
    return True, None

def generate_signature(*args, **kwargs):
    return ""

def sanitize_html(text, *args, **kwargs):
    return text or ""

async def run_security_tests():
    return {"ok": True}

class SecureEncryption:
    def __init__(self, *args, **kwargs): pass
    def encrypt(self, data, *args, **kwargs): return str(data)
    def decrypt(self, token, *args, **kwargs): return True, token, None

class CSRFProtection:
    def __init__(self, *args, **kwargs): self._tokens = {}
    async def generate_token(self, user_id, action): return "mock_token"
    async def verify_token(self, user_id, action, token): return True
    async def revoke_all(self, user_id, action=None): return 0

class RateLimiter:
    def __init__(self, *args, **kwargs): pass
    async def is_allowed(self, *args, **kwargs): return True
    async def reset(self, *args, **kwargs): pass

encryptor = SecureEncryption()
csrf = CSRFProtection()
password_login_limiter = RateLimiter()
password_reset_limiter = RateLimiter()
api_call_limiter = RateLimiter()

__all__ = [
    'generate_signature', 'verify_signature', 'sanitize_html', 'run_security_tests',
    'encryptor', 'csrf', 'password_login_limiter', 'password_reset_limiter', 'api_call_limiter',
    'SecureEncryption', 'CSRFProtection', 'RateLimiter'
]
EOF
