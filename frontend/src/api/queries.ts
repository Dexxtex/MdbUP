import { useQuery } from "@tanstack/react-query";
import { apiFetch, isApiError, pageItems } from "./client";
import { queryKeys, type CollectionFilters, type RunFilters } from "./query-keys";
import { settingsFromItems } from "./settings";
import type {
  AppSettings,
  Binding,
  BindingList,
  Collection,
  CollectionList,
  Credential,
  CredentialList,
  DashboardResponse,
  EpisodeEventList,
  NotificationChannel,
  NotificationChannelList,
  Operation,
  OperationList,
  Preview,
  Provider,
  ProviderList,
  Run,
  RunStatus,
  SessionResponse,
  SettingsOut,
  Snapshot,
  SnapshotItemList,
  SnapshotList,
  Source,
  SourceList,
  SystemStatus,
  Target,
  TargetList,
} from "./types";

const ACTIVE_RUN_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "PENDING",
  "PREFLIGHT",
  "PLANNING",
  "AWAITING_APPROVAL",
  "APPLYING",
  "VERIFYING",
]);

export function isActiveRun(status: RunStatus | undefined): boolean {
  return status != null && ACTIVE_RUN_STATUSES.has(status);
}

export function useSession() {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: ({ signal }) =>
      apiFetch<SessionResponse>("/auth/session", { signal }),
    retry: false,
    staleTime: 60_000,
  });
}

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: ({ signal }) => apiFetch<DashboardResponse>("/dashboard", { signal }),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}

export function useProviders(country: string) {
  return useQuery({
    queryKey: queryKeys.providers(country),
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<ProviderList>(
        `/providers?country=${encodeURIComponent(country)}`,
        { signal },
      );
      return pageItems<Provider>(payload);
    },
  });
}

export function useSources() {
  return useQuery({
    queryKey: queryKeys.sources,
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<SourceList>("/sources", { signal });
      return pageItems<Source>(payload);
    },
  });
}

function collectionQueryString(filters: CollectionFilters): string {
  const params = new URLSearchParams();
  if (filters.providerId) params.set("provider_id", filters.providerId);
  if (filters.mediaType) params.set("media_type", filters.mediaType);
  if (filters.origin) params.set("origin", filters.origin);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.isActive) params.set("is_active", filters.isActive);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function useCollections(filters: CollectionFilters) {
  return useQuery({
    queryKey: queryKeys.collections(filters),
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<CollectionList>(
        `/collections${collectionQueryString(filters)}`,
        { signal },
      );
      return pageItems<Collection>(payload);
    },
  });
}

export function useGenres(mediaType: string) {
  return useQuery({
    queryKey: queryKeys.genres(mediaType),
    queryFn: ({ signal }) =>
      apiFetch<{ media_type: string; items: { id: number; name: string }[] }>(
        `/genres?media_type=${encodeURIComponent(mediaType)}`,
        { signal },
      ),
    staleTime: Infinity,
  });
}

export function useCollection(collectionId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.collection(collectionId ?? ""),
    queryFn: ({ signal }) =>
      apiFetch<Collection>(`/collections/${collectionId}`, { signal }),
    enabled: Boolean(collectionId),
  });
}

export function useCollectionSnapshots(collectionId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.collectionSnapshots(collectionId ?? ""),
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<SnapshotList>(
        `/collections/${collectionId}/snapshots`,
        { signal },
      );
      return pageItems<Snapshot>(payload);
    },
    enabled: Boolean(collectionId),
  });
}

export function useCollectionEpisodeEvents(
  collectionId: string | undefined,
  limit = 50,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.collectionEpisodeEvents(collectionId ?? "", limit),
    queryFn: ({ signal }) =>
      apiFetch<EpisodeEventList>(
        `/collections/${collectionId}/episode-events?limit=${limit}`,
        { signal },
      ),
    enabled: Boolean(collectionId) && enabled,
  });
}

