import type { CatalogChangeWindow } from "./types";

export interface CollectionFilters {
  providerId?: string;
  mediaType?: string;
  origin?: string;
  kind?: string;
  isActive?: string;
}

export interface RunFilters {
  providerId?: string;
  status?: string;
  mediaType?: string;
}

export interface CatalogChangeFilters {
  window: CatalogChangeWindow;
  providerId?: string;
  mediaType?: string;
  sourceKey?: string;
  direction?: string;
  search?: string;
  page?: number;
  pageSize?: number;
}

export const queryKeys = {
  session: ["session"] as const,
  dashboard: ["dashboard"] as const,
  providers: (country: string) => ["providers", country] as const,
  providerCatalog: (country: string) => ["providers", "catalog", country] as const,
  sources: ["sources"] as const,
  tvdbCompanies: (query: string) => ["sources", "tvdb", "companies", query] as const,
  collections: (filters: CollectionFilters) => ["collections", filters] as const,
  collection: (id: string) => ["collection", id] as const,
  collectionSnapshots: (id: string) => ["collection", id, "snapshots"] as const,
  collectionEpisodeEvents: (id: string, limit: number) =>
    ["collection", id, "episode-events", limit] as const,
  snapshotItems: (id: string, search: string) =>
    ["snapshot", id, "items", search] as const,
  catalogChanges: (filters: CatalogChangeFilters) =>
    ["catalog-changes", filters] as const,
  targets: (mediaType?: string) => ["targets", mediaType ?? "all"] as const,
  genres: (mediaType: string) => ["genres", mediaType] as const,
  runs: (filters: RunFilters) => ["runs", filters] as const,
  bindings: ["bindings"] as const,
  binding: (id: string) => ["binding", id] as const,
  preview: (id: string) => ["preview", id] as const,
  run: (id: string) => ["run", id] as const,
  runOperations: (id: string) => ["run", id, "operations"] as const,
  settings: ["settings"] as const,
  systemStatus: ["system", "status"] as const,
  credentials: ["credentials"] as const,
  notificationChannels: ["notifications", "channels"] as const,
};
