"""GraphQL documents for the public JustWatch endpoint.

Every document here was verified against the live endpoint: field names,
argument names and enum values are the ones the server actually accepts.
Introspection is disabled server-side, so there is no schema to generate from.

Keep the selections narrow: the endpoint rejects oversized graphs with
``operation complexity`` and refuses more than 100 items per page.
"""

from __future__ import annotations

# Shared selection for a movie/show. ``externalIds`` carries the TMDb and IMDb
# ids, which is what the media identity resolver needs.
FRAGMENT_TITLE = """
fragment TitleDetails on MovieOrShow {
  id
  objectType
  content(country: $country, language: $language) {
    title
    originalReleaseYear
    fullPath
    runtime
    externalIds { imdbId tmdbId }
  }
  offers(country: $country, platform: WEB) {
    monetizationType
    presentationType
    standardWebURL
    package { clearName shortName }
  }
}
"""

QUERY_PACKAGES = """
query Packages($country: Country!, $platform: Platform!) {
  packages(country: $country, platform: $platform, includeAddons: false) {
    id
    shortName
    clearName
    technicalName
    monetizationTypes
  }
}
"""

QUERY_GENRES = """
query Genres($language: Language!) {
  genres { shortName technicalName slug(language: $language) }
}
"""

QUERY_POPULAR_TITLES = (
    """
query PopularTitles(
    $country: Country!
    $language: Language!
    $first: Int!
    $offset: Int
    $filter: TitleFilter
) {
  popularTitles(country: $country, first: $first, offset: $offset, filter: $filter) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges { node { ...TitleDetails } }
  }
}
"""
    + FRAGMENT_TITLE
)

QUERY_NEW_TITLES = (
    """
query NewTitles(
    $country: Country!
    $language: Language!
    $first: Int!
    $offset: Int
    $pageType: NewPageType!
    $filter: TitleFilter
) {
  newTitles(
    country: $country
    first: $first
    offset: $offset
    pageType: $pageType
    filter: $filter
  ) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges { node { ...TitleDetails } }
  }
}
"""
    + FRAGMENT_TITLE
)

QUERY_STREAMING_CHARTS = (
    """
query StreamingCharts(
    $country: Country!
    $language: Language!
    $first: Int!
    $after: String
    $filter: StreamingChartsFilter
) {
  streamingCharts(country: $country, first: $first, after: $after, filter: $filter) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      streamingChartInfo { rank trend trendDifference daysInTop10 topRank }
      node { ...TitleDetails }
    }
  }
}
"""
    + FRAGMENT_TITLE
)

QUERY_HEALTHCHECK = """
query Healthcheck {
  __typename
}
"""

# Enum values accepted by the endpoint (verified).
NEW_PAGE_TYPES = frozenset({"NEW", "UPCOMING", "LEAVING_SOON"})
CHART_OBJECT_TYPES = frozenset({"MOVIE", "SHOW"})

QUERY_SEASONS = """
query Seasons($showId: ID!, $country: Country!, $language: Language!) {
  node(id: $showId) {
    ... on Show {
      seasons {
        id
        totalEpisodeCount
        content(country: $country, language: $language) { title }
      }
    }
  }
}
"""

QUERY_EPISODES = """
query Episodes($seasonId: ID!, $country: Country!, $language: Language!) {
  node(id: $seasonId) {
    ... on Season {
      episodes {
        id
        content(country: $country, language: $language) {
          title
          seasonNumber
          episodeNumber
        }
        offers(country: $country, platform: WEB) {
          monetizationType
          presentationType
          standardWebURL
          package { clearName shortName }
        }
      }
    }
  }
}
"""
