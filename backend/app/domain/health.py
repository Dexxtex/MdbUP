"""Esito di una sonda di salute, condiviso da integrazioni, connettori e servizi.

Vive nel dominio perché non è né trasporto (HTTP) né orchestrazione: è il valore
che client HTTP e connettori si scambiano, e che i servizi registrano.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthStatus:
    ok: bool
    message: str = ""
    latency_ms: int | None = None
