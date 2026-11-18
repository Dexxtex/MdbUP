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

logger = get_logger(__name__)

AUTH = "AUTH"
VALIDATION = "VALIDATION"
SOURCE = "SOURCE"
TARGET = "TARGET"
POLICY = "POLICY"
CONFLICT = "CONFLICT"
INTERNAL = "INTERNAL"


class AppError(Exception):
    """Base class for errors that map onto the API error envelope."""

    status_code: int = 500
    category: str = INTERNAL
    code: str = "INTERNAL_ERROR"
    default_message: str = "Errore interno."
    retryable: bool = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        category: str | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.code
        self.category = category or self.category
        self.details = details or {}
        self.retryable = self.retryable if retryable is None else retryable
        self.status_code = status_code or self.status_code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(self.message)


class ValidationError(AppError):
    status_code = 422
    category = VALIDATION
    code = "VALIDATION_ERROR"
    default_message = "Dati non validi."


class AuthError(AppError):
    status_code = 401
    category = AUTH
    code = "AUTH_UNAUTHENTICATED"
    default_message = "Autenticazione richiesta."


class ForbiddenError(AppError):
    status_code = 403
    category = AUTH
    code = "AUTH_FORBIDDEN"
    default_message = "Permessi insufficienti per questa operazione."


class InvalidCredentialsError(AppError):
    status_code = 401
    category = AUTH
    code = "AUTH_INVALID_CREDENTIALS"
    default_message = "Credenziali non valide."


class InvalidBootstrapTokenError(AppError):
    status_code = 400
    category = AUTH
    code = "AUTH_INVALID_BOOTSTRAP_TOKEN"
    default_message = "Token di bootstrap non valido."


class BootstrapDisabledError(AppError):
    status_code = 503
    category = AUTH
    code = "AUTH_BOOTSTRAP_DISABLED"
    default_message = "Bootstrap disabilitato: BOOTSTRAP_TOKEN non configurato."


class AlreadyBootstrappedError(AppError):
    status_code = 409
    category = AUTH
    code = "AUTH_ALREADY_BOOTSTRAPPED"
    default_message = "Esiste già un utente: il bootstrap è chiuso."


class RateLimitedError(AppError):
    status_code = 429
    category = AUTH
    code = "AUTH_RATE_LIMITED"
    default_message = "Troppi tentativi. Riprova più tardi."
    retryable = True


class CsrfError(AppError):
    status_code = 403
    category = AUTH
    code = "AUTH_CSRF_INVALID"
    default_message = "Token CSRF mancante o non valido."


class OriginRejectedError(AppError):
    status_code = 403
    category = AUTH
    code = "AUTH_ORIGIN_REJECTED"
    default_message = "Origine della richiesta non consentita."


class NotFoundError(AppError):
    status_code = 404
    category = VALIDATION
    code = "RESOURCE_NOT_FOUND"
    default_message = "Risorsa non trovata."


class ConflictError(AppError):
    status_code = 409
    category = CONFLICT
    code = "CONFLICT"
    default_message = "Operazione in conflitto con lo stato attuale."


class CredentialMissingError(AppError):
    status_code = 409
    category = CONFLICT
    code = "CREDENTIAL_MISSING"
    default_message = "Credenziale non configurata."


class SourceUnavailableError(AppError):
    status_code = 409
    category = CONFLICT
    code = "SOURCE_NOT_AVAILABLE"
    default_message = "Fonte non disponibile."


class EncryptionKeyMissingError(AppError):
    status_code = 503
    category = INTERNAL
    code = "ENCRYPTION_KEY_MISSING"
    default_message = "APP_ENCRYPTION_KEY non configurata: impossibile cifrare le credenziali."


class ServiceUnavailableError(AppError):
    status_code = 503
    category = INTERNAL
    code = "SERVICE_UNAVAILABLE"
    default_message = "Servizio temporaneamente non disponibile."
    retryable = True


class FeatureNotImplementedError(AppError):
    status_code = 501
    category = INTERNAL
    code = "NOT_IMPLEMENTED"
    default_message = "Funzionalità non ancora implementata."

    def __init__(self, feature: str) -> None:
        super().__init__(
            f"Funzionalità '{feature}' non ancora implementata in questa fase.",
            details={"feature": feature},
        )


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
