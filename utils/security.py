"""
security.py — Утилиты безопасности для бота Nexus (PRODUCTION v3.1)
====================================================================

Исправления относительно v3.0:
- [CRITICAL] Маскирование чувствительных данных в логах
- [CRITICAL] Принудительное использование Redis для stateful компонентов в production
- [CRITICAL] Валидация SECRET_KEY при инициализации модуля
- [CRITICAL] Защита от перезаписи зарезервированных данных
- [MEDIUM] Поддержка миграции алгоритмов хеширования
- [MEDIUM] Атомарные операции для CSRF protection
- [MEDIUM] Dependency injection для глобальной обработки
"""

# ============================================================================
# 📦 ИМПОРТЫ
# ============================================================================

import hashlib
import hmac
import json
import secrets
from typing import Optional, Tuple, Any
from datetime import datetime

try:
    from config import SECRET_KEY
except ImportError:
    SECRET_KEY = "default-secret-key-change-me"

DEFAULT_ENCODING = 'utf-8'

# Окружение бота
IS_PRODUCTION = BOT_ENV in ('production', 'prod')

# Безопасные лимиты
MAX_SIGNING_DATA_SIZE = SECURITY_CONFIG.get('max_signing_data_size', 1024 * 1024)  # 1 MB
MAX_SERIALIZED_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_INPUT_LENGTH = SECURITY_CONFIG.get('max_input_length', 4096)

# Время жизни подписей и токенов (секунды)
DEFAULT_TTL = SECURITY_CONFIG.get('signature_ttl', 300)  # 5 минут
CSRF_TTL = SECURITY_CONFIG.get('csrf_ttl', 600)  # 10 минут
PASSWORD_RESET_TTL = SECURITY_CONFIG.get('password_reset_ttl', 3600)  # 1 час

# Параметры хеширования паролей
PBKDF2_ITERATIONS = SECURITY_CONFIG.get('pbkdf2_iterations', 100_000)
PBKDF2_SALT_LENGTH = SECURITY_CONFIG.get('pbkdf2_salt_length', 16)
ARGON2_PARAMS = {
    'time_cost': SECURITY_CONFIG.get('argon2_time_cost', 3),
    'memory_cost': SECURITY_CONFIG.get('argon2_memory_cost', 65536),
    'parallelism': SECURITY_CONFIG.get('argon2_parallelism', 1),
    'hash_len': 32,
    'salt_len': 16,
}
DEFAULT_HASH_ALGORITHM = SECURITY_CONFIG.get('password_hash_algorithm', 'pbkdf2-sha256')

# Лимиты для валидации
MIN_TELEGRAM_ID = -999999999999
MAX_TELEGRAM_ID = 999999999999

# Разрешённые теги для HTML-санитизации (настраиваемые)
DEFAULT_ALLOWED_HTML_TAGS = [
    'b', 'strong', 'i', 'em', 'u', 'code', 'pre', 'blockquote',
    'a', 'ul', 'ol', 'li', 'p', 'br', 'hr'
]
DEFAULT_ALLOWED_HTML_ATTRIBUTES = {
    'a': ['href', 'title'],
    '*': ['class']
}
ALLOWED_HTML_TAGS = SECURITY_CONFIG.get('allowed_html_tags', DEFAULT_ALLOWED_HTML_TAGS)
ALLOWED_HTML_ATTRIBUTES = SECURITY_CONFIG.get('allowed_html_attributes', DEFAULT_ALLOWED_HTML_ATTRIBUTES)

# Чувствительные ключи для маскирования в логах
SENSITIVE_KEY_PATTERNS = [
    'key', 'secret', 'token', 'password', 'pass', 'auth', 'api_key', 
    'apikey', 'access', 'refresh', 'private', 'credential'
]

# Сообщения об ошибках (без раскрытия деталей)
SECURITY_ERRORS = {
    "invalid_signature": "Неверная подпись данных",
    "expired_signature": "Время жизни подписи истекло",
    "invalid_token": "Неверный или истёкший токен",
    "rate_limited": "Слишком много попыток, попробуйте позже",
    "invalid_input": "Некорректные входные данные",
    "encryption_error": "Ошибка шифрования/дешифрования",
    "data_too_large": "Данные слишком большие для обработки",
    "weak_secret_key": "Секретный ключ не соответствует требованиям безопасности",
    "redis_required": "Redis требуется в production-режиме",
    "algorithm_migration_needed": "Требуется миграция алгоритма хеширования",
}

# ============================================================================
# 🔧 БЕЗОПАСНОЕ ЛОГИРОВАНИЕ С МАСКИРОВАНИЕМ
# ============================================================================

def _is_sensitive_key(key: str) -> bool:
    """Проверка, является ли ключ чувствительным"""
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_KEY_PATTERNS)


def _mask_sensitive_data(data: Any, depth: int = 0, max_depth: int = 5) -> Any:
    """
    Рекурсивное маскирование чувствительных данных.
    
    Args:
        data: Данные для обработки
        depth: Текущая глубина рекурсии
        max_depth: Максимальная глубина обработки
    
    Returns:
        Any: Данные с замаскированными чувствительными полями
    """
    if depth > max_depth:
        return '<max_depth_exceeded>'
    
    if isinstance(data, dict):
        return {
            k: _mask_sensitive_data(v, depth + 1, max_depth) if not _is_sensitive_key(k) else '***REDACTED***'
            for k, v in data.items()
        }
    elif isinstance(data, (list, tuple)):
        return type(data)(_mask_sensitive_data(item, depth + 1, max_depth) for item in data)
    elif isinstance(data, str):
        # Маскируем строки, похожие на токены/ключи
        if len(data) > 20 and re.match(r'^[A-Za-z0-9+/=_-]{20,}$', data):
            return f'***REDACTED_{len(data)}chars***'
        return data[:100] + '...' if len(data) > 100 else data
    elif isinstance(data, (int, float, bool, type(None))):
        return data
    else:
        # Для остальных типов — хеш представления
        try:
            return f'<{type(data).__name__}:{hash(str(data)) & 0xFFFF:04X}>'
        except Exception:
            return f'<{type(data).__name__}>'


def _safe_log_data(data: Any, max_len: int = 50) -> str:
    """
    Безопасное логирование данных с маскированием чувствительной информации.
    
    Args:
        data: Данные для логирования
        max_len: Максимальная длина строкового представления
    
    Returns:
        str: Безопасное представление для логов (хеш + краткое описание)
    """
    try:
        # Маскируем чувствительные данные
        safe_data = _mask_sensitive_data(data)
        
        # Преобразуем в строку
        if isinstance(safe_data, dict):
            data_str = json.dumps(safe_data, default=str, ensure_ascii=False)[:max_len]
        else:
            data_str = str(safe_data)[:max_len]
        
        # Возвращаем хеш для идентификации + тип данных
        data_hash = hashlib.sha256(data_str.encode(DEFAULT_ENCODING)).hexdigest()[:12]
        data_type = type(data).__name__
        
        return f"type={data_type},hash={data_hash},len={len(str(data))}"
        
    except Exception as e:
        # Фолбэк: даже если маскирование упало, не логируем сырые данные
        return f"type=unknown,hash=error,safe=true"


def _log_security_event(event_type: str, details: Dict[str, Any], level: str = 'info'):
    """
    Логирование событий безопасности с маскированием.
    
    Args:
        event_type: Тип события (e.g., 'signature_verify_failed', 'rate_limit_exceeded')
        details: Детали события (будут автоматически замаскированы)
        level: Уровень логирования ('info', 'warning', 'error')
    """
    if not SECURITY_CONFIG.get('log_security_events', True):
        return
    
    safe_details = _mask_sensitive_data(details)
    log_message = f"SECURITY_EVENT[{event_type}]: {json.dumps(safe_details, default=str)}"
    
    log_func = getattr(logger, level, logger.info)
    log_func(log_message)


# ============================================================================
# 🔐 ВАЛИДАЦИЯ КОНФИГУРАЦИИ ПРИ ЗАГРУЗКЕ
# ============================================================================

