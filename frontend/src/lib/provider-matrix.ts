import type { Binding, Collection, MediaType, Provider } from "../api/types";
import { isJustWatchSource } from "./justwatch";

/** Gli 8 servizi italiani della matrice comparativa Fase 9. */
const PROVIDER_MATRIX_SERVICES: readonly string[] = [
  "Netflix",
  "Prime Video",
  "Disney+",
  "Apple TV+",
  "NOW",
  "Paramount+",
  "RaiPlay",
  "Mediaset Infinity",
];

export type ProviderMatrixFilter = "all" | "stale" | "active-bindings";
export type ProviderMatrixSortKey =
  | "name"
  | "justwatch"
  | "tmdb-movie"
  | "tmdb-show"
  | "bindings";
export type SortDirection = "asc" | "desc";

const STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;

/** Fase 9: verifica per media type, con fallback al flag storico. */
export function justWatchVerifiedForMedia(
  provider: Provider,
  mediaType: MediaType,
): boolean {
  const specific =
    mediaType === "MOVIE"
      ? provider.justwatch_movie_verified
      : provider.justwatch_tv_verified;
  return specific ?? provider.justwatch_verified === true;
}

export function isSnapshotStale(
  lastSnapshotAt: string | null,
  now: number = Date.now(),
  staleAfterMs: number = STALE_AFTER_MS,
): boolean {
  if (!lastSnapshotAt) return true;
  return now - new Date(lastSnapshotAt).getTime() > staleAfterMs;
}

interface MediaSnapshotState {
  mapped: boolean;
  collections: number;
  lastSnapshotAt: string | null;
  stale: boolean;
}

export interface ProviderMatrixRow {
  provider: Provider;
  justwatch: {
    movieVerified: boolean;
    tvVerified: boolean;
    collections: number;
    lastSnapshotAt: string | null;
    stale: boolean;
  };
  tmdb: {
    movie: MediaSnapshotState;
    show: MediaSnapshotState;
  };
  activeBindings: number;
  missingSnapshot: boolean;
  needsAttention: boolean;
}

function latestSnapshotAt(collections: readonly Collection[]): string | null {
  let latest: string | null = null;
  for (const collection of collections) {
    const finishedAt =
      collection.last_valid_snapshot?.finished_at ??
      collection.latest_snapshot?.finished_at ??
      null;
    if (finishedAt && (!latest || finishedAt > latest)) latest = finishedAt;
  }
  return latest;
}

function mediaState(
  collections: readonly Collection[],
  mediaType: MediaType,
  mapped: boolean,
  now: number,
): MediaSnapshotState {
  const matching = collections.filter(
    (collection) =>
      collection.media_type === mediaType && collection.source_key === "tmdb",
  );
  const lastSnapshotAt = latestSnapshotAt(matching);
  return {
    mapped,
    collections: matching.length,
    lastSnapshotAt,
    stale: isSnapshotStale(lastSnapshotAt, now),
  };
}

function matchesMatrixService(provider: Provider): number {
  const name = provider.name.toLowerCase();
  return PROVIDER_MATRIX_SERVICES.findIndex((service) =>
    name.includes(service.toLowerCase()),
  );
}

export function buildProviderMatrix(
  providers: readonly Provider[],
  collections: readonly Collection[],
  bindings: readonly Binding[],
  now: number = Date.now(),
): ProviderMatrixRow[] {
  const selected = providers
    .map((provider) => ({ provider, order: matchesMatrixService(provider) }))
    // The matrix is not limited to the historical eight services: a provider
    // created by the operator must appear here too. Known services keep their
    // curated order; custom ones follow alphabetically.
    .sort((a, b) => {
      const left = a.order < 0 ? Number.MAX_SAFE_INTEGER : a.order;
      const right = b.order < 0 ? Number.MAX_SAFE_INTEGER : b.order;
      return left - right || a.provider.name.localeCompare(b.provider.name, "it");
    });

  return selected.map(({ provider }) => {
    const providerCollections = collections.filter(
      (collection) => collection.provider_id === provider.id,
    );
    const justwatchCollections = providerCollections.filter((collection) =>
      isJustWatchSource(collection.source_key),
    );
    const tmdbCollections = providerCollections.filter(
      (collection) => collection.source_key === "tmdb",
    );
    const justwatchLastSnapshot = latestSnapshotAt(justwatchCollections);
    const justwatchStale = isSnapshotStale(justwatchLastSnapshot, now);
    const movie = mediaState(
      tmdbCollections,
      "MOVIE",
      provider.mapping_verified_movie,
      now,
    );
    const show = mediaState(
      tmdbCollections,
      "SHOW",
      provider.mapping_verified_tv,
      now,
    );
    const collectionIds = new Set(providerCollections.map((item) => item.id));
    const activeBindings = bindings.filter(
      (binding) => binding.enabled && collectionIds.has(binding.collection_id),
    ).length;
    const missingSnapshot =
      justwatchCollections.length === 0 ||
      movie.collections === 0 ||
      show.collections === 0 ||
      justwatchLastSnapshot == null ||
      movie.lastSnapshotAt == null ||
      show.lastSnapshotAt == null;

    return {
      provider,
      justwatch: {
        movieVerified: justWatchVerifiedForMedia(provider, "MOVIE"),
        tvVerified: justWatchVerifiedForMedia(provider, "SHOW"),
        collections: justwatchCollections.length,
        lastSnapshotAt: justwatchLastSnapshot,
        stale: justwatchStale,
      },
      tmdb: { movie, show },
      activeBindings,
      missingSnapshot,
      needsAttention:
        missingSnapshot || justwatchStale || movie.stale || show.stale,
    };
  });
}

export function filterProviderMatrix(
  rows: readonly ProviderMatrixRow[],
  filter: ProviderMatrixFilter,
): ProviderMatrixRow[] {
  if (filter === "stale") return rows.filter((row) => row.needsAttention);
  if (filter === "active-bindings") {
    return rows.filter((row) => row.activeBindings > 0);
  }
  return [...rows];
}

function sortValue(row: ProviderMatrixRow, key: ProviderMatrixSortKey): string | number {
  if (key === "name") return row.provider.name;
  if (key === "bindings") return row.activeBindings;
  if (key === "justwatch") return row.justwatch.lastSnapshotAt ?? "";
  if (key === "tmdb-movie") return row.tmdb.movie.lastSnapshotAt ?? "";
  return row.tmdb.show.lastSnapshotAt ?? "";
}

export function sortProviderMatrix(
  rows: readonly ProviderMatrixRow[],
  key: ProviderMatrixSortKey,
  direction: SortDirection,
  collator: Intl.Collator = new Intl.Collator("it-IT"),
): ProviderMatrixRow[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const left = sortValue(a, key);
    const right = sortValue(b, key);
    if (typeof left === "string" && typeof right === "string") {
      return collator.compare(left, right) * factor;
    }
    return ((left as number) - (right as number)) * factor;
  });
}
