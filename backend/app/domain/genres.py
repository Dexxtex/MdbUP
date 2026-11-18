"""Official TMDb genre ids (stable across releases)."""

from __future__ import annotations

from app.domain.enums import MediaType

TMDB_GENRES: dict[str, tuple[tuple[int, str], ...]] = {
    MediaType.MOVIE.value: (
        (28, "Azione"),
        (12, "Avventura"),
        (16, "Animazione"),
        (35, "Commedia"),
        (80, "Crime"),
        (99, "Documentario"),
        (18, "Dramma"),
        (10751, "Famiglia"),
        (14, "Fantasy"),
        (36, "Storia"),
        (27, "Horror"),
        (10402, "Musica"),
        (9648, "Mistero"),
        (10749, "Romantico"),
        (878, "Fantascienza"),
        (10770, "Film TV"),
        (53, "Thriller"),
        (10752, "Guerra"),
        (37, "Western"),
    ),
    MediaType.SHOW.value: (
        (10759, "Azione e avventura"),
        (16, "Animazione"),
        (35, "Commedia"),
        (80, "Crime"),
        (99, "Documentario"),
        (18, "Dramma"),
        (10751, "Famiglia"),
        (10762, "Bambini"),
        (9648, "Mistero"),
        (10763, "News"),
        (10764, "Reality"),
        (10765, "Sci-Fi e Fantasy"),
        (10766, "Soap"),
        (10767, "Talk"),
        (10768, "Guerra e politica"),
        (37, "Western"),
    ),
}


def genres_for(media_type: str) -> tuple[tuple[int, str], ...]:
    return TMDB_GENRES.get(media_type, ())
