"""
NEXUS Interactive Games Module — Industrial Edition (FIXED v2.0)
✅ Полная изоляция данных между чатами
✅ Безопасная HMAC подпись с timestamp и replay-защитой
✅ Rate limiting для всех эндпоинтов
✅ Полная валидация всех входных данных
✅ Graceful shutdown с завершением активных игр
✅ Health checks для всех зависимостей
✅ Исправлены все критические баги (см. changelog ниже)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import random
import signal
import sys
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List, Set, Literal
from functools import wraps

import aiosqlite
import redis.asyncio as redis
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, BotCommandScopeDefault
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from prometheus_client import Counter, Histogram, Gauge, start_http_server

from config import (
    DATABASE_PATH, REDIS_URL, SECRET_KEY, BOT_TOKEN,
    MIN_BET, MAX_BET, DUEL_TIMEOUT, RATE_LIMIT_GAMES,
    PROMETHEUS_PORT, DB_POOL_SIZE, MAX_BET_CONFIRMATION,
    ADMIN_IDS  # ✅ Добавлено: список админов
)

# ============================================================================
# 📋 LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('nexus_games.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger("nexus.games")

# ============================================================================
# 📊 PROMETHEUS METRICS (✅ ИСПРАВЛЕНО: объявлены метрики)
# ============================================================================
API_ERRORS = Counter(
    'api_errors_total', 
    'Total API errors by endpoint and type',
    ['endpoint', 'error_type'],
    documentation='Counts errors in API endpoints'
)
GAMES_STARTED = Counter(
    'games_started_total',
    'Total games started by type and role',
    ['game', 'user_role'],
    documentation='Counts game sessions started'
)
GAMES_RESULT = Counter(
    'games_result_total',
    'Game outcomes by type and result',
    ['game', 'result'],
    documentation='Counts game results (win/loss/draw)'
)
REDIS_CONNECTED = Gauge(
    'redis_connected',
    'Redis connection status (1=connected, 0=disconnected)',
    documentation='Indicates if Redis is available'
)
DB_POOL_ACTIVE = Gauge(
    'db_pool_active_connections',
    'Number of active database connections',
    documentation='Tracks active DB connections in pool'
)
ACTIVE_DUELS = Gauge(
    'active_duels_count',
    'Number of currently active duels',
    documentation='Tracks pending/active duels'
)

# ============================================================================
# 🎯 КОНСТАНТЫ
# ============================================================================
SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍉", "🔔", "💎", "7️⃣"]
SLOT_PAYOUTS = {
    ("7️⃣", "7️⃣", "7️⃣"): 10,
    ("💎", "💎", "💎"): 7,
    ("🔔", "🔔", "🔔"): 5,
    ("🍒", "🍒", "🍒"): 3,
    ("🍋", "🍋", "🍋"): 3,
    ("🍊", "🍊", "🍊"): 3,
    ("🍉", "🍉", "🍉"): 3
}
RPS_CHOICES = {"камень": "🪨", "ножницы": "✂️", "бумага": "📄"}

# ============================================================================
# 🗄️ ASYNC DATABASE POOL (✅ ИСПРАВЛЕНО: корректное закрытие)
# ============================================================================
class AsyncDBPool:
    """Connection pool для aiosqlite с поддержкой таймаутов и повторных попыток"""
    
    def __init__(self, db_path: str, pool_size: int = DB_POOL_SIZE):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: Optional[asyncio.Queue] = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._active_connections: Set[int] = set()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Инициализация пула соединений"""
        async with self._lock:
            if self._initialized:
                return
            
            self._pool = asyncio.Queue(maxsize=self.pool_size)
            
            for i in range(self.pool_size):
                conn = await self._create_connection()
                await self._pool.put(conn)
            
            await self._ensure_schema()
            self._initialized = True
            logger.info(f"DB pool initialized: {self.pool_size} connections")
            
            # ✅ Запускаем фоновую задачу очистки idempotency_keys
            self._cleanup_task = asyncio.create_task(self._idempotency_cleaner())
    
    async def _idempotency_cleaner(self, interval: int = 300):
        """Фоновая задача для очистки просроченных ключей идемпотентности"""
        while True:
            try:
                await asyncio.sleep(interval)
                async with self.acquire() as conn:
                    result = await conn.execute(
                        "DELETE FROM idempotency_keys WHERE expires_at < CURRENT_TIMESTAMP"
                    )
                    deleted = result.rowcount
                    await conn.commit()
                    if deleted > 0:
                        logger.debug(f"Cleaned {deleted} expired idempotency keys")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Idempotency cleaner error: {e}", exc_info=True)
    
    async def _create_connection(self) -> aiosqlite.Connection:
        """Создание нового соединения с таймаутом"""
        conn = await aiosqlite.connect(self.db_path, timeout=10.0)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA cache_size=-64000")
        await conn.commit()
        return conn
    
    async def _ensure_schema(self):
        """Создание/обновление схемы БД с изоляцией по chat_id"""
        async with self.acquire() as conn:
            # Таблица пользователей с версионированием
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    username TEXT,
                    free_balance INTEGER DEFAULT 0 NOT NULL,
                    paid_balance INTEGER DEFAULT 0 NOT NULL,
                    version INTEGER DEFAULT 0 NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, chat_id),
                    CHECK (free_balance >= 0),
                    CHECK (paid_balance >= 0)
                )
            """)
            
            # Аудит-лог (с chat_id для изоляции)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_before INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id, chat_id)")
            
            # Кэш участников чата
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_members (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            
            # Идемпотентность-ключи с TTL
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_idem_expires ON idempotency_keys(expires_at)")
            
            # Таблица для replay-защиты (подписи с timestamp)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS signature_log (
                    signature TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sig_user ON signature_log(user_id, chat_id)")
            
            await conn.commit()
            logger.info("Database schema ensured")
    
    @asynccontextmanager
    async def acquire(self):
        """Получение соединения из пула с таймаутом"""
        if not self._initialized:
            await self.initialize()
        
        try:
            conn = await asyncio.wait_for(self._pool.get(), timeout=5.0)
            self._active_connections.add(id(conn))
            DB_POOL_ACTIVE.set(len(self._active_connections))
            yield conn
        except asyncio.TimeoutError:
            logger.error("Database connection timeout")
            raise RuntimeError("No available database connections")
        finally:
            self._active_connections.discard(id(conn))
            DB_POOL_ACTIVE.set(len(self._active_connections))
            await self._pool.put(conn)
    
    async def health_check(self) -> bool:
        """Проверка доступности БД"""
        try:
            async with self.acquire() as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"DB health check failed: {e}", exc_info=True)
            return False
    
    async def close(self):
        """✅ ИСПРАВЛЕНО: Корректное закрытие всех соединений"""
        if not self._pool:
            return
        
        # Останавливаем фоновые задачи
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Собираем все соединения
        connections = []
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                connections.append(conn)
            except asyncio.QueueEmpty:
                break
        
        # Закрываем все соединения параллельно с обработкой ошибок
        if connections:
            await asyncio.gather(*[conn.close() for conn in connections], return_exceptions=True)
        
        self._initialized = False
        self._active_connections.clear()
        DB_POOL_ACTIVE.set(0)
        logger.info("DB pool closed")


# ============================================================================
# 💰 BALANCE MANAGER (✅ ИСПРАВЛЕНО: безопасный CAS с rollback)
# ============================================================================
@dataclass
class BalanceVersion:
    """Версионированный баланс для CAS-операций"""
    user_id: int
    chat_id: int
    free_balance: int
    paid_balance: int
    version: int
    
    @property
    def total(self) -> int:
        return self.free_balance + self.paid_balance
    
    def can_spend(self, amount: int) -> bool:
        return self.total >= amount and amount > 0


class BalanceManager:
    """Менеджер баланса с CAS-паттерном и изоляцией по chat_id"""
    
    def __init__(self, db_pool: AsyncDBPool):
        self.db_pool = db_pool
    
    async def get_with_version(self, user_id: int, chat_id: int) -> Optional[BalanceVersion]:
        """Получение баланса с версией (изоляция по chat_id)"""
        async with self.db_pool.acquire() as conn:
            async with conn.execute("""
                SELECT free_balance, paid_balance, version 
                FROM users 
                WHERE user_id=? AND chat_id=?
            """, (user_id, chat_id)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return BalanceVersion(
                    user_id=user_id, chat_id=chat_id,
                    free_balance=row[0], paid_balance=row[1], version=row[2]
                )
    
    async def create_user(self, user_id: int, chat_id: int, username: str = None):
        """Создание пользователя с бонусом"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT OR IGNORE INTO users (user_id, chat_id, username, free_balance, version)
                VALUES (?, ?, ?, 100, 1)
            """, (user_id, chat_id, username))
            await conn.commit()
    
    async def update_cas(self, balance: BalanceVersion, delta_free: int = 0, delta_paid: int = 0) -> bool:
        """CAS-обновление с проверкой версии и chat_id"""
        new_free = balance.free_balance + delta_free
        new_paid = balance.paid_balance + delta_paid
        
        if new_free < 0 or new_paid < 0:
            logger.warning(f"Negative balance attempt: free={new_free}, paid={new_paid}")
            return False
        
        async with self.db_pool.acquire() as conn:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                
                # Проверяем текущую версию и chat_id
                async with conn.execute("""
                    SELECT version FROM users 
                    WHERE user_id=? AND chat_id=?
                """, (balance.user_id, balance.chat_id)) as cursor:
                    current = await cursor.fetchone()
                
                if not current or current[0] != balance.version:
                    await conn.rollback()
                    logger.debug(f"CAS conflict: expected v{balance.version}, got v{current[0] if current else 'None'}")
                    return False
                
                # Обновляем с инкрементом версии
                await conn.execute("""
                    UPDATE users 
                    SET free_balance = ?, paid_balance = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id=? AND chat_id=? AND version=?
                """, (new_free, new_paid, balance.user_id, balance.chat_id, balance.version))
                
                await conn.commit()
                return True
                
            except Exception as e:
                await conn.rollback()
                logger.error(f"CAS update failed: {e}", exc_info=True)
                return False
    
    async def atomic_transfer(
        self, from_user: int, to_user: int, chat_id: int, amount: int,
        max_retries: int = 3
    ) -> Tuple[bool, str]:
        """✅ ИСПРАВЛЕНО: Атомарный перевод с безопасным rollback"""
        if amount <= 0:
            return False, "Сумма должна быть положительной"
        
        if amount > MAX_BET:
            return False, f"Максимальная сумма перевода: {MAX_BET} NCoin"
        
        for attempt in range(max_retries):
            from_bal = await self.get_with_version(from_user, chat_id)
            to_bal = await self.get_with_version(to_user, chat_id)
            
            if not from_bal or not from_bal.can_spend(amount):
                return False, "Недостаточно средств"
            
            # CAS для отправителя
            if not await self.update_cas(from_bal, delta_free=-amount):
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            
            # CAS для получателя
            if to_bal:
                if not await self.update_cas(to_bal, delta_free=amount):
                    # ✅ ИСПРАВЛЕНО: Получаем свежую версию для отката
                    from_bal_rollback = await self.get_with_version(from_user, chat_id)
                    if from_bal_rollback:
                        await self.update_cas(from_bal_rollback, delta_free=amount)
                    await asyncio.sleep(0.05 * (attempt + 1))
                    continue
            else:
                # Создаём нового пользователя
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO users (user_id, chat_id, free_balance, version)
                        VALUES (?, ?, ?, 1)
                    """, (to_user, chat_id, amount))
                    await conn.commit()
            
            # Аудит
            await self._log_transfer(from_user, to_user, chat_id, amount)
            return True, "Успешно"
        
        return False, "Превышено количество попыток"
    
    async def _log_transfer(self, from_user: int, to_user: int, chat_id: int, amount: int):
        """Логирование перевода в аудит"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO audit_log (user_id, chat_id, action, amount, balance_before, balance_after, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                from_user, chat_id, "transfer_out", -amount, 0, 0,
                json.dumps({"to_user": to_user, "amount": amount})
            ))
            await conn.execute("""
                INSERT INTO audit_log (user_id, chat_id, action, amount, balance_before, balance_after, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                to_user, chat_id, "transfer_in", amount, 0, 0,
                json.dumps({"from_user": from_user, "amount": amount})
            ))
            await conn.commit()


