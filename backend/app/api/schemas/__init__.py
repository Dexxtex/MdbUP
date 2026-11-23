"""Schemi request/response dell'API: un pacchetto, un modulo per dominio.

I router importano la superficie pubblica da qui (``from app.api import schemas``)
oppure il sottodominio direttamente quando serve limitare le dipendenze
(``from app.api.schemas.catalog import ...``). I nomi delle classi Pydantic non
cambiano: il contratto OpenAPI resta identico.
"""

from __future__ import annotations

from app.api.schemas.auth import (
    BootstrapOut,
    BootstrapRequest,
    ChangePasswordRequest,
    LoginRequest,
    SessionOut,
    UserOut,
)
from app.api.schemas.credentials import (
    CredentialListOut,
    CredentialOut,
    CredentialSecretIn,
    CredentialVerifyOut,
)
from app.api.schemas.errors import ErrorBody, ErrorEnvelope
from app.api.schemas.settings import SettingItemOut, SettingsOut, SettingsPatchRequest
from app.api.schemas.system import (
    BackupStatusOut,
    CatalogAcquisitionOut,
    HealthOut,
    ReadinessOut,
    StorageStatusOut,
    SystemHealthOut,
    SystemStatusOut,
    UpcomingRunOut,
)

__all__ = [
    "BackupStatusOut",
    "BootstrapOut",
    "BootstrapRequest",
    "CatalogAcquisitionOut",
    "ChangePasswordRequest",
    "CredentialListOut",
    "CredentialOut",
    "CredentialSecretIn",
    "CredentialVerifyOut",
    "ErrorBody",
    "ErrorEnvelope",
    "HealthOut",
    "LoginRequest",
    "ReadinessOut",
    "SessionOut",
    "SettingItemOut",
    "SettingsOut",
    "SettingsPatchRequest",
    "StorageStatusOut",
    "SystemHealthOut",
    "SystemStatusOut",
    "UpcomingRunOut",
    "UserOut",
]
