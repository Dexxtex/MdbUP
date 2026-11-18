"""Backup verification: checksum, age header, PGDMP magic and status file."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.services import backup
from app.services.system_status import read_backup_status

ARCHIVE_NAME = "mdbup-20261118T100000Z.dump.age"
AGE_PAYLOAD = b"age-encryption.org/v1\n-> X25519 abc\n" + b"\x00" * 32


def _write_archive(
    directory: Path,
    *,
    content: bytes = AGE_PAYLOAD,
    checksum: str | None = None,
    name: str = ARCHIVE_NAME,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / name
    archive.write_bytes(content)
    digest = checksum if checksum is not None else hashlib.sha256(content).hexdigest()
    if digest != "missing":
        (directory / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")
    return archive


def _verify(directory: Path, status_file: Path, **kwargs):
    return backup.verify_latest_backup(backup_dir=directory, status_file=status_file, **kwargs)


def test_valid_archive_is_ok_and_writes_the_status_file(tmp_path) -> None:
    _write_archive(tmp_path)
    status_file = tmp_path / "last_backup.json"

    result = _verify(tmp_path, status_file)

    assert result.status == "OK"
    assert result.ok is True
    assert result.file == ARCHIVE_NAME
    assert result.size_bytes == len(AGE_PAYLOAD)
    assert result.sha256 == hashlib.sha256(AGE_PAYLOAD).hexdigest()
    assert result.decrypted is False
    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["status"] == "OK"
    assert payload["file"] == ARCHIVE_NAME
    assert payload["sha256"] == result.sha256
    assert payload["timestamp"].endswith("Z")


def test_checksum_mismatch_is_reported(tmp_path) -> None:
    _write_archive(tmp_path, checksum="0" * 64)
    status_file = tmp_path / "last_backup.json"

    result = _verify(tmp_path, status_file)

    assert result.status == "CHECKSUM_MISMATCH"
    assert result.ok is False
    assert json.loads(status_file.read_text(encoding="utf-8"))["status"] == "CHECKSUM_MISMATCH"


def test_missing_checksum_file_is_reported(tmp_path) -> None:
    _write_archive(tmp_path, checksum="missing")
    result = _verify(tmp_path, tmp_path / "last_backup.json")
    assert result.status == "CHECKSUM_MISSING"


def test_empty_archive_is_reported(tmp_path) -> None:
    _write_archive(tmp_path, content=b"")
    result = _verify(tmp_path, tmp_path / "last_backup.json")
    assert result.status == "EMPTY"


def test_archive_without_age_header_is_reported(tmp_path) -> None:
    _write_archive(tmp_path, content=b"PGDMP not encrypted")
    result = _verify(tmp_path, tmp_path / "last_backup.json")
    assert result.status == "INVALID_HEADER"


def test_missing_directory_reports_missing(tmp_path) -> None:
    status_file = tmp_path / "last_backup.json"
    result = _verify(tmp_path / "absent", status_file)
    assert result.status == "MISSING"
    assert json.loads(status_file.read_text(encoding="utf-8"))["file"] is None


def test_newest_archive_is_selected(tmp_path) -> None:
    _write_archive(tmp_path, name="mdbup-20260101T000000Z.dump.age")
    newest = _write_archive(tmp_path, name="mdbup-20261118T100000Z.dump.age")
    result = _verify(tmp_path, tmp_path / "last_backup.json")
    assert result.file == newest.name


def test_age_decryption_failure_is_reported(tmp_path) -> None:
    archive = _write_archive(tmp_path)
    identity = tmp_path / "identity.txt"
    identity.write_text("AGE-SECRET-KEY-1\n", encoding="utf-8")

    # ``sys.executable`` is not age: the command exits non-zero.
    result = _verify(
        tmp_path,
        tmp_path / "last_backup.json",
        age_identity_file=identity,
        age_binary=sys.executable,
    )

    assert result.status == "DECRYPT_FAILED"
    assert result.decrypted is False
    assert archive.exists()


def test_pgdmp_magic_detection(tmp_path) -> None:
    dump = tmp_path / "plain.dump"
    dump.write_bytes(b"PGDMP\x01\x0e\x00")
    assert backup.has_pgdmp_magic(dump) is True
    dump.write_bytes(b"NOTADUMP")
    assert backup.has_pgdmp_magic(dump) is False


def test_read_backup_status_exposes_the_last_valid_timestamp(tmp_path) -> None:
    status_file = tmp_path / "last_backup.json"
    status_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-11-18T10:00:00Z",
                "file": ARCHIVE_NAME,
                "size": 42,
                "sha256": "a" * 64,
                "status": "OK",
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        app_env="test",
        backup_dir=str(tmp_path),
        backup_status_file=str(status_file),
    )

    status = read_backup_status(settings)

    assert status.status == "OK"
    assert status.last_valid_at is not None
    assert status.last_valid_at.isoformat() == "2026-11-18T10:00:00+00:00"
    assert status.file == ARCHIVE_NAME


def test_read_backup_status_ignores_a_failed_backup(tmp_path) -> None:
    status_file = tmp_path / "last_backup.json"
    status_file.write_text(
        json.dumps({"timestamp": "2026-11-18T10:00:00Z", "status": "FAILED"}),
        encoding="utf-8",
    )
    settings = Settings(
        app_env="test",
        backup_dir=str(tmp_path),
        backup_status_file=str(status_file),
    )

    status = read_backup_status(settings)

    assert status.status == "FAILED"
    assert status.last_valid_at is None


def test_status_file_defaults_to_backup_dir() -> None:
    settings = Settings(app_env="test", backup_dir="/backups", backup_status_file="")
    assert settings.effective_backup_status_file.replace("\\", "/") == "/backups/last_backup.json"