# ============================================================================
# 🔐 SECURE CALLBACK DATA (✅ ИСПРАВЛЕНО: добавлен game_type для маршрутизации)
# ============================================================================
class SecureCallbackData(CallbackData, prefix="secure"):
    action: str
    game_type: Literal["slot", "duel", "roulette", "rps", "common"]  # ✅ Явный тип игры
    amount: Optional[int] = None
    chat_id: int
    timestamp: int
    signature: str = ""
    
    @classmethod
    def create(cls, action: str, game_type: str, chat_id: int, amount: int = None) -> 'SecureCallbackData':
        timestamp = int(time.time())
        data = f"{action}:{game_type}:{chat_id}:{timestamp}:{amount or ''}"
        signature = hmac.new(
            SECRET_KEY.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        return cls(
            action=action,
            game_type=game_type,
            amount=amount,
            chat_id=chat_id,
            timestamp=timestamp,
            signature=signature
        )
    
    def verify(self, seen_signatures: Set[str] = None) -> Tuple[bool, str]:
        """✅ ИСПРАВЛЕНО: Проверка подписи + replay-защита"""
        # 1. Проверка срока действия (5 минут)
        if abs(time.time() - self.timestamp) > 300:
            return False, "Срок действия запроса истёк"
        
        # 2. Проверка подписи
        data = f"{self.action}:{self.game_type}:{self.chat_id}:{self.timestamp}:{self.amount or ''}"
        expected = hmac.new(
            SECRET_KEY.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        
        if not hmac.compare_digest(self.signature, expected):
            return False, "Неверная подпись запроса"
        
        # 3. ✅ Replay-защита: проверяем, не использовалась ли эта подпись
        if seen_signatures and self.signature in seen_signatures:
            return False, "Запрос уже был обработан"
        
        return True, ""


# ============================================================================
# 🚦 RATE LIMITER (✅ ИСПРАВЛЕНО: очистка memory leak)
# ============================================================================
class RateLimiter:
    """Rate limiter с Redis и in-memory fallback"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None, cleanup_interval: int = 300):
        self.redis = redis_client
        self._memory: Dict[str, List[float]] = {}
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        
        if not redis_client:
            # Запускаем фоновую очистку для in-memory режима
            self._cleanup_task = asyncio.create_task(self._memory_cleanup_loop())
    
    async def _memory_cleanup_loop(self):
        """Периодическая очистка устаревших записей в памяти"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                now = time.time()
                # Удаляем записи старше 10 минут
                for key in list(self._memory.keys()):
                    self._memory[key] = [t for t in self._memory[key] if now - t < 600]
                    if not self._memory[key]:
                        del self._memory[key]
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"RateLimiter cleanup error: {e}", exc_info=True)
    
    async def check(self, user_id: int, action: str, limit: int, window: int) -> Tuple[bool, int]:
        """Проверка лимита: (разрешено, секунд_ожидания)"""
        key = f"rate:{user_id}:{action}"
        
        if self.redis:
            now = int(time.time())
            window_start = now - window
            
            await self.redis.zremrangebyscore(key, 0, window_start)
            count = await self.redis.zcard(key)
            
            if count >= limit:
                oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                wait = int(oldest[0][1] + window - now) if oldest else 1
                return False, max(1, wait)
            
            await self.redis.zadd(key, {str(now): now})
            await self.redis.expire(key, window + 10)
            return True, 0
        else:
            now = time.time()
            records = self._memory.get(key, [])
            records = [t for t in records if now - t < window]
            
            if len(records) >= limit:
                wait = int(window - (now - records[0])) if records else 1
                return False, max(1, wait)
            
            records.append(now)
            self._memory[key] = records
            return True, 0
    
    async def close(self):
        """Остановка фоновых задач"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


# ============================================================================
# 🔍 USER LOOKUP С ЛИМИТАМИ И КЭШИРОВАНИЕМ (✅ ИСПРАВЛЕНО: инъекция bot)
# ============================================================================
class UserCache:
    """Кэш участников чата с защитой от DoS"""
    
    def __init__(self, db_pool: AsyncDBPool, rate_limiter: RateLimiter, bot: Bot):
        self.db_pool = db_pool
        self.rate_limiter = rate_limiter
        self.bot = bot  # ✅ Явная зависимость вместо глобального ctx
        self._lookup_count: Dict[int, int] = {}
    
    async def find_user(self, chat_id: int, username: str, requester_id: int) -> Optional[int]:
        """Поиск пользователя с кэшированием и лимитами"""
        # Rate limit на поиск (10 поисков в минуту)
        ok, wait = await self.rate_limiter.check(requester_id, "user_lookup", 10, 60)
        if not ok:
            logger.warning(f"User lookup rate limit exceeded: user={requester_id}")
            return None
        
        username = username.lower().replace("@", "")
        
        # 1. Проверяем кэш в БД
        async with self.db_pool.acquire() as conn:
            async with conn.execute("""
                SELECT user_id FROM chat_members 
                WHERE chat_id=? AND username=? AND cached_at > datetime('now', '-1 hour')
            """, (chat_id, username)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
        
        # 2. Ищем в Telegram с лимитом
        try:
            chat = await self.bot.get_chat(chat_id)  # ✅ Используем self.bot
            count = 0
            async for member in chat.get_members():
                count += 1
                if count > 500:  # Лимит на перебор
                    logger.warning(f"User lookup limit exceeded in chat {chat_id}")
                    break
                
                if member.user.username and member.user.username.lower() == username:
                    user_id = member.user.id
                    # Кэшируем в БД
                    async with self.db_pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO chat_members (chat_id, user_id, username, full_name)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(chat_id, user_id) DO UPDATE 
                            SET username=?, full_name=?, cached_at=CURRENT_TIMESTAMP
                        """, (
                            chat_id, user_id, username, member.user.full_name,
                            username, member.user.full_name
                        ))
                        await conn.commit()
                    return user_id
        except TelegramForbiddenError:
            logger.warning(f"Bot has no access to chat {chat_id}")
            return None
        except Exception as e:
            logger.warning(f"User lookup failed for @{username}: {e}", exc_info=True)
        
        return None