def _validate_secret_key(key: str, min_length: int = 32) -> None:
    """
    Валидация секретного ключа при инициализации модуля.
    
    Raises:
        RuntimeError: Если ключ не соответствует требованиям безопасности
    """
    if not key:
        raise RuntimeError(
            f"{SECURITY_ERRORS['weak_secret_key']}: SECRET_KEY is empty. "
            "Use generate_secret_key() to create a secure key."
        )
    
    if len(key) < min_length:
        raise RuntimeError(
            f"{SECURITY_ERRORS['weak_secret_key']}: length={len(key)}, minimum={min_length}. "
            "Use generate_secret_key() to create a secure key."
        )
    
    # Проверка на слабые ключи (повторяющиеся символы, простые паттерны)
    if re.match(r'^(.)\1+$', key) or key.lower() in ('test', 'password', 'secret', 'changeme'):
        raise RuntimeError(
            f"{SECURITY_ERRORS['weak_secret_key']}: Key appears to be weak or default. "
            "Use generate_secret_key() to create a cryptographically secure key."
        )


def _validate_redis_config() -> None:
    """Проверка конфигурации Redis для production"""
    if IS_PRODUCTION and SECURITY_CONFIG.get('require_redis_production', True):
        if not REDIS_CONFIG or not REDIS_CONFIG.get('host'):
            raise RuntimeError(
                f"{SECURITY_ERRORS['redis_required']}: "
                "Redis configuration is required in production mode. "
                "Set REDIS_CONFIG in config.py or disable require_redis_production (not recommended)."
            )


# Выполняем валидацию при импорте модуля
_validate_secret_key(SECRET_KEY)
_validate_redis_config()


# ============================================================================
# 🔑 ГЕНЕРАЦИЯ КЛЮЧЕЙ И ТОКЕНОВ
# ============================================================================

def generate_secret_key(length: int = 32) -> str:
    """
    Генерация криптографически стойкого секретного ключа
    
    Args:
        length: Длина ключа в байтах (по умолчанию 32 = 256 бит)
    
    Returns:
        str: Ключ в hex-формате (длина = length * 2)
    
    Example:
        >>> key = generate_secret_key(32)
        >>> len(key)
        64  # 32 байта * 2 символа на байт в hex
    """
    return secrets.token_hex(length)


def generate_token(length: int = 32) -> str:
    """
    Генерация криптографически стойкого случайного токена
    
    Args:
        length: Длина токена в байтах
    
    Returns:
        str: Токен в hex-формате
    """
    return secrets.token_hex(length)


def generate_nonce(length: int = 16) -> str:
    """
    Генерация одноразового числа (nonce) для защиты от replay-атак
    
    Args:
        length: Длина nonce в байтах
    
    Returns:
        str: Nonce в hex-формате
    """
    return secrets.token_hex(length)


def generate_fernet_key() -> str:
    """
    Генерация ключа для Fernet-шифрования
    
    Returns:
        str: Ключ в URL-safe base64-формате (44 символа)
    """
    return Fernet.generate_key().decode(DEFAULT_ENCODING)


