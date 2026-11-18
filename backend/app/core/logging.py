"""Structured JSON logging with centralized secret redaction."""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

from app.core.config import Settings

REDACTED = "[REDACTED]"

# Keys are compared case-insensitively at every nesting level.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "token_hash",
        "access_token",
        "refresh_token",
        "bootstrap_token",
        "csrf",
        "csrf_token",
        "x-csrf-token",
        "apikey",
        "api_key",
        "authorization",
        "cookie",
        "set-cookie",
        "secret",
        "secret_key",
        "access_key",
        "app_encryption_key",
        "session",
        "session_token",
    }
)

_QUERY_SECRET_PATTERN = re.compile(
    r"(?i)\b(apikey|api_key|token|secret|password|access_key|secret_key)=([^&\s\"']+)"
)


def redact_text(text: str) -> str:
    """Mask secret-looking query string parameters inside a free-form string."""
    return _QUERY_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}={REDACTED}", text)


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``mapping`` with sensitive keys and values masked."""
    redacted: dict[str, Any] = {}
    for key, value in mapping.items():
        if str(key).lower() in SENSITIVE_KEYS:
            redacted[key] = REDACTED
        elif isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        elif isinstance(value, str):
            redacted[key] = redact_text(value)
        else:
            redacted[key] = value
    return redacted


def _redaction_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    return redact_mapping(event_dict)


def configure_logging(settings: Settings) -> None:
    """Configure structlog once per process."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redaction_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.getLogger().setLevel(level)
    # httpx logs the full request URL at INFO, including MDBList's ``apikey``
    # query parameter and Telegram's bot token in the path. Keep transport logs
    # at WARNING; the application logs its own redacted request events.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger bound to ``name``."""
    return structlog.get_logger(name)
