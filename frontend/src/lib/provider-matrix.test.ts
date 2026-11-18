import { describe, expect, it } from "vitest";
import type { Binding, Collection, Provider, Snapshot } from "../api/types";
import {
  buildProviderMatrix,
  filterProviderMatrix,
  isSnapshotStale,
  justWatchVerifiedForMedia,
  sortProviderMatrix,
} from "./provider-matrix";

const NOW = new Date("2026-01-10T12:00:00Z").getTime();

function provider(overrides: Partial<Provider> = {}): Provider {
  return {
    id: "provider-1",
    slug: "netflix",
    name: "Netflix",
    kind: "FLATRATE",
    logo_url: null,
    website_url: null,
    country_code: "IT",
    tmdb_provider_id: "8",
    tmdb_provider_id_movie: "8",
    tmdb_provider_id_tv: "8",
    mapping_verified: true,
    mapping_verified_movie: true,
    mapping_verified_tv: true,
    justwatch_provider_id: "8",
    justwatch_verified: true,
    justwatch_movie_verified: true,
    justwatch_tv_verified: true,
    justwatch_monetization_types: ["FLATRATE"],
    collections_count: 0,
    movie_collections: 0,
    show_collections: 0,
    ...overrides,
  };
}

function snapshot(id: string, finishedAt: string): Snapshot {
  return {
    id,
    status: "COMPLETE",
    quality: "CLEAN",
    is_valid: true,
    started_at: finishedAt,
    finished_at: finishedAt,
    pages_expected: 1,
    pages_fetched: 1,
    items_count: 10,
    resolved_count: 10,
    unresolved_count: 0,
    duplicate_count: 0,
    error_count: 0,
    checksum: null,
    invalid_reason: null,
  };
}

function collection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: "collection-1",
    slug: "netflix-film",
    name: "Netflix film",
    provider_id: "provider-1",
    provider_slug: "netflix",
    provider_name: "Netflix",
    source_id: "source-1",
    source_key: "justwatch",
    country_code: "IT",
    media_type: "MOVIE",
    kind: "CATALOG",
    origin: "AGGREGATOR",
    date_basis: "UNKNOWN",
    description: null,
    filters: {},
    quality_flags: {},
    provider_names: ["Netflix"],
    is_local_filter: false,
    is_multi_provider: false,
    offer_types: ["FLATRATE"],
    sort_mode: "provider",
    is_active: true,
    latest_snapshot: null,
    last_valid_snapshot: null,
    ...overrides,
  };
}

