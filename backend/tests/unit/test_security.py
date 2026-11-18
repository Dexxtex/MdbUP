"""Password hashing, token digests and the rate limiter."""

from __future__ import annotations

import pytest

from app.core.security import (
    PasswordPolicyError,
    RateLimiter,
    constant_time_equals,
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    validate_password_strength,
    verify_password,
)


def test_password_hash_roundtrip_and_rehash_detection() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "correct horse battery staple") is True
    assert verify_password(password_hash, "wrong password") is False
    assert needs_rehash(password_hash) is False


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("not-a-hash", "whatever") is False


def test_password_policy_enforces_length_and_email() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_strength("short", "admin@example.com")
    with pytest.raises(PasswordPolicyError):
        validate_password_strength("admin@example.com", "admin@example.com")
    validate_password_strength("a-long-enough-password", "admin@example.com")


def test_session_tokens_are_opaque_and_hashed() -> None:
    token = generate_token()
    digest = hash_token(token)

    assert len(token) >= 32
    assert isinstance(digest, bytes)
    assert len(digest) == 32
    assert digest != token.encode()
    assert constant_time_equals(digest, hash_token(token)) is True
    assert constant_time_equals(digest, hash_token(generate_token())) is False


def test_rate_limiter_blocks_after_limit_and_resets() -> None:
    limiter = RateLimiter("")

    decisions = [limiter.check("login:1.2.3.4", limit=2, window_seconds=60) for _ in range(3)]

    assert [decision.allowed for decision in decisions] == [True, True, False]
    assert decisions[-1].retry_after_seconds > 0
    limiter.reset("login:1.2.3.4")
    assert limiter.check("login:1.2.3.4", limit=2, window_seconds=60).allowed is True


def test_rate_limiter_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        RateLimiter("").check("key", limit=0, window_seconds=60)