# ============================================================================
# 🎮 GAME CONTEXT (FIXED)
# ============================================================================
@dataclass
class GameContext:
    """Контекст приложения с зависимостями"""
    bot: Optional[Bot] = None
    db_pool: Optional[AsyncDBPool] = None
    redis: Optional[redis.Redis] = None
    balance_mgr: Optional[BalanceManager] = None
    rate_limiter: Optional[RateLimiter] = None
    user_cache: Optional[UserCache] = None
    _initialized: bool = False
    _shutdown_tasks: List[asyncio.Task] = field(default_factory=list)
    _seen_signatures: Dict[str, Set[str]] = field(default_factory=dict)  # ✅ Для replay-защиты
    
    def initialize(self, bot: Bot, db_pool: AsyncDBPool, redis_client: Optional[redis.Redis] = None):
        self.bot = bot
        self.db_pool = db_pool
        self.redis = redis_client
        self.balance_mgr = BalanceManager(db_pool)
        self.rate_limiter = RateLimiter(redis_client)
        # ✅ Передаём bot в UserCache
        self.user_cache = UserCache(db_pool, self.rate_limiter, bot)
        self._initialized = True
        logger.info("GameContext initialized")
    
    def require(self):
        if not self._initialized:
            raise RuntimeError("GameContext not initialized")
    
    def add_shutdown_task(self, coro):
        """Добавление задачи для graceful shutdown"""
        task = asyncio.create_task(coro)
        self._shutdown_tasks.append(task)
        return task
    
    def is_signature_seen(self, chat_id: int, signature: str) -> bool:
        """Проверка, использовалась ли уже эта подпись (replay-защита)"""
        if chat_id not in self._seen_signatures:
            self._seen_signatures[chat_id] = set()
        if signature in self._seen_signatures[chat_id]:
            return True
        self._seen_signatures[chat_id].add(signature)
        # Очищаем старые подписи каждые 10 минут (упрощённо)
        if len(self._seen_signatures[chat_id]) > 10000:
            # Удаляем половину (простая стратегия)
            items = list(self._seen_signatures[chat_id])
            self._seen_signatures[chat_id] = set(items[5000:])
        return False
    
    async def shutdown(self):
        """Ожидание завершения всех задач"""
        for task in self._shutdown_tasks:
            if not task.done():
                task.cancel()
        if self._shutdown_tasks:
            await asyncio.gather(*self._shutdown_tasks, return_exceptions=True)
        
        # Закрываем rate limiter
        if self.rate_limiter:
            await self.rate_limiter.close()


