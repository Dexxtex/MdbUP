"""Application settings loaded from environment variables and ``*_FILE`` secrets."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "MdbUP API"
APP_VERSION = "0.2.0"

# Secrets that may be provided as Docker secrets (``NAME_FILE``) instead of env vars.
SECRET_FILE_FIELDS = (
    "app_encryption_key",
    "app_encryption_keys",
    "bootstrap_token",
    "database_url",
    "metrics_token",
)


def read_secret(name: str) -> str | None:
    """Read ``NAME_FILE`` (Docker secret) when present.

    Plain environment variables are handled by pydantic-settings; this helper
    must not override an explicit constructor argument with the environment.
    """
    upper = name.upper()
    file_path = os.environ.get(f"{upper}_FILE")
    if file_path:
        path = Path(file_path)
        if not path.is_file():
            raise RuntimeError(f"{upper}_FILE punta a un file inesistente: {file_path}")
        try:
            return path.read_text(encoding="utf-8").strip()
        except PermissionError as exc:
            raise RuntimeError(
                f"{upper}_FILE non leggibile dal processo (uid/gid 10001): {file_path}. "
                "Con Docker Compose i secret sono bind-mount con i permessi dell'host: "
                "usare chmod 0644 sui file e chmod 0700 sulla directory secrets/."
            ) from exc
    return None


class Settings(BaseSettings):
    """Runtime configuration.

    ``APP_ENCRYPTION_KEY`` and ``BOOTSTRAP_TOKEN`` are optional at startup so the
    API can boot in development; the endpoints that need them fail with an
    explicit error instead of crashing the process.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["dev", "test", "production"] = "dev"
    app_base_url: str = "http://localhost:8000"
    app_timezone: str = "Europe/Rome"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    database_url: str = "sqlite:///./mdbup.db"
    db_pool_size: int = 10
    db_statement_timeout_ms: int = 15000

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_always_eager: bool = False

    app_encryption_key: str = ""
    app_encryption_key_version: int = 1
    # Optional JSON keyring: {"1": "<base64 key>", "2": "<base64 key>"}.
    # It lets a rotation keep the old key available while the new one becomes active.
    app_encryption_keys: str = ""
    bootstrap_token: str = ""

    session_cookie_name: str = "mdbsync-session"
    csrf_cookie_name: str = "mdbsync-csrf"
    cookie_secure: bool = False
    session_ttl_days: int = 7
    session_idle_hours: int = 12
    session_touch_interval_minutes: int = 5
    login_max_attempts: int = 5
    login_window_minutes: int = 15
    login_lockout_minutes: int = 30
    bootstrap_max_attempts: int = 3
    cors_origins: str = ""
    notifications_summary_enabled: bool = False
    notifications_summary_hour: int = 8

    sync_batch_size: int = 100
    sync_max_removal_absolute: int = 50
    sync_max_removal_percent: float = 10.0
    sync_max_addition_percent: float = 50.0
    snapshot_retention_days: int = 90
    run_retention_days: int = 180
    failed_run_retention_days: int = 90
    job_retention_days: int = 30
    session_retention_days: int = 7
    http_timeout_seconds: int = 20
    http_max_retries: int = 4
    http_backoff_base_ms: int = 500
    http_backoff_max_ms: int = 30000
    http_jitter_ratio: float = 0.30

    default_country_code: str = "IT"
    # Fonte proposta per le nuove collezioni: JustWatch (pubblico) o TMDb.
    default_source: str = "justwatch"
    # Acquisizioni scaglionate del catalogo JustWatch: un solo enqueue per tick.
    catalog_schedule_enabled: bool = True
    # Directory della SPA compilata servita dall'API (immagine Docker: /app/static).
    frontend_dist_dir: str = "/app/static"

    # JustWatch public GraphQL endpoint (distinct from the commercial Partner
    # API, which stays contract-gated). No credential: the throttle below is the
    # only thing standing between the app and a silent IP block.
    justwatch_base_url: str = "https://apis.justwatch.com/graphql"
    justwatch_language: str = "it"
    justwatch_min_interval_ms: int = 1000
    # Local response cache: keyed by query + variables, deep-copied on read.
    justwatch_cache_ttl_seconds: int = 300
    justwatch_cache_max_entries: int = 512

    # Prometheus endpoint: never public. Without a token it answers 503.
    metrics_enabled: bool = True
    metrics_token: str = ""

    # Read-only backup directory shared with the api/worker containers. The
    # status file is written by ``deploy/scripts/backup.sh`` and ``backup-verify``.
    backup_dir: str = "/backups"
    backup_status_file: str = ""
    backup_age_identity_file: str = ""

    def model_post_init(self, __context: object) -> None:
        for field in SECRET_FILE_FIELDS:
            value = read_secret(field)
            if value:
                object.__setattr__(self, field, value)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def effective_backup_status_file(self) -> str:
        """``BACKUP_STATUS_FILE`` or ``<BACKUP_DIR>/last_backup.json``."""
        return self.backup_status_file.strip() or str(Path(self.backup_dir) / "last_backup.json")

    @property
    def bootstrap_enabled(self) -> bool:
        return bool(self.bootstrap_token)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_https(self) -> bool:
        return self.app_base_url.lower().startswith("https://")

    @property
    def session_cookie(self) -> str:
        """Effective session cookie name, with ``__Host-`` only in HTTPS mode."""
        return self._cookie_name(self.session_cookie_name)

    @property
    def csrf_cookie(self) -> str:
        """Effective CSRF cookie name, with ``__Host-`` only in HTTPS mode."""
        return self._cookie_name(self.csrf_cookie_name)

    def _cookie_name(self, configured: str) -> str:
        base = configured.strip()
        if base.startswith("__Host-"):
            base = base[len("__Host-") :]
        return f"__Host-{base}" if self.cookie_secure else base


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
