import { describe, expect, it } from "vitest";
import {
  buildCollectionPayload,
  builderProvenanceLabel,
  resolveDefaultSource,
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

describe("fonte predefinita del builder", () => {
  it("usa JustWatch come fallback e rispetta TMDb", () => {
    expect(resolveDefaultSource(undefined)).toBe("justwatch");
    expect(resolveDefaultSource("unknown")).toBe("justwatch");
    expect(resolveDefaultSource("tmdb")).toBe("tmdb");
  });
});

describe("badge di provenienza", () => {
  it("restituisce l'etichetta esatta della combinata e di JustWatch", () => {
    expect(builderProvenanceLabel("combined", "CUSTOM_FILTER")).toBe(
      "Combinata locale (JustWatch + TMDb)",
    );
    expect(builderProvenanceLabel("justwatch", "CHART")).toBe(
      "Classifica JustWatch",
    );
    expect(builderProvenanceLabel("justwatch", "CATALOG")).toBe(
      "Fonte: JustWatch (Aggregatore)",
    );
    expect(builderProvenanceLabel("tmdb", "CATALOG")).toBe("TMDb");
  });
});

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

  it("costruisce il payload della combinata locale con modo e sorgenti", () => {
    const payload = buildCollectionPayload(
      input({
        sourceKey: "combined",
        combineMode: "INTERSECTION",
        sourceCollectionIds: ["collection-jw", "collection-tmdb"],
        name: "Combinata Netflix",
        slug: "combinata-netflix",
      }),
    );
    expect(payload.source_key).toBe("combined");
    expect(payload.kind).toBe("CUSTOM_FILTER");
    expect(payload.combine_mode).toBe("INTERSECTION");
    expect(payload.source_collection_ids).toEqual([
      "collection-jw",
      "collection-tmdb",
    ]);
    expect(payload.monetization_type).toBe("FLATRATE");
  });

  it("invia offerte vuote quando JustWatch usa tutte le offerte", () => {
    const payload = buildCollectionPayload(
      input({ sourceKey: "justwatch", justWatchOfferMode: "ALL" }),
    );
    expect(payload.offer_types).toEqual([]);
    expect(payload.monetization_type).toBe("FLATRATE");
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