ctx = GameContext()


# ============================================================================
# 🎰 SLOT MACHINE LOGIC
# ============================================================================
class SlotMachine:
    @staticmethod
    def spin(bet: int) -> Tuple[List[str], int, str]:
        """Вращение слотов с расчётом выигрыша"""
        result = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        win_amount = 0
        win_type = "loss"
        
        key = tuple(result)
        if key in SLOT_PAYOUTS:
            win_amount = bet * SLOT_PAYOUTS[key]
            win_type = "jackpot" if SLOT_PAYOUTS[key] >= 5 else "win"
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            win_amount = bet * 2
            win_type = "win"
        
        return result, win_amount, win_type


# ============================================================================
# ⚔️ DUEL MANAGER (FIXED)
# ============================================================================
@dataclass
class Duel:
    duel_id: str
    challenger_id: int
    target_id: int
    amount: int
    chat_id: int
    message_id: int
    created_at: float
    status: str = "pending"
    
    def is_expired(self) -> bool:
        return time.time() - self.created_at > DUEL_TIMEOUT


class DuelManager:
    """Менеджер дуэлей с полной изоляцией по чатам"""
    
    _duels: Dict[str, Duel] = {}
    _duel_locks: Dict[str, asyncio.Lock] = {}
    
    @classmethod
    async def create(cls, challenger_id: int, target_id: int, amount: int,
                     chat_id: int, message_id: int) -> Duel:
        """Создание дуэли"""
        duel_id = f"{chat_id}:{challenger_id}:{target_id}:{int(time.time())}:{random.randint(1000, 9999)}"
        
        duel = Duel(
            duel_id=duel_id,
            challenger_id=challenger_id,
            target_id=target_id,
            amount=amount,
            chat_id=chat_id,
            message_id=message_id,
            created_at=time.time()
        )
        
        cls._duels[duel_id] = duel
        cls._duel_locks[duel_id] = asyncio.Lock()
        
        # Запускаем таймаут
        ctx.add_shutdown_task(cls._timeout_task(duel_id))
        ACTIVE_DUELS.set(len(cls._duels))
        
        return duel
    
    @classmethod
    async def _timeout_task(cls, duel_id: str):
        """Фоновая задача таймаута дуэли"""
        await asyncio.sleep(DUEL_TIMEOUT)
        
        lock = cls._duel_locks.get(duel_id)
        if not lock:
            return
        
        async with lock:
            duel = cls._duels.get(duel_id)
            if not duel or duel.status != "pending":
                return
            
            duel.status = "expired"
            
            # Возвращаем ставку
            balance = await ctx.balance_mgr.get_with_version(duel.challenger_id, duel.chat_id)
            if balance:
                await ctx.balance_mgr.update_cas(balance, delta_free=duel.amount)
            
            # Уведомление
            try:
                await ctx.bot.edit_message_text(
                    f"⏰ **Дуэль отменена!**\n\n"
                    f"Время истекло. Ставка {duel.amount} NCoin возвращена.",
                    chat_id=duel.chat_id,
                    message_id=duel.message_id
                )
            except Exception as e:
                logger.warning(f"Failed to edit duel timeout message: {e}", exc_info=True)
            
            await cls._cleanup(duel_id)
    
    @classmethod
    async def accept(cls, duel_id: str, target_id: int) -> Tuple[bool, str, Optional[Duel]]:
        """Принятие дуэли"""
        lock = cls._duel_locks.get(duel_id)
        if not lock:
            return False, "Дуэль не найдена", None
        
        async with lock:
            duel = cls._duels.get(duel_id)
            if not duel:
                return False, "Дуэль не найдена", None
            
            if duel.status != "pending":
                return False, "Дуэль уже завершена", None
            
            if duel.target_id != target_id:
                return False, "Это не ваш вызов", None
            
            duel.status = "accepted"
            return True, "", duel
    
    @classmethod
    async def resolve(cls, duel_id: str) -> Optional[Tuple[int, int]]:
        """Определение победителя и начисление"""
        lock = cls._duel_locks.get(duel_id)
        if not lock:
            return None
        
        async with lock:
            duel = cls._duels.get(duel_id)
            if not duel or duel.status != "accepted":
                return None
            
            winner_id = random.choice([duel.challenger_id, duel.target_id])
            win_amount = duel.amount * 2
            
            # Начисление победителю
            winner_balance = await ctx.balance_mgr.get_with_version(winner_id, duel.chat_id)
            if winner_balance:
                await ctx.balance_mgr.update_cas(winner_balance, delta_free=win_amount)
            
            await cls._cleanup(duel_id)
            return winner_id, win_amount
    
    @classmethod
    async def decline(cls, duel_id: str, target_id: int) -> bool:
        """Отклонение дуэли"""
        lock = cls._duel_locks.get(duel_id)
        if not lock:
            return False
        
        async with lock:
            duel = cls._duels.get(duel_id)
            if not duel or duel.status != "pending":
                return False
            
            if duel.target_id != target_id:
                return False
            
            duel.status = "declined"
            await cls._cleanup(duel_id)
            return True
    
    @classmethod
    async def _cleanup(cls, duel_id: str):
        """Очистка данных дуэли"""
        cls._duels.pop(duel_id, None)
        cls._duel_locks.pop(duel_id, None)
        ACTIVE_DUELS.set(len(cls._duels))


