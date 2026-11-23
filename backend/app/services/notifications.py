"""Notification channels and event delivery.

Only relevant events are sent: a run waiting for approval, a failed/uncertain
run, an authentication rejection and the optional daily summary. Transport
secrets are encrypted with the same keyring as integration credentials and are
never returned by the API or written to logs.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
import redis
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import (
    ALGORITHM,
    DecryptionError,
    SecretCipher,
    build_aad,
    mask_secret,
)
from app.core.crypto import MissingKeyMaterialError as CryptoKeyMissingError
from app.core.logging import get_logger
from app.core.time import ensure_utc, utcnow
from app.db.models import NotificationChannel, SyncRun
from app.domain.enums import (
    NOTIFICATION_EVENTS,
    AuditActorType,
    NotificationChannelKind,
    NotificationEventType,
    SyncRunStatus,
)
from app.domain.errors import ConflictError, NotFoundError, ValidationError
from app.repositories import audit
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import settings as settings_repo
from app.repositories import targets as targets_repo

logger = get_logger(__name__)

TELEGRAM_TOKEN = re.compile(r"^\d+:[A-Za-z0-9_-]+$")
MAX_MESSAGE_LENGTH = 3500
# Three retries after the first failure, with exponential backoff. The fourth
# consecutive failure clears ``next_retry_at`` and stops retrying.
RETRY_BACKOFF_SECONDS = (60, 300, 900)
MAX_RETRY_ATTEMPTS = len(RETRY_BACKOFF_SECONDS)
_DEDUPE_MEMORY: dict[str, float] = {}
_DEDUPE_GUARD = threading.Lock()


@dataclass(frozen=True)
class DeliveryResult:
    channel_id: uuid.UUID
    channel_name: str
    ok: bool
    status_code: int | None
    error: str | None = None


@dataclass(frozen=True)
class DispatchSummary:
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    results: list[DeliveryResult] = field(default_factory=list)


def retry_delay_seconds(retry_count: int) -> int | None:
    """Backoff before the next attempt; ``None`` when the budget is exhausted."""
    if retry_count <= 0 or retry_count > MAX_RETRY_ATTEMPTS:
        return None
    return RETRY_BACKOFF_SECONDS[retry_count - 1]


def _cipher(settings: Settings) -> SecretCipher:
    try:
        return SecretCipher.from_settings(settings)
    except CryptoKeyMissingError as exc:
        raise ValidationError(
            "APP_ENCRYPTION_KEY non configurata: impossibile cifrare i segreti delle notifiche.",
            code="ENCRYPTION_KEY_MISSING",
        ) from exc
    except ValueError as exc:
        raise ValidationError(str(exc), code="ENCRYPTION_KEY_INVALID") from exc


def _aad(channel: NotificationChannel, key_version: int) -> bytes:
    return build_aad(
        scope="NOTIFICATION",
        source_id=channel.id,
        key=channel.kind,
        key_version=key_version,
    )


def _encrypt_secret(channel: NotificationChannel, secret: str, settings: Settings) -> None:
    cipher = _cipher(settings)
    encrypted = cipher.encrypt(secret, aad=_aad(channel, cipher.active_version))
    channel.secret_ciphertext = encrypted.ciphertext
    channel.secret_nonce = encrypted.nonce
    channel.secret_algorithm = ALGORITHM
    channel.secret_key_version = encrypted.key_version
    channel.secret_masked_hint = mask_secret(secret)


def _decrypt_secret(channel: NotificationChannel, settings: Settings) -> str:
    if (
        channel.secret_ciphertext is None
        or channel.secret_nonce is None
        or channel.secret_key_version is None
    ):
        raise ValidationError(
            "Segreto del canale di notifica non configurato.",
            code="NOTIFICATION_SECRET_MISSING",
        )
    cipher = _cipher(settings)
    try:
        return cipher.decrypt(
            channel.secret_ciphertext,
            channel.secret_nonce,
            channel.secret_key_version,
            aad=_aad(channel, channel.secret_key_version),
        )
    except DecryptionError as exc:
        logger.error("notification_secret_decryption_failed", channel_id=str(channel.id))
        raise ValidationError(
            "Segreto del canale illeggibile: chiave di cifratura non valida.",
            code="NOTIFICATION_SECRET_INVALID",
        ) from exc


def normalize_events(events: list[str] | None) -> list[str]:
    """Validate subscriptions; empty means all relevant events."""
    if not events:
        return sorted(NOTIFICATION_EVENTS)
    normalized: list[str] = []
    for raw in events:
        value = str(raw).strip().upper()
        if value == "ALL":
            return sorted(NOTIFICATION_EVENTS)
        if value not in NOTIFICATION_EVENTS:
            raise ValidationError(
                f"Evento di notifica sconosciuto: '{raw}'.",
                code="NOTIFICATION_EVENT_INVALID",
                details={"allowed": sorted(NOTIFICATION_EVENTS)},
            )
        if value not in normalized:
            normalized.append(value)
    return normalized


def _validate_config(kind: str, config: dict[str, Any] | None) -> dict[str, Any]:
    raw = config or {}
    if not isinstance(raw, dict):
        raise ValidationError(
            "La configurazione del canale deve essere un oggetto.",
            code="NOTIFICATION_CONFIG_INVALID",
        )
    if kind == NotificationChannelKind.TELEGRAM.value:
        chat_id = raw.get("chat_id")
        if not isinstance(chat_id, (str, int)) or not str(chat_id).strip():
            raise ValidationError(
                "Telegram richiede config.chat_id.",
                code="NOTIFICATION_CONFIG_INVALID",
            )
        return {"chat_id": str(chat_id).strip()}
    if raw:
        raise ValidationError(
            "Webhook e Discord non accettano configurazione aggiuntiva.",
            code="NOTIFICATION_CONFIG_INVALID",
        )
    return {}


def _validate_secret(kind: str, secret: str) -> str:
    value = secret.strip()
    if not value:
        raise ValidationError(
            "Il segreto del canale non può essere vuoto.",
            code="NOTIFICATION_SECRET_INVALID",
        )
    if kind in (
        NotificationChannelKind.WEBHOOK.value,
        NotificationChannelKind.DISCORD.value,
    ):
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise ValidationError(
                "URL del webhook non valido.", code="NOTIFICATION_SECRET_INVALID"
            ) from exc
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValidationError(
                "Il webhook deve essere un URL HTTP(S) senza credenziali incorporate.",
                code="NOTIFICATION_SECRET_INVALID",
            )
    elif kind == NotificationChannelKind.TELEGRAM.value:
        if not TELEGRAM_TOKEN.match(value):
            raise ValidationError(
                "Token bot Telegram non valido (formato atteso: <id>:<token>).",
                code="NOTIFICATION_SECRET_INVALID",
            )
    else:  # pragma: no cover - kind is validated by the enum
        raise ValidationError("Tipo di canale non valido.", code="NOTIFICATION_KIND_INVALID")
    return value


def _parse_kind(raw: str) -> NotificationChannelKind:
    try:
        return NotificationChannelKind(str(raw).strip().upper())
    except ValueError as exc:
        allowed = ", ".join(kind.value for kind in NotificationChannelKind)
        raise ValidationError(
            f"Tipo di canale non valido: usare uno tra {allowed}.",
            code="NOTIFICATION_KIND_INVALID",
        ) from exc


def list_channels(db: Session) -> list[NotificationChannel]:
    return list(db.scalars(select(NotificationChannel).order_by(NotificationChannel.name)).all())


def get_channel(db: Session, channel_id: uuid.UUID) -> NotificationChannel:
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise NotFoundError(
            "Canale di notifica non trovato.",
            details={"channel_id": str(channel_id)},
        )
    return channel


def create_channel(
    db: Session,
    settings: Settings,
    *,
    name: str,
    kind: str,
    secret: str,
    events: list[str] | None,
    config: dict[str, Any] | None,
    is_enabled: bool,
    actor_user_id: uuid.UUID | None = None,
) -> NotificationChannel:
    channel_kind = _parse_kind(kind)
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError("Il nome del canale è obbligatorio.")
    if db.scalar(select(NotificationChannel).where(NotificationChannel.name == clean_name)):
        raise ConflictError(
            "Esiste già un canale con questo nome.",
            code="NOTIFICATION_CHANNEL_EXISTS",
            details={"name": clean_name},
        )
    channel = NotificationChannel(
        id=uuid.uuid4(),
        name=clean_name,
        kind=channel_kind.value,
        is_enabled=is_enabled,
        events=normalize_events(events),
        config=_validate_config(channel_kind.value, config),
        secret_algorithm=ALGORITHM,
    )
    _encrypt_secret(channel, _validate_secret(channel_kind.value, secret), settings)
    db.add(channel)
    db.flush()
    # Adding the first channel must not replay the historical runs.
    channel_count = db.scalar(select(func.count()).select_from(NotificationChannel)) or 0
    if channel_count == 1:
        db.execute(
            update(SyncRun).where(SyncRun.notified_at.is_(None)).values(notified_at=utcnow())
        )
    audit.record(
        db,
        action="notification_channel_created",
        entity_type="notification_channel",
        entity_id=str(channel.id),
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"name": channel.name, "kind": channel.kind, "events": channel.events},
    )
    db.commit()
    return channel


def update_channel(
    db: Session,
    settings: Settings,
    channel_id: uuid.UUID,
    *,
    name: str | None = None,
    secret: str | None = None,
    events: list[str] | None = None,
    config: dict[str, Any] | None = None,
    is_enabled: bool | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> NotificationChannel:
    channel = get_channel(db, channel_id)
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Il nome del canale è obbligatorio.")
        duplicate = db.scalar(
            select(NotificationChannel).where(
                NotificationChannel.name == clean_name,
                NotificationChannel.id != channel.id,
            )
        )
        if duplicate is not None:
            raise ConflictError(
                "Esiste già un canale con questo nome.",
                code="NOTIFICATION_CHANNEL_EXISTS",
            )
        channel.name = clean_name
    if events is not None:
        channel.events = normalize_events(events)
    if config is not None:
        channel.config = _validate_config(channel.kind, config)
    if is_enabled is not None:
        channel.is_enabled = is_enabled
    if secret is not None and secret.strip():
        _encrypt_secret(channel, _validate_secret(channel.kind, secret), settings)
    audit.record(
        db,
        action="notification_channel_updated",
        entity_type="notification_channel",
        entity_id=str(channel.id),
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"name": channel.name, "enabled": channel.is_enabled, "events": channel.events},
    )
    db.commit()
    return channel


def delete_channel(
    db: Session,
    channel_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    channel = get_channel(db, channel_id)
    db.delete(channel)
    audit.record(
        db,
        action="notification_channel_deleted",
        entity_type="notification_channel",
        entity_id=str(channel_id),
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"name": channel.name},
    )
    db.commit()


def _send(
    db: Session,
    settings: Settings,
    channel: NotificationChannel,
    *,
    event: str,
    message: str,
    payload: dict[str, Any],
) -> DeliveryResult:
    started = time.monotonic()
    status_code: int | None = None
    error: str | None = None
    try:
        secret = _decrypt_secret(channel, settings)
        with httpx.Client(
            timeout=min(float(settings.http_timeout_seconds), 15.0),
            follow_redirects=False,
        ) as client:
            if channel.kind == NotificationChannelKind.WEBHOOK.value:
                response = client.post(
                    secret,
                    json={
                        "event": event,
                        "message": message,
                        "payload": payload,
                        "app_url": settings.app_base_url.rstrip("/"),
                        "timestamp": utcnow().isoformat(),
                    },
                    headers={"User-Agent": "MdbUP/0.2"},
                )
            elif channel.kind == NotificationChannelKind.DISCORD.value:
                response = client.post(
                    secret,
                    json={"content": message[:1900]},
                    headers={"User-Agent": "MdbUP/0.2"},
                )
            else:
                chat_id = str((channel.config or {}).get("chat_id", ""))
                response = client.post(
                    f"https://api.telegram.org/bot{secret}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message[:4000],
                        "disable_web_page_preview": True,
                    },
                    headers={"User-Agent": "MdbUP/0.2"},
                )
        status_code = response.status_code
        if response.status_code >= 400:
            error = f"HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        # Never include the URL/token in the stored error.
        error = f"Errore di rete ({type(exc).__name__})"
    except (ValidationError, DecryptionError) as exc:
        error = getattr(exc, "message", str(exc))[:300]
    ok = error is None
    moment = utcnow()
    channel.last_status = "SENT" if ok else "FAILED"
    channel.last_error = None if ok else (error or "Errore sconosciuto")[:1000]
    # Persist the event even on failure: the retry task resends this exact
    # message after a restart, without rebuilding it from the run state.
    channel.last_event = event
    channel.last_payload = {"message": message[:MAX_MESSAGE_LENGTH], "payload": payload}
    if ok:
        channel.last_sent_at = moment
        channel.retry_count = 0
        channel.next_retry_at = None
    else:
        channel.retry_count = (channel.retry_count or 0) + 1
        delay = retry_delay_seconds(channel.retry_count)
        channel.next_retry_at = None if delay is None else moment + timedelta(seconds=delay)
        if delay is None:
            logger.warning(
                "notification_retry_exhausted",
                channel_id=str(channel.id),
                attempts=channel.retry_count,
            )
    db.flush()
    logger.info(
        "notification_delivery",
        channel_id=str(channel.id),
        kind=channel.kind,
        notification_event=event,
        ok=ok,
        status_code=status_code,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return DeliveryResult(
        channel_id=channel.id,
        channel_name=channel.name,
        ok=ok,
        status_code=status_code,
        error=error,
    )


def dispatch_event(
    db: Session,
    settings: Settings,
    *,
    event: NotificationEventType | str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> DispatchSummary:
    event_value = str(event)
    channels = list(
        db.scalars(
            select(NotificationChannel).where(NotificationChannel.is_enabled.is_(True))
        ).all()
    )
    selected = [
        channel
        for channel in channels
        if event_value in (channel.events or []) or "ALL" in (channel.events or [])
    ]
    results = [
        _send(
            db,
            settings,
            channel,
            event=event_value,
            message=message[:MAX_MESSAGE_LENGTH],
            payload=payload or {},
        )
        for channel in selected
    ]
    return DispatchSummary(
        attempted=len(results),
        sent=sum(1 for result in results if result.ok),
        failed=sum(1 for result in results if not result.ok),
        results=results,
    )


def retry_due_notifications(
    db: Session,
    settings: Settings,
    *,
    now: Any | None = None,
    limit: int = 50,
) -> dict[str, int]:
    """Resend failed deliveries whose backoff has elapsed.

    Runs on the maintenance queue: a failing channel never blocks a sync run and
    the outcome is only recorded on the channel row and in the logs.
    """
    moment = ensure_utc(now or utcnow())
    due = list(
        db.scalars(
            select(NotificationChannel)
            .where(
                NotificationChannel.is_enabled.is_(True),
                NotificationChannel.last_status == "FAILED",
                NotificationChannel.next_retry_at.is_not(None),
                NotificationChannel.next_retry_at <= moment,
            )
            .order_by(NotificationChannel.next_retry_at)
            .limit(limit)
        ).all()
    )
    sent = 0
    failed = 0
    skipped = 0
    for channel in due:
        stored = channel.last_payload if isinstance(channel.last_payload, dict) else {}
        message = str(stored.get("message") or "")
        if not message or not channel.last_event:
            # Legacy row without a stored payload: nothing to resend.
            channel.next_retry_at = None
            db.commit()
            skipped += 1
            continue
        payload = stored.get("payload")
        result = _send(
            db,
            settings,
            channel,
            event=channel.last_event,
            message=message,
            payload=payload if isinstance(payload, dict) else {},
        )
        db.commit()
        if result.ok:
            sent += 1
        else:
            failed += 1
    if due:
        logger.info(
            "notification_retry_run",
            due=len(due),
            sent=sent,
            failed=failed,
            skipped=skipped,
        )
    return {"due": len(due), "sent": sent, "failed": failed, "skipped": skipped}


def send_test(db: Session, settings: Settings, channel_id: uuid.UUID) -> DeliveryResult:
    channel = get_channel(db, channel_id)
    result = _send(
        db,
        settings,
        channel,
        event="TEST",
        message=(
            "MdbUP — notifica di prova\n"
            f"Canale: {channel.name}\n"
            f"URL applicazione: {settings.app_base_url.rstrip('/')}"
        ),
        payload={"test": True},
    )
    db.commit()
    return result


def _run_message(
    db: Session,
    settings: Settings,
    run: SyncRun,
    event: NotificationEventType,
) -> tuple[str, dict[str, Any]]:
    binding = bindings_repo.get_binding(db, run.binding_id)
    collection = collections_repo.get_collection(db, binding.collection_id) if binding else None
    target = targets_repo.get_target(db, run.target_id)
    collection_name = collection.name if collection is not None else "Collezione sconosciuta"
    target_name = target.name if target is not None else "Lista sconosciuta"
    link = f"{settings.app_base_url.rstrip('/')}/app/runs/{run.id}"
    payload = {
        "run_id": str(run.id),
        "collection": collection_name,
        "target": target_name,
        "to_add": run.to_add_count,
        "to_remove": run.to_remove_count,
        "failed": run.failed_count,
        "uncertain": run.uncertain_count,
        "status": run.status,
        "link": link,
    }
    if event is NotificationEventType.RUN_PENDING_APPROVAL:
        message = (
            "MdbUP — run in attesa di approvazione\n"
            f"Lista: {collection_name} → {target_name}\n"
            f"Aggiunte previste: {run.to_add_count}\n"
            f"Rimozioni previste: {run.to_remove_count}\n"
            f"Motivo: {run.abort_reason or 'soglie di sicurezza superate'}\n"
            f"Apri: {link}"
        )
    elif event is NotificationEventType.RUN_UNCERTAIN:
        message = (
            "MdbUP — operazioni remote incerte\n"
            f"Lista: {collection_name} → {target_name}\n"
            f"Fallite: {run.failed_count} · Incerta: {run.uncertain_count}\n"
            f"Apri e riconcilia: {link}"
        )
    else:
        message = (
            "MdbUP — run fallito\n"
            f"Lista: {collection_name} → {target_name}\n"
            f"Errore: {run.error_code or run.abort_reason or 'sconosciuto'}\n"
            f"Apri: {link}"
        )
    return message, payload


def scan_run_notifications(db: Session, settings: Settings) -> dict[str, int]:
    """Send alerts for runs that reached a relevant state and were not notified."""
    enabled = db.scalar(
        select(func.count())
        .select_from(NotificationChannel)
        .where(NotificationChannel.is_enabled.is_(True))
    )
    if not enabled:
        return {"scanned": 0, "sent": 0, "failed": 0}
    runs = list(
        db.scalars(
            select(SyncRun)
            .where(
                SyncRun.notified_at.is_(None),
                SyncRun.status.in_(
                    (
                        SyncRunStatus.AWAITING_APPROVAL.value,
                        SyncRunStatus.FAILED.value,
                        SyncRunStatus.PARTIAL.value,
                    )
                ),
            )
            .order_by(SyncRun.created_at)
            .limit(50)
        ).all()
    )
    sent = 0
    failed = 0
    for run in runs:
        if run.status == SyncRunStatus.AWAITING_APPROVAL.value:
            event = NotificationEventType.RUN_PENDING_APPROVAL
        elif run.status == SyncRunStatus.PARTIAL.value:
            event = NotificationEventType.RUN_UNCERTAIN
        else:
            event = NotificationEventType.RUN_FAILED
        message, payload = _run_message(db, settings, run, event)
        summary = dispatch_event(db, settings, event=event, message=message, payload=payload)
        sent += summary.sent
        failed += summary.failed
        run.notified_at = utcnow()
        db.commit()
    return {"scanned": len(runs), "sent": sent, "failed": failed}


def _dedupe(settings: Settings, namespace: str, key: str, ttl_seconds: int) -> bool:
    """Return True exactly once per key/TTL (Redis, in-memory fallback)."""
    full_key = f"mdbup:notifications:{namespace}:{key}"
    if settings.redis_url:
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
                decode_responses=True,
            )
            return bool(client.set(full_key, "1", nx=True, ex=ttl_seconds))
        except redis.RedisError:
            pass
    now = time.monotonic()
    with _DEDUPE_GUARD:
        expires = _DEDUPE_MEMORY.get(full_key, 0.0)
        if expires > now:
            return False
        _DEDUPE_MEMORY[full_key] = now + ttl_seconds
        return True


def notify_auth_error(
    db: Session,
    settings: Settings,
    *,
    service: str,
    status_code: int | None,
    detail: str = "",
) -> DispatchSummary:
    """Alert on a 401/403 from TMDb/MDBList, at most once every six hours."""
    key = f"{service.lower()}:{status_code or 'network'}"
    if not _dedupe(settings, "auth", key, 6 * 60 * 60):
        return DispatchSummary()
    message = (
        "MdbUP — credenziale rifiutata\n"
        f"Servizio: {service}\n"
        f"Stato: {status_code or 'errore di rete'}\n"
        f"Dettaglio: {detail[:500] or 'verificare la chiave nelle Impostazioni.'}"
    )
    summary = dispatch_event(
        db,
        settings,
        event=NotificationEventType.AUTH_ERROR,
        message=message,
        payload={"service": service, "status_code": status_code},
    )
    db.commit()
    return summary


def send_periodic_summary(
    db: Session, settings: Settings, *, now: Any | None = None
) -> dict[str, Any]:
    """Send the optional daily summary at the configured hour."""
    values = settings_repo.effective_values(db, settings)
    if not values.get("notifications_summary_enabled"):
        return {"sent": 0, "skipped": "disabled"}
    moment = ensure_utc(now or utcnow())
    if moment.hour != int(values.get("notifications_summary_hour", 8)):
        return {"sent": 0, "skipped": "not_due"}
    if not _dedupe(settings, "summary", moment.date().isoformat(), 24 * 60 * 60):
        return {"sent": 0, "skipped": "already_sent"}
    enabled = db.scalar(
        select(func.count())
        .select_from(NotificationChannel)
        .where(NotificationChannel.is_enabled.is_(True))
    )
    if not enabled:
        return {"sent": 0, "skipped": "no_channels"}
    since = moment - timedelta(hours=24)
    runs = list(db.scalars(select(SyncRun).where(SyncRun.finished_at >= since)).all())
    counts: dict[str, int] = {}
    added = removed = failed = uncertain = 0
    for run in runs:
        counts[run.status] = counts.get(run.status, 0) + 1
        added += run.added_count
        removed += run.removed_count
        failed += run.failed_count
        uncertain += run.uncertain_count
    status_line = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    message = (
        "MdbUP — riepilogo sincronizzazioni (24h)\n"
        f"Run: {len(runs)} · Aggiunte: {added} · Rimozioni: {removed}\n"
        f"Fallite: {failed} · Incerta: {uncertain}\n"
        f"Stati: {status_line or 'nessun run'}"
    )
    summary = dispatch_event(
        db,
        settings,
        event=NotificationEventType.SUMMARY,
        message=message,
        payload={"runs": len(runs), "statuses": counts},
    )
    db.commit()
    return {"sent": summary.sent, "failed": summary.failed, "runs": len(runs)}
