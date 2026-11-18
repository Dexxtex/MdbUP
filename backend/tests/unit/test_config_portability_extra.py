"""Configuration portability error branches and cross-reference import."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.domain.errors import ValidationError
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import targets as targets_repo
from app.services import config_portability


@pytest.fixture()
def session(db) -> Session:
    db_session = get_session_factory()()
    try:
        yield db_session
    finally:
        db_session.close()


def _base_payload() -> dict:
    return {
        "version": 1,
        "providers": [],
        "targets": [],
        "collections": [],
        "bindings": [],
        "settings": {},
    }


def test_import_rejects_malformed_sections(session: Session, seeded, app_settings) -> None:
    with pytest.raises(ValidationError) as error:
        config_portability.import_config(session, app_settings, {"version": 1, "providers": "bad"})
    assert error.value.code == "CONFIG_INVALID"
    with pytest.raises(ValidationError):
        config_portability.import_config(
            session, app_settings, {**_base_payload(), "settings": "bad"}
        )


def test_import_provider_validation_and_unknown_mapping(
    session: Session, seeded, app_settings
) -> None:
    with pytest.raises(ValidationError):
        config_portability.import_config(
            session, app_settings, {**_base_payload(), "providers": [{"slug": "", "name": "X"}]}
        )
    payload = {
        **_base_payload(),
        "providers": [
            {
                "slug": "new-provider",
                "name": "New Provider",
                "mappings": [
                    {"source_key": "missing-source", "external_provider_id": "1"},
                ],
            }
        ],
    }
    result = config_portability.import_config(session, app_settings, payload)
    assert result["providers"] == 1


def test_import_target_collection_binding_and_filters(
    session: Session, seeded, app_settings
) -> None:
    source = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert source is not None
    payload = {
        **_base_payload(),
        "targets": [{"remote_list_id": 987654, "name": "Imported", "mediatype": "MOVIE"}],
        "collections": [
            {
                "slug": "imported-collection",
                "provider_slug": "netflix",
                "source_key": "tmdb",
                "name": "Imported",
                "filters": {
                    "source_collection_slug": "netflix-movie",
                    "shared_snapshot_collection_slug": "netflix-movie",
                    "source_collection_slugs": ["netflix-movie"],
                    "provider_slugs": ["netflix"],
                },
            }
        ],
        "bindings": [
            {
                "collection_slug": "imported-collection",
                "target_remote_list_id": 987654,
                "is_enabled": True,
                "schedule_interval_hours": 2,
            }
        ],
        "settings": {"catalog_schedule_enabled": False, "unknown": "ignored"},
    }
    result = config_portability.import_config(session, app_settings, payload)
    assert result["targets"] == 1
    assert result["collections"] == 1
    assert result["bindings"] == 1
    assert result["settings"] == 1
    collection = collections_repo.get_collection_by_slug(session, "imported-collection")
    assert collection is not None
    assert collection.filters["source_collection_id"] == str(source.id)
    target = targets_repo.get_by_remote_list_id(session, 987654)
    assert target is not None
    binding = bindings_repo.get_by_collection_target(
        session, collection_id=collection.id, target_id=target.id
    )
    assert binding is not None
    assert binding.is_enabled is True
    assert binding.schedule_interval_hours == 2
    assert binding.next_run_at is not None


def test_import_rejects_unresolved_rows(session: Session, seeded, app_settings) -> None:
    with pytest.raises(ValidationError):
        config_portability.import_config(
            session, app_settings, {**_base_payload(), "targets": [{"name": "bad"}]}
        )
    with pytest.raises(ValidationError):
        config_portability.import_config(
            session,
            app_settings,
            {**_base_payload(), "collections": [{"slug": "x", "provider_slug": "netflix"}]},
        )
    with pytest.raises(ValidationError):
        config_portability.import_config(
            session,
            app_settings,
            {
                **_base_payload(),
                "collections": [{"slug": "x", "provider_slug": "missing", "source_key": "tmdb"}],
            },
        )
    with pytest.raises(ValidationError):
        config_portability.import_config(
            session,
            app_settings,
            {**_base_payload(), "bindings": [{"collection_slug": "x", "target_remote_list_id": 1}]},
        )
    with pytest.raises(ValidationError):
        config_portability.import_config(
            session,
            app_settings,
            {**_base_payload(), "settings": {"default_source": "not-a-source"}},
        )


def test_export_with_notification_channel_is_secret_free(
    session: Session, seeded, app_settings
) -> None:
    from app.db.models import NotificationChannel

    channel = NotificationChannel(
        kind="WEBHOOK",
        name="Imported webhook",
        config={"url": "https://example.test/hook"},
        events=["RUN_FAILED"],
        secret_ciphertext=b"ciphertext",
        secret_nonce=b"nonce",
        secret_key_version=1,
    )
    session.add(channel)
    session.commit()
    exported = config_portability.export_config(session, app_settings)
    assert exported["notification_channels"]
    assert "ciphertext" not in str(exported)