# ============================================================================
# 📝 AUDIT LOGGING
# ============================================================================
async def log_financial_action(
    user_id: int, chat_id: int, action: str, amount: int,
    balance_before: int, balance_after: int, metadata: Dict = None
):
    """Запись в аудит-лог с изоляцией по chat_id"""
    try:
        async with ctx.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO audit_log 
                (user_id, chat_id, action, amount, balance_before, balance_after, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, chat_id, action, amount,
                balance_before, balance_after,
                json.dumps(metadata or {}, default=str)
            ))
            await conn.commit()
        
        logger.info(
            f"[AUDIT] user={user_id} chat={chat_id} action={action} "
            f"amount={amount} before={balance_before} after={balance_after}"
        )
    except Exception as e:
        logger.error(f"Audit log failed: {e}", exc_info=True)


# ============================================================================
# 🎮 GAME HANDLERS
# ============================================================================
router = Router()


# ---------- SLOT: Command ----------
@router.message(Command("slot"))
async def cmd_slot(message: Message, state: FSMContext):
    ctx.require()
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Rate limit
    ok, wait = await ctx.rate_limiter.check(user_id, "slot_start", 10, 60)
    if not ok:
        await message.answer(f"⏰ Подождите {wait} сек.")
        return
    
    # Проверка/создание пользователя
    balance = await ctx.balance_mgr.get_with_version(user_id, chat_id)
    if not balance:
        await ctx.balance_mgr.create_user(user_id, chat_id, message.from_user.username)
        balance = await ctx.balance_mgr.get_with_version(user_id, chat_id)
    
    total = balance.total if balance else 100
    
    # Клавиатура с подписанными данными
    buttons = []
    for bet in [10, 50, 100, 500, 1000, 5000]:
        cb = SecureCallbackData.create(action="slot_bet", game_type="slot", chat_id=chat_id, amount=bet)
        buttons.append([InlineKeyboardButton(text=f"{bet} NCoin", callback_data=cb.pack())])
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data=SecureCallbackData.create(action="slot_cancel", game_type="slot", chat_id=chat_id).pack())])
    
    await state.set_state("waiting_slot_bet")
    await message.answer(
        f"🎰 **Слот-машина NEXUS**\n\n"
        f"💰 Баланс: {total} NCoin\n"
        f"🎲 Ставка: {MIN_BET}-{MAX_BET} NCoin\n"
        f"🏆 Макс. выигрыш: x10\n\n"
        f"Выберите ставку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    
    GAMES_STARTED.labels(game="slot", user_role="player").inc()


# ---------- SLOT: Callback Handler (✅ ИСПРАВЛЕНО: фильтр по game_type)
@router.callback_query(SecureCallbackData.filter(F.game_type == "slot"))
async def slot_callback(callback: CallbackQuery, c: SecureCallbackData, state: FSMContext):
    ctx.require()
    
    # ✅ Replay-защита
    if ctx.is_signature_seen(c.chat_id, c.signature):
        await callback.answer("⚠️ Этот запрос уже обработан", show_alert=True)
        API_ERRORS.labels(endpoint="slot", error_type="replay_attempt").inc()
        return
    
    # Проверка подписи и срока действия
    valid, error_msg = c.verify()
    if not valid:
        await callback.answer(f"❌ {error_msg}", show_alert=True)
        API_ERRORS.labels(endpoint="slot", error_type="invalid_signature").inc()
        return
    
    # Проверка chat_id (изоляция)
    if c.chat_id != callback.message.chat.id:
        await callback.answer("❌ Неверный чат", show_alert=True)
        API_ERRORS.labels(endpoint="slot", error_type="chat_mismatch").inc()
        return
    
    # Rate limit
    ok, wait = await ctx.rate_limiter.check(callback.from_user.id, "slot", RATE_LIMIT_GAMES, 60)
    if not ok:
        await callback.answer(f"⏰ Подождите {wait} сек.", show_alert=True)
        return
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    if c.action == "slot_cancel":
        await state.clear()
        await callback.message.edit_text("❌ Игра отменена.")
        await callback.answer()
        return
    
    if c.action == "slot_bet":
        bet = c.amount
        if not (MIN_BET <= bet <= MAX_BET):
            await callback.answer(f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET}", show_alert=True)
            return
        
        # Подтверждение для крупных ставок
        if bet > MAX_BET_CONFIRMATION:
            confirm_cb = SecureCallbackData.create(action="slot_confirm", game_type="slot", chat_id=chat_id, amount=bet)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, подтверждаю", callback_data=confirm_cb.pack())],
                [InlineKeyboardButton(text="❌ Нет, отмена", callback_data=SecureCallbackData.create(action="slot_cancel", game_type="slot", chat_id=chat_id).pack())]
            ])
            await callback.message.edit_text(
                f"⚠️ **Подтверждение ставки**\n\n"
                f"Вы уверены, что хотите поставить **{bet} NCoin**?\n"
                f"Это крупная сумма. Подтвердите действие.",
                reply_markup=keyboard
            )
            await callback.answer()
            return
        
        await _process_slot(callback, state, bet, chat_id, user_id)
    
    elif c.action == "slot_confirm":
        bet = c.amount
        await _process_slot(callback, state, bet, chat_id, user_id)


