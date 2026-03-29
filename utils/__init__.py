# utils/__init__.py

"""
Утилиты для бота Nexus
"""

from . import logger
from . import rate_limiter
from . import security

# Основные экспорты для удобства
from .security import (
    # Генерация ключей
    generate_secret_key,
    generate_token,
    generate_nonce,
    
    # Подписи
    generate_signature,
    verify_signature,
    generate_signed_payload,
    verify_signed_payload,
    
    # Хеширование
    hash_password,
    verify_password,
    needs_password_migration,
    hash_data,
    
    # Шифрование
    SecureEncryption,
    
    # Валидация
    validate_telegram_id,
    sanitize_text_input,
    sanitize_html,
    escape_for_display,
    validate_bet_amount,
    
    # CSRF и Rate limiting
    CSRFProtection,
    RateLimiter,
    KeyRing,
    SecurityContext,
    
    # Глобальные экземпляры
    get_encryptor,
    get_csrf,
    get_rate_limiter,
    password_login_limiter,
    password_reset_limiter,
    api_call_limiter,
    
    # Константы
    IS_PRODUCTION,
    SECURITY_ERRORS,
    
    # Тестирование
    run_security_tests,
)

__all__ = [
    'logger',
    'rate_limiter',
    'security',
    # ... все экспорты из списка выше
]
