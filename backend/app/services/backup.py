"""Backup verification: checksum, age header and (optionally) the dump magic.

``BACKUP_STATUS_FILE`` is the single source of truth for ``/api/metrics`` and
``/api/system/status``: ``deploy/scripts/backup.sh`` writes it after a successful
backup, ``backup-verify`` refreshes it after a deeper check. Only the standard
library and an optional ``age`` binary are used; the identity file is never
logged and the decrypted dump lives in a temporary file that is always removed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.core.time import isoformat_utc, utcnow

logger = get_logger(__name__)

ARCHIVE_GLOB = "mdbup-*.dump.age"
AGE_HEADER = b"age-encryption.org/v1"
PGDMP_MAGIC = b"PGDMP"
DECRYPT_TIMEOUT_SECONDS = 300

STATUS_OK = "OK"
STATUS_MISSING = "MISSING"
STATUS_EMPTY = "EMPTY"
STATUS_CHECKSUM_MISSING = "CHECKSUM_MISSING"
STATUS_CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
STATUS_INVALID_HEADER = "INVALID_HEADER"
STATUS_DECRYPT_FAILED = "DECRYPT_FAILED"
STATUS_PGDMP_INVALID = "PGDMP_INVALID"


@dataclass(frozen=True)
class BackupVerification:
    """Outcome of one verification run, serialized into the status file."""

    file: str | None
    status: str
    size_bytes: int = 0
    sha256: str | None = None
    error: str | None = None
    decrypted: bool = False
    age_available: bool = False
    verified_at: datetime = field(default_factory=utcnow)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def as_status_payload(self) -> dict[str, object]:
        return {
            "timestamp": isoformat_utc(self.verified_at),
            "file": self.file,
            "size": self.size_bytes,
            "sha256": self.sha256,
            "status": self.status,
            "error": self.error,
            "decrypted": self.decrypted,
            "age_available": self.age_available,
        }


def latest_archive(backup_dir: Path) -> Path | None:
    """Newest ``mdbup-*.dump.age`` by name (the stamp sorts lexicographically)."""
    if not backup_dir.is_dir():
        return None
    archives = sorted(backup_dir.glob(ARCHIVE_GLOB), key=lambda path: path.name)
    return archives[-1] if archives else None


def sha256_of(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_checksum(archive: Path) -> str | None:
    """Read the digest from ``<archive>.sha256`` (``sha256sum`` output format)."""
    checksum_file = archive.with_name(f"{archive.name}.sha256")
    if not checksum_file.is_file():
        return None
    try:
        content = checksum_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    token = content.split()[0] if content else ""
    return token.lower() or None


def has_age_header(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(AGE_HEADER)) == AGE_HEADER
    except OSError:
        return False


def has_pgdmp_magic(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(PGDMP_MAGIC)) == PGDMP_MAGIC
    except OSError:
        return False


def _decrypt_and_check(
    archive: Path, identity_file: Path, age_binary: str
) -> tuple[str, str | None]:
    """Decrypt to a temporary file and check the ``pg_dump`` magic.

    Returns ``(status, error)``; the temporary plaintext is always removed.
    """
    descriptor, name = tempfile.mkstemp(prefix="mdbup-verify-", suffix=".dump")
    os.close(descriptor)
    temporary = Path(name)
    try:
        completed = subprocess.run(
            [
                age_binary,
                "--decrypt",
                "--identity",
                str(identity_file),
                "--output",
                str(temporary),
                str(archive),
            ],
            capture_output=True,
            timeout=DECRYPT_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0:
            return STATUS_DECRYPT_FAILED, f"age --decrypt ha restituito {completed.returncode}"
        if not has_pgdmp_magic(temporary):
            return STATUS_PGDMP_INVALID, "il dump decifrato non ha il magic PGDMP"
        return STATUS_OK, None
    except (OSError, subprocess.SubprocessError) as exc:
        return STATUS_DECRYPT_FAILED, f"age non eseguibile ({type(exc).__name__})"
    finally:
        temporary.unlink(missing_ok=True)


def verify_latest_backup(
    *,
    backup_dir: Path,
    status_file: Path | None = None,
    age_identity_file: Path | None = None,
    age_binary: str | None = None,
    now: datetime | None = None,
) -> BackupVerification:
    """Verify the newest encrypted dump and refresh the status file."""
    archive = latest_archive(backup_dir)
    if archive is None:
        verification = BackupVerification(
            file=None,
            status=STATUS_MISSING,
            error=f"nessun archivio {ARCHIVE_GLOB} in {backup_dir}",
            age_available=age_binary is not None,
            verified_at=now or utcnow(),
        )
        _write_status(status_file, verification)
        return verification

    if age_identity_file is not None and not age_identity_file.is_file():
        # The api/worker mount has no private key; the host script does the
        # deeper check. Do not turn a missing identity into a failed backup.
        logger.info("backup_verify_identity_missing", path=str(age_identity_file))
        age_identity_file = None
    size = archive.stat().st_size
    digest = sha256_of(archive)
    verification = _verify_archive(
        archive,
        size=size,
        digest=digest,
        age_identity_file=age_identity_file,
        age_binary=age_binary,
        now=now,
    )
    _write_status(status_file, verification)
    logger.info(
        "backup_verify",
        file=verification.file,
        status=verification.status,
        decrypted=verification.decrypted,
    )
    return verification


def _verify_archive(
    archive: Path,
    *,
    size: int,
    digest: str,
    age_identity_file: Path | None,
    age_binary: str | None,
    now: datetime | None,
) -> BackupVerification:
    common: dict[str, Any] = {
        "file": archive.name,
        "size_bytes": size,
        "sha256": digest,
        "age_available": age_binary is not None,
        "verified_at": now or utcnow(),
    }
    if size == 0:
        return BackupVerification(status=STATUS_EMPTY, error="archivio vuoto", **common)
    expected = read_checksum(archive)
    if expected is None:
        return BackupVerification(
            status=STATUS_CHECKSUM_MISSING,
            error=f"file {archive.name}.sha256 assente",
            **common,
        )
    if expected != digest:
        return BackupVerification(
            status=STATUS_CHECKSUM_MISMATCH,
            error="sha256 dell'archivio diverso dal file .sha256",
            **common,
        )
    if not has_age_header(archive):
        return BackupVerification(
            status=STATUS_INVALID_HEADER,
            error="header age assente o non valido",
            **common,
        )
    if age_identity_file is None or age_binary is None:
        # Decryption needs both the private key and the age binary: skip it and
        # keep the checksum/header verdict.
        return BackupVerification(status=STATUS_OK, **common)
    status, error = _decrypt_and_check(archive, age_identity_file, age_binary)
    if status != STATUS_OK:
        return BackupVerification(status=status, error=error, **common)
    return BackupVerification(status=STATUS_OK, decrypted=True, **common)


def _write_status(status_file: Path | None, verification: BackupVerification) -> None:
    """Write the status file atomically; a read-only mount is not a failure."""
    if status_file is None:
        return
    if not os.access(status_file.parent, os.W_OK):
        logger.info("backup_status_read_only", path=str(status_file))
        return
    payload = json.dumps(verification.as_status_payload(), ensure_ascii=False) + "\n"
    temporary = status_file.with_name(f"{status_file.name}.tmp")
    try:
        status_file.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, status_file)
    except OSError as exc:
        # The api/worker mount /backups read-only: verification still succeeds,
        # only the status refresh is skipped. The host script updates it.
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        logger.warning(
            "backup_status_write_failed",
            path=str(status_file),
            error=type(exc).__name__,
        )