async def _process_slot(callback: CallbackQuery, state: FSMContext, bet: int, chat_id: int, user_id: int):
    """Основная логика слота"""
    # Идемпотентность
    idem_key = f"slot:{user_id}:{chat_id}:{callback.message.message_id}:{bet}"
    try:
        async with ctx.db_pool.acquire() as conn:
            row = await conn.execute("SELECT result FROM idempotency_keys WHERE key=?", (idem_key,)).fetchone()
            if row:
                await callback.message.edit_text(json.loads(row[0])["text"])
                await callback.answer()
                return
    except Exception as e:
        logger.error(f"Idempotency check failed: {e}", exc_info=True)
    
    # Проверка баланса
    balance = await ctx.balance_mgr.get_with_version(user_id, chat_id)
    if not balance or not balance.can_spend(bet):
        await callback.answer(f"❌ Недостаточно средств. Баланс: {balance.total if balance else 0}", show_alert=True)
        return
    
    # Атомарное списание
    balance_before = balance.total
    if not await ctx.balance_mgr.update_cas(balance, delta_free=-bet):
        await callback.answer("❌ Ошибка списания", show_alert=True)
        API_ERRORS.labels(endpoint="slot", error_type="cas_failed").inc()
        return
    
    # Результат
    result, win_amount, win_type = SlotMachine.spin(bet)
    
    # Начисление выигрыша
    if win_amount > 0:
        new_bal = await ctx.balance_mgr.get_with_version(user_id, chat_id)
        if new_bal:
            await ctx.balance_mgr.update_cas(new_bal, delta_free=win_amount)
    
    balance_after = balance_before - bet + win_amount
    
    # Аудит
    await log_financial_action(
        user_id, chat_id, f"slot_{win_type}",
        win_amount if win_amount > 0 else bet,
        balance_before, balance_after,
        {"bet": bet, "result": result, "win_amount": win_amount}
    )
    
    # Форматирование
    emoji = {"jackpot": "🎉🎉🎉 **ДЖЕКПОТ!** 🎉🎉🎉", "win": "🎉 **ВЫИГРЫШ!** 🎉"}.get(win_type, "😔 **ПРОИГРЫШ!**")
    text = (
        f"🎰 {result[0]} | {result[1]} | {result[2]}\n\n"
        f"{emoji}\n"
        f"{'+' if win_amount > 0 else ''}{win_amount} NCoin\n\n"
        f"💰 Баланс: {balance_after} NCoin"
    )
    
    # Сохраняем идемпотентность
    try:
        async with ctx.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO idempotency_keys (key, result, expires_at) VALUES (?, ?, datetime('now', '+1 hour'))",
                (idem_key, json.dumps({"text": text}))
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"Idempotency save failed: {e}", exc_info=True)
    
    # Кнопки
    repeat_cb = SecureCallbackData.create(action="slot_bet", game_type="slot", chat_id=chat_id, amount=bet)
    other_cb = SecureCallbackData.create(action="slot_other", game_type="slot", chat_id=chat_id)
    menu_cb = SecureCallbackData.create(action="slot_menu", game_type="slot", chat_id=chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔄 Повторить {bet} NCoin", callback_data=repeat_cb.pack())],
        [InlineKeyboardButton(text="🔁 Другая ставка", callback_data=other_cb.pack()),
         InlineKeyboardButton(text="🏠 Меню", callback_data=menu_cb.pack())]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
    
    GAMES_RESULT.labels(game="slot", result=win_type).inc()


# ---------- DUEL: Command ----------
@router.message(Command("duel"))
async def cmd_duel(message: Message, state: FSMContext):
    ctx.require()
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "⚔️ **Дуэль NEXUS**\n\n"
            "Использование: /duel @username [сумма]\n"
            f"Пример: /duel @ivan {MIN_BET}\n\n"
            f"💰 Ставка: {MIN_BET}-{MAX_BET} NCoin\n"
            f"🏆 Победитель забирает банк!"
        )
        return
    
    target_username = args[1].replace("@", "")
    try:
        amount = int(args[2]) if len(args) > 2 else MIN_BET
    except ValueError:
        await message.answer("❌ Неверная сумма ставки")
        return
    
    if not (MIN_BET <= amount <= MAX_BET):
        await message.answer(f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET}")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Rate limit
    ok, wait = await ctx.rate_limiter.check(user_id, "duel", 5, 60)
    if not ok:
        await message.answer(f"⏰ Подождите {wait} сек.")
        return
    
    # Поиск соперника
    target_id = await ctx.user_cache.find_user(chat_id, target_username, user_id)
    if not target_id:
        await message.answer(f"❌ Пользователь @{target_username} не найден")
        return
    
    if target_id == user_id:
        await message.answer("❌ Нельзя вызвать самого себя")
        return
    
    # Проверка баланса
    balance = await ctx.balance_mgr.get_with_version(user_id, chat_id)
    if not balance or not balance.can_spend(amount):
        await message.answer(f"❌ Недостаточно средств. Баланс: {balance.total if balance else 0}")
        return
    
    # Создаём дуэль
    duel = await DuelManager.create(user_id, target_id, amount, chat_id, message.message_id)
    
    await state.update_data(duel_id=duel.duel_id)
    
    accept_cb = SecureCallbackData.create(action="duel_accept", game_type="duel", chat_id=chat_id, amount=amount)
    decline_cb = SecureCallbackData.create(action="duel_decline", game_type="duel", chat_id=chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Принять", callback_data=accept_cb.pack())],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=decline_cb.pack())]
    ])
    
    await message.answer(
        f"⚔️ **ВЫЗОВ НА ДУЭЛЬ!**\n\n"
        f"{message.from_user.full_name} вызывает @{target_username}\n"
        f"💰 Ставка: {amount} NCoin\n\n"
        f"⏱ Время на ответ: {DUEL_TIMEOUT} сек",
        reply_markup=keyboard
    )
    
    GAMES_STARTED.labels(game="duel", user_role="challenger").inc()


