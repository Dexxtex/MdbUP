"""AES-256-GCM encryption for integration credentials.

The plaintext secret never leaves this module: the database stores ciphertext,
nonce, ``key_version`` and a masked hint only.

The AAD binds a ciphertext to its context (``scope|source_id|key|version``), so a
row copied to another scope or key name fails to decrypt.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.core.config import Settings

KEY_SIZE = 32
NONCE_SIZE = 12
ALGORITHM = "AES-256-GCM"
MASK_PREFIX = "\u2022\u2022\u2022\u2022"
MASKED_VISIBLE_CHARS = 4


class EncryptionKeyMissingError(RuntimeError):
    """Raised when ``APP_ENCRYPTION_KEY`` is not configured."""


class DecryptionError(RuntimeError):
    """Raised when a ciphertext cannot be decrypted with the given key/AAD."""


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: bytes
    nonce: bytes
    key_version: int


def load_key(material: str) -> bytes:
    """Decode a base64 encoded 32 byte key."""
    if not material:
        raise EncryptionKeyMissingError(
            "APP_ENCRYPTION_KEY non configurata: le credenziali non possono essere cifrate."
        )
    try:
        key = base64.b64decode(material, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("APP_ENCRYPTION_KEY non è base64 valido.") from exc
    if len(key) != KEY_SIZE:
        raise ValueError(f"APP_ENCRYPTION_KEY deve essere di {KEY_SIZE} byte (trovati {len(key)}).")
    return key


def mask_secret(value: str) -> str:
    """Return ``••••`` plus the last four characters of the secret.

    Secrets of four characters or fewer are fully masked: showing their only
    characters would disclose the whole secret.
    """
    if len(value) <= MASKED_VISIBLE_CHARS:
        return MASK_PREFIX
    return f"{MASK_PREFIX}{value[-MASKED_VISIBLE_CHARS:]}"


def build_aad(
    *,
    scope: str,
    source_id: uuid.UUID | str | None,
    key: str,
    key_version: int,
) -> bytes:
    """Build the additional authenticated data for a credential row."""
    source_part = "" if source_id is None else str(source_id)
    return f"{scope}|{source_part}|{key}|{key_version}".encode()


class SecretCipher:
    """Encrypt/decrypt secrets with AES-256-GCM, keyed by ``key_version``."""

    def __init__(self, keys: Mapping[int, bytes], active_version: int) -> None:
        if active_version not in keys:
            raise ValueError(f"key_version {active_version} non presente nel keyring.")
        for version, key in keys.items():
            if len(key) != KEY_SIZE:
                raise ValueError(f"Chiave {version} non valida: attesi {KEY_SIZE} byte.")
        self._keys = dict(keys)
        self._active_version = active_version

    @property
    def active_version(self) -> int:
        return self._active_version

    def has_version(self, version: int) -> bool:
        return version in self._keys

    def key_for(self, version: int) -> bytes:
        try:
            return self._keys[version]
        except KeyError as exc:
            raise ValueError(f"key_version {version} non disponibile nel keyring.") from exc

    @classmethod
    def from_settings(cls, settings: Settings) -> SecretCipher:
        """Build a cipher from the active key and the optional keyring."""
        return cls(load_keyring(settings), settings.app_encryption_key_version)

    def encrypt(self, plaintext: str, *, aad: bytes) -> EncryptedSecret:
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = AESGCM(self._keys[self._active_version]).encrypt(
            nonce, plaintext.encode("utf-8"), aad
        )
        return EncryptedSecret(ciphertext=ciphertext, nonce=nonce, key_version=self._active_version)

    def decrypt(self, ciphertext: bytes, nonce: bytes, key_version: int, *, aad: bytes) -> str:
        key = self._keys.get(key_version)
        if key is None:
            raise DecryptionError(f"key_version {key_version} non disponibile nel keyring.")
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, aad).decode("utf-8")
        except InvalidTag as exc:
            raise DecryptionError(
                "Decifratura fallita: chiave, versione o contesto (AAD) non corrispondono."
            ) from exc


def load_keyring(settings: Settings) -> dict[int, bytes]:
    """Return every configured key version, including the active key.

    ``APP_ENCRYPTION_KEYS`` is a JSON object ``{"1": "<base64>", ...}``. The
    active ``APP_ENCRYPTION_KEY``/``APP_ENCRYPTION_KEY_VERSION`` pair is always
    included; a conflicting duplicate version is rejected instead of silently
    choosing one key.
    """
    keys: dict[int, bytes] = {}
    raw = (settings.app_encryption_keys or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise ValueError("APP_ENCRYPTION_KEYS non è JSON valido.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("APP_ENCRYPTION_KEYS deve essere un oggetto JSON.")
        for version, material in parsed.items():
            try:
                parsed_version = int(version)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Versione chiave non valida: {version!r}.") from exc
            if not isinstance(material, str):
                raise ValueError(f"La chiave {parsed_version} non è una stringa base64.")
            keys[parsed_version] = load_key(material)
    active = load_key(settings.app_encryption_key)
    existing = keys.get(settings.app_encryption_key_version)
    if existing is not None and existing != active:
        raise ValueError(
            "APP_ENCRYPTION_KEY non coincide con la chiave attiva in APP_ENCRYPTION_KEYS."
        )
    keys[settings.app_encryption_key_version] = active
    return keys


def encryption_key_available(settings: Settings) -> bool:
    """True when a usable ``APP_ENCRYPTION_KEY`` is configured."""
    try:
        load_key(settings.app_encryption_key)
    except (EncryptionKeyMissingError, ValueError):
        return False
    return True
