"""Small repository branches not exercised through the API."""

from __future__ import annotations

from app.db.session import get_session_factory
from app.repositories import media as media_repo
from app.repositories import targets as targets_repo
from app.repositories import users as users_repo


def test_target_upsert_metadata_and_remote_read(db, seeded) -> None:
    session = get_session_factory()()
    try:
        target = targets_repo.upsert_target(
            session, remote_list_id=991, name="Original", mediatype="MOVIE"
        )
        same = targets_repo.upsert_target(
            session,
            remote_list_id=991,
            name="Updated",
            mediatype="MOVIE",
            remote_url="https://example.test",
            is_private=True,
            item_count=2,
        )
        assert same.id == target.id
        assert same.name == "Updated" and same.is_private is True
        targets_repo.update_remote_metadata(
            session,
            same,
            name="Meta",
            remote_slug="slug",
            remote_url=None,
            is_private=False,
            item_count=4,
            capabilities={"x": True},
            verified=True,
        )
        assert same.remote_slug == "slug"
        assert same.capabilities == {"x": True}
        assert same.last_verified_at is not None
        targets_repo.mark_remote_read(session, same, item_count=5)
        assert same.last_remote_read_at is not None and same.item_count == 5
        targets_repo.set_verified_at(session, same)
        assert same.last_verified_at is not None
    finally:
        session.close()


def test_user_session_helpers(db) -> None:
    session = get_session_factory()()
    try:
        user = users_repo.create_user(session, email="Repo@Test.Example", password_hash="old")
        users_repo.record_login(session, user)
        users_repo.update_password_hash(session, user, "new")
        assert user.last_login_at is not None and user.password_hash == "new"
        from datetime import timedelta

        from app.core.time import utcnow

        db_session = users_repo.create_session(
            session,
            user_id=user.id,
            token_hash=b"t",
            csrf_hash=b"c",
            expires_at=utcnow() + timedelta(hours=1),
            ip="127.0.0.1",
            user_agent="agent" * 200,
        )
        assert db_session.user_agent is not None and len(db_session.user_agent) <= 512
        users_repo.touch_session(session, db_session)
        users_repo.update_csrf_hash(session, db_session, b"new")
        users_repo.revoke_session(session, db_session)
        assert db_session.revoked_at is not None
        assert users_repo.revoke_all_sessions(session, user.id) >= 0
    finally:
        session.close()


def test_media_resolve_updates_existing_ids(db, seeded) -> None:
    session = get_session_factory()()
    try:
        media = media_repo.resolve_media(
            session,
            media_type="MOVIE",
            tmdb_id=None,
            imdb_id="tt9931",
            title="",
            year=None,
        )
        assert media is not None
        updated = media_repo.resolve_media(
            session,
            media_type="MOVIE",
            tmdb_id=9931,
            imdb_id="tt9931",
            title="Title",
            year=2024,
        )
        assert updated is not None and updated.id == media.id
        assert updated.tmdb_id == 9931
        assert updated.release_year == 2024
        assert (
            media_repo.resolve_media(
                session, media_type="MOVIE", tmdb_id=None, imdb_id=None, title="x", year=None
            )
            is None
        )
    finally:
        session.close()
