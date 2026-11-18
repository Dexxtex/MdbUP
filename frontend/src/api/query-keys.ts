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

export const queryKeys = {
  session: ["session"] as const,
  dashboard: ["dashboard"] as const,
  providers: (country: string) => ["providers", country] as const,
  sources: ["sources"] as const,
  collections: (filters: CollectionFilters) => ["collections", filters] as const,
  collection: (id: string) => ["collection", id] as const,
  collectionSnapshots: (id: string) => ["collection", id, "snapshots"] as const,
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
