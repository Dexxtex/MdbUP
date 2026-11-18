from __future__ import annotations

from enum import StrEnum


class MediaType(StrEnum):
    MOVIE = "MOVIE"
    SHOW = "SHOW"


class TargetMediaType(StrEnum):
    MOVIE = "MOVIE"
    SHOW = "SHOW"
    SEASON = "SEASON"
    EPISODE = "EPISODE"


class CollectionKind(StrEnum):
    CATALOG = "CATALOG"
    RECENTLY_ADDED = "RECENTLY_ADDED"
    UPCOMING = "UPCOMING"
    CHART = "CHART"
    CUSTOM_FILTER = "CUSTOM_FILTER"


class CollectionOrigin(StrEnum):
    OFFICIAL = "OFFICIAL"
    AGGREGATOR = "AGGREGATOR"
    CUSTOM = "CUSTOM"


class DateBasis(StrEnum):
    PROVIDER_OFFICIAL = "PROVIDER_OFFICIAL"
    AGGREGATOR_FIRST_SEEN = "AGGREGATOR_FIRST_SEEN"
    APP_FIRST_SEEN = "APP_FIRST_SEEN"
    UNKNOWN = "UNKNOWN"


class OfferType(StrEnum):
    FLATRATE = "FLATRATE"
    RENT = "RENT"
    BUY = "BUY"
    ADS = "ADS"
    FREE = "FREE"


class AvailabilityStatus(StrEnum):
    """Availability of a title at acquisition time.

    ``UPCOMING`` items never enter the current catalog: they live only in their
    own ``UPCOMING`` collection snapshot.
    """

    CURRENT = "CURRENT"
    UPCOMING = "UPCOMING"
    LEAVING = "LEAVING"


class SnapshotStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SnapshotQuality(StrEnum):
    CLEAN = "CLEAN"
    WARNINGS = "WARNINGS"
    ANOMALY = "ANOMALY"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


class SyncMode(StrEnum):
    MIRROR = "MIRROR"
    APPEND_ONLY = "APPEND_ONLY"


class SyncRunStatus(StrEnum):
    PENDING = "PENDING"
    PREFLIGHT = "PREFLIGHT"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPLYING = "APPLYING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


ACTIVE_RUN_STATUSES = frozenset(
    {
        SyncRunStatus.PENDING,
        SyncRunStatus.PREFLIGHT,
        SyncRunStatus.PLANNING,
        SyncRunStatus.AWAITING_APPROVAL,
        SyncRunStatus.APPLYING,
        SyncRunStatus.VERIFYING,
    }
)

TERMINAL_RUN_STATUSES = frozenset(
    {
        SyncRunStatus.SUCCEEDED,
        SyncRunStatus.PARTIAL,
        SyncRunStatus.FAILED,
        SyncRunStatus.BLOCKED,
        SyncRunStatus.CANCELLED,
    }
)


class SyncOperationAction(StrEnum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    REORDER = "REORDER"


class SyncOperationStatus(StrEnum):
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"
    SKIPPED = "SKIPPED"


class SourceStatus(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    OK = "OK"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class SourceType(StrEnum):
    API = "API"
    DATA_EXPORT = "DATA_EXPORT"
    MANUAL_CSV = "MANUAL_CSV"


class CredentialScope(StrEnum):
    SOURCE = "SOURCE"
    TARGET = "TARGET"
    SYSTEM = "SYSTEM"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRY = "RETRY"
    CANCELLED = "CANCELLED"


class EpisodeEventType(StrEnum):
    SEASON_ADDED = "SEASON_ADDED"
    SEASON_REMOVED = "SEASON_REMOVED"
    EPISODE_ADDED = "EPISODE_ADDED"
    EPISODE_REMOVED = "EPISODE_REMOVED"


class SchedulePolicy(StrEnum):
    AUTO_APPLY_IF_SAFE = "AUTO_APPLY_IF_SAFE"
    ALWAYS_APPROVE = "ALWAYS_APPROVE"
    DRY_RUN_ONLY = "DRY_RUN_ONLY"


class AuditActorType(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    SCHEDULER = "SCHEDULER"


class NotificationChannelKind(StrEnum):
    WEBHOOK = "WEBHOOK"
    TELEGRAM = "TELEGRAM"
    DISCORD = "DISCORD"


class NotificationEventType(StrEnum):
    RUN_PENDING_APPROVAL = "RUN_PENDING_APPROVAL"
    RUN_FAILED = "RUN_FAILED"
    RUN_UNCERTAIN = "RUN_UNCERTAIN"
    AUTH_ERROR = "AUTH_ERROR"
    SUMMARY = "SUMMARY"


NOTIFICATION_EVENTS = frozenset(event.value for event in NotificationEventType)