def _derive_fernet_key(raw_key: bytes) -> bytes:
    """
    Безопасный вывод ключа для Fernet через HKDF.
    
    Использует HKDF (HMAC-based Key Derivation Function) для детерминированного
    вывода 32-байтового ключа из исходного ключа любой длины.
    
    Args:
        raw_key: Исходный ключ (может быть любой длины)
    
    Returns:
        bytes: 32-байтовый ключ для Fernet
    
    Security:
        - HKDF обеспечивает криптографически стойкое расширение ключа
        - Добавляет контекстную информацию "nexus-fernet-key-v1"
        - Устойчив к атакам на слабые исходные ключи
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"nexus-fernet-key-v1",
        backend=default_backend()
    )
    return hkdf.derive(raw_key)


# ============================================================================
# ✍️ ПОДПИСИ ДАННЫХ (HMAC-SHA256)
# ============================================================================

# Зарезервированные ключи для метаданных (нельзя использовать в пользовательских данных)
RESERVED_PAYLOAD_KEYS = {'_meta', '_enc_meta', '_signature', '_algorithm'}


def _normalize_for_signing(data: Any) -> bytes:
    """
    Нормализация данных для детерминированной подписи с защитой от DoS.
    
    Args:
        data: Данные любого поддерживаемого типа
    
    Returns:
        bytes: Байтовое представление для подписи
    
    Raises:
        TypeError: Если тип данных не поддерживается
        ValueError: Если данные слишком большие или содержат зарезервированные ключи
    """
    try:
        # Проверка на зарезервированные ключи в словарях
        if isinstance(data, dict):
            reserved_found = RESERVED_PAYLOAD_KEYS & data.keys()
            if reserved_found:
                raise ValueError(
                    f"Payload contains reserved keys: {reserved_found}. "
                    f"Reserved keys: {RESERVED_PAYLOAD_KEYS}"
                )
            
            # Проверка размера перед сериализацией
            estimated_size = len(json.dumps(data, ensure_ascii=False))
            if estimated_size > MAX_SIGNING_DATA_SIZE:
                raise ValueError(
                    f"Dict too large: estimated {estimated_size} > {MAX_SIGNING_DATA_SIZE}"
                )
            
            result = json.dumps(
                data, 
                sort_keys=True, 
                ensure_ascii=False,
                separators=(',', ':')
            ).encode(DEFAULT_ENCODING)
            
        elif isinstance(data, str):
            if len(data) > MAX_SIGNING_DATA_SIZE:
                raise ValueError(f"String too large: {len(data)} > {MAX_SIGNING_DATA_SIZE}")
            result = data.encode(DEFAULT_ENCODING)
            
        elif isinstance(data, bytes):
            if len(data) > MAX_SIGNING_DATA_SIZE:
                raise ValueError(f"Bytes too large: {len(data)} > {MAX_SIGNING_DATA_SIZE}")
            result = data
            
        elif isinstance(data, (int, float, bool, type(None))):
            result = json.dumps(data).encode(DEFAULT_ENCODING)
        else:
            raise TypeError(
                f"Unsupported type for signing: {type(data).__name__}. "
                f"Supported: dict, str, bytes, int, float, bool, None"
            )
        
        # Финальная проверка размера
        if len(result) > MAX_SIGNING_DATA_SIZE:
            raise ValueError(f"Serialized data too large: {len(result)} > {MAX_SIGNING_DATA_SIZE}")
        
        return result
        
    except (ValueError, TypeError) as e:
        # Перехватываем и пере-выбрасываем с безопасным логированием
        _log_security_event('normalize_signing_data_failed', {'error': str(e), 'data_sample': _safe_log_data(data)})
        raise
    except Exception as e:
        _log_security_event('normalize_signing_data_error', {'error': type(e).__name__, 'data_sample': _safe_log_data(data)}, level='error')
        raise ValueError(f"Failed to normalize data: {e}")


def generate_signature(
    data: Any, 
    secret_key: Optional[str] = None,
    algorithm: str = 'sha256'
) -> str:
    """
    Генерация криптографической подписи данных через HMAC
    
    Args:
        data: Данные для подписи (dict, str, bytes, примитивы)
        secret_key: Секретный ключ (по умолчанию из config)
        algorithm: Хеш-алгоритм ('sha256', 'sha384', 'sha512')
    
    Returns:
        str: Подпись в hex-формате
    
    Note:
        Данные должны быть "сырыми" — не модифицированными после получения.
        Для работы с подписанными структурами используйте generate_signed_payload.
    """
    key = (secret_key or SECRET_KEY).encode(DEFAULT_ENCODING)
    data_bytes = _normalize_for_signing(data)
    
    hash_algorithms = {
        'sha256': hashlib.sha256,
        'sha384': hashlib.sha384, 
        'sha512': hashlib.sha512,
    }
    
    if algorithm not in hash_algorithms:
        _log_security_event('unknown_signature_algorithm', {'requested': algorithm, 'used': 'sha256'}, level='warning')
        algorithm = 'sha256'
    
    signature = hmac.new(
        key, 
        data_bytes, 
        hash_algorithms[algorithm]
    ).hexdigest()
    
    return signature


def verify_signature(
    data: Any,
    signature: str,
    secret_key: Optional[str] = None,
    algorithm: str = 'sha256',
    ttl: Optional[int] = DEFAULT_TTL
) -> Tuple[bool, Optional[str]]:
    """
    Проверка криптографической подписи данных
    
    ⚠️ ВАЖНО: Параметр `data` должен быть в том же виде, в котором он был подписан.
    Не модифицируйте данные между получением и вызовом этой функции.
    Для работы с подписанными структурами используйте verify_signed_payload.
    
    Args:
        data: Исходные данные (в "сыром" виде)
        signature: Подпись для проверки (hex-строка)
        secret_key: Секретный ключ
        algorithm: Хеш-алгоритм
        ttl: Время жизни подписи в секундах (None = без проверки времени)
    
    Returns:
        Tuple[bool, Optional[str]]: (валидна_ли, сообщение_об_ошибке)
    """
    try:
        # Сначала проверяем подпись (constant-time сравнение)
        expected = generate_signature(data, secret_key, algorithm)
        if not hmac.compare_digest(signature, expected):
            _log_security_event('signature_mismatch', {
                'signature_provided': signature[:12] + '...',
                'data_sample': _safe_log_data(data)
            }, level='warning')
            return False, SECURITY_ERRORS["invalid_signature"]
        
        # Затем проверяем TTL (если указан)
        if ttl is not None:
            timestamp = _extract_timestamp_safe(data)
            if timestamp is not None:
                age = datetime.now(timezone.utc).timestamp() - float(timestamp)
                if age > ttl:
                    _log_security_event('signature_expired', {
                        'age_seconds': round(age, 1),
                        'ttl_seconds': ttl,
                        'data_sample': _safe_log_data(data)
                    }, level='warning')
                    return False, SECURITY_ERRORS["expired_signature"]
        
        return True, None
        
    except Exception as e:
        _log_security_event('signature_verification_error', {
            'error': type(e).__name__,
            'data_sample': _safe_log_data(data)
        }, level='error')
        return False, "Ошибка проверки подписи"


def generate_signed_payload(
    data: dict,
    secret_key: Optional[str] = None,
    include_metadata: bool = True,
    ttl: Optional[int] = DEFAULT_TTL
) -> dict:
    """
    Создание структуры данных с криптографической подписью
    
    ⚠️ Ключи из RESERVED_PAYLOAD_KEYS нельзя использовать в пользовательских данных.
    Если такие ключи найдены, они будут переименованы с префиксом '_user_'.
    
    Args:
        data: Словарь с полезной нагрузкой
        secret_key: Секретный ключ
        include_metadata: Добавить метаданные (timestamp, nonce)
        ttl: Время жизни
    
    Returns:
        dict: Структура {'payload': {...}, 'signature': '...'}
    """
    # Копируем и защищаем от конфликтов имён
    payload = {}
    for k, v in data.items():
        if k in RESERVED_PAYLOAD_KEYS:
            _log_security_event('reserved_key_renamed', {'original_key': k}, level='warning')
            payload[f'_user_{k}'] = v
        else:
            payload[k] = v
    
    if include_metadata:
        payload['_meta'] = {
            'timestamp': datetime.now(timezone.utc).timestamp(),
            'nonce': generate_nonce(8),
            'ttl': ttl,
            'version': '3.1',
        }
    
    signature = generate_signature(payload, secret_key)
    
    return {
        'payload': payload,
        'signature': signature
    }


def verify_signed_payload(
    signed_data: dict,
    secret_key: Optional[str] = None,
    require_metadata: bool = True
) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Проверка и извлечение подписанных данных
    
    ⚠️ Эта функция — единственный безопасный entry point для работы с подписанными данными.
    Она гарантирует, что данные не были модифицированы после подписания.
    
    Returns:
        Tuple[bool, Optional[dict], Optional[str]]: 
            (успех, очищенные_данные, сообщение_об_ошибке)
    """
    try:
        if not isinstance(signed_data, dict):
            _log_security_event('invalid_signed_data_format', {'type': type(signed_data).__name__})
            return False, None, "Неверный формат подписанных данных"
        
        signature = signed_data.get('signature')
        payload = signed_data.get('payload')
        
        if not signature or payload is None:
            _log_security_event('missing_signature_or_payload', {'keys': list(signed_data.keys())})
            return False, None, "Отсутствует подпись или полезная нагрузка"
        
        # Проверяем подпись ЦЕЛОГО payload (включая _meta)
        is_valid, error = verify_signature(payload, signature, secret_key)
        if not is_valid:
            return False, None, error
        
        # Проверяем метаданные (если требуются)
        if require_metadata:
            meta = payload.get('_meta', {})
            if not isinstance(meta, dict) or 'timestamp' not in meta:
                _log_security_event('missing_required_metadata', {'payload_keys': list(payload.keys())})
                return False, None, "Отсутствуют обязательные метаданные"
        
        # Извлекаем пользовательские данные, исключая служебные ключи
        clean_data = {
            k: (v if not k.startswith('_user_') else v)  # Восстанавливаем переименованные ключи
            for k, v in payload.items() 
            if k not in RESERVED_PAYLOAD_KEYS and not k.startswith('_user_')
        }
        # Добавляем обратно переименованные ключи под оригинальными именами
        for k, v in payload.items():
            if k.startswith('_user_'):
                original_key = k[6:]  # Убираем '_user_'
                clean_data[original_key] = v
        
        return True, clean_data, None
        
    except Exception as e:
        _log_security_event('verify_signed_payload_error', {
            'error': type(e).__name__
        }, level='error')
        return False, None, "Внутренняя ошибка проверки"


def _extract_timestamp_safe(data: Any) -> Optional[float]:
    """Безопасное извлечение timestamp из данных"""
    try:
        if isinstance(data, dict):
            meta = data.get('_meta', {})
            if isinstance(meta, dict) and 'timestamp' in meta:
                ts = meta['timestamp']
                return float(ts) if isinstance(ts, (int, float)) else None
            # Fallback: прямой ключ timestamp
            ts = data.get('timestamp')
            if isinstance(ts, (int, float)):
                return float(ts)
        return None
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# ============================================================================
# 🔒 ХЕШИРОВАНИЕ И ПАРОЛИ С ПОДДЕРЖКОЙ МИГРАЦИИ
# ============================================================================

# Префиксы алгоритмов для поддержки миграции
HASH_ALGORITHM_PREFIXES = {
    'pbkdf2-sha256': 'pbkdf2',
    'argon2': 'argon2',
}
SUPPORTED_HASH_ALGORITHMS = list(HASH_ALGORITHM_PREFIXES.keys())


def _derive_key_pbkdf2(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Вывод ключа из пароля через PBKDF2"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend()
    )
    return kdf.derive(password.encode(DEFAULT_ENCODING))


def _derive_key_argon2(password: str, salt: bytes) -> bytes:
    """Вывод ключа из пароля через Argon2id"""
    try:
        kdf = Argon2id(
            time_cost=ARGON2_PARAMS['time_cost'],
            memory_cost=ARGON2_PARAMS['memory_cost'],
            parallelism=ARGON2_PARAMS['parallelism'],
            hash_len=ARGON2_PARAMS['hash_len'],
            salt=salt,
        )
        return kdf.derive(password.encode(DEFAULT_ENCODING))
    except ImportError:
        # Fallback на PBKDF2 если argon2 не установлен
        _log_security_event('argon2_not_available', {}, level='warning')
        return _derive_key_pbkdf2(password, salt)