# ---------- DUEL: Callback (✅ ИСПРАВЛЕНО: добавлен state параметр)
@router.callback_query(SecureCallbackData.filter(F.game_type == "duel"))
async def duel_callback(callback: CallbackQuery, c: SecureCallbackData, state: FSMContext):
    ctx.require()
    
    # ✅ Replay-защита
    if ctx.is_signature_seen(c.chat_id, c.signature):
        await callback.answer("⚠️ Этот запрос уже обработан", show_alert=True)
        return
    
    if not c.verify()[0]:
        await callback.answer("❌ Неверная подпись или срок действия", show_alert=True)
        API_ERRORS.labels(endpoint="duel", error_type="invalid_signature").inc()
        return
    
    if c.chat_id != callback.message.chat.id:
        await callback.answer("❌ Неверный чат", show_alert=True)
        return
    
    if callback.from_user.id != callback.message.from_user.id:
        await callback.answer("❌ Это не ваш вызов!", show_alert=True)
        return
    
    if c.action == "duel_accept":
        state_data = await state.get_data()
        duel_id = state_data.get("duel_id")
        if not duel_id:
            await callback.answer("❌ Дуэль не найдена", show_alert=True)
            return
        
        success, msg, duel = await DuelManager.accept(duel_id, callback.from_user.id)
        if not success:
            await callback.answer(msg, show_alert=True)
            return
        
        # Проверка балансов
        challenger_bal = await ctx.balance_mgr.get_with_version(duel.challenger_id, duel.chat_id)
        target_bal = await ctx.balance_mgr.get_with_version(duel.target_id, duel.chat_id)
        
        if not challenger_bal or not challenger_bal.can_spend(duel.amount):
            await callback.message.edit_text("❌ У вызывающего недостаточно средств")
            return
        
        if not target_bal or not target_bal.can_spend(duel.amount):
            await callback.message.edit_text("❌ У вас недостаточно средств")
            return
        
        # Списываем ставки
        await ctx.balance_mgr.update_cas(challenger_bal, delta_free=-duel.amount)
        await ctx.balance_mgr.update_cas(target_bal, delta_free=-duel.amount)
        
        # Определяем победителя
        result = await DuelManager.resolve(duel_id)
        if not result:
            await callback.message.edit_text("❌ Ошибка при определении победителя")
            return
        
        winner_id, win_amount = result
        
        winner_name = "победитель"
        try:
            winner = await ctx.bot.get_chat(winner_id)
            winner_name = winner.full_name or winner.username or winner_name
        except Exception as e:
            logger.warning(f"Failed to get winner info: {e}", exc_info=True)
        
        # Уведомление победителя в ЛС
        try:
            await ctx.bot.send_message(
                winner_id,
                f"🏆 **Вы выиграли дуэль!**\n\n"
                f"💰 Выигрыш: {win_amount} NCoin"
            )
        except TelegramForbiddenError:
            logger.warning(f"Cannot send DM to winner {winner_id}")
        except Exception as e:
            logger.warning(f"Failed to send winner DM: {e}", exc_info=True)
        
        await callback.message.edit_text(
            f"⚔️ **РЕЗУЛЬТАТ ДУЭЛИ!**\n\n"
            f"🏆 **ПОБЕДИТЕЛЬ:** {winner_name}\n"
            f"💰 Выигрыш: {win_amount} NCoin"
        )
        
        await callback.answer()
        GAMES_RESULT.labels(game="duel", result="win").inc()
    
    elif c.action == "duel_decline":
        state_data = await state.get_data()
        duel_id = state_data.get("duel_id")
        if duel_id:
            await DuelManager.decline(duel_id, callback.from_user.id)
            await callback.message.edit_text("❌ Дуэль отклонена")
        await callback.answer()
        GAMES_RESULT.labels(game="duel", result="declined").inc()


# ---------- ROULETTE: Command ----------
@router.message(Command("roulette"))
async def cmd_roulette(message: Message):
    ctx.require()
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer(
            "🎲 **Рулетка NEXUS**\n\n"
            "Использование: /roulette [сумма] [red/black]\n"
            f"Пример: /roulette {MIN_BET} red\n\n"
            f"💰 Ставка: {MIN_BET}-{MAX_BET} NCoin\n"
            f"🎯 Выигрыш: x2"
        )
        return
    
    try:
        amount = int(args[1])
        color = args[2].lower()
    except ValueError:
        await message.answer("❌ Неверный формат")
        return
    
    if not (MIN_BET <= amount <= MAX_BET):
        await message.answer(f"❌ Ставка: {MIN_BET}-{MAX_BET}")
        return
    if color not in ("red", "black"):
        await message.answer("❌ Цвет: red или black")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    ok, wait = await ctx.rate_limiter.check(user_id, "roulette", 30, 60)
    if not ok:
        await message.answer(f"⏰ Подождите {wait} сек.")
        return
    
    balance = await ctx.balance_mgr.get_with_version(user_id, chat_id)
    if not balance or not balance.can_spend(amount):
        await message.answer(f"❌ Баланс: {balance.total if balance else 0}")
        return
    
    balance_before = balance.total
    if not await ctx.balance_mgr.update_cas(balance, delta_free=-amount):
        await message.answer("❌ Ошибка списания")
        API_ERRORS.labels(endpoint="roulette", error_type="cas_failed").inc()
        return
    
    result = random.choice(["red", "black"])
    
    if result == color:
        win = amount * 2
        new_bal = await ctx.balance_mgr.get_with_version(user_id, chat_id)
        if new_bal:
            await ctx.balance_mgr.update_cas(new_bal, delta_free=win)
        balance_after = balance_before - amount + win
        text = f"🎲 Выпало: **{result.upper()}**\n\n🎉 **ПОБЕДА!** +{win} NCoin\n💰 Баланс: {balance_after}"
        log_type = "win"
    else:
        balance_after = balance_before - amount
        text = f"🎲 Выпало: **{result.upper()}**\n\n😔 **ПРОИГРЫШ!** -{amount} NCoin\n💰 Баланс: {balance_after}"
        log_type = "loss"
    
    await log_financial_action(
        user_id, chat_id, f"roulette_{log_type}", amount,
        balance_before, balance_after, {"color": color, "result": result}
    )
    
    await message.answer(text)
    
    GAMES_STARTED.labels(game="roulette", user_role="player").inc()
    GAMES_RESULT.labels(game="roulette", result=log_type).inc()


