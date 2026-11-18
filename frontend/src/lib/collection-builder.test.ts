import { describe, expect, it } from "vitest";
import {
  buildCollectionPayload,
  type CollectionBuilderInput,
} from "./collection-builder";

function input(overrides: Partial<CollectionBuilderInput> = {}): CollectionBuilderInput {
  return {
    sourceKey: "tmdb",
    providerId: "provider-1",
    mediaType: "MOVIE",
    kind: "CATALOG",
    name: "Netflix IT — Film",
    slug: "netflix-it-movie",
    description: "Catalogo",
    offerType: "FLATRATE",
    genreIds: [28, 12],
    sourceCollectionId: "",
    sourceCollectionIds: [],
    sharedSnapshotId: "",
    excludeGenreIds: [],
    minVoteAverage: "",
    minVoteCount: "",
    yearFrom: "",
    yearTo: "",
    originalLanguage: "",
    localSortBy: "vote_average.desc",
    windowDays: "14",
    isActive: true,
    ...overrides,
  };
}

describe("buildCollectionPayload", () => {
  it("costruisce un payload JustWatch con offerte, anni e source_key", () => {
    const payload = buildCollectionPayload(
      input({
        sourceKey: "justwatch",
        kind: "CHART",
        offerType: "FLATRATE",
        yearFrom: "2000",
        yearTo: "2025",
      }),
    );
    expect(payload.source_key).toBe("justwatch");
    expect(payload.kind).toBe("CHART");
    expect(payload.offer_types).toEqual(["FLATRATE"]);
    expect(payload.year_from).toBe(2000);
    expect(payload.year_to).toBe(2025);
    expect(payload.genre_ids).toEqual([]);
    expect(payload.window_days).toBeUndefined();
    expect(payload.source_collection_id).toBeUndefined();
  });

  it("non invia filtri locali TMDb al ramo JustWatch", () => {
    const payload = buildCollectionPayload(
      input({
        sourceKey: "justwatch",
        kind: "UPCOMING",
        sourceCollectionIds: ["collection-1"],
        excludeGenreIds: [18],
        originalLanguage: "it",
      }),
    );
    expect(payload.source_collection_ids).toBeUndefined();
    expect(payload.exclude_genre_ids).toBeUndefined();
    expect(payload.original_language).toBeUndefined();
  });

  it("mantiene il payload TMDb attuale per le novità", () => {
    const payload = buildCollectionPayload(
      input({
        kind: "RECENTLY_ADDED",
        sourceCollectionId: "collection-1",
        windowDays: "7",
      }),
    );
    expect(payload.source_key).toBe("tmdb");
    expect(payload.genre_ids).toEqual([28, 12]);
    expect(payload.window_days).toBe(7);
    expect(payload.source_collection_id).toBe("collection-1");
  });
});