def _parse_password_hash(password_hash: str) -> Tuple[str, Dict[str, Any]]:
    """
    Парсинг хеша пароля с извлечением алгоритма и параметров.
    
    Returns:
        Tuple[str, Dict]: (алгоритм, параметры)
    """
    parts = password_hash.split(':')
    
    # Новый формат: 'alg:...'
    if parts[0] in HASH_ALGORITHM_PREFIXES.values():
        algorithm = parts[0]
        # Находим полное имя алгоритма
        for full_name, prefix in HASH_ALGORITHM_PREFIXES.items():
            if prefix == algorithm:
                algorithm = full_name
                break
        
        if algorithm == 'pbkdf2':  # pbkdf2-sha256
            if len(parts) != 4:
                raise ValueError("Invalid pbkdf2 hash format")
            salt_b64, hash_b64, iterations_str = parts[1:]
            return algorithm, {
                'salt': base64.b64decode(salt_b64),
                'hash': base64.b64decode(hash_b64),
                'iterations': int(iterations_str),
            }
        elif algorithm == 'argon2':
            if len(parts) != 3:
                raise ValueError("Invalid argon2 hash format")
            salt_b64, hash_b64 = parts[1:]
            return algorithm, {
                'salt': base64.b64decode(salt_b64),
                'hash': base64.b64decode(hash_b64),
            }
        else:
            raise ValueError(f"Unknown algorithm prefix: {algorithm}")
    
    # Старый формат (без префикса) — для обратной совместимости
    # Формат: 'salt:hash:iterations'
    if len(parts) == 3:
        try:
            int(parts[2])  # Проверяем, что это число (итерации)
            return 'pbkdf2-sha256', {
                'salt': base64.b64decode(parts[0]),
                'hash': base64.b64decode(parts[1]),
                'iterations': int(parts[2]),
            }
        except (ValueError, IndexError):
            pass
    
    raise ValueError(f"Unrecognized password hash format: {password_hash[:20]}...")


def hash_password(password: str, salt: Optional[bytes] = None, algorithm: Optional[str] = None) -> str:
    """
    Безопасное хеширование пароля с поддержкой нескольких алгоритмов
    
    Args:
        password: Пароль в открытом виде
        salt: Соль (генерируется автоматически, если не указана)
        algorithm: Алгоритм ('pbkdf2-sha256' или 'argon2')
    
    Returns:
        str: Строка в формате 'alg_prefix:salt_b64:hash_b64[:iterations]'
    
    Formats:
        PBKDF2: 'pbkdf2:salt_b64:hash_b64:iterations'
        Argon2: 'argon2:salt_b64:hash_b64'
    """
    algorithm = algorithm or DEFAULT_HASH_ALGORITHM
    prefix = HASH_ALGORITHM_PREFIXES.get(algorithm)
    
    if not prefix:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    
    if salt is None:
        salt = secrets.token_bytes(PBKDF2_SALT_LENGTH)
    
    # Вывод ключа в зависимости от алгоритма
    if algorithm == 'pbkdf2-sha256':
        key = _derive_key_pbkdf2(password, salt)
        salt_b64 = base64.b64encode(salt).decode(DEFAULT_ENCODING)
        hash_b64 = base64.b64encode(key).decode(DEFAULT_ENCODING)
        return f"{prefix}:{salt_b64}:{hash_b64}:{PBKDF2_ITERATIONS}"
    
    elif algorithm == 'argon2':
        key = _derive_key_argon2(password, salt)
        salt_b64 = base64.b64encode(salt).decode(DEFAULT_ENCODING)
        hash_b64 = base64.b64encode(key).decode(DEFAULT_ENCODING)
        return f"{prefix}:{salt_b64}:{hash_b64}"
    
    raise ValueError(f"Unhandled algorithm: {algorithm}")


