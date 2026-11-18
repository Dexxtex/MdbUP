"""Collection acquisition: fetch every page, normalize, resolve and snapshot.

One call creates exactly one ``CollectionSnapshot``. The snapshot is written in
a single transaction and only becomes ``is_valid`` when it is ``COMPLETE``,
``CLEAN``, non-empty, error-free and fully resolved; only then does the
collection pointer ``last_valid_snapshot_id`` move.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import ConflictError, NotFoundError, SourceUnavailableError
from app.connectors.base import (
    NormalizedItem,
    NotSupportedError,
    SourceCollection,
    SourceConnector,
)
from app.connectors.justwatch.connector import JustWatchConnector
from app.core.logging import get_logger
from app.core.time import ensure_utc, utcnow
from app.db.models import Availability, Collection, CollectionSnapshot, Media, SnapshotItem
from app.domain.enums import (
    COMBINED_DERIVATION,
    AuditActorType,
    AvailabilityStatus,
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
    OfferType,
    ResolutionStatus,
    SnapshotQuality,
    SnapshotStatus,
)
from app.repositories import audit
from app.repositories import availability as availability_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import providers as providers_repo
from app.repositories import snapshots as snapshots_repo
from app.services import normalization

logger = get_logger(__name__)

MAX_PAGES = 500


@dataclass(frozen=True)
class AcquisitionOutcome:
    """Result of one acquisition, mirroring the persisted snapshot counters."""

    snapshot_id: uuid.UUID
    status: SnapshotStatus
    quality: SnapshotQuality
    is_valid: bool
    items_count: int
    resolved_count: int
    unresolved_count: int
    duplicate_count: int
    error_count: int
    pages_expected: int | None
    pages_fetched: int
    checksum: str | None
    invalid_reason: str | None
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _RunState:
    normalized: list[NormalizedItem] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    pages_expected: int | None = None
    pages_fetched: int = 0
    fatal: bool = False


def acquire_collection(
    db: Session,
    collection_id: uuid.UUID,
    connector: SourceConnector,
    *,
    actor_user_id: uuid.UUID | None = None,
    actor_type: AuditActorType = AuditActorType.SYSTEM,
    job_execution_id: uuid.UUID | None = None,
    page_size: int | None = None,
    max_pages: int = MAX_PAGES,
) -> AcquisitionOutcome:
    """Acquire ``collection_id`` into a new immutable snapshot."""
    collection = collections_repo.get_collection(db, collection_id)
    if collection is None:
        raise NotFoundError(
            "Collezione non trovata.", details={"collection_id": str(collection_id)}
        )
    if snapshots_repo.get_running_snapshot(db, collection.id) is not None:
        raise ConflictError(
            "Acquisizione già in corso per questa collezione.",
            code="ACQUISITION_ALREADY_RUNNING",
        )
    collection_pk = collection.id
    snapshot = snapshots_repo.create_running_snapshot(
        db, collection_pk, job_execution_id=job_execution_id
    )
    try:
        if _is_recently_detected(collection):
            outcome = _acquire_recently_detected(db, collection, snapshot)
        elif _is_local_filter(collection):
            outcome = _acquire_from_local_filter(db, collection, snapshot)
        elif _is_combined_local(collection):
            outcome = _acquire_from_combined_local(db, collection, snapshot)
        elif (collection.filters or {}).get("shared_snapshot_collection_id"):
            outcome = _acquire_from_shared_snapshot(db, collection, snapshot)
        else:
            source_collection = _source_collection(db, collection)
            state = _collect_pages(
                connector, source_collection, page_size=page_size, max_pages=max_pages
            )
            outcome = _finalize(db, collection, snapshot, connector, state)
            _observe_justwatch_tv(db, collection, connector, snapshot, state)
    except Exception as exc:
        logger.exception(
            "acquisition_failed", collection_id=str(collection_pk), error=type(exc).__name__
        )
        db.rollback()
        _record_failed_snapshot(db, collection_pk, exc)
        db.commit()
        raise
    audit.record(
        db,
        action="collection_acquired",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        after={
            "snapshot_id": str(snapshot.id),
            "status": outcome.status.value,
            "is_valid": outcome.is_valid,
            "items_count": outcome.items_count,
        },
    )
    db.commit()
    return outcome


def _is_recently_detected(collection: Collection) -> bool:
    filters = collection.filters or {}
    return (
        collection.kind == CollectionKind.RECENTLY_ADDED.value
        and filters.get("derivation") == "RECENTLY_DETECTED"
    )


def _is_local_filter(collection: Collection) -> bool:
    filters = collection.filters or {}
    return (
        collection.kind == CollectionKind.CUSTOM_FILTER.value
        and filters.get("derivation") == "LOCAL_FILTER"
    )


def _is_combined_local(collection: Collection) -> bool:
    filters = collection.filters or {}
    return (
        collection.kind == CollectionKind.CUSTOM_FILTER.value
        and filters.get("derivation") == COMBINED_DERIVATION
    )


def _payload_number(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _payload_genres(payload: dict[str, Any]) -> set[int]:
    raw = payload.get("genre_ids") or []
    if not isinstance(raw, (list, tuple)):
        return set()
    result: set[int] = set()
    for value in raw:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            result.add(value)
        elif isinstance(value, str) and value.isdigit():
            result.add(int(value))
    return result


def _payload_year(payload: dict[str, Any], media: Media) -> int | None:
    # Prefer the source payload: the media row is a canonical identity and may
    # carry a different year (for example a re-release).
    for key in ("release_date", "first_air_date"):
        raw = payload.get(key)
        if isinstance(raw, str) and len(raw) >= 4 and raw[:4].isdigit():
            return int(raw[:4])
    if media.release_year is not None:
        return int(media.release_year)
    return None


def _local_filter_accepts(
    media: Media,
    payload: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    genres = _payload_genres(payload)
    include_raw = str(filters.get("with_genres", "")).strip()
    if include_raw:
        include = {int(value) for value in include_raw.split(",") if value.isdigit()}
        if include and not (include & genres):
            return False
    exclude_raw = str(filters.get("exclude_genres", "")).strip()
    if exclude_raw:
        exclude = {int(value) for value in exclude_raw.split(",") if value.isdigit()}
        if exclude & genres:
            return False
    min_vote_average = filters.get("min_vote_average")
    if min_vote_average is not None:
        value = _payload_number(payload, "vote_average")
        if value is None or value < float(min_vote_average):
            return False
    min_vote_count = filters.get("min_vote_count")
    if min_vote_count is not None:
        value = _payload_number(payload, "vote_count")
        if value is None or value < float(min_vote_count):
            return False
    year = _payload_year(payload, media)
    if filters.get("year_from") is not None and (year is None or year < int(filters["year_from"])):
        return False
    if filters.get("year_to") is not None and (year is None or year > int(filters["year_to"])):
        return False
    language = filters.get("original_language")
    return not (
        language and str(payload.get("original_language", "")).lower() != str(language).lower()
    )


def _local_sort_key(entry: tuple[SnapshotItem, Media, Collection], sort_by: str) -> tuple[Any, ...]:
    item, media, _collection = entry
    payload = item.source_payload or {}
    title = (media.title or "").lower()
    if sort_by == "vote_count.desc":
        return (-(_payload_number(payload, "vote_count") or 0.0), title)
    if sort_by == "release_date.desc":
        return (-(_payload_year(payload, media) or 0), title)
    if sort_by == "title.asc":
        return (title,)
    if sort_by == "popularity.desc":
        return (-(_payload_number(payload, "popularity") or 0.0), title)
    return (-(_payload_number(payload, "vote_average") or 0.0), title)


def _acquire_from_local_filter(
    db: Session,
    collection: Collection,
    snapshot: CollectionSnapshot,
) -> AcquisitionOutcome:
    """Build a snapshot from valid snapshots of one or more providers.

    No connector is called: the result is a local union/filter of data already
    in PostgreSQL. Missing source snapshots are reported as warnings and the
    remaining sources are still usable.
    """
    filters = collection.filters or {}
    raw_ids = filters.get("source_collection_ids") or []
    source_ids: list[uuid.UUID] = []
    for raw in raw_ids:
        try:
            source_ids.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    warnings: list[str] = []
    sources: list[Collection] = []
    for source_id in source_ids:
        source = collections_repo.get_collection(db, source_id)
        if source is None:
            warnings.append(f"SOURCE_COLLECTION_MISSING:{source_id}")
            continue
        if source.media_type != collection.media_type:
            warnings.append(f"SOURCE_MEDIA_TYPE_MISMATCH:{source.slug}")
            continue
        sources.append(source)
    entries: dict[uuid.UUID, tuple[SnapshotItem, Media, Collection]] = {}
    for source in sources:
        snapshot_id = source.last_valid_snapshot_id
        source_snapshot = (
            snapshots_repo.get_snapshot(db, snapshot_id) if snapshot_id is not None else None
        )
        if (
            source_snapshot is None
            or not source_snapshot.is_valid
            or source_snapshot.items_count == 0
        ):
            warnings.append(f"SOURCE_SNAPSHOT_MISSING:{source.slug}")
            continue
        snapshot_items_id = snapshots_repo.items_snapshot_id(db, source_snapshot)
        rows = db.execute(
            select(SnapshotItem, Media)
            .join(Media, SnapshotItem.media_id == Media.id)
            .where(SnapshotItem.snapshot_id == snapshot_items_id)
            .order_by(SnapshotItem.position)
        ).all()
        for item, media in rows:
            if media.id in entries:
                continue
            entries[media.id] = (item, media, source)
    selected = [
        entry
        for entry in entries.values()
        if _local_filter_accepts(entry[1], entry[0].source_payload or {}, filters)
    ]
    sort_by = str(filters.get("sort_by") or "vote_average.desc")
    selected.sort(key=lambda entry: _local_sort_key(entry, sort_by))
    for position, (item, media, source) in enumerate(selected):
        payload = dict(item.source_payload or {})
        payload["local_filter"] = True
        payload["source_collection_id"] = str(source.id)
        payload["source_collection_slug"] = source.slug
        payload["provider_id"] = str(source.provider_id)
        snapshots_repo.add_item(
            db,
            snapshot,
            position=position,
            media_id=media.id,
            source_item_id=str(media.tmdb_id or media.imdb_id or media.id),
            source_payload=payload,
            source_date_created=None,
            date_basis=DateBasis.UNKNOWN.value,
            resolution_status=ResolutionStatus.RESOLVED.value,
            resolution_error=None,
            availability_status=item.availability_status,
        )
    items_count = len(selected)
    snapshot.status = SnapshotStatus.COMPLETE.value
    snapshot.quality = (
        SnapshotQuality.CLEAN.value if not warnings else SnapshotQuality.WARNINGS.value
    )
    snapshot.is_valid = items_count > 0 and not warnings
    snapshot.finished_at = utcnow()
    snapshot.pages_expected = 1
    snapshot.pages_fetched = 1
    snapshot.items_count = items_count
    snapshot.resolved_count = items_count
    snapshot.unresolved_count = 0
    snapshot.duplicate_count = 0
    snapshot.error_count = 0
    snapshot.errors = []
    snapshot.warnings = ["LOCAL_FILTER", *warnings]
    snapshot.checksum = hashlib.sha256(
        ",".join(sorted(str(media.id) for _item, media, _source in selected)).encode("utf-8")
    ).hexdigest()
    if not sources:
        invalid_reason = "local_filter_no_sources"
    elif items_count == 0:
        invalid_reason = "local_filter_empty"
    elif warnings:
        invalid_reason = "local_filter_sources_incomplete"
    else:
        invalid_reason = None
    snapshot.invalid_reason = invalid_reason
    if snapshot.is_valid:
        collections_repo.set_last_valid_snapshot(db, collection, snapshot.id)
    db.flush()
    return AcquisitionOutcome(
        snapshot_id=snapshot.id,
        status=SnapshotStatus.COMPLETE,
        quality=SnapshotQuality(snapshot.quality),
        is_valid=snapshot.is_valid,
        items_count=items_count,
        resolved_count=items_count,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        pages_expected=1,
        pages_fetched=1,
        checksum=snapshot.checksum,
        invalid_reason=invalid_reason,
        errors=[],
    )


def _acquire_from_combined_local(
    db: Session,
    collection: Collection,
    snapshot: CollectionSnapshot,
) -> AcquisitionOutcome:
    """Combine valid JustWatch/TMDb snapshots locally (no external calls).

    UNION keeps every media seen in at least one source, INTERSECTION keeps only
    media present in all available sources. Media and episodes are never
    created here: only existing resolved snapshot items are re-used.
    """
    filters = collection.filters or {}
    raw_ids = filters.get("source_collection_ids") or []
    source_ids: list[uuid.UUID] = []
    for raw in raw_ids:
        try:
            source_ids.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    combine_mode = str(filters.get("combine_mode") or "UNION").upper()
    if combine_mode not in ("UNION", "INTERSECTION"):
        combine_mode = "UNION"
    warnings: list[str] = []
    sources: list[Collection] = []
    for source_id in source_ids:
        source = collections_repo.get_collection(db, source_id)
        if source is None:
            warnings.append(f"SOURCE_COLLECTION_MISSING:{source_id}")
            continue
        if source.media_type != collection.media_type:
            warnings.append(f"SOURCE_MEDIA_TYPE_MISMATCH:{source.slug}")
            continue
        sources.append(source)
    per_source: list[dict[uuid.UUID, tuple[SnapshotItem, Media, Collection]]] = []
    for source in sources:
        snapshot_id = source.last_valid_snapshot_id
        source_snapshot = (
            snapshots_repo.get_snapshot(db, snapshot_id) if snapshot_id is not None else None
        )
        if (
            source_snapshot is None
            or not source_snapshot.is_valid
            or source_snapshot.items_count == 0
        ):
            warnings.append(f"SOURCE_SNAPSHOT_MISSING:{source.slug}")
            continue
        snapshot_items_id = snapshots_repo.items_snapshot_id(db, source_snapshot)
        rows = db.execute(
            select(SnapshotItem, Media)
            .join(Media, SnapshotItem.media_id == Media.id)
            .where(SnapshotItem.snapshot_id == snapshot_items_id)
            .order_by(SnapshotItem.position)
        ).all()
        mapping: dict[uuid.UUID, tuple[SnapshotItem, Media, Collection]] = {}
        for item, media in rows:
            mapping.setdefault(media.id, (item, media, source))
        per_source.append(mapping)
    selected_ids: set[uuid.UUID]
    if combine_mode == "INTERSECTION":
        common: set[uuid.UUID] | None = None
        for mapping in per_source:
            keys = set(mapping)
            common = keys if common is None else common & keys
        selected_ids = common or set()
    else:
        union: set[uuid.UUID] = set()
        for mapping in per_source:
            union.update(mapping)
        selected_ids = union
    selected: list[tuple[SnapshotItem, Media, Collection]] = []
    for media_id in selected_ids:
        entry = next(mapping[media_id] for mapping in per_source if media_id in mapping)
        if _local_filter_accepts(entry[1], entry[0].source_payload or {}, filters):
            selected.append(entry)
    sort_by = str(filters.get("sort_by") or "vote_average.desc")
    selected.sort(key=lambda entry: _local_sort_key(entry, sort_by))
    for position, (item, media, source) in enumerate(selected):
        payload = dict(item.source_payload or {})
        payload["combined_local"] = True
        payload["combine_mode"] = combine_mode
        payload["source_collection_id"] = str(source.id)
        payload["source_collection_slug"] = source.slug
        payload["provider_id"] = str(source.provider_id)
        snapshots_repo.add_item(
            db,
            snapshot,
            position=position,
            media_id=media.id,
            source_item_id=str(media.tmdb_id or media.imdb_id or media.id),
            source_payload=payload,
            source_date_created=None,
            date_basis=DateBasis.UNKNOWN.value,
            resolution_status=ResolutionStatus.RESOLVED.value,
            resolution_error=None,
            availability_status=item.availability_status,
        )
    items_count = len(selected)
    snapshot.status = SnapshotStatus.COMPLETE.value
    snapshot.quality = (
        SnapshotQuality.CLEAN.value if not warnings else SnapshotQuality.WARNINGS.value
    )
    snapshot.is_valid = items_count > 0 and not warnings
    snapshot.finished_at = utcnow()
    snapshot.pages_expected = 1
    snapshot.pages_fetched = 1
    snapshot.items_count = items_count
    snapshot.resolved_count = items_count
    snapshot.unresolved_count = 0
    snapshot.duplicate_count = 0
    snapshot.error_count = 0
    snapshot.errors = []
    snapshot.warnings = ["COMBINED_LOCAL", *warnings]
    snapshot.checksum = hashlib.sha256(
        ",".join(sorted(str(media.id) for _item, media, _source in selected)).encode("utf-8")
    ).hexdigest()
    if not sources:
        invalid_reason = "combined_local_no_sources"
    elif items_count == 0:
        invalid_reason = "combined_local_empty"
    elif warnings:
        invalid_reason = "combined_local_sources_incomplete"
    else:
        invalid_reason = None
    snapshot.invalid_reason = invalid_reason
    if snapshot.is_valid:
        collections_repo.set_last_valid_snapshot(db, collection, snapshot.id)
    db.flush()
    return AcquisitionOutcome(
        snapshot_id=snapshot.id,
        status=SnapshotStatus.COMPLETE,
        quality=SnapshotQuality(snapshot.quality),
        is_valid=snapshot.is_valid,
        items_count=items_count,
        resolved_count=items_count,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        pages_expected=1,
        pages_fetched=1,
        checksum=snapshot.checksum,
        invalid_reason=invalid_reason,
        errors=[],
    )


def _acquire_recently_detected(
    db: Session,
    collection: Collection,
    snapshot: CollectionSnapshot,
) -> AcquisitionOutcome:
    """Build a snapshot from local Availability history (no TMDb calls).

    The first snapshot of the source catalog is the baseline: items whose
    ``first_seen_at`` is equal to (or earlier than) that baseline are not
    "new". Only later observations inside the window are included.
    """
    filters = collection.filters or {}
    source_collection_id = filters.get("source_collection_id")
    if not source_collection_id:
        raise ConflictError(
            "Collezione 'Appena rilevati' senza source_collection_id.",
            code="DERIVATION_SOURCE_MISSING",
        )
    try:
        source_id = uuid.UUID(str(source_collection_id))
    except ValueError as exc:
        raise ConflictError(
            "source_collection_id non valido.",
            code="DERIVATION_SOURCE_INVALID",
        ) from exc
    source_collection = collections_repo.get_collection(db, source_id)
    if source_collection is None:
        raise ConflictError(
            "Collezione sorgente non trovata.",
            code="DERIVATION_SOURCE_MISSING",
            details={"source_collection_id": str(source_id)},
        )
    window_days = int(filters.get("window_days") or 14)
    window_days = max(1, min(window_days, 90))
    baseline_at = db.scalar(
        select(func.min(CollectionSnapshot.started_at)).where(
            CollectionSnapshot.collection_id == source_id,
            CollectionSnapshot.status == SnapshotStatus.COMPLETE.value,
            CollectionSnapshot.items_count > 0,
        )
    )
    rows: list[tuple[Media, Availability]] = []
    if baseline_at is not None:
        cutoff = ensure_utc(snapshot.started_at) - timedelta(days=window_days)
        rows = list(
            db.execute(
                select(Media, Availability)
                .join(Availability, Availability.media_id == Media.id)
                .where(
                    Availability.provider_id == collection.provider_id,
                    Availability.country_code == collection.country_code,
                    Availability.offer_type == OfferType.FLATRATE.value,
                    Media.media_type == collection.media_type,
                    Availability.first_seen_at > baseline_at,
                    Availability.first_seen_at >= cutoff,
                )
                .order_by(Availability.first_seen_at.desc())
            ).all()
        )
    seen: set[uuid.UUID] = set()
    deduplicated: list[tuple[Media, Availability]] = []
    for media, availability in rows:
        if media.id in seen:
            continue
        seen.add(media.id)
        deduplicated.append((media, availability))
    for position, (media, availability) in enumerate(deduplicated):
        snapshots_repo.add_item(
            db,
            snapshot,
            position=position,
            media_id=media.id,
            source_item_id=str(media.tmdb_id or media.imdb_id or media.id),
            source_payload={
                "first_seen_at": ensure_utc(availability.first_seen_at).isoformat(),
                "provider_id": str(collection.provider_id),
                "derivation": "RECENTLY_DETECTED",
            },
            source_date_created=None,
            date_basis=DateBasis.APP_FIRST_SEEN.value,
            resolution_status=ResolutionStatus.RESOLVED.value,
            resolution_error=None,
            availability_status=AvailabilityStatus.CURRENT.value,
        )
    items_count = len(deduplicated)
    snapshot.status = SnapshotStatus.COMPLETE.value
    snapshot.quality = SnapshotQuality.CLEAN.value
    snapshot.is_valid = items_count > 0
    snapshot.finished_at = utcnow()
    snapshot.pages_expected = 1
    snapshot.pages_fetched = 1
    snapshot.items_count = items_count
    snapshot.resolved_count = items_count
    snapshot.unresolved_count = 0
    snapshot.duplicate_count = 0
    snapshot.error_count = 0
    snapshot.errors = []
    snapshot.warnings = []
    snapshot.checksum = hashlib.sha256(
        ",".join(sorted(str(media.id) for media, _ in deduplicated)).encode("utf-8")
    ).hexdigest()
    snapshot.invalid_reason = None if items_count else "baseline_empty"
    if snapshot.is_valid:
        collections_repo.set_last_valid_snapshot(db, collection, snapshot.id)
    db.flush()
    return AcquisitionOutcome(
        snapshot_id=snapshot.id,
        status=SnapshotStatus.COMPLETE,
        quality=SnapshotQuality.CLEAN,
        is_valid=snapshot.is_valid,
        items_count=items_count,
        resolved_count=items_count,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        pages_expected=1,
        pages_fetched=1,
        checksum=snapshot.checksum,
        invalid_reason=snapshot.invalid_reason,
        errors=list(snapshot.errors or []),
    )


def _acquire_from_shared_snapshot(
    db: Session,
    collection: Collection,
    snapshot: CollectionSnapshot,
) -> AcquisitionOutcome:
    """Build a snapshot from another valid snapshot, filtered by genre.

    This is the quota optimisation: several genre collections of the same
    provider/region/media type can share one complete catalog acquisition.
    """
    filters = collection.filters or {}
    shared_id = filters.get("shared_snapshot_collection_id")
    if not shared_id:
        raise ConflictError(
            "shared_snapshot_collection_id mancante.",
            code="SHARED_SNAPSHOT_MISSING",
        )
    try:
        shared_collection_id = uuid.UUID(str(shared_id))
    except ValueError as exc:
        raise ConflictError(
            "shared_snapshot_collection_id non valido.",
            code="SHARED_SNAPSHOT_INVALID",
        ) from exc
    shared_collection = collections_repo.get_collection(db, shared_collection_id)
    if shared_collection is None:
        raise ConflictError(
            "Collezione condivisa non trovata.",
            code="SHARED_SNAPSHOT_MISSING",
        )
    if (
        shared_collection.provider_id != collection.provider_id
        or shared_collection.media_type != collection.media_type
    ):
        raise ConflictError(
            "La collezione condivisa ha provider o tipo media diverso.",
            code="SHARED_SNAPSHOT_MISMATCH",
        )
    shared_snapshot_id = shared_collection.last_valid_snapshot_id
    if shared_snapshot_id is None:
        raise ConflictError(
            "La collezione condivisa non ha uno snapshot valido.",
            code="SHARED_SNAPSHOT_MISSING",
        )
    shared_snapshot = snapshots_repo.get_snapshot(db, shared_snapshot_id)
    if shared_snapshot is None:
        raise ConflictError(
            "Snapshot condiviso non trovato.",
            code="SHARED_SNAPSHOT_MISSING",
        )
    genre_ids = {
        int(value)
        for value in str(filters.get("with_genres", "")).split(",")
        if value.strip().isdigit()
    }
    shared_items_id = snapshots_repo.items_snapshot_id(db, shared_snapshot)
    shared_items = list(
        db.scalars(
            select(SnapshotItem)
            .where(SnapshotItem.snapshot_id == shared_items_id)
            .order_by(SnapshotItem.position)
        ).all()
    )
    selected: list[SnapshotItem] = []
    for item in shared_items:
        if genre_ids:
            raw = item.source_payload or {}
            item_genres = {
                int(value)
                for value in raw.get("genre_ids", [])
                if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
            }
            if not (genre_ids & item_genres):
                continue
        selected.append(item)
    for position, item in enumerate(selected):
        snapshots_repo.add_item(
            db,
            snapshot,
            position=position,
            media_id=item.media_id,
            source_item_id=item.source_item_id,
            source_payload=dict(item.source_payload or {}),
            source_date_created=item.source_date_created,
            date_basis=item.date_basis,
            resolution_status=item.resolution_status,
            resolution_error=item.resolution_error,
            availability_status=item.availability_status,
        )
    items_count = len(selected)
    unresolved_count = sum(
        1 for item in selected if item.resolution_status != ResolutionStatus.RESOLVED.value
    )
    snapshot.status = SnapshotStatus.COMPLETE.value
    snapshot.quality = (
        SnapshotQuality.CLEAN.value if unresolved_count == 0 else SnapshotQuality.WARNINGS.value
    )
    snapshot.is_valid = items_count > 0 and unresolved_count == 0
    snapshot.finished_at = utcnow()
    snapshot.pages_expected = 1
    snapshot.pages_fetched = 1
    snapshot.items_count = items_count
    snapshot.resolved_count = items_count - unresolved_count
    snapshot.unresolved_count = unresolved_count
    snapshot.duplicate_count = 0
    snapshot.error_count = 0
    snapshot.errors = []
    snapshot.warnings = ["SHARED_SNAPSHOT_REUSE"]
    snapshot.checksum = hashlib.sha256(
        ",".join(sorted(str(item.media_id) for item in selected)).encode("utf-8")
    ).hexdigest()
    snapshot.invalid_reason = None if snapshot.is_valid else "shared_snapshot_empty"
    if snapshot.is_valid:
        collections_repo.set_last_valid_snapshot(db, collection, snapshot.id)
    db.flush()
    return AcquisitionOutcome(
        snapshot_id=snapshot.id,
        status=SnapshotStatus.COMPLETE,
        quality=SnapshotQuality(snapshot.quality),
        is_valid=snapshot.is_valid,
        items_count=items_count,
        resolved_count=snapshot.resolved_count,
        unresolved_count=unresolved_count,
        duplicate_count=0,
        error_count=0,
        pages_expected=1,
        pages_fetched=1,
        checksum=snapshot.checksum,
        invalid_reason=snapshot.invalid_reason,
        errors=list(snapshot.errors or []),
    )


def _source_collection(db: Session, collection: Collection) -> SourceCollection:
    """Translate the persisted collection into the connector contract."""
    mapping = providers_repo.get_mapping(
        db,
        provider_id=collection.provider_id,
        source_id=collection.source_id,
        country_code=collection.country_code,
    )
    if mapping is None:
        raise SourceUnavailableError(
            "Mapping del provider non configurato: eseguire il seed dei provider.",
            details={
                "collection_id": str(collection.id),
                "provider_id": str(collection.provider_id),
                "country_code": collection.country_code,
            },
        )
    media_type = MediaType(collection.media_type)
    offer_types = [str(value) for value in (collection.offer_types or [])]
    mapping_metadata = mapping.metadata_json or {}
    provider_external_id = (
        mapping_metadata.get("tv_provider_id")
        if media_type is MediaType.SHOW
        else mapping_metadata.get("movie_provider_id")
    ) or mapping.external_provider_id
    return SourceCollection(
        key=collection.source_collection_key or collection.slug,
        name=collection.name,
        provider_external_id=str(provider_external_id),
        media_type=media_type,
        kind=CollectionKind(collection.kind),
        origin=CollectionOrigin(collection.origin),
        date_basis=DateBasis(collection.date_basis),
        source_url=collection.source_url,
        metadata={
            "provider_id": str(provider_external_id),
            "media_type": media_type.value,
            "offer_types": offer_types,
            "watch_region": collection.country_code,
            "filters": collection.filters or {},
        },
    )


def _collect_pages(
    connector: SourceConnector,
    source_collection: SourceCollection,
    *,
    page_size: int | None,
    max_pages: int,
) -> _RunState:
    state = _RunState()
    requested_page_size = page_size or connector.capabilities.max_page_size
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        try:
            page = connector.fetch_collection_page(source_collection, cursor, requested_page_size)
        except NotSupportedError as exc:
            state.errors.append({"code": "NOT_SUPPORTED", "message": str(exc)})
            state.fatal = state.pages_fetched == 0
            break
        except Exception as exc:
            state.errors.append(
                {
                    "code": type(exc).__name__,
                    "message": str(exc)[:300],
                    "page": state.pages_fetched + 1,
                }
            )
            state.fatal = state.pages_fetched == 0
            break
        if state.pages_expected is None and page.total_pages is not None:
            state.pages_expected = min(page.total_pages, max_pages)
        state.pages_fetched += 1
        for raw in page.items:
            try:
                state.normalized.append(connector.normalize_item(raw))
            except Exception as exc:
                state.errors.append(
                    {
                        "code": "NORMALIZE_FAILED",
                        "message": str(exc)[:300],
                        "source_item_id": raw.source_item_id,
                    }
                )
        if page.next_cursor is None:
            break
        if state.pages_fetched >= max_pages:
            state.warnings.append(
                {"code": "PAGE_CAP_REACHED", "message": f"Limite di {max_pages} pagine."}
            )
            break
        if page.next_cursor in seen_cursors:
            state.warnings.append(
                {"code": "CURSOR_LOOP", "message": "Cursore ripetuto: acquisizione interrotta."}
            )
            break
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    return state


def _finalize(
    db: Session,
    collection: Collection,
    snapshot: CollectionSnapshot,
    connector: SourceConnector,
    state: _RunState,
) -> AcquisitionOutcome:
    deduplicated = normalization.deduplicate(state.normalized)
    resolved_count = 0
    unresolved_count = 0
    media_duplicates = 0
    seen_media: set[uuid.UUID] = set()
    rows: list[tuple[NormalizedItem, uuid.UUID | None, ResolutionStatus, str | None]] = []
    for item in deduplicated.items:
        status = normalization.resolution_status(item)
        media = None
        resolution_error: str | None = None
        if status is ResolutionStatus.RESOLVED:
            media = media_repo.resolve_media(
                db,
                media_type=item.media_type,
                tmdb_id=item.tmdb_id,
                imdb_id=item.imdb_id,
                title=item.title,
                year=item.year,
                metadata={"source": connector.key},
            )
            if media is None:
                status = ResolutionStatus.UNRESOLVED
                resolution_error = "external_id_missing"
        if media is not None:
            # Upcoming titles are not available yet: they must not enter the
            # availability history that drives the "appena rilevati" derivation.
            if item.availability_status != AvailabilityStatus.UPCOMING.value:
                availability_repo.upsert_observed(
                    db,
                    media_id=media.id,
                    provider_id=collection.provider_id,
                    country_code=collection.country_code,
                    offer_type=str((collection.offer_types or [OfferType.FLATRATE.value])[0]),
                    source_id=collection.source_id,
                    first_seen_at=snapshot.started_at,
                    metadata={
                        "source": connector.key,
                        "collection_id": str(collection.id),
                    },
                )
            # Two different identity keys can resolve to the same media row
            # (tmdb vs imdb); the snapshot allows one row per media.
            if media.id in seen_media:
                media_duplicates += 1
                continue
            seen_media.add(media.id)
            resolved_count += 1
        else:
            unresolved_count += 1
        rows.append((item, media.id if media is not None else None, status, resolution_error))
    items_count = len(rows)
    duplicate_count = deduplicated.duplicates + media_duplicates
    snapshot_status, quality = _classify(
        state,
        items_count,
        unresolved_count,
        duplicate_count,
        partial_on_error=connector.capabilities.partial_on_error,
    )
    is_valid = (
        snapshot_status is SnapshotStatus.COMPLETE
        and quality is SnapshotQuality.CLEAN
        and items_count > 0
        and not state.errors
        and unresolved_count == 0
    )
    invalid_reason = _invalid_reason(
        snapshot_status, items_count, unresolved_count, duplicate_count, len(state.errors)
    )
    checksum = normalization.checksum(deduplicated.items)
    finished_at = utcnow()
    previous = (
        snapshots_repo.get_snapshot(db, collection.last_valid_snapshot_id)
        if collection.last_valid_snapshot_id is not None
        else None
    )
    reuse_previous = bool(
        is_valid and previous is not None and previous.is_valid and previous.checksum == checksum
    )

    if reuse_previous and previous is not None:
        # Keep the verification in the snapshot history but reuse the physical
        # rows owned by the previous valid snapshot (or by its own base).
        snapshot.items_from_snapshot_id = previous.items_from_snapshot_id or previous.id
    else:
        for position, (item, media_id, status, resolution_error) in enumerate(rows):
            snapshots_repo.add_item(
                db,
                snapshot,
                position=position,
                media_id=media_id,
                source_item_id=_source_item_id(item),
                source_payload=item.raw,
                source_date_created=item.source_date_created,
                date_basis=item.date_basis.value,
                resolution_status=status.value,
                resolution_error=resolution_error,
                availability_status=item.availability_status,
            )

    snapshot.status = snapshot_status.value
    snapshot.quality = quality.value
    snapshot.is_valid = is_valid
    snapshot.finished_at = finished_at
    snapshot.last_verified_at = finished_at
    snapshot.pages_expected = state.pages_expected
    snapshot.pages_fetched = state.pages_fetched
    snapshot.items_count = items_count
    snapshot.resolved_count = resolved_count
    snapshot.unresolved_count = unresolved_count
    snapshot.duplicate_count = duplicate_count
    snapshot.error_count = len(state.errors)
    snapshot.errors = state.errors
    snapshot.warnings = state.warnings
    snapshot.checksum = checksum
    snapshot.invalid_reason = invalid_reason
    if is_valid:
        collections_repo.set_last_valid_snapshot(db, collection, snapshot.id)
    db.flush()
    return AcquisitionOutcome(
        snapshot_id=snapshot.id,
        status=snapshot_status,
        quality=quality,
        is_valid=is_valid,
        items_count=items_count,
        resolved_count=resolved_count,
        unresolved_count=unresolved_count,
        duplicate_count=duplicate_count,
        error_count=len(state.errors),
        pages_expected=state.pages_expected,
        pages_fetched=state.pages_fetched,
        checksum=snapshot.checksum,
        invalid_reason=invalid_reason,
        errors=list(state.errors),
    )


def _classify(
    state: _RunState,
    items_count: int,
    unresolved_count: int,
    duplicate_count: int,
    *,
    partial_on_error: bool = False,
) -> tuple[SnapshotStatus, SnapshotQuality]:
    if state.fatal and not partial_on_error:
        status = SnapshotStatus.FAILED
    elif (
        state.fatal
        or state.errors
        or (state.pages_expected is not None and state.pages_fetched < state.pages_expected)
    ):
        # A source with ``partial_on_error`` never hides a failure behind a
        # COMPLETE page: even a first-page error yields INCOMPLETE/ANOMALY.
        status = SnapshotStatus.INCOMPLETE
    else:
        status = SnapshotStatus.COMPLETE
    if status is not SnapshotStatus.COMPLETE or items_count == 0:
        quality = SnapshotQuality.ANOMALY
    elif unresolved_count or duplicate_count or state.warnings:
        quality = SnapshotQuality.WARNINGS
    else:
        quality = SnapshotQuality.CLEAN
    return status, quality


def _invalid_reason(
    status: SnapshotStatus,
    items_count: int,
    unresolved_count: int,
    duplicate_count: int,
    error_count: int,
) -> str | None:
    reasons: list[str] = []
    if status is SnapshotStatus.FAILED:
        reasons.append("fetch_failed")
    elif status is SnapshotStatus.INCOMPLETE:
        reasons.append("incomplete_pages")
    if items_count == 0:
        reasons.append("empty_catalog")
    if unresolved_count:
        reasons.append(f"unresolved_items:{unresolved_count}")
    if duplicate_count:
        reasons.append(f"duplicates:{duplicate_count}")
    if error_count:
        reasons.append(f"errors:{error_count}")
    return ", ".join(reasons)[:500] if reasons else None


def _observe_justwatch_tv(
    db: Session,
    collection: Collection,
    connector: SourceConnector,
    snapshot: CollectionSnapshot,
    state: _RunState,
) -> None:
    """Best-effort season/episode events for JustWatch SHOW collections.

    TV errors never invalidate the catalog snapshot: they are recorded as
    warnings on the snapshot itself.
    """
    if collection.media_type != MediaType.SHOW.value:
        return
    if collection.kind not in (
        CollectionKind.CATALOG.value,
        CollectionKind.RECENTLY_ADDED.value,
    ):
        return
    if not isinstance(connector, JustWatchConnector):
        return
    from app.services import justwatch_tv_events

    outcome = justwatch_tv_events.observe_tv_events(
        db, collection=collection, connector=connector, snapshot_id=snapshot.id
    )
    for warning in outcome.warnings:
        state.warnings.append({"code": "TV_EVENTS_PARTIAL", "message": warning})
    if outcome.warnings:
        snapshot.warnings = state.warnings


def _source_item_id(item: NormalizedItem) -> str | None:
    raw_id = item.raw.get("id") if isinstance(item.raw, dict) else None
    if isinstance(raw_id, int):
        return str(raw_id)
    if item.tmdb_id is not None:
        return str(item.tmdb_id)
    return item.imdb_id


def _record_failed_snapshot(db: Session, collection_id: uuid.UUID, exc: Exception) -> None:
    """Persist a FAILED snapshot after an unexpected error rolled the run back."""
    snapshot = CollectionSnapshot(
        collection_id=collection_id,
        status=SnapshotStatus.FAILED.value,
        quality=SnapshotQuality.ANOMALY.value,
        is_valid=False,
        finished_at=utcnow(),
        errors=[{"code": type(exc).__name__, "message": str(exc)[:300]}],
        error_count=1,
        invalid_reason=f"unexpected_error:{type(exc).__name__}"[:500],
    )
    db.add(snapshot)
    db.flush()
