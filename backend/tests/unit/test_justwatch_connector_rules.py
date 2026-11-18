"""JustWatch connector rules: flatrate default, package/media post-filter, labels."""

from __future__ import annotations

from app.connectors.base import HealthStatus, SourceCollection
from app.connectors.justwatch.connector import JustWatchConnector
from app.domain.enums import (
    AvailabilityStatus,
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
)
from app.integrations.justwatch.models import (
    JustWatchChartEntry,
    JustWatchOffer,
    JustWatchPage,
    JustWatchTitle,
)


def _offer(package: str = "nfx", monetization: str = "FLATRATE") -> JustWatchOffer:
    return JustWatchOffer(monetization_type=monetization, package_short_name=package)


def _title(
    node_id: str,
    *,
    media_type: MediaType = MediaType.MOVIE,
    offers: tuple[JustWatchOffer, ...] = (),
    tmdb_id: int | None = 603,
) -> JustWatchTitle:
    return JustWatchTitle(
        node_id=node_id,
        media_type=media_type,
        title=f"Title {node_id}",
        year=2020,
        tmdb_id=tmdb_id,
        imdb_id=None,
        offers=offers,
        raw={"id": node_id},
    )


class StubClient:
    """One canned page per endpoint; records the arguments it received."""

    def __init__(
        self,
        *,
        titles: tuple[JustWatchTitle, ...] = (),
        charts: tuple[JustWatchChartEntry, ...] = (),
    ) -> None:
        self.titles = titles
        self.charts = charts
        self.calls: list[dict[str, object]] = []

    def popular_titles(self, country, language, **kwargs) -> JustWatchPage:
        self.calls.append({"operation": "popular_titles", **kwargs})
        return JustWatchPage(titles=self.titles, next_cursor=None, total_items=len(self.titles))

    def new_titles(self, country, language, page_type, **kwargs) -> JustWatchPage:
        self.calls.append({"operation": "new_titles", "page_type": page_type, **kwargs})
        return JustWatchPage(titles=self.titles, next_cursor=None, total_items=len(self.titles))

    def streaming_charts(self, country, language, **kwargs) -> JustWatchPage:
        self.calls.append({"operation": "streaming_charts", **kwargs})
        return JustWatchPage(charts=self.charts, next_cursor=None, total_items=len(self.charts))

    def list_packages(self, country):
        return []

    def list_genres(self, language):
        return []

    def healthcheck(self):
        return HealthStatus(ok=True, message="stub")

    def close(self) -> None:
        return None


def _collection(
    kind: CollectionKind,
    media_type: MediaType = MediaType.MOVIE,
    *,
    filters: dict | None = None,
) -> SourceCollection:
    return SourceCollection(
        key=f"nfx:{media_type.value}",
        name="Netflix — Film — Catalogo JustWatch",
        provider_external_id="nfx",
        media_type=media_type,
        kind=kind,
        origin=CollectionOrigin.AGGREGATOR,
        date_basis=DateBasis.UNKNOWN,
        metadata={
            "watch_region": "IT",
            "packages": ["nfx"],
            "media_type": media_type.value,
            "year_from": 1900,
            "year_to": 2030,
            "filters": filters or {},
        },
    )


def test_new_titles_movies_inside_a_show_collection_are_dropped() -> None:
    """``newTitles`` ignores objectTypes: the SHOW collection stays empty."""
    client = StubClient(titles=(_title("movie-1", media_type=MediaType.MOVIE, offers=(_offer(),)),))
    connector = JustWatchConnector(client, language="it")
    page = connector.fetch_collection_page(
        _collection(CollectionKind.RECENTLY_ADDED, MediaType.SHOW), None, 100
    )
    assert page.items == ()
    call = client.calls[-1]
    assert call["operation"] == "new_titles"
    assert call["object_type"] is MediaType.SHOW
    assert call["monetization_types"] == ["FLATRATE"]


def test_titles_without_the_required_package_are_dropped() -> None:
    client = StubClient(
        titles=(
            _title("dnp-only", offers=(_offer(package="dnp"),)),
            _title("nfx", offers=(_offer(),)),
        )
    )
    connector = JustWatchConnector(client, language="it")
    page = connector.fetch_collection_page(_collection(CollectionKind.CATALOG), None, 100)
    assert [item.source_item_id for item in page.items] == ["nfx"]


