"""AES-256-GCM credential encryption."""

from __future__ import annotations

import base64

import pytest

from app.core.crypto import (
    DecryptionError,
    MissingKeyMaterialError,
    SecretCipher,
    build_aad,
    encryption_key_available,
    load_key,
    mask_secret,
)

KEY_A = b"a" * 32
KEY_B = b"b" * 32


def _cipher(version: int = 1, key: bytes = KEY_A) -> SecretCipher:
    return SecretCipher({version: key}, version)


def test_encrypt_decrypt_roundtrip() -> None:
    cipher = _cipher()
    aad = build_aad(scope="SOURCE", source_id=None, key="api_key", key_version=1)

    encrypted = cipher.encrypt("super-secret-value", aad=aad)

    assert encrypted.ciphertext != b"super-secret-value"
    assert len(encrypted.nonce) == 12
    assert encrypted.key_version == 1
    assert cipher.decrypt(encrypted.ciphertext, encrypted.nonce, 1, aad=aad) == (
        "super-secret-value"
    )


def test_decrypt_fails_with_wrong_aad() -> None:
    cipher = _cipher()
    aad = build_aad(
        scope="SOURCE",
        source_id="11111111-1111-1111-1111-111111111111",
        key="api_key",
        key_version=1,
    )
    encrypted = cipher.encrypt("secret", aad=aad)
    other_aad = build_aad(scope="TARGET", source_id=None, key="api_key", key_version=1)

    with pytest.raises(DecryptionError):
        cipher.decrypt(encrypted.ciphertext, encrypted.nonce, 1, aad=other_aad)


def test_decrypt_fails_with_unknown_key_version() -> None:
    cipher = _cipher()
    aad = build_aad(scope="TARGET", source_id=None, key="api_key", key_version=1)
    encrypted = cipher.encrypt("secret", aad=aad)

    with pytest.raises(DecryptionError):
        cipher.decrypt(encrypted.ciphertext, encrypted.nonce, 2, aad=aad)


def test_keyring_supports_rotation() -> None:
    aad = build_aad(scope="TARGET", source_id=None, key="api_key", key_version=1)
    old = SecretCipher({1: KEY_A}, 1).encrypt("secret", aad=aad)
    rotated = SecretCipher({1: KEY_A, 2: KEY_B}, 2)

    assert rotated.decrypt(old.ciphertext, old.nonce, 1, aad=aad) == "secret"
    new = rotated.encrypt("secret", aad=aad)
    assert new.key_version == 2


def test_mask_secret_keeps_last_four_characters() -> None:
    assert mask_secret("abcdef123456") == "\u2022\u2022\u2022\u20223456"
    assert mask_secret("abc") == "\u2022\u2022\u2022\u2022"
    assert mask_secret("") == "\u2022\u2022\u2022\u2022"


def test_load_key_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        load_key(base64.b64encode(b"short").decode())


def test_load_key_requires_a_value() -> None:
    with pytest.raises(MissingKeyMaterialError):
        load_key("")


def test_encryption_key_available_reflects_configuration() -> None:
    class _Settings:
        app_encryption_key = ""

    class _Configured:
        app_encryption_key = base64.b64encode(KEY_A).decode()

    assert encryption_key_available(_Settings()) is False  # type: ignore[arg-type]
    assert encryption_key_available(_Configured()) is True  # type: ignore[arg-type]