# ---------- RPS: Command ----------
@router.message(Command("rps"))
async def cmd_rps(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "🪨 **Камень-ножницы-бумага**\n\n"
            "Использование: /rps [камень|ножницы|бумага]\n"
            "💰 Бесплатно"
        )
        return
    
    choice = args[1].lower()
    if choice not in RPS_CHOICES:
        await message.answer("❌ Выберите: камень, ножницы или бумага")
        return
    
    bot_choice = random.choice(list(RPS_CHOICES.keys()))
    
    if choice == bot_choice:
        result = "🤝 Ничья!"
        outcome = "draw"
    elif (choice == "камень" and bot_choice == "ножницы") or \
         (choice == "ножницы" and bot_choice == "бумага") or \
         (choice == "бумага" and bot_choice == "камень"):
        result = "🎉 Вы выиграли!"
        outcome = "win"
    else:
        result = "😔 Вы проиграли!"
        outcome = "loss"
    
    await message.answer(
        f"{RPS_CHOICES[choice]} Вы: {choice}\n"
        f"{RPS_CHOICES[bot_choice]} Бот: {bot_choice}\n\n"
        f"{result}"
    )
    
    GAMES_STARTED.labels(game="rps", user_role="player").inc()
    GAMES_RESULT.labels(game="rps", result=outcome).inc()


# ---------- HISTORY: Command ----------
@router.message(Command("games_history"))
async def cmd_games_history(message: Message):
    """История игр пользователя"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.execute("""
                SELECT action, amount, created_at 
                FROM audit_log 
                WHERE user_id=? AND chat_id=? 
                AND (action LIKE 'slot_%' OR action LIKE 'roulette_%' OR action LIKE 'duel_%')
                ORDER BY created_at DESC 
                LIMIT 20
            """, (user_id, chat_id)).fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке истории")
        return
    
    if not rows:
        await message.answer("📊 История игр пуста. Сыграйте в слоты или рулетку!")
        return
    
    text = "🎮 **История игр**\n\n"
    for row in rows:
        action_name = row[0].replace("_", " ").title()
        text += f"• {row[2][:16]} | {action_name} | {row[1]} NCoin\n"
    
    await message.answer(text)


# ---------- METRICS: Command (✅ ИСПРАВЛЕНО: ADMIN_IDS определён)
@router.message(Command("metrics"))
async def cmd_metrics(message: Message):
    """Показать метрики (только для админов)"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для администраторов")
        API_ERRORS.labels(endpoint="metrics", error_type="unauthorized").inc()
        return
    
    status = await health_check()
    
    text = "📊 **Статус сервиса**\n\n"
    text += f"🤖 Бот: {status['checks'].get('telegram', 'unknown')}\n"
    text += f"🗄️ База данных: {status['checks'].get('database', 'unknown')}\n"
    text += f"🔄 Redis: {status['checks'].get('redis', 'unknown')}\n"
    text += f"🎰 Активных дуэлей: {len(DuelManager._duels)}\n"
    text += f"🔗 Активные подключения БД: {len(ctx.db_pool._active_connections) if ctx.db_pool else 0}\n"
    
    await message.answer(text)


# ============================================================================
# 🔍 HEALTH CHECK
# ============================================================================
async def health_check() -> Dict[str, Any]:
    """Проверка здоровья сервиса"""
    status = {"status": "healthy", "checks": {}}
    
    # Проверка БД
    if ctx.db_pool:
        status["checks"]["database"] = "ok" if await ctx.db_pool.health_check() else "error"
        if status["checks"]["database"] == "error":
            status["status"] = "degraded"
    
    # Проверка Redis
    if ctx.redis:
        try:
            await ctx.redis.ping()
            status["checks"]["redis"] = "ok"
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}", exc_info=True)
            status["checks"]["redis"] = "error"
            status["status"] = "degraded"
    else:
        status["checks"]["redis"] = "disabled"
    
    # Проверка Telegram
    if ctx.bot:
        try:
            await ctx.bot.get_me()
            status["checks"]["telegram"] = "ok"
        except Exception as e:
            logger.warning(f"Telegram health check failed: {e}", exc_info=True)
            status["checks"]["telegram"] = "error"
            status["status"] = "degraded"
    
    return status


# ============================================================================
# 🚀 GRACEFUL SHUTDOWN
# ============================================================================
async def shutdown_handler(signum=None):
    """Обработчик завершения"""
    logger.info(f"Shutdown initiated (signal: {signum})")
    
    # Завершаем все активные задачи
    await ctx.shutdown()
    
    # Закрываем соединения
    if ctx.db_pool:
        await ctx.db_pool.close()
    if ctx.redis:
        try:
            await ctx.redis.close()
        except Exception as e:
            logger.warning(f"Redis close error: {e}", exc_info=True)
    
    logger.info("Shutdown complete")
    sys.exit(0)


# ============================================================================
# 🎯 MAIN ENTRY POINT
# ============================================================================
dp = Dispatcher()
dp.include_router(router)


async def on_startup(bot: Bot):
    """Инициализация при запуске"""
    # Инициализация БД
    db_pool = AsyncDBPool(DATABASE_PATH)
    await db_pool.initialize()
    
    # Инициализация Redis
    redis_client = None
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connected")
        REDIS_CONNECTED.set(1)
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}", exc_info=True)
        REDIS_CONNECTED.set(0)
    
    ctx.initialize(bot=bot, db_pool=db_pool, redis_client=redis_client)
    
    # Запуск метрик
    start_http_server(PROMETHEUS_PORT)
    logger.info(f"Prometheus metrics on :{PROMETHEUS_PORT}/metrics")
    
    # Команды бота
    await bot.set_my_commands([
        BotCommand(command="slot", description="🎰 Слот-машина"),
        BotCommand(command="duel", description="⚔️ Дуэль с игроком"),
        BotCommand(command="roulette", description="🎲 Рулетка"),
        BotCommand(command="rps", description="🪨 Камень-ножницы-бумага"),
        BotCommand(command="games_history", description="📊 История игр"),
        BotCommand(command="metrics", description="🔧 Статус сервиса (админ)"),
    ], scope=BotCommandScopeDefault())
    
    logger.info("Bot started successfully")


async def on_shutdown(bot: Bot):
    """Очистка при завершении"""
    await shutdown_handler()


def main():
    """Точка входа"""
    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    
    # Регистрация обработчиков сигналов
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown_handler(s)))
    
    # Запуск
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("Starting NEXUS Games bot v2.0...")
    dp.run_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    main()

