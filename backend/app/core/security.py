"""Password hashing, opaque tokens, CSRF helpers and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass

import redis
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.logging import get_logger

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 32

logger = get_logger(__name__)

# Argon2id parameters from docs/phase1/06-security.md.
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


class PasswordPolicyError(ValueError):
    """Raised when a password does not satisfy the policy."""


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against an Argon2id hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash uses outdated Argon2 parameters."""
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password_strength(password: str, email: str) -> None:
    """Enforce the password policy (min 12, max 128, not equal to the email)."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(
            f"La password deve contenere almeno {PASSWORD_MIN_LENGTH} caratteri."
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(f"La password non può superare {PASSWORD_MAX_LENGTH} caratteri.")
    if password.strip().lower() == email.strip().lower():
        raise PasswordPolicyError("La password non può coincidere con l'email.")


def generate_token(nbytes: int = SESSION_TOKEN_BYTES) -> str:
    """Generate an opaque URL-safe token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> bytes:
    """Return the SHA-256 digest stored in the database for a token."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def constant_time_equals(left: str | bytes, right: str | bytes) -> bool:
    """Compare two values in constant time."""
    left_bytes = left.encode("utf-8") if isinstance(left, str) else left
    right_bytes = right.encode("utf-8") if isinstance(right, str) else right
    return hmac.compare_digest(left_bytes, right_bytes)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    """Fixed-window counter backed by Redis, with an in-memory fallback.

    The fallback keeps the same limit but counts per process: with a single API
    process (the Compose topology) it is equivalent, and it still fails closed
    while Redis is unreachable instead of allowing unlimited attempts.
    """

    def __init__(
        self,
        redis_url: str = "",
        *,
        namespace: str = "mdbup:ratelimit",
        client: redis.Redis | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._namespace = namespace
        self._client: redis.Redis | None = client
        self._provided_client = client is not None
        self._redis_unavailable = False
        self._memory: dict[str, list[float]] = {}
        self._memory_lockout: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        lockout_seconds: int = 0,
    ) -> RateLimitDecision:
        """Register one attempt for ``key`` and report whether it is allowed.

        ``lockout_seconds`` extends the denial beyond the current fixed window
        after the limit is exceeded. The lockout is stored in Redis too, so a
        restart or a second API process cannot bypass it.
        """
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit e window_seconds devono essere positivi.")
        if lockout_seconds < 0:
            raise ValueError("lockout_seconds non può essere negativo.")
        client = self._redis_client()
        if client is not None:
            try:
                return self._check_redis(
                    client,
                    key,
                    limit=limit,
                    window_seconds=window_seconds,
                    lockout_seconds=lockout_seconds,
                )
            except redis.RedisError as exc:
                self._redis_unavailable = True
                logger.warning("rate_limit_redis_unavailable", error=str(exc))
        return self._check_memory(key, limit, window_seconds, lockout_seconds)

    def reset(self, key: str) -> None:
        """Clear the counter and any lockout for ``key``."""
        with self._lock:
            self._memory.pop(key, None)
            self._memory_lockout.pop(key, None)
        client = self._redis_client()
        if client is not None:
            try:
                client.delete(f"{self._namespace}:{key}", f"{self._namespace}:{key}:lockout")
            except redis.RedisError:
                self._redis_unavailable = True

    def _redis_client(self) -> redis.Redis | None:
        if self._provided_client:
            return None if self._redis_unavailable else self._client
        if self._redis_unavailable or not self._redis_url:
            return None
        if self._client is None:
            self._client = redis.Redis.from_url(
                self._redis_url,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
                decode_responses=True,
            )
        return self._client

    def _check_redis(
        self,
        client: redis.Redis,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> RateLimitDecision:
        full_key = f"{self._namespace}:{key}"
        lockout_key = f"{full_key}:lockout"
        lockout_ttl = int(client.ttl(lockout_key) or -1)
        if lockout_ttl > 0:
            return RateLimitDecision(
                allowed=False,
                remaining=0,
                retry_after_seconds=lockout_ttl,
            )
        pipeline = client.pipeline()
        pipeline.incr(full_key)
        pipeline.ttl(full_key)
        count, ttl = pipeline.execute()
        count = int(count)
        ttl = int(ttl) if ttl is not None else -1
        if ttl < 0:
            client.expire(full_key, window_seconds)
            ttl = window_seconds
        allowed = count <= limit
        retry_after = 0
        if not allowed:
            retry_after = max(1, ttl)
            if lockout_seconds > 0:
                client.set(lockout_key, "1", ex=lockout_seconds)
                retry_after = max(retry_after, lockout_seconds)
        return RateLimitDecision(
            allowed=allowed,
            remaining=max(0, limit - count),
            retry_after_seconds=retry_after,
        )

    def _check_memory(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> RateLimitDecision:
        now = time.monotonic()
        with self._lock:
            locked_until = self._memory_lockout.get(key, 0.0)
            if locked_until > now:
                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=max(1, int(locked_until - now) + 1),
                )
            cutoff = now - window_seconds
            hits = [hit for hit in self._memory.get(key, []) if hit > cutoff]
            hits.append(now)
            self._memory[key] = hits
            allowed = len(hits) <= limit
            retry_after = 0
            if not allowed:
                retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
                if lockout_seconds > 0:
                    self._memory_lockout[key] = now + lockout_seconds
                    retry_after = max(retry_after, lockout_seconds)
        return RateLimitDecision(
            allowed=allowed,
            remaining=max(0, limit - len(hits)),
            retry_after_seconds=retry_after,
        )


def build_rate_limiter(redis_url: str) -> RateLimiter:
    """Create a rate limiter for the configured Redis URL."""
    return RateLimiter(redis_url)
