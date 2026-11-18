"""Target use-case branches: remote failure, duplicates and visibility."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.domain.commands import TargetCreateIn
from app.domain.errors import ConflictError, NotFoundError, ValidationError
from app.integrations.mdblist.client import MdbListError
from app.integrations.mdblist.models import MdbListList
from app.repositories import targets as targets_repo
from app.services import targets


@pytest.fixture()
def session(db) -> Session:
    db_session = get_session_factory()()
    try:
        yield db_session
    finally:
        db_session.close()


class FakeClient:
    def __init__(self, *, fail=False, mediatype="MOVIE", duplicate=False):
        self.fail = fail
        self.mediatype = mediatype
        self.duplicate = duplicate
        self.closed = False

    def create_list(self, name, private=False):
        if self.fail:
            raise MdbListError("no")
        return MdbListList(
            id=8801 if not self.duplicate else 8802,
            name=name,
            mediatype=self.mediatype,
            user_id=1,
            private=private,
            slug="fake-list",
            item_count=0,
        )

    def get_list(self, list_id):
        if self.fail:
            raise MdbListError("no")
        return MdbListList(
            id=list_id,
            name="Remote",
            mediatype=self.mediatype,
            user_id=1,
            private=True,
            slug="remote",
            item_count=3,
        )

    def update_list(self, list_id, *, private=True):
        if self.fail:
            raise MdbListError("no")
        return MdbListList(
            id=list_id,
            name="Remote",
            mediatype=self.mediatype,
            user_id=1,
            private=private,
            slug="remote",
            item_count=3,
        )

    def close(self):
        self.closed = True


def test_target_validation_and_remote_errors(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    with pytest.raises(NotFoundError):
        targets.get_target(session, uuid.uuid4())
    monkeypatch.setattr(targets.sync_service, "build_client", lambda *a, **k: FakeClient(fail=True))
    with pytest.raises(ConflictError):
        targets.create_target(session, app_settings, TargetCreateIn(media_type="MOVIE", name="xyz"))
    with pytest.raises(NotFoundError):
        targets.update_target_visibility(session, app_settings, uuid.uuid4(), private=True)


def test_target_create_duplicate_and_media_mismatch(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    monkeypatch.setattr(
        targets.sync_service, "build_client", lambda *a, **k: FakeClient(mediatype="SHOW")
    )
    with pytest.raises(ValidationError):
        targets.create_target(session, app_settings, TargetCreateIn(media_type="MOVIE", name="xyz"))
    monkeypatch.setattr(targets.sync_service, "build_client", lambda *a, **k: FakeClient())
    view = targets.create_target(
        session, app_settings, TargetCreateIn(media_type="MOVIE", name="New list")
    )
    assert view.remote_list_id == "8801"
    with pytest.raises(ConflictError) as error:
        targets.create_target(
            session, app_settings, TargetCreateIn(media_type="MOVIE", name="Again list")
        )
    assert error.value.code == "TARGET_ALREADY_LINKED"


def test_update_visibility_success_and_not_found(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    with pytest.raises(NotFoundError):
        targets.update_target_visibility(session, app_settings, uuid.uuid4(), private=True)
    monkeypatch.setattr(targets.sync_service, "build_client", lambda *a, **k: FakeClient())
    target = targets_repo.create_target(
        session, remote_list_id=8803, name="Visibility", mediatype="MOVIE"
    )
    session.commit()
    view = targets.update_target_visibility(session, app_settings, target.id, private=False)
    assert view.private is False