def test_non_flatrate_offers_are_excluded_by_default() -> None:
    client = StubClient(
        titles=(
            _title("rent", offers=(_offer(monetization="RENT"),)),
            _title("buy", offers=(_offer(monetization="BUY"),)),
            _title("ads", offers=(_offer(monetization="ADS"),)),
            _title("free", offers=(_offer(monetization="FREE"),)),
            _title("flatrate", offers=(_offer(),)),
        )
    )
    connector = JustWatchConnector(client, language="it")
    page = connector.fetch_collection_page(_collection(CollectionKind.CATALOG), None, 100)
    assert [item.source_item_id for item in page.items] == ["flatrate"]
    assert page.items[0].offer_types == frozenset({"FLATRATE"})
    assert page.items[0].source_payload["_offer_types"] == ["FLATRATE"]


def test_explicit_offer_types_allow_other_monetizations() -> None:
    client = StubClient(
        titles=(
            _title("rent", offers=(_offer(monetization="RENT"),)),
            _title("flatrate", offers=(_offer(),)),
        )
    )
    connector = JustWatchConnector(client, language="it")
    collection = _collection(CollectionKind.CATALOG, filters={"offer_types": ["rent"]})
    page = connector.fetch_collection_page(collection, None, 100)
    assert [item.source_item_id for item in page.items] == ["rent"]


def test_titles_without_external_ids_are_dropped() -> None:
    client = StubClient(titles=(_title("no-ids", offers=(_offer(),), tmdb_id=None),))
    connector = JustWatchConnector(client, language="it")
    page = connector.fetch_collection_page(_collection(CollectionKind.CATALOG), None, 100)
    assert page.items == ()


def test_chart_keeps_the_source_rank_and_filters_by_package_and_offer() -> None:
    client = StubClient(
        charts=(
            JustWatchChartEntry(title=_title("global-20", offers=(_offer(),)), rank=20, trend="UP"),
            JustWatchChartEntry(
                title=_title("rented-144", offers=(_offer(monetization="RENT"),)), rank=144
            ),
        )
    )
    connector = JustWatchConnector(client, language="it")
    page = connector.fetch_collection_page(_collection(CollectionKind.CHART), None, 100)
    assert [item.source_item_id for item in page.items] == ["global-20"]
    # The rank is the global chart rank, not a Top 10 position.
    assert page.items[0].source_payload["_chart"]["rank"] == 20
    assert page.items[0].source_payload["_chart"]["trend"] == "UP"


def test_collection_names_use_the_justwatch_labels() -> None:
    class PackagesClient(StubClient):
        def list_packages(self, country):
            from app.integrations.justwatch.models import JustWatchPackage

            return [JustWatchPackage(short_name="nfx", name="Netflix")]

    collections = JustWatchConnector(PackagesClient(), language="it").list_collections("IT")
    names = {
        (collection.kind, collection.media_type): collection.name for collection in collections
    }
    movie = MediaType.MOVIE
    assert names[(CollectionKind.CATALOG, movie)] == "Netflix — Film — Catalogo JustWatch"
    assert names[(CollectionKind.CHART, movie)] == "Netflix — Film — Classifica JustWatch"
    assert names[(CollectionKind.RECENTLY_ADDED, movie)] == "Netflix — Film — Novità JustWatch"
    assert names[(CollectionKind.UPCOMING, movie)] == "Netflix — Film — In arrivo JustWatch"
    assert all("Top 10" not in name for name in names.values())


def test_upcoming_items_are_marked_upcoming_and_catalog_is_current() -> None:
    client = StubClient(titles=(_title("t1", offers=(_offer(),)),))
    connector = JustWatchConnector(client, language="it")
    upcoming = connector.fetch_collection_page(_collection(CollectionKind.UPCOMING), None, 100)
    assert upcoming.items[0].availability_status == AvailabilityStatus.UPCOMING.value
    current = connector.fetch_collection_page(_collection(CollectionKind.CATALOG), None, 100)
    assert current.items[0].availability_status == AvailabilityStatus.CURRENT.value


def test_upcoming_title_without_offers_is_kept_but_not_in_catalog() -> None:
    """An announced title may have no offer yet; it must stay in UPCOMING only."""
    client = StubClient(titles=(_title("announced"),))
    connector = JustWatchConnector(client, language="it")
    upcoming = connector.fetch_collection_page(_collection(CollectionKind.UPCOMING), None, 100)
    assert [item.source_item_id for item in upcoming.items] == ["announced"]
    assert upcoming.items[0].availability_status == AvailabilityStatus.UPCOMING.value
    assert upcoming.items[0].offer_types == frozenset()
    catalog = connector.fetch_collection_page(_collection(CollectionKind.CATALOG), None, 100)
    assert catalog.items == ()


def test_capabilities_never_hide_a_partial_failure() -> None:
    capabilities = JustWatchConnector(StubClient(), language="it").capabilities
    assert capabilities.partial_on_error is True
    assert capabilities.seasons_episodes is True
    assert capabilities.full_pagination is True
    assert capabilities.added_dates is False
    assert capabilities.requires_contract is False
