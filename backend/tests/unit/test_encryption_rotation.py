"""Encryption key rotation re-encrypts stored secrets without plaintext re-entry."""

from __future__ import annotations

import base64
import json

from app.cli import rotate_encryption_key
from app.core.config import Settings
from app.db.session import get_session_factory
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind
from tests.conftest import ENCRYPTION_KEY


def test_rotate_encryption_key_reencrypts_tmdb_credential(db, seeded, app_settings) -> None:
    new_key = base64.b64encode(b"abcdefghijklmnopqrstuvwxyz012345").decode()
    keyring = json.dumps({"1": ENCRYPTION_KEY, "2": new_key})
    session = get_session_factory()()
    try:
        credentials_service.set_secret(
            session, app_settings, CredentialKind.TMDB, "tmdb-secret-value"
        )
    finally:
        session.close()

    rotating = Settings(
        database_url=app_settings.database_url,
        app_encryption_key=ENCRYPTION_KEY,
        app_encryption_key_version=1,
        app_encryption_keys=keyring,
        redis_url="",
    )
    assert rotate_encryption_key(rotating, new_version=2) == 0

    new_settings = Settings(
        database_url=app_settings.database_url,
        app_encryption_key=new_key,
        app_encryption_key_version=2,
        app_encryption_keys=keyring,
        redis_url="",
    )
    session = get_session_factory()()
    try:
        assert (
            credentials_service.get_secret(session, new_settings, CredentialKind.TMDB)
            == "tmdb-secret-value"
        )
    finally:
        session.close()
