"""Application error taxonomy and the single API error envelope.

Every error response has the shape::

    {"error": {"code", "category", "message", "retryable",
               "request_id", "details", "retry_after_s"}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.domain.errors import (
    AUTH,
    CONFLICT,
    INTERNAL,
    POLICY,
    SOURCE,
    TARGET,
    VALIDATION,
    AlreadyBootstrappedError,
    AppError,
    AuthError,
    BootstrapDisabledError,
    ConflictError,
    CredentialMissingError,
    CsrfError,
    EncryptionKeyMissingError,
    ForbiddenError,
    InvalidBootstrapTokenError,
    InvalidCredentialsError,
    NotFoundError,
    OriginRejectedError,
    RateLimitedError,
    ServiceUnavailableError,
    SourceUnavailableError,
    ValidationError,
)

__all__ = [
    "AUTH",
    "CONFLICT",
    "INTERNAL",
    "POLICY",
    "SOURCE",
    "TARGET",
    "VALIDATION",
    "AlreadyBootstrappedError",
    "AppError",
    "AuthError",
    "BootstrapDisabledError",
    "ConflictError",
    "CredentialMissingError",
    "CsrfError",
    "EncryptionKeyMissingError",
    "ForbiddenError",
    "InvalidBootstrapTokenError",
    "InvalidCredentialsError",
    "NotFoundError",
    "OriginRejectedError",
    "RateLimitedError",
    "ServiceUnavailableError",
    "SourceUnavailableError",
    "ValidationError",
]

logger = get_logger(__name__)


def request_id_from_request(request: Request) -> str | None:
    """Return the request id assigned by the request-context middleware."""
    return getattr(request.state, "request_id", None)


def error_payload(error: AppError, request_id: str | None) -> dict[str, Any]:
    """Build the error envelope body."""
    body: dict[str, Any] = {
        "code": error.code,
        "category": error.category,
        "message": error.message,
        "retryable": error.retryable,
        "request_id": request_id,
        "details": error.details,
    }
    if error.retry_after_seconds is not None:
        body["retry_after_s"] = error.retry_after_seconds
    return {"error": body}


def error_response(error: AppError, request_id: str | None) -> JSONResponse:
    """Build a JSON error response with the standard envelope."""
    headers: dict[str, str] = {}
    if error.retry_after_seconds is not None:
        headers["Retry-After"] = str(error.retry_after_seconds)
    return JSONResponse(
        status_code=error.status_code,
        content=error_payload(error, request_id),
        headers=headers or None,
    )


def _validation_details(exc: RequestValidationError) -> dict[str, Any]:
    """Keep only JSON-serializable validation error fields."""
    errors = [
        {"loc": list(item.get("loc", ())), "msg": item.get("msg"), "type": item.get("type")}
        for item in exc.errors()
    ]
    fields: dict[str, str] = {}
    for item in errors:
        loc = item.get("loc") or []
        if loc:
            field = str(loc[-1])
            fields.setdefault(field, str(item.get("msg") or "Valore non valido."))
    return {"errors": errors, "fields": fields}


def register_exception_handlers(app: FastAPI) -> None:
    """Register the handlers that produce the error envelope."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = request_id_from_request(request)
        if exc.status_code >= 500:
            logger.error(
                "app_error",
                code=exc.code,
                category=exc.category,
                status_code=exc.status_code,
                request_id=request_id,
            )
        else:
            logger.info(
                "app_error",
                code=exc.code,
                category=exc.category,
                status_code=exc.status_code,
                request_id=request_id,
            )
        return error_response(exc, request_id)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        error = ValidationError(details=_validation_details(exc))
        return error_response(error, request_id_from_request(request))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        category = VALIDATION if exc.status_code < 500 else INTERNAL
        error = AppError(
            str(exc.detail),
            code="HTTP_ERROR",
            category=category,
            status_code=exc.status_code,
        )
        return error_response(error, request_id_from_request(request))

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_from_request(request)
        logger.exception("unhandled_exception", request_id=request_id, error=str(exc))
        return error_response(AppError(), request_id)
