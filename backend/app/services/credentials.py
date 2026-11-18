"""Credential management: encrypted storage, masked listing, connection checks.

No endpoint ever returns a plaintext secret: only ``masked_hint``, ``key_version``
and timestamps leave this module.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import (
    ALGORITHM,
    DecryptionError,
    SecretCipher,
    build_aad,
    mask_secret,
)
from app.core.crypto import (
    EncryptionKeyMissingError as CryptoKeyMissingError,
)
from app.core.logging import get_logger
from app.db.models import Credential
from app.domain.enums import AuditActorType, CredentialScope
from app.domain.errors import (
    CredentialMissingError,
    EncryptionKeyMissingError,
    NotFoundError,
    SourceUnavailableError,
    ValidationError,
)
from app.integrations.tmdb.client import tmdb_auth_mode
from app.repositories import audit
from app.repositories import credentials as credentials_repo

logger = get_logger(__name__)

# Verification probes use fixed allowlisted hosts; no user-supplied URL is fetched.
_VERIFY_ENDPOINTS: dict[str, tuple[str, str]] = {
    "TMDB": ("https://api.themoviedb.org/3/configuration", "tmdb"),
    "MDBLIST": ("https://api.mdblist.com/user", "query"),
}


class CredentialKind(StrEnum):
    TMDB = "TMDB"
    MDBLIST = "MDBLIST"
    JUSTWATCH = "JUSTWATCH"


@dataclass(frozen=True)
class CredentialSpec:
    kind: CredentialKind
    scope: CredentialScope
    source_key: str | None
    key: str
    label: str
    available: bool = True
    unavailable_reason: str | None = None


CREDENTIAL_SPECS: dict[CredentialKind, CredentialSpec] = {
    CredentialKind.TMDB: CredentialSpec(
        kind=CredentialKind.TMDB,
        scope=CredentialScope.SOURCE,
        source_key="tmdb",
        key="api_key",
        label="TMDb API key",
    ),
    CredentialKind.MDBLIST: CredentialSpec(
        kind=CredentialKind.MDBLIST,
        scope=CredentialScope.TARGET,
        source_key=None,
        key="api_key",
        label="MDBList API key",
    ),
    CredentialKind.JUSTWATCH: CredentialSpec(
        kind=CredentialKind.JUSTWATCH,
        scope=CredentialScope.SOURCE,
        source_key="justwatch_partner",
        key="partner_token",
        label="JustWatch partner token",
        available=False,
        unavailable_reason="Contratto JustWatch non disponibile in questa fase.",
    ),
}


@dataclass(frozen=True)
class CredentialStatus:
    kind: CredentialKind
    configured: bool
    masked_hint: str | None
    key_version: int | None
    status: str
    updated_at: datetime | None
    last_verified_at: datetime | None


@dataclass(frozen=True)
class VerificationResult:
    kind: CredentialKind
    ok: bool
    status_code: int | None
    latency_ms: int | None
    message: str


def parse_kind(raw: str) -> CredentialKind:
    """Parse a path parameter into a credential kind (case-insensitive)."""
    try:
        return CredentialKind(raw.strip().upper())
    except ValueError as exc:
        allowed = ", ".join(kind.value for kind in CredentialKind)
        raise ValidationError(
            f"Tipo di credenziale non valido: usare uno tra {allowed}.",
            code="VALIDATION_UNKNOWN_CREDENTIAL_KIND",
            details={"kind": raw},
        ) from exc


def _spec(kind: CredentialKind) -> CredentialSpec:
    spec = CREDENTIAL_SPECS[kind]
    if not spec.available:
        raise SourceUnavailableError(spec.unavailable_reason or "Fonte non disponibile.")
    return spec


def _source_id(db: Session, spec: CredentialSpec) -> uuid.UUID:
    """Resolve the source row a SOURCE-scoped credential belongs to."""
    if spec.source_key is None:
        raise ValidationError("La credenziale non è associata a una fonte.")
    source_id = credentials_repo.get_source_id_by_key(db, spec.source_key)
    if source_id is None:
        raise SourceUnavailableError(
            f"Fonte '{spec.source_key}' non registrata: eseguire il seed delle fonti.",
            details={"source_key": spec.source_key},
        )
    return source_id


def _cipher(settings: Settings) -> SecretCipher:
    try:
        return SecretCipher.from_settings(settings)
    except CryptoKeyMissingError as exc:
        raise EncryptionKeyMissingError() from exc
    except ValueError as exc:
        raise EncryptionKeyMissingError(str(exc)) from exc


def list_status(db: Session) -> list[CredentialStatus]:
    """Return every known credential kind with masked metadata only."""
    rows = credentials_repo.list_credentials(db)
    by_identity = {(row.scope, row.key): row for row in rows}
    statuses: list[CredentialStatus] = []
    for spec in CREDENTIAL_SPECS.values():
        if not spec.available:
            statuses.append(
                CredentialStatus(
                    kind=spec.kind,
                    configured=False,
                    masked_hint=None,
                    key_version=None,
                    status="UNAVAILABLE",
                    updated_at=None,
                    last_verified_at=None,
                )
            )
            continue
        row = by_identity.get((spec.scope.value, spec.key))
        statuses.append(_status_of(spec, row))
    return statuses


def _status_of(spec: CredentialSpec, row: Credential | None) -> CredentialStatus:
    if row is None:
        return CredentialStatus(
            kind=spec.kind,
            configured=False,
            masked_hint=None,
            key_version=None,
            status="MISSING",
            updated_at=None,
            last_verified_at=None,
        )
    return CredentialStatus(
        kind=spec.kind,
        configured=True,
        masked_hint=row.masked_hint,
        key_version=row.key_version,
        status="CONFIGURED",
        updated_at=row.updated_at,
        last_verified_at=row.last_verified_at,
    )


def set_secret(
    db: Session,
    settings: Settings,
    kind: CredentialKind,
    value: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Encrypt and store a secret for ``kind``."""
    spec = _spec(kind)
    cipher = _cipher(settings)
    source_id = _source_id(db, spec) if spec.scope is CredentialScope.SOURCE else None
    secret = value.strip()
    if not secret:
        raise ValidationError("Il segreto non può essere vuoto.")
    aad = build_aad(
        scope=spec.scope.value,
        source_id=source_id,
        key=spec.key,
        key_version=cipher.active_version,
    )
    encrypted = cipher.encrypt(secret, aad=aad)
    credentials_repo.upsert_credential(
        db,
        scope=spec.scope.value,
        source_id=source_id,
        key=spec.key,
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        algorithm=ALGORITHM,
        key_version=encrypted.key_version,
        masked_hint=mask_secret(secret),
    )
    audit.record(
        db,
        action="credential_updated",
        entity_type="credential",
        entity_id=f"{spec.scope.value}:{spec.key}",
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"kind": spec.kind.value, "masked_hint": mask_secret(secret)},
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()


