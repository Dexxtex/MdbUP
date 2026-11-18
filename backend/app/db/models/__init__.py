"""All ORM models. Importing this package registers every table on ``Base.metadata``."""

from __future__ import annotations

from app.db.models.audit import AuditLog
from app.db.models.availability import Availability
from app.db.models.collection import Collection
from app.db.models.credential import Credential
from app.db.models.episode import EpisodeEvent
from app.db.models.healthcheck import SourceHealthcheck
from app.db.models.job import JobExecution
from app.db.models.mdblist import MdblistTarget
from app.db.models.media import Media
from app.db.models.notification import NotificationChannel
from app.db.models.provider import Provider, ProviderMapping
from app.db.models.session import UserSession
from app.db.models.settings import AppSetting
from app.db.models.snapshot import CollectionSnapshot, SnapshotItem
from app.db.models.source import Source
from app.db.models.sync import SyncBinding, SyncOperation, SyncRun, SyncRunEvent
from app.db.models.user import AppUser

__all__ = [
    "AppSetting",
    "AppUser",
    "AuditLog",
    "Availability",
    "Collection",
    "CollectionSnapshot",
    "Credential",
    "EpisodeEvent",
    "JobExecution",
    "MdblistTarget",
    "Media",
    "NotificationChannel",
    "Provider",
    "ProviderMapping",
    "SnapshotItem",
    "Source",
    "SourceHealthcheck",
    "SyncBinding",
    "SyncOperation",
    "SyncRun",
    "SyncRunEvent",
    "UserSession",
]