function binding(overrides: Partial<Binding> = {}): Binding {
  return {
    id: "binding-1",
    collection_id: "collection-1",
    target_id: "target-1",
    media_type: "MOVIE",
    mode: "MIRROR",
    schedule: "MANUAL",
    schedule_cron: "0 3 * * *",
    schedule_interval_hours: null,
    max_removal_pct: 10,
    max_removal_abs: 50,
    max_remove_count: 50,
    max_remove_percent: 10,
    thresholds: { max_removal_pct: 10, max_removal_abs: 50 },
    preserve_order: false,
    reorder_enabled: false,
    schedule_policy: "AUTO_APPLY_IF_SAFE",
    require_review: true,
    enabled: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("verifica JustWatch per media type", () => {
  it("usa i flag specifici quando presenti", () => {
    const item = provider({
      justwatch_verified: true,
      justwatch_movie_verified: false,
      justwatch_tv_verified: true,
    });
    expect(justWatchVerifiedForMedia(item, "MOVIE")).toBe(false);
    expect(justWatchVerifiedForMedia(item, "SHOW")).toBe(true);
  });

  it("ricade sul flag storico justwatch_verified", () => {
    const item = provider({
      justwatch_verified: true,
      justwatch_movie_verified: undefined,
      justwatch_tv_verified: undefined,
    });
    expect(justWatchVerifiedForMedia(item, "MOVIE")).toBe(true);
    expect(justWatchVerifiedForMedia(item, "SHOW")).toBe(true);
  });
});

describe("freschezza snapshot", () => {
  it("considera mancante lo snapshot nullo e scaduto quello oltre 7 giorni", () => {
    expect(isSnapshotStale(null, NOW)).toBe(true);
    expect(isSnapshotStale("2026-01-09T12:00:00Z", NOW)).toBe(false);
    expect(isSnapshotStale("2025-12-01T12:00:00Z", NOW)).toBe(true);
  });
});

describe("buildProviderMatrix", () => {
  it("calcola mapping, freschezza e binding attivi per gli 8 servizi", () => {
    const netflix = provider();
    const prime = provider({
      id: "provider-2",
      slug: "amazon-prime-video",
      name: "Amazon Prime Video",
      justwatch_provider_id: "119",
    });
    const collections = [
      collection({
        id: "jw-1",
        provider_id: netflix.id,
        source_key: "justwatch",
        last_valid_snapshot: snapshot("snap-jw", "2026-01-09T00:00:00Z"),
      }),
      collection({
        id: "tmdb-movie",
        provider_id: netflix.id,
        source_key: "tmdb",
        media_type: "MOVIE",
        kind: "CATALOG",
        last_valid_snapshot: snapshot("snap-movie", "2026-01-08T00:00:00Z"),
      }),
      collection({
        id: "tmdb-show",
        provider_id: netflix.id,
        source_key: "tmdb",
        media_type: "SHOW",
        kind: "CATALOG",
        last_valid_snapshot: snapshot("snap-show", "2026-01-07T00:00:00Z"),
      }),
    ];
    const bindings = [
      binding({ id: "b-1", collection_id: "jw-1", enabled: true }),
      binding({ id: "b-2", collection_id: "tmdb-movie", enabled: false }),
    ];

    const rows = buildProviderMatrix([prime, netflix], collections, bindings, NOW);

    expect(rows.map((row) => row.provider.name)).toEqual([
      "Netflix",
      "Amazon Prime Video",
    ]);
    const [netflixRow, primeRow] = rows;
    expect(netflixRow.justwatch.movieVerified).toBe(true);
    expect(netflixRow.justwatch.lastSnapshotAt).toBe("2026-01-09T00:00:00Z");
    expect(netflixRow.tmdb.movie.lastSnapshotAt).toBe("2026-01-08T00:00:00Z");
    expect(netflixRow.activeBindings).toBe(1);
    expect(netflixRow.missingSnapshot).toBe(false);
    expect(primeRow.missingSnapshot).toBe(true);
    expect(primeRow.needsAttention).toBe(true);
  });

  it("ignora i provider fuori dagli 8 servizi italiani", () => {
    const rows = buildProviderMatrix(
      [provider(), provider({ id: "p-3", slug: "mubi", name: "MUBI" })],
      [],
      [],
      NOW,
    );
    expect(rows.map((row) => row.provider.name)).toEqual(["Netflix"]);
  });
});

describe("filtri e ordinamento matrice", () => {
  const netflix = provider();
  const prime = provider({
    id: "provider-2",
    slug: "amazon-prime-video",
    name: "Amazon Prime Video",
  });
  const collections = [
    collection({
      id: "jw-1",
      provider_id: netflix.id,
      source_key: "justwatch",
      last_valid_snapshot: snapshot("snap-1", "2026-01-09T00:00:00Z"),
    }),
    collection({
      id: "tmdb-1",
      provider_id: netflix.id,
      source_key: "tmdb",
      media_type: "MOVIE",
      last_valid_snapshot: snapshot("snap-2", "2026-01-09T00:00:00Z"),
    }),
    collection({
      id: "tmdb-2",
      provider_id: netflix.id,
      source_key: "tmdb",
      media_type: "SHOW",
      last_valid_snapshot: snapshot("snap-3", "2026-01-09T00:00:00Z"),
    }),
  ];
  const rows = buildProviderMatrix(
    [netflix, prime],
    collections,
    [binding({ collection_id: "jw-1", enabled: true })],
    NOW,
  );

  it("filtra snapshot mancanti/scaduti e binding attivi", () => {
    expect(filterProviderMatrix(rows, "all")).toHaveLength(2);
    expect(filterProviderMatrix(rows, "active-bindings").map((row) => row.provider.slug)).toEqual([
      "netflix",
    ]);
    expect(filterProviderMatrix(rows, "stale").map((row) => row.provider.slug)).toEqual([
      "amazon-prime-video",
    ]);
  });

  it("ordina per nome e per binding attivi", () => {
    expect(
      sortProviderMatrix(rows, "name", "asc").map((row) => row.provider.name),
    ).toEqual(["Amazon Prime Video", "Netflix"]);
    expect(
      sortProviderMatrix(rows, "bindings", "desc").map((row) => row.provider.name),
    ).toEqual(["Netflix", "Amazon Prime Video"]);
  });
});
