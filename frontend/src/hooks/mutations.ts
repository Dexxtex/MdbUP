import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import { queryKeys } from "../api/query-keys";
import { settingsFromItems, settingsPatch } from "../api/settings";
import type {
  AcquireOut,
  AppSettings,
  Binding,
  CombineMode,
  BindingThresholds,
  Collection,
  CollectionCreatePayload,
  CredentialKind,
  CredentialVerifyOut,
  JobAccepted,
  NotificationChannel,
  NotificationTestOut,
  OfferType,
  ProviderCreatePayload,
  PreviewAccepted,
  Provider,
  RunAccepted,
  SessionResponse,
  SettingsOut,
  SourceHealthcheck,
  Target,
  User,
} from "../api/types";

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface BootstrapPayload {
  token: string;
  email: string;
  password: string;
}

export interface CreateBindingPayload {
  collection_id: string;
  target_id: string;
  justwatch_policy_accepted: boolean;
  mode: string;
  schedule: string;
  schedule_time: string;
  thresholds: BindingThresholds;
  preserve_order: boolean;
  reorder_enabled: boolean;
  schedule_policy: string;
  require_review: boolean;
  enabled: boolean;
  policy_version: string;
}


export interface CollectionUpdatePayload {
  name?: string;
  source_key?: "tmdb" | "justwatch" | "combined";
  combine_mode?: CombineMode;
  kind?: string;
  offer_types?: OfferType[];
  genre_ids?: number[];
  exclude_genre_ids?: number[];
  monetization_type?: string;
  window_days?: number;
  source_collection_id?: string;
  source_collection_ids?: string[];
  shared_snapshot_collection_id?: string;
  min_vote_average?: number;
  min_vote_count?: number;
  year_from?: number;
  year_to?: number;
  original_language?: string;
  local_sort_by?: string;
  description?: string;
  is_active?: boolean;
}

export interface CreatePreviewPayload {
  collection_id: string;
  target_id?: string;
  mode?: string;
  thresholds?: BindingThresholds;
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LoginPayload) =>
      apiFetch<SessionResponse>("/auth/login", { method: "POST", body: payload }),
    onSuccess: (data) => {
      if (data?.user) {
        queryClient.setQueryData<SessionResponse>(queryKeys.session, {
          user: data.user,
          csrf_token: data.csrf_token,
        });
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.session });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      queryClient.clear();
    },
  });
}

export function useBootstrap() {
  return useMutation({
    mutationFn: (payload: BootstrapPayload) =>
      apiFetch<{ user: User }>("/auth/bootstrap", {
        method: "POST",
        body: payload,
      }),
  });
}

export function useAcquireCollection(collectionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<AcquireOut>(`/collections/${collectionId}/acquire`, {
        method: "POST",
        body: {},
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.collection(collectionId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.collectionSnapshots(collectionId),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections({}) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useCreateTarget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; private: boolean; media_type: string }) =>
      apiFetch<Target>("/targets", {
        method: "POST",
        body: { mode: "new", name: payload.name, private: payload.private, media_type: payload.media_type },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["targets"] });
    },
  });
}

export function useCreateProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProviderCreatePayload) =>
      apiFetch<Provider>("/providers", { method: "POST", body: payload }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["providers"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useDeleteProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (providerId: string) =>
      apiFetch<void>(`/providers/${providerId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["providers"] });
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      void queryClient.invalidateQueries({ queryKey: ["collection"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["catalog-changes"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
    },
  });
}

export function useDeleteCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (collectionId: string) =>
      apiFetch<void>(`/collections/${collectionId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      void queryClient.invalidateQueries({ queryKey: ["collection"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["catalog-changes"] });
      void queryClient.invalidateQueries({ queryKey: ["providers"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useCreateCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CollectionCreatePayload) =>
      apiFetch<Collection>("/collections", { method: "POST", body: payload }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useUpdateCollection(collectionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CollectionUpdatePayload) =>
      apiFetch<Collection>(`/collections/${collectionId}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.collection(collectionId) });
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useHealthcheckSource(sourceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<SourceHealthcheck>(`/sources/${sourceId}/healthcheck`, {
        method: "POST",
        body: {},
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useCreatePreview() {
  return useMutation({
    mutationFn: (payload: CreatePreviewPayload) =>
      apiFetch<PreviewAccepted>("/previews", { method: "POST", body: payload }),
  });
}

export function useCreateBinding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateBindingPayload) =>
      apiFetch<Binding>("/bindings", { method: "POST", body: payload }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export interface UpdateBindingPayload {
  mode?: string;
  schedule?: string;
  schedule_time?: string;
  schedule_interval_hours?: number;
  schedule_cron?: string;
  max_remove_count?: number;
  max_remove_percent?: number;
  enabled?: boolean;
  policy_version?: string;
  target_private?: boolean;
  schedule_policy?: string;
  require_review?: boolean;
  preserve_order?: boolean;
  reorder_enabled?: boolean;
}

export function useUpdateBinding(bindingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UpdateBindingPayload) =>
      apiFetch<Binding>(`/bindings/${bindingId}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.binding(bindingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
      void queryClient.invalidateQueries({ queryKey: ["targets"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useApproveRun(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { plan_hash: string; note?: string }) =>
      apiFetch<JobAccepted>(`/runs/${runId}/approve`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useCancelRun(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<JobAccepted>(`/runs/${runId}/cancel`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useStartRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { bindingId: string; dryRun: boolean }) =>
      apiFetch<RunAccepted>(`/bindings/${payload.bindingId}/runs`, {
        method: "POST",
        body: {
          dry_run: payload.dryRun,
          idempotency_key: newIdempotencyKey(),
        },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<AppSettings>): Promise<AppSettings> => {
      const response = await apiFetch<SettingsOut>("/settings", {
        method: "PATCH",
        body: settingsPatch(payload),
      });
      return settingsFromItems(response.items);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.settings, data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export interface NotificationChannelPayload {
  name: string;
  kind: string;
  secret?: string;
  events: string[];
  config: Record<string, unknown>;
  enabled: boolean;
}

export function useCreateNotificationChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: NotificationChannelPayload) =>
      apiFetch<NotificationChannel>("/notifications/channels", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notificationChannels });
    },
  });
}

export function useUpdateNotificationChannel(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<NotificationChannelPayload>) =>
      apiFetch<NotificationChannel>(`/notifications/channels/${channelId}`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notificationChannels });
    },
  });
}

export function useDeleteNotificationChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) =>
      apiFetch<void>(`/notifications/channels/${channelId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notificationChannels });
    },
  });
}

export function useTestNotificationChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) =>
      apiFetch<NotificationTestOut>(`/notifications/channels/${channelId}/test`, {
        method: "POST",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notificationChannels });
    },
  });
}

export function useSaveCredential(kind: CredentialKind) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (apiKey: string) =>
      apiFetch<void>(`/credentials/${kind}`, {
        method: "PUT",
        // Il backend accetta `CredentialSecretIn.value` (non `api_key`).
        body: { value: apiKey },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.credentials });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
    },
  });
}

export function useDeleteCredential(kind: CredentialKind) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`/credentials/${kind}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.credentials });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
    },
  });
}

export function useVerifyCredential(kind: CredentialKind) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<CredentialVerifyOut>(`/credentials/${kind}/verify`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.credentials });
    },
  });
}
