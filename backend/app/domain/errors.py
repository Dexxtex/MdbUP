"""Domain/application errors.

These exceptions belong to the application core, not to the HTTP layer. The
FastAPI adapters in :mod:`app.api.errors` translate them into the public error
envelope and re-export the classes for backward compatibility.
"""

from __future__ import annotations

from typing import Any

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
