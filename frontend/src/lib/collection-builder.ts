import type { CollectionCreatePayload, Provider } from "../api/types";
import type {
  BuilderSource,
  CollectionKind,
  CombineMode,
  DefaultSource,
  MediaType,
  OfferType,
} from "../api/types";

const COMBINED_SOURCE_LABEL = "Combinata locale (JustWatch + TMDb)";
const JUSTWATCH_SOURCE_LABEL = "Fonte: JustWatch (Aggregatore)";
const JUSTWATCH_CHART_SOURCE_LABEL = "Classifica JustWatch";

/**
 * Il provider ha un ID TMDb per il tipo media richiesto. La verifica live è
 * separata: un mapping manuale resta selezionabile nel builder, mentre il
 * backend registra ``provider_mapping_verified=false``.
 */
export function hasTmdbMapping(provider: Provider, mediaType: MediaType): boolean {
  const externalId =
    mediaType === "SHOW" ? provider.tmdb_provider_id_tv : provider.tmdb_provider_id_movie;
  return Boolean(externalId);
}

/** `settings.default_source` può mancare o essere invalido: JustWatch vince. */
export function resolveDefaultSource(value: unknown): DefaultSource {
  return value === "tmdb" ? "tmdb" : "justwatch";
}

/** Anteprima esatta del `source_label` che il backend restituirà. */
export function builderProvenanceLabel(
  sourceKey: BuilderSource,
  kind: CollectionKind,
): string {
  if (sourceKey === "combined") return COMBINED_SOURCE_LABEL;
  if (sourceKey === "justwatch") {
    return kind === "CHART" ? JUSTWATCH_CHART_SOURCE_LABEL : JUSTWATCH_SOURCE_LABEL;
  }
  return "TMDb";
}

export interface CollectionBuilderInput {
  sourceKey: BuilderSource;
  combineMode?: CombineMode;
  justWatchOfferMode?: "FLATRATE" | "ALL";
  providerId: string;
  mediaType: MediaType;
  kind: CollectionKind;
  name: string;
  slug: string;
  description: string;
  offerType: OfferType;
  genreIds: number[];
  sourceCollectionId: string;
  sourceCollectionIds: string[];
  sharedSnapshotId: string;
  excludeGenreIds: number[];
  minVoteAverage: string;
  minVoteCount: string;
  yearFrom: string;
  yearTo: string;
  originalLanguage: string;
  localSortBy: string;
  windowDays: string;
  isActive: boolean;
}

function optionalNumber(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/**
 * Il payload cambia con la fonte: JustWatch usa `offer_types`, anni e kind
 * propri, mentre i filtri TMDb/locali non vengono inviati. Tenere la
 * costruzione fuori dalla pagina rende verificabile il contratto via test.
 */
export function buildCollectionPayload(input: CollectionBuilderInput): CollectionCreatePayload {
  const identity = {
    provider_id: input.providerId || undefined,
    media_type: input.mediaType,
    name: input.name.trim(),
    slug: input.slug.trim(),
    kind: input.kind,
    description: input.description.trim() || undefined,
    is_active: input.isActive,
  };

  if (input.sourceKey === "combined") {
    return {
      ...identity,
      kind: "CUSTOM_FILTER",
      source_key: "combined",
      combine_mode: input.combineMode ?? "UNION",
      source_collection_ids: input.sourceCollectionIds,
      monetization_type: "FLATRATE",
      genre_ids: [],
    };
  }

  if (input.sourceKey === "justwatch") {
    return {
      ...identity,
      source_key: "justwatch",
      offer_types: input.justWatchOfferMode === "ALL" ? [] : [input.offerType],
      monetization_type: input.offerType,
      genre_ids: [],
      year_from: optionalNumber(input.yearFrom),
      year_to: optionalNumber(input.yearTo),
    };
  }

  const days = optionalNumber(input.windowDays);
  return {
    ...identity,
    source_key: "tmdb",
    genre_ids: input.genreIds,
    monetization_type: input.offerType,
    ...(input.kind === "RECENTLY_ADDED"
      ? { window_days: days, source_collection_id: input.sourceCollectionId }
      : {}),
    ...(input.kind === "CUSTOM_FILTER"
      ? {
          source_collection_ids: input.sourceCollectionIds,
          exclude_genre_ids: input.excludeGenreIds,
          min_vote_average: optionalNumber(input.minVoteAverage),
          min_vote_count: optionalNumber(input.minVoteCount),
          year_from: optionalNumber(input.yearFrom),
          year_to: optionalNumber(input.yearTo),
          original_language: input.originalLanguage.trim() || undefined,
          local_sort_by: input.localSortBy,
        }
      : {}),
    ...(input.kind === "CATALOG" && input.sharedSnapshotId
      ? { shared_snapshot_collection_id: input.sharedSnapshotId }
      : {}),
  };
}
