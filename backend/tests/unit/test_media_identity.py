"""Movie/show identity separation and planner keys."""

from __future__ import annotations

import uuid

from app.repositories import media as media_repo
from app.services.planning import SourceItem, source_key


def test_same_tmdb_id_is_a_different_media_for_movie_and_show(db) -> None:
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        movie = media_repo.resolve_media(
            session,
            media_type="MOVIE",
            tmdb_id=603,
            imdb_id=None,
            title="Matrix",
            year=1999,
        )
        show = media_repo.resolve_media(
            session,
            media_type="SHOW",
            tmdb_id=603,
            imdb_id=None,
            title="Matrix (show)",
            year=1999,
        )
        assert movie is not None and show is not None
        assert movie.id != show.id
        assert movie.media_type == "MOVIE"
        assert show.media_type == "SHOW"
        assert (
            media_repo.resolve_media(
                session,
                media_type="MOVIE",
                tmdb_id=603,
                imdb_id=None,
                title="Matrix",
                year=1999,
            ).id
            == movie.id
        )
    finally:
        session.close()


def test_planner_keys_include_media_type() -> None:
    movie_key = source_key(
        SourceItem(
            media_type="MOVIE",
            tmdb_id=603,
            imdb_id=None,
            media_id=uuid.uuid4(),
        )
    )
    show_key = source_key(
        SourceItem(
            media_type="SHOW",
            tmdb_id=603,
            imdb_id=None,
            media_id=uuid.uuid4(),
        )
    )
    assert movie_key is not None and show_key is not None
    assert movie_key != show_key
    assert movie_key.label() == "MOVIE:tmdb:603"
    assert show_key.label() == "SHOW:tmdb:603"