export function useSnapshotItems(snapshotId: string | undefined, pageSize = 50) {
  return useQuery({
    queryKey: queryKeys.snapshotItems(snapshotId ?? ""),
    queryFn: ({ signal }) =>
      apiFetch<SnapshotItemList>(
        `/snapshots/${snapshotId}/items?page=1&page_size=${pageSize}`,
        { signal },
      ),
    enabled: Boolean(snapshotId),
  });
}

export function useTargets(mediaType?: string) {
  return useQuery({
    queryKey: queryKeys.targets(mediaType),
    queryFn: async ({ signal }) => {
      const query = mediaType ? `?media_type=${encodeURIComponent(mediaType)}` : "";
      const payload = await apiFetch<TargetList>(`/targets${query}`, { signal });
      return pageItems<Target>(payload);
    },
  });
}

export function useBindings() {
  return useQuery({
    queryKey: queryKeys.bindings,
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<BindingList>("/bindings", { signal });
      return pageItems<Binding>(payload);
    },
  });
}

export function useBinding(bindingId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.binding(bindingId ?? ""),
    queryFn: ({ signal }) =>
      apiFetch<Binding>(`/bindings/${bindingId}`, { signal }),
    enabled: Boolean(bindingId),
  });
}

export function useRuns(filters: RunFilters) {
  return useQuery({
    queryKey: queryKeys.runs(filters),
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams();
      if (filters.providerId) params.set("provider_id", filters.providerId);
      if (filters.status) params.set("status", filters.status);
      if (filters.mediaType) params.set("media_type", filters.mediaType);
      params.set("page_size", "100");
      const payload = await apiFetch<{ items: Run[]; total: number }>(
        `/runs?${params.toString()}`,
        { signal },
      );
      return payload;
    },
  });
}

export function usePreview(previewId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.preview(previewId ?? ""),
    queryFn: ({ signal }) =>
      apiFetch<Preview>(`/previews/${previewId}`, { signal }),
    enabled: Boolean(previewId),
    refetchInterval: (query) =>
      query.state.data?.state === "RUNNING" ? 2_000 : false,
    refetchIntervalInBackground: false,
  });
}

export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.run(runId ?? ""),
    queryFn: ({ signal }) => apiFetch<Run>(`/runs/${runId}`, { signal }),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      isActiveRun(query.state.data?.status) ? 2_000 : false,
    refetchIntervalInBackground: false,
    // docs/phase1/07-frontend-api.md §2.4: il refresh al focus è attivo solo per i
    // run in corso, così tornando sul tab lo stato non resta indietro fino al tick.
    refetchOnWindowFocus: true,
  });
}

export function useRunOperations(runId: string | undefined, runIsActive = false) {
  return useQuery({
    queryKey: queryKeys.runOperations(runId ?? ""),
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<OperationList>(
        `/runs/${runId}/operations`,
        { signal },
      );
      return pageItems<Operation>(payload);
    },
    enabled: Boolean(runId),
    refetchInterval: runIsActive ? 2_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
}

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: async ({ signal }): Promise<AppSettings> => {
      const payload = await apiFetch<SettingsOut>("/settings", { signal });
      return settingsFromItems(payload.items);
    },
  });
}

export function useNotificationChannels() {
  return useQuery({
    queryKey: queryKeys.notificationChannels,
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<NotificationChannelList>(
        "/notifications/channels",
        { signal },
      );
      return pageItems<NotificationChannel>(payload);
    },
  });
}

/**
 * `GET /api/system/status` è in rollout: un 404 (endpoint non ancora presente)
 * significa "stato sconosciuto", non un errore da mostrare all'utente.
 */
export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: async ({ signal }): Promise<SystemStatus | null> => {
      try {
        return await apiFetch<SystemStatus>("/system/status", { signal });
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useCredentials() {
  return useQuery({
    queryKey: queryKeys.credentials,
    queryFn: async ({ signal }) => {
      const payload = await apiFetch<CredentialList>("/credentials", { signal });
      return pageItems<Credential>(payload);
    },
  });
}