def delete_secret(
    db: Session,
    kind: CredentialKind,
    *,
    actor_user_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Remove a stored credential."""
    spec = _spec(kind)
    source_id = _source_id(db, spec) if spec.scope is CredentialScope.SOURCE else None
    row = credentials_repo.get_credential(
        db, scope=spec.scope.value, source_id=source_id, key=spec.key
    )
    if row is None:
        raise NotFoundError(f"Nessuna credenziale configurata per {spec.kind.value}.")
    credentials_repo.delete_credential(db, row)
    audit.record(
        db,
        action="credential_deleted",
        entity_type="credential",
        entity_id=f"{spec.scope.value}:{spec.key}",
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"kind": spec.kind.value},
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()


def get_secret(db: Session, settings: Settings, kind: CredentialKind) -> str:
    """Decrypt the secret for ``kind``; used by connectors and verification."""
    spec = _spec(kind)
    cipher = _cipher(settings)
    source_id = _source_id(db, spec) if spec.scope is CredentialScope.SOURCE else None
    row = credentials_repo.get_credential(
        db, scope=spec.scope.value, source_id=source_id, key=spec.key
    )
    if row is None:
        raise CredentialMissingError(f"Credenziale {spec.kind.value} non configurata.")
    aad = build_aad(
        scope=row.scope,
        source_id=row.source_id,
        key=row.key,
        key_version=row.key_version,
    )
    try:
        return cipher.decrypt(row.ciphertext, row.nonce, row.key_version, aad=aad)
    except DecryptionError as exc:
        logger.error("credential_decryption_failed", kind=spec.kind.value)
        raise CredentialMissingError(
            "Credenziale illeggibile: chiave di cifratura o versione non valida.",
        ) from exc


def verify(
    db: Session,
    settings: Settings,
    kind: CredentialKind,
    *,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> VerificationResult:
    """Probe the remote API with the stored secret (no plaintext in the result)."""
    spec = _spec(kind)
    endpoint = _VERIFY_ENDPOINTS.get(spec.kind.value)
    if endpoint is None:  # pragma: no cover - guarded by _spec availability
        raise SourceUnavailableError(spec.unavailable_reason or "Fonte non disponibile.")
    secret = get_secret(db, settings, kind)
    url, auth_style = endpoint
    started = time.monotonic()
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=False) as client:
            if auth_style == "tmdb":
                if tmdb_auth_mode(secret) == "bearer":
                    response = client.get(url, headers={"Authorization": f"Bearer {secret}"})
                else:
                    response = client.get(url, params={"api_key": secret})
            else:
                response = client.get(url, params={"apikey": secret})
    except httpx.HTTPError as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.warning("credential_verify_failed", kind=spec.kind.value, error=type(exc).__name__)
        return VerificationResult(
            kind=spec.kind,
            ok=False,
            status_code=None,
            latency_ms=latency_ms,
            message="Connessione al servizio non riuscita.",
        )
    latency_ms = int((time.monotonic() - started) * 1000)
    ok = response.status_code < 400
    if ok:
        source_id = _source_id(db, spec) if spec.scope is CredentialScope.SOURCE else None
        row = credentials_repo.get_credential(
            db, scope=spec.scope.value, source_id=source_id, key=spec.key
        )
        if row is not None:
            credentials_repo.mark_verified(db, row)
        audit.record(
            db,
            action="credential_verified",
            entity_type="credential",
            entity_id=f"{spec.scope.value}:{spec.key}",
            actor_user_id=actor_user_id,
            actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
            after={"kind": spec.kind.value, "status_code": response.status_code},
            request_id=request_id,
        )
        db.commit()
    if not ok and response.status_code in (401, 403):
        from app.services import notifications as notifications_service

        notifications_service.notify_auth_error(
            db,
            settings,
            service=spec.kind.value,
            status_code=response.status_code,
            detail="Verifica manuale della credenziale dalle Impostazioni.",
        )
    message = (
        "Credenziale valida."
        if ok
        else f"Il servizio ha risposto con stato {response.status_code}."
    )
    return VerificationResult(
        kind=spec.kind,
        ok=ok,
        status_code=response.status_code,
        latency_ms=latency_ms,
        message=message,
    )