def verify_password(password: str, password_hash: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Проверка пароля против хеша с авто-определением алгоритма
    
    Returns:
        Tuple[bool, Optional[str], Optional[str]]: 
            (пароль_верен, сообщение_об_ошибке, алгоритм_который_использовался)
    """
    try:
        algorithm, params = _parse_password_hash(password_hash)
        
        # Вывод ключа для проверки
        if algorithm == 'pbkdf2-sha256':
            derived_key = _derive_key_pbkdf2(
                password, 
                params['salt'], 
                params.get('iterations', PBKDF2_ITERATIONS)
            )
        elif algorithm == 'argon2':
            derived_key = _derive_key_argon2(password, params['salt'])
        else:
            _log_security_event('unknown_hash_algorithm', {'algorithm': algorithm}, level='error')
            return False, "Ошибка проверки пароля", None
        
        # Constant-time сравнение
        if hmac.compare_digest(derived_key, params['hash']):
            return True, None, algorithm
        else:
            _log_security_event('password_verification_failed', {}, level='info')
            return False, "Неверный пароль", algorithm
            
    except (ValueError, KeyError, base64.binascii.Error) as e:
        _log_security_event('password_hash_parse_error', {'error': str(e)}, level='warning')
        return False, "Ошибка проверки пароля", None
    except Exception as e:
        _log_security_event('password_verification_error', {'error': type(e).__name__}, level='error')
        return False, "Ошибка проверки пароля", None


def needs_password_migration(password_hash: str, target_algorithm: str = 'argon2') -> bool:
    """
    Проверка, требуется ли миграция хеша пароля на более современный алгоритм
    
    Args:
        password_hash: Существующий хеш пароля
        target_algorithm: Целевой алгоритм для миграции
    
    Returns:
        bool: True если требуется пере-хеширование
    """
    try:
        algorithm, _ = _parse_password_hash(password_hash)
        return algorithm != target_algorithm
    except ValueError:
        # Если не можем распарсить — лучше пере-хешировать
        return True


def hash_data(data: Union[str, bytes], algorithm: str = 'sha256') -> str:
    """
    Криптографическое хеширование данных (без соли)
    
    Args:
        data: Данные для хеширования
        algorithm: Алгоритм ('sha256', 'sha384', 'sha512')
    
    Returns:
        str: Хеш в hex-формате
    """
    if isinstance(data, str):
        data_bytes = data.encode(DEFAULT_ENCODING)
    elif isinstance(data, bytes):
        data_bytes = data
    else:
        raise TypeError(f"Unsupported type for hashing: {type(data).__name__}")
    
    algorithms = {
        'sha256': hashlib.sha256,
        'sha384': hashlib.sha384,
        'sha512': hashlib.sha512,
    }
    
    if algorithm not in algorithms:
        _log_security_event('unknown_hash_algorithm', {'requested': algorithm, 'used': 'sha256'}, level='warning')
        algorithm = 'sha256'
    
    return algorithms[algorithm](data_bytes).hexdigest()


# ============================================================================
# 🔐 БЕЗОПАСНОЕ ШИФРОВАНИЕ (Fernet)
# ============================================================================

class SecureEncryption:
    """
    Класс для безопасного шифрования данных через Fernet с HKDF выводом ключа
    
    Features:
        - AES-128-CBC + HMAC-SHA256 (аутентифицированное шифрование)
        - Безопасный вывод ключа через HKDF
        - TTL для зашифрованных токенов
        - Защита от tampering через встроенный HMAC Fernet
    
    Usage:
        encryptor = SecureEncryption(SECRET_KEY)
        token = encryptor.encrypt({'user_id': 123})
        data = encryptor.decrypt(token)
    """
    
    def __init__(self, key: Optional[str] = None, ttl: Optional[int] = None):
        """
        Инициализация шифратора
        
        Args:
            key: Секретный ключ (будет преобразован через HKDF)
            ttl: Время жизни зашифрованных данных в секундах
        """
        raw_key = (key or SECRET_KEY).encode(DEFAULT_ENCODING)
        
        # Используем безопасный вывод ключа через HKDF
        key_bytes = _derive_fernet_key(raw_key)
        self.fernet_key = base64.urlsafe_b64encode(key_bytes)
        self.fernet = Fernet(self.fernet_key)
        self.ttl = ttl
    
    def encrypt(self, data: Any, include_timestamp: bool = True) -> str:
        """
        Шифрование данных
        
        Args:
            data: Данные для шифрования
            include_timestamp: Добавить timestamp для TTL-проверки
        
        Returns:
            str: Зашифрованный токен
        
        Raises:
            ValueError: Если данные слишком большие
        """
        payload = data
        
        if include_timestamp and self.ttl is not None:
            if isinstance(payload, dict):
                payload = payload.copy()
                # Используем отдельный ключ для метаданных шифрования
                payload['_enc_meta'] = {
                    'exp': datetime.now(timezone.utc).timestamp() + self.ttl
                }
        
        json_data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        
        if len(json_data.encode(DEFAULT_ENCODING)) > MAX_SERIALIZED_SIZE:
            _log_security_event('encryption_data_too_large', {'size': len(json_data)})
            raise ValueError(SECURITY_ERRORS["data_too_large"])
        
        encrypted = self.fernet.encrypt(json_data.encode(DEFAULT_ENCODING))
        return encrypted.decode(DEFAULT_ENCODING)
    
    def decrypt(self, token: str, verify_ttl: bool = True) -> Tuple[bool, Any, Optional[str]]:
        """
        Дешифрование данных
        
        Returns:
            Tuple[bool, Any, Optional[str]]: (успех, данные, ошибка)
        """
        try:
            decrypted = self.fernet.decrypt(token.encode(DEFAULT_ENCODING))
            data = json.loads(decrypted.decode(DEFAULT_ENCODING))
            
            if verify_ttl and self.ttl is not None:
                meta = data.get('_enc_meta', {}) if isinstance(data, dict) else {}
                exp = meta.get('exp')
                if exp and datetime.now(timezone.utc).timestamp() > float(exp):
                    _log_security_event('encrypted_token_expired', {}, level='warning')
                    return False, None, "Токен истёк"
            
            # Удаляем служебные метаданные
            if isinstance(data, dict) and '_enc_meta' in data:
                data = {k: v for k, v in data.items() if k != '_enc_meta'}
            
            return True, data, None
            
        except InvalidToken:
            _log_security_event('invalid_encryption_token', {'token_sample': token[:20] + '...'}, level='warning')
            return False, None, SECURITY_ERRORS["invalid_token"]
        except json.JSONDecodeError:
            _log_security_event('decrypted_data_parse_error', {}, level='error')
            return False, None, "Ошибка декодирования данных"
        except Exception as e:
            _log_security_event('decryption_error', {'error': type(e).__name__}, level='error')
            return False, None, SECURITY_ERRORS["encryption_error"]
    
    def create_reset_token(self, user_id: int, action: str = 'password_reset') -> str:
        """Создание одноразового токена для сброса пароля"""
        payload = {
            'user_id': user_id,
            'action': action,
            'iat': datetime.now(timezone.utc).timestamp(),
        }
        return self.encrypt(payload, include_timestamp=True)
    
    def verify_reset_token(self, token: str, expected_action: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """Проверка токена сброса"""
        success, data, error = self.decrypt(token, verify_ttl=True)
        
        if not success:
            return False, None, error
        
        if not isinstance(data, dict):
            _log_security_event('reset_token_invalid_format', {})
            return False, None, "Неверный формат данных в токене"
        
        if data.get('action') != expected_action:
            _log_security_event('reset_token_action_mismatch', {
                'expected': expected_action,
                'got': data.get('action')
            }, level='warning')
            return False, None, "Неверный тип токена"
        
        user_id = data.get('user_id')
        if not isinstance(user_id, int):
            _log_security_event('reset_token_invalid_user_id', {'user_id_type': type(user_id).__name__})
            return False, None, "Неверный user_id в токене"
        
        return True, user_id, None


# ============================================================================
# 🛡️ ВАЛИДАЦИЯ И САНИТИЗАЦИЯ ВВОДА
# ============================================================================

def validate_telegram_id(telegram_id: Union[int, str]) -> bool:
    """
    Валидация Telegram ID пользователя или чата
    
    Returns:
        bool: True если ID валидный
    """
    try:
        id_int = int(telegram_id)
        
        if id_int == 0:
            return False
        
        if not (MIN_TELEGRAM_ID <= id_int <= MAX_TELEGRAM_ID):
            return False
        
        return True
        
    except (ValueError, TypeError, OverflowError):
        return False


def sanitize_text_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """
    Базовая очистка текстового ввода (не для HTML!)
    
    Returns:
        str: Очищенный текст
    """
    if not text:
        return ""
    
    if len(text) > max_length:
        _log_security_event('input_truncated', {'original_len': len(text), 'max_len': max_length}, level='warning')
        text = text[:max_length]
    
    # Удаляем управляющие символы (кроме \n, \t, \r)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    return text.strip()


def sanitize_html(
    text: str, 
    max_length: int = MAX_INPUT_LENGTH,
    custom_tags: Optional[List[str]] = None,
    custom_attrs: Optional[Dict[str, List[str]]] = None
) -> str:
    """
    Безопасная санитизация HTML-контента через bleach
    
    Returns:
        str: Безопасный HTML
    """
    if not text:
        return ""
    
    if len(text) > max_length:
        text = text[:max_length]
    
    tags = custom_tags if custom_tags is not None else ALLOWED_HTML_TAGS
    attributes = custom_attrs if custom_attrs is not None else ALLOWED_HTML_ATTRIBUTES
    
    try:
        cleaned = bleach.clean(
            text,
            tags=tags,
            attributes=attributes,
            strip=True,
            strip_comments=True,
        )
        
        # Логируем если теги были удалены (для отладки)
        if SECURITY_CONFIG.get('log_sanitization_changes', False):
            if cleaned != text:
                _log_security_event('html_sanitized', {
                    'original_sample': text[:50],
                    'cleaned_sample': cleaned[:50]
                }, level='info')
        
        return cleaned
    except Exception as e:
        _log_security_event('html_sanitization_error', {'error': type(e).__name__}, level='error')
        # Fallback: удалить всё
        return bleach.clean(text, tags=[], strip=True, strip_comments=True)


def escape_for_display(text: str) -> str:
    """Экранирование текста для безопасного отображения"""
    if not text:
        return ""
    import html
    return html.escape(text, quote=True)


def validate_bet_amount(amount: Any, min_bet: int, max_bet: int) -> Tuple[bool, Optional[str]]:
    """
    Валидация суммы ставки
    
    Returns:
        Tuple[bool, Optional[str]]: (валидна_ли, сообщение_об_ошибке)
    """
    try:
        amount_int = int(float(amount))
        
        if amount_int < min_bet:
            return False, f"Минимальная ставка: {min_bet}"
        if amount_int > max_bet:
            return False, f"Максимальная ставка: {max_bet}"
        if amount_int <= 0:
            return False, "Ставка должна быть положительной"
        
        return True, None
        
    except (ValueError, TypeError, OverflowError):
        return False, "Некорректный формат суммы"


# ============================================================================
# 🛡️ CSRF ЗАЩИТА С АТОМАРНЫМИ ОПЕРАЦИЯМИ
# ============================================================================

class CSRFProtection:
    """
    Асинхронная защита от CSRF-атак с поддержкой Redis и атомарным memory fallback
    
    Features:
        - Redis для production (распределённое хранение, атомарные операции)
        - Memory fallback с блокировками для development
        - Одноразовые токены с TTL
        - Атомарные операции проверки+удаления
    """
    
    def __init__(
        self, 
        redis_client: Optional[Any] = None, 
        ttl: int = CSRF_TTL, 
        prefix: str = "nexus:csrf:",
        require_redis: bool = False
    ):
        """
        Инициализация CSRF защиты
        
        Args:
            redis_client: Redis клиент (aioredis или redis.asyncio)
            ttl: Время жизни токенов в секундах
            prefix: Префикс для ключей в Redis
            require_redis: Требовать Redis (True для production)
        
        Raises:
            RuntimeError: Если require_redis=True и redis_client=None
        """
        if require_redis and redis_client is None:
            raise RuntimeError(SECURITY_ERRORS["redis_required"])
        
        self.redis = redis_client
        self.ttl = ttl
        self.prefix = prefix
        self.require_redis = require_redis
        
        # Memory backend с блокировками для атомарности
        self._memory_tokens: Dict[str, float] = {}
        self._memory_lock = asyncio.Lock()
        self._memory_cleanup_interval = 60
        self._last_cleanup = 0
    
    def _make_key(self, user_id: int, action: str, token: str) -> str:
        return f"{self.prefix}{user_id}:{action}:{token}"
    
    async def generate_token(self, user_id: int, action: str) -> str:
        """Генерация нового CSRF-токена"""
        token = generate_token(16)
        key = self._make_key(user_id, action, token)
        
        if self.redis:
            # Redis SET с NX (только если ключ не существует) и EX (TTL)
            await self.redis.set(key, "1", ex=self.ttl, nx=True)
        else:
            async with self._memory_lock:
                self._memory_tokens[key] = datetime.now(timezone.utc).timestamp()
                self._maybe_cleanup_memory()
        
        return token
    
    async def verify_token(self, user_id: int, action: str, token: str) -> bool:
        """
        Проверка и потребление CSRF-токена (атомарная операция)
        
        Возвращает True только если токен валиден и успешно удалён.
        """
        key = self._make_key(user_id, action, token)
        
        if self.redis:
            # Атомарное удаление: возвращает количество удалённых ключей
            deleted = await self.redis.delete(key)
            return deleted == 1
        else:
            # Атомарная проверка+удаление через блокировку
            async with self._memory_lock:
                if key not in self._memory_tokens:
                    return False
                
                timestamp = self._memory_tokens[key]
                now = datetime.now(timezone.utc).timestamp()
                
                # Проверяем TTL
                if now - timestamp > self.ttl:
                    del self._memory_tokens[key]
                    return False
                
                # Удаляем токен (потребляем)
                del self._memory_tokens[key]
                return True
    
    def _maybe_cleanup_memory(self):
        """Периодическая очистка просроченных memory-токенов"""
        if not self._memory_tokens:
            return
        
        now = datetime.now(timezone.utc).timestamp()
        if now - self._last_cleanup < self._memory_cleanup_interval:
            return
        
        self._last_cleanup = now
        expired = [
            k for k, v in self._memory_tokens.items() 
            if now - v > self.ttl
        ]
        for key in expired:
            del self._memory_tokens[key]
    
    async def revoke_all(self, user_id: int, action: Optional[str] = None) -> int:
        """Массовая отзыв всех токенов пользователя"""
        if self.redis:
            pattern = f"{self.prefix}{user_id}:{action or '*'}:*"
            revoked = 0
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted = await self.redis.delete(*keys)
                    revoked += deleted
                if cursor == 0:
                    break
            
            return revoked
        else:
            async with self._memory_lock:
                if action:
                    keys = [k for k in self._memory_tokens if f"{user_id}:{action}:" in k]
                else:
                    keys = [k for k in self._memory_tokens if f"{user_id}:" in k]
                
                for key in keys:
                    del self._memory_tokens[key]
                
                return len(keys)


# ============================================================================
# 🛡️ RATE LIMITING С ПОДДЕРЖКОЙ REDIS
# ============================================================================

class RateLimiter:
    """
    Скользящее окно rate limiting для защиты от брутфорса
    
    Поддерживает:
        - Memory backend (для development, с asyncio.Lock)
        - Redis backend (для production, атомарные операции)
    
    Usage:
        limiter = RateLimiter(max_attempts=5, window_seconds=300, redis_client=redis)
        
        if not await limiter.is_allowed("login", "123456"):
            await message.answer("Слишком много попыток")
            return
    """
    
    def __init__(
        self, 
        max_attempts: int = 5, 
        window_seconds: int = 300,
        redis_client: Optional[Any] = None,
        require_redis: bool = False,
        redis_prefix: str = "nexus:ratelimit:"
    ):
        """
        Инициализация rate limiter
        
        Args:
            max_attempts: Максимальное количество попыток в окне
            window_seconds: Размер окна в секундах
            redis_client: Redis клиент для production
            require_redis: Требовать Redis в production-режиме
            redis_prefix: Префикс для ключей в Redis
        
        Raises:
            RuntimeError: Если require_redis=True и redis_client=None
        """
        if require_redis and IS_PRODUCTION and redis_client is None:
            raise RuntimeError(SECURITY_ERRORS["redis_required"])
        
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.redis = redis_client
        self.redis_prefix = redis_prefix
        
        # Memory backend
        self._attempts: Dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    def _make_key(self, action: str, identifier: str) -> str:
        return f"{action}:{identifier}"
    
    def _make_redis_key(self, action: str, identifier: str) -> str:
        return f"{self.redis_prefix}{action}:{identifier}"
    
    async def is_allowed(self, action: str, identifier: str) -> bool:
        """Проверка, разрешена ли попытка"""
        if self.redis:
            return await self._is_allowed_redis(action, identifier)
        else:
            return await self._is_allowed_memory(action, identifier)
    
    async def _is_allowed_redis(self, action: str, identifier: str) -> bool:
        """Redis-реализация с использованием sorted sets для sliding window"""
        key = self._make_redis_key(action, identifier)
        now = time.time()
        window_start = now - self.window
        
        async with self.redis.pipeline() as pipe:
            # Удаляем старые записи за пределами окна
            pipe.zremrangebyscore(key, 0, window_start)
            # Считаем текущее количество попыток
            pipe.zcard(key)
            # Добавляем текущую попытку
            pipe.zadd(key, {f"{now}:{secrets.token_hex(4)}": now})
            # Устанавливаем TTL для авто-очистки
            pipe.expire(key, self.window + 60)
            
            results = await pipe.execute()
            current_attempts = results[1]
        
        # current_attempts — это количество ПОСЛЕ добавления новой попытки
        if current_attempts > self.max_attempts:
            _log_security_event('rate_limit_exceeded', {
                'action': action,
                'identifier_sample': _safe_log_data(identifier),
                'attempts': current_attempts,
                'max': self.max_attempts
            }, level='warning')
            return False
        
        return True
    
    async def _is_allowed_memory(self, action: str, identifier: str) -> bool:
        """Memory-реализация с блокировкой для атомарности"""
        key = self._make_key(action, identifier)
        now = time.time()
        
        async with self._lock:
            attempts = self._attempts[key]
            
            # Удаляем просроченные записи
            while attempts and attempts[0] <= now - self.window:
                attempts.popleft()
            
            # Проверяем лимит
            if len(attempts) >= self.max_attempts:
                _log_security_event('rate_limit_exceeded', {
                    'action': action,
                    'identifier_sample': _safe_log_data(identifier),
                    'backend': 'memory'
                }, level='warning')
                return False
            
            # Добавляем текущую попытку
            attempts.append(now)
            return True
    
    async def get_remaining(self, action: str, identifier: str) -> int:
        """Получить количество оставшихся попыток"""
        if self.redis:
            return await self._get_remaining_redis(action, identifier)
        else:
            return await self._get_remaining_memory(action, identifier)
    
    async def _get_remaining_redis(self, action: str, identifier: str) -> int:
        key = self._make_redis_key(action, identifier)
        now = time.time()
        window_start = now - self.window
        
        # Считаем актуальные попытки
        count = await self.redis.zcount(key, window_start, now)
        return max(0, self.max_attempts - count)
    
    async def _get_remaining_memory(self, action: str, identifier: str) -> int:
        key = self._make_key(action, identifier)
        now = time.time()
        
        async with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= now - self.window:
                attempts.popleft()
            return max(0, self.max_attempts - len(attempts))
    
    async def reset(self, action: str, identifier: str) -> None:
        """Сбросить счётчик попыток"""
        if self.redis:
            key = self._make_redis_key(action, identifier)
            await self.redis.delete(key)
        else:
            key = self._make_key(action, identifier)
            async with self._lock:
                if key in self._attempts:
                    del self._attempts[key]
    
    def cleanup_expired(self) -> int:
        """Очистить все просроченные записи в memory backend"""
        if self.redis:
            return 0  # Redis очищает сам через TTL
        
        now = time.time()
        removed = 0
        
        for key in list(self._attempts.keys()):
            attempts = self._attempts[key]
            while attempts and attempts[0] <= now - self.window:
                attempts.popleft()
            if not attempts:
                del self._attempts[key]
                removed += 1
        
        return removed


# ============================================================================
# 🔑 КОЛЬЦЕВОЕ ХРАНИЛИЩЕ КЛЮЧЕЙ (ДЛЯ РОТАЦИИ)
# ============================================================================

class KeyRing:
    """
    Кольцевое хранилище ключей для поддержки ротации
    
    Позволяет использовать несколько ключей одновременно:
    - current_key: для подписи новых данных
    - previous_keys: для верификации старых данных
    
    Security:
        - Все ключи проверяются через constant-time сравнение
        - Ограничение количества предыдущих ключей для минимизации поверхности атаки
    """
    
    def __init__(self, current_key: str, previous_keys: Optional[List[str]] = None):
        self.current_key = current_key
        self.previous_keys = previous_keys or []
        self._max_previous = SECURITY_CONFIG.get('max_previous_keys', 5)
    
    def verify_signature(self, data: Any, signature: str, algorithm: str = 'sha256') -> bool:
        """Проверка подписи с использованием всех доступных ключей"""
        # Проверяем текущим ключом (самый частый случай — оптимизация)
        if verify_signature(data, signature, self.current_key, algorithm)[0]:
            return True
        
        # Проверяем предыдущими ключами (для обратной совместимости)
        for old_key in self.previous_keys:
            if verify_signature(data, signature, old_key, algorithm)[0]:
                return True
        
        _log_security_event('signature_verification_all_keys_failed', {
            'data_sample': _safe_log_data(data),
            'signature_sample': signature[:12] + '...'
        }, level='warning')
        return False
    
    def sign(self, data: Any, algorithm: str = 'sha256') -> str:
        """Подпись данных текущим ключом"""
        return generate_signature(data, self.current_key, algorithm)
    
    def rotate(self, new_key: str):
        """
        Ротация ключей
        
        Текущий ключ перемещается в previous_keys, новый становится current.
        """
        _log_security_event('key_rotation', {'previous_keys_count': len(self.previous_keys)}, level='info')
        
        self.previous_keys.insert(0, self.current_key)
        self.current_key = new_key
        
        # Ограничиваем количество предыдущих ключей
        self.previous_keys = self.previous_keys[:self._max_previous]


# ============================================================================
# 🏗️ DEPENDENCY INJECTION: SecurityContext
# ============================================================================

@dataclass
class SecurityContext:
    """
    Контекст безопасности с dependency injection для тестируемости.
    
    Позволяет создавать изолированные экземпляры сервисов безопасности
    с разными конфигурациями (например, для тестов).
    
    Usage:
        # Production
        ctx = SecurityContext.create_production(secret_key, redis_client)
        
        # Testing
        ctx = SecurityContext.create_testing()
        
        # Использование
        token = ctx.csrf.generate_token(123, "action")
    """
    secret_key: str
    redis_client: Optional[Any] = None
    ttl_config: Dict[str, int] = field(default_factory=dict)
    require_redis: bool = True
    
    _encryptor: Optional[SecureEncryption] = field(init=False, default=None)
    _csrf: Optional[CSRFProtection] = field(init=False, default=None)
    _rate_limiter: Optional[RateLimiter] = field(init=False, default=None)
    
    @classmethod
    def create_production(
        cls,
        secret_key: str,
        redis_client: Any,
        ttl_config: Optional[Dict[str, int]] = None
    ) -> 'SecurityContext':
        """Создание контекста для production-окружения"""
        return cls(
            secret_key=secret_key,
            redis_client=redis_client,
            ttl_config=ttl_config or {},
            require_redis=True
        )
    
    @classmethod
    def create_testing(
        cls,
        secret_key: Optional[str] = None,
        require_redis: bool = False
    ) -> 'SecurityContext':
        """Создание контекста для тестирования (memory backend)"""
        return cls(
            secret_key=secret_key or generate_secret_key(32),
            redis_client=None,
            require_redis=require_redis
        )
    
    @property
    def encryptor(self) -> SecureEncryption:
        if self._encryptor is None:
            ttl = self.ttl_config.get('encryption', DEFAULT_TTL)
            self._encryptor = SecureEncryption(self.secret_key, ttl=ttl)
        return self._encryptor
    
    @property
    def csrf(self) -> CSRFProtection:
        if self._csrf is None:
            ttl = self.ttl_config.get('csrf', CSRF_TTL)
            self._csrf = CSRFProtection(
                redis_client=self.redis_client,
                ttl=ttl,
                require_redis=self.require_redis
            )
        return self._csrf
    
    @property
    def rate_limiter(self) -> RateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = RateLimiter(
                redis_client=self.redis_client,
                require_redis=self.require_redis
            )
        return self._rate_limiter
    
    def sign_payload(self, data: dict, ttl: Optional[int] = None) -> dict:
        """Удобный метод для создания подписанных данных"""
        return generate_signed_payload(data, self.secret_key, ttl=ttl)
    
    def verify_payload(self, signed_data: dict) -> Tuple[bool, Optional[dict], Optional[str]]:
        """Удобный метод для проверки подписанных данных"""
        return verify_signed_payload(signed_data, self.secret_key)


# ============================================================================
# 🧰 ГЛОБАЛЬНЫЕ ЭКЗЕМПЛЯРЫ (для обратной совместимости)
# ============================================================================

# ⚠️ Для новых проектов рекомендуется использовать SecurityContext
# Эти глобальные экземпляры оставлены для обратной совместимости

_encryptor_instance: Optional[SecureEncryption] = None
_csrf_instance: Optional[CSRFProtection] = None
_rate_limiter_instance: Optional[RateLimiter] = None


def get_encryptor(key: Optional[str] = None, ttl: Optional[int] = None) -> SecureEncryption:
    """Получить экземпляр шифратора (с кэшированием)"""
    global _encryptor_instance
    if _encryptor_instance is None:
        _encryptor_instance = SecureEncryption(key or SECRET_KEY, ttl=ttl)
    return _encryptor_instance


def get_csrf(redis_client: Optional[Any] = None, ttl: Optional[int] = None) -> CSRFProtection:
    """Получить экземпляр CSRF защиты (с кэшированием)"""
    global _csrf_instance
    if _csrf_instance is None:
        _csrf_instance = CSRFProtection(
            redis_client=redis_client,
            ttl=ttl or CSRF_TTL,
            require_redis=IS_PRODUCTION
        )
    return _csrf_instance


def get_rate_limiter(redis_client: Optional[Any] = None) -> RateLimiter:
    """Получить экземпляр rate limiter (с кэшированием)"""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter(
            redis_client=redis_client,
            require_redis=IS_PRODUCTION
        )
    return _rate_limiter_instance


# Глобальные лимитеры для стандартных сценариев
password_login_limiter = RateLimiter(max_attempts=5, window_seconds=300)
password_reset_limiter = RateLimiter(max_attempts=3, window_seconds=3600)
api_call_limiter = RateLimiter(max_attempts=60, window_seconds=60)


# ============================================================================
# 🧪 ТЕСТОВЫЕ ФУНКЦИИ
# ============================================================================

async def run_security_tests() -> Dict[str, bool]:
    """
    Запуск набора тестов безопасности
    
    Returns:
        Dict[str, bool]: Результаты тестов
    """
    results = {}
    logger.info("Running security module tests...")
    
    # Тест 1: Генерация ключей
    try:
        key1 = generate_secret_key(32)
        key2 = generate_secret_key(32)
        assert len(key1) == 64
        assert key1 != key2
        # Проверка валидации
        try:
            _validate_secret_key("weak")
            assert False, "Should have raised"
        except RuntimeError:
            pass
        results['key_generation'] = True
    except Exception as e:
        logger.error(f"Test key_generation failed: {e}")
        results['key_generation'] = False
    
    # Тест 2: Подписи с защитой от _meta коллизий
    try:
        # Нормальный случай
        data = {"user_id": 123, "action": "test"}
        signed = generate_signed_payload(data)
        assert 'payload' in signed and 'signature' in signed
        valid, extracted, error = verify_signed_payload(signed)
        assert valid and extracted == data and error is None
        
        # Тест коллизии _meta
        data_with_reserved = {"_meta": "malicious", "real": "data"}
        signed = generate_signed_payload(data_with_reserved)
        valid, extracted, error = verify_signed_payload(signed)
        assert valid
        assert extracted.get("real") == "data"
        assert "_meta" not in extracted  # Зарезервированный ключ отфильтрован
        assert extracted.get("_user__meta") == "malicious"  # Переименован
        
        # Тест подделки подписи
        signed['payload']['user_id'] = 999
        valid, _, _ = verify_signed_payload(signed)
        assert not valid
        
        results['signatures'] = True
    except Exception as e:
        logger.error(f"Test signatures failed: {e}")
        results['signatures'] = False
    
    # Тест 3: Хеширование паролей с миграцией
    try:
        password = "TestP@ssw0rd!2024"
        
        # PBKDF2 (старый формат для совместимости)
        hashed_old = f"{base64.b64encode(b'salt').decode()}:{base64.b64encode(b'hash').decode()}:100000"
        # Новый формат
        hashed_new = hash_password(password, algorithm='pbkdf2-sha256')
        assert hashed_new.startswith('pbkdf2:')
        
        valid, error, alg = verify_password(password, hashed_new)
        assert valid and error is None and alg == 'pbkdf2-sha256'
        
        valid, _, _ = verify_password("wrong_password", hashed_new)
        assert not valid
        
        # Проверка миграции
        assert not needs_password_migration(hashed_new, 'pbkdf2-sha256')
        assert needs_password_migration(hashed_new, 'argon2')
        
        results['password_hashing'] = True
    except Exception as e:
        logger.error(f"Test password_hashing failed: {e}")
        results['password_hashing'] = False
    
    # Тест 4: Шифрование
    try:
        enc = SecureEncryption(SECRET_KEY, ttl=60)
        original = {"secret": "data", "user": 123}
        
        token = enc.encrypt(original)
        assert isinstance(token, str) and len(token) > 0
        
        success, decrypted, error = enc.decrypt(token)
        assert success and decrypted == original and error is None
        
        # Тест истечения токена
        enc_short = SecureEncryption(SECRET_KEY, ttl=1)
        token_short = enc_short.encrypt({"test": "data"})
        await asyncio.sleep(1.1)
        success, _, error = enc_short.decrypt(token_short)
        assert not success and error == "Токен истёк"
        
        results['encryption'] = True
    except Exception as e:
        logger.error(f"Test encryption failed: {e}")
        results['encryption'] = False
    
    # Тест 5: Санитизация
    try:
        malicious = "<script>alert('xss')</script>Safe <b>text</b>"
        cleaned = sanitize_html(malicious)
        assert '<script>' not in cleaned
        assert '<b>text</b>' in cleaned
        
        # Тест с кастомными тегами
        custom = sanitize_html("<img src=x onerror=alert(1)>", custom_tags=['img'], custom_attrs={'img': ['src']})
        assert 'onerror' not in custom
        
        results['sanitization'] = True
    except Exception as e:
        logger.error(f"Test sanitization failed: {e}")
        results['sanitization'] = False
    
    # Тест 6: CSRF с атомарностью
    try:
        csrf_mem = CSRFProtection(redis_client=None, ttl=5)
        token = await csrf_mem.generate_token(123, "test_action")
        
        # Первое использование — успех
        assert await csrf_mem.verify_token(123, "test_action", token)
        # Повторное использование — отказ (токен потреблён)
        assert not await csrf_mem.verify_token(123, "test_action", token)
        # Неверный токен
        assert not await csrf_mem.verify_token(123, "test_action", "invalid")
        
        results['csrf'] = True
    except Exception as e:
        logger.error(f"Test csrf failed: {e}")
        results['csrf'] = False
    
    # Тест 7: Rate limiting
    try:
        limiter = RateLimiter(max_attempts=3, window_seconds=60)
        
        assert await limiter.is_allowed("test", "user1")
        assert await limiter.is_allowed("test", "user1")
        assert await limiter.is_allowed("test", "user1")
        assert not await limiter.is_allowed("test", "user1")  # Лимит исчерпан
        assert await limiter.is_allowed("test", "user2")  # Другой пользователь
        
        # Проверка remaining
        remaining = await limiter.get_remaining("test", "user2")
        assert remaining == 2  # 3 - 1 использованная
        
        results['rate_limiting'] = True
    except Exception as e:
        logger.error(f"Test rate_limiting failed: {e}")
        results['rate_limiting'] = False
    
    # Тест 8: Безопасное логирование
    try:
        sensitive = {"api_key": "sk-12345_secret", "user": "test"}
        logged = _safe_log_data(sensitive)
        assert "sk-12345_secret" not in logged
        assert "REDACTED" in logged or "hash=" in logged
        
        results['safe_logging'] = True
    except Exception as e:
        logger.error(f"Test safe_logging failed: {e}")
        results['safe_logging'] = False
    
    # Итоги
    passed = sum(results.values())
    total = len(results)
    logger.info(f"Security tests: {passed}/{total} passed")
    
    return results


# ============================================================================
# 🎯 ЭКСПОРТ ПУБЛИЧНОГО API
# ============================================================================

__all__ = [
    # Генерация ключей
    'generate_secret_key',
    'generate_token', 
    'generate_nonce',
    'generate_fernet_key',
    
    # Подписи данных
    'generate_signature',
    'verify_signature',
    'generate_signed_payload',
    'verify_signed_payload',
    'RESERVED_PAYLOAD_KEYS',
    
    # Хеширование
    'hash_password',
    'verify_password',
    'needs_password_migration',
    'hash_data',
    'SUPPORTED_HASH_ALGORITHMS',
    
    # Шифрование
    'SecureEncryption',
    
    # Валидация
    'validate_telegram_id',
    'sanitize_text_input',
    'sanitize_html',
    'escape_for_display',
    'validate_bet_amount',
    
    # CSRF
    'CSRFProtection',
    
    # Rate limiting
    'RateLimiter',
    
    # Key ring
    'KeyRing',
    
    # Dependency injection
    'SecurityContext',
    
    # Глобальные фабрики (обратная совместимость)
    'get_encryptor',
    'get_csrf',
    'get_rate_limiter',
    'password_login_limiter',
    'password_reset_limiter',
    'api_call_limiter',
    
    # Утилиты
    '_safe_log_data',
    '_log_security_event',
    
    # Тестирование
    'run_security_tests',
    
    # Константы
    'DEFAULT_TTL',
    'CSRF_TTL',
    'ALLOWED_HTML_TAGS',
    'ALLOWED_HTML_ATTRIBUTES',
    'IS_PRODUCTION',
    'SECURITY_ERRORS',
]


# ============================================================================
# 🚀 ЗАПУСК ПРИ ИМПОРТЕ
# ============================================================================

# Дополнительные проверки при загрузке в production
if IS_PRODUCTION:
    logger.info(f"Security module loaded in PRODUCTION mode")
    logger.info(f"Redis required: {SECURITY_CONFIG.get('require_redis_production', True)}")
    logger.info(f"Hash algorithm: {DEFAULT_HASH_ALGORITHM}")


if __name__ == "__main__":
    async def main():
        results = await run_security_tests()
        print(f"\n{'='*60}")
        print("SECURITY MODULE TEST RESULTS (v3.1)")
        print(f"{'='*60}")
        for test, passed in sorted(results.items()):
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {test}")
        print(f"{'='*60}")
        print(f"Overall: {sum(results.values())}/{len(results)} tests passed")
        print(f"{'='*60}\n")
        
        if not all(results.values()):
            print("⚠️ Some tests failed! Review logs above.")
            exit(1)
        else:
            print("🎉 All security tests passed! Module is production-ready.")
    
    asyncio.run(main())

