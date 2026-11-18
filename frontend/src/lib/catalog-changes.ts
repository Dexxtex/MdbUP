import type {
  CatalogChangeDirection,
  CatalogChangeItem,
  CatalogChangeWindow,
  EpisodeEventType,
} from "../api/types";
import { sourceLabel, type Tone } from "./status";


export const CATALOG_CHANGE_WINDOWS: readonly {
  value: CatalogChangeWindow;
  label: string;
}[] = [
  { value: "24h", label: "Oggi" },
  { value: "7d", label: "7g" },
  { value: "14d", label: "14g" },
  { value: "30d", label: "30g" },
];

export const CATALOG_CHANGE_DIRECTIONS: readonly {
  value: CatalogChangeDirection;
  label: string;
}[] = [
  { value: "ADDED", label: "Entrati" },
  { value: "REMOVED", label: "Usciti" },
];

export interface CatalogChangeFilters {
  window: CatalogChangeWindow;
  providerId?: string;
  mediaType?: string;
  sourceKey?: string;
  direction?: CatalogChangeDirection | "";
  search?: string;
  page?: number;
  pageSize?: number;
}

/**
 * Costruisce la query di `GET /api/catalog-changes`: i filtri vuoti non vengono
 * inviati, così il backend applica i propri default.
 */
export function catalogChangesQuery(filters: CatalogChangeFilters): string {
  const params = new URLSearchParams();
  params.set("window", filters.window);
  if (filters.providerId) params.set("provider_id", filters.providerId);
  if (filters.mediaType) params.set("media_type", filters.mediaType);
  if (filters.sourceKey) params.set("source_key", filters.sourceKey);
  if (filters.direction) params.set("direction", filters.direction);
  const search = filters.search?.trim();
  if (search) params.set("search", search);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 50));
  return `?${params.toString()}`;
}

export function catalogChangeWindowLabel(window: CatalogChangeWindow): string {
  return CATALOG_CHANGE_WINDOWS.find((item) => item.value === window)?.label ?? window;
}

export function catalogChangeDirectionLabel(direction: CatalogChangeDirection): string {
  return direction === "ADDED" ? "Entrato" : "Uscito";
}

export function catalogChangeDirectionTone(direction: CatalogChangeDirection): Tone {
  return direction === "ADDED" ? "success" : "danger";
}

export function catalogChangeDirectionSign(direction: CatalogChangeDirection): string {
  return direction === "ADDED" ? "+" : "−";
}

/** Etichetta esatta calcolata dal backend (es. "Fonte: JustWatch (Aggregatore)"). */
export function catalogChangeSourceLabel(item: CatalogChangeItem): string {
  return item.source_label || sourceLabel(item.source_key) || item.source_key;
}

/** Nome breve della fonte per righe compatte (JustWatch/TMDb). */
export function catalogChangeSourceName(item: CatalogChangeItem): string {
  return sourceLabel(item.source_key) ?? item.source_label ?? item.source_key;
}

const EPISODE_EVENT_LABELS: Record<EpisodeEventType, string> = {
  SEASON_ADDED: "Nuova stagione",
  SEASON_REMOVED: "Stagione rimossa",
  EPISODE_ADDED: "Nuovo episodio",
  EPISODE_REMOVED: "Episodio rimosso",
};

export function episodeEventLabel(eventType: EpisodeEventType): string {
  return EPISODE_EVENT_LABELS[eventType] ?? eventType;
}

export function episodeEventTone(eventType: EpisodeEventType): Tone {
  return eventType.endsWith("_ADDED") ? "success" : "danger";
}
