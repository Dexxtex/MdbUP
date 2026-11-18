"""Media identity, deduplication and snapshot checksum."""

from __future__ import annotations

from app.connectors.base import NormalizedItem
from app.domain.enums import DateBasis, MediaType, ResolutionStatus
from app.services import normalization


def _item(
    media_type: MediaType,
    tmdb_id: int | None,
    imdb_id: str | None = None,
    title: str = "Titolo",
) -> NormalizedItem:
    return NormalizedItem(
        media_type=media_type,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        title=title,
        year=2020,
        offer_types=frozenset({"FLATRATE"}),
        source_date_created=None,
        date_basis=DateBasis.UNKNOWN,
        raw={},
    )


def test_media_key_prefers_tmdb_then_imdb() -> None:
    assert normalization.media_key(MediaType.MOVIE, 603, "tt0133093") == "MOVIE:tmdb:603"
    assert normalization.media_key(MediaType.SHOW, None, "tt0903747") == "SHOW:imdb:tt0903747"
    assert normalization.media_key(MediaType.MOVIE, None, None) is None


def test_resolution_status_without_external_id_is_unresolved() -> None:
    assert normalization.resolution_status(_item(MediaType.MOVIE, 603)) is ResolutionStatus.RESOLVED
    assert (
        normalization.resolution_status(_item(MediaType.MOVIE, None, "tt0133093"))
        is ResolutionStatus.RESOLVED
    )
    assert (
        normalization.resolution_status(_item(MediaType.MOVIE, None)) is ResolutionStatus.UNRESOLVED
    )


def test_deduplicate_keeps_movie_and_show_with_same_numeric_id() -> None:
    movie = _item(MediaType.MOVIE, 1399, title="Film")
    show = _item(MediaType.SHOW, 1399, title="Serie")
    result = normalization.deduplicate([movie, show])
    assert result.duplicates == 0
    assert [item.media_type for item in result.items] == [MediaType.MOVIE, MediaType.SHOW]


def test_deduplicate_drops_repeated_identity_and_keeps_first() -> None:
    first = _item(MediaType.MOVIE, 603, title="Primo")
    second = _item(MediaType.MOVIE, 603, title="Secondo")
    result = normalization.deduplicate([first, second])
    assert result.duplicates == 1
    assert len(result.items) == 1
    assert result.items[0].title == "Primo"


def test_deduplicate_keeps_unresolved_items() -> None:
    unresolved_a = _item(MediaType.MOVIE, None, title="Senza ID A")
    unresolved_b = _item(MediaType.MOVIE, None, title="Senza ID B")
    result = normalization.deduplicate([unresolved_a, unresolved_b])
    assert result.duplicates == 0
    assert len(result.items) == 2


def test_checksum_is_order_independent_and_stable() -> None:
    items = [_item(MediaType.MOVIE, 1), _item(MediaType.SHOW, 2)]
    assert normalization.checksum(items) == normalization.checksum(reversed(items))
    assert normalization.checksum(items) != normalization.checksum(items[:1])
    assert len(normalization.checksum(items)) == 64
