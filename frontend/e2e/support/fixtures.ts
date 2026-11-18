import type {
  Binding,
  Collection,
  DashboardResponse,
  NotificationChannel,
  Provider,
  Run,
  SessionResponse,
  SettingsOut,
  SystemStatus,
  Target,
  User,
} from "../../src/api/types";
import { errorEnvelope, type ApiMock } from "./api-mock";

export const CSRF_TOKEN = "csrf-e2e-token";

export const USER: User = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "admin@example.com",
  is_admin: true,
  created_at: "2026-01-01T08:00:00Z",
  last_login_at: "2026-01-02T08:00:00Z",
};

export const SESSION: SessionResponse = { user: USER, csrf_token: CSRF_TOKEN };

export const UNAUTHORIZED = errorEnvelope("AUTH_UNAUTHENTICATED", "AUTH", "Non autenticato.");

export const PROVIDER_NETFLIX: Provider = {
  id: "22222222-2222-4222-8222-222222222221",
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
  collections_count: 1,
  movie_collections: 1,
  show_collections: 0,
};

export const PROVIDER_PRIME: Provider = {
  id: "22222222-2222-4222-8222-222222222222",
  slug: "amazon-prime-video",
  name: "Amazon Prime Video",
  kind: "FLATRATE",
  logo_url: null,
  website_url: null,
  country_code: "IT",
  tmdb_provider_id: "119",
  tmdb_provider_id_movie: "119",
  tmdb_provider_id_tv: "119",
  mapping_verified: true,
  mapping_verified_movie: true,
  mapping_verified_tv: true,
  collections_count: 1,
  movie_collections: 1,
  show_collections: 0,
};

export const GENRES = {
  media_type: "MOVIE",
  items: [
    { id: 28, name: "Azione" },
    { id: 12, name: "Avventura" },
    { id: 878, name: "Fantascienza" },
  ],
};

export const SOURCE_COLLECTION_NETFLIX: Collection = {
  id: "33333333-3333-4333-8333-333333333331",
  slug: "netflix-film-azione",
  name: "Netflix film azione",
  provider_id: PROVIDER_NETFLIX.id,
  provider_slug: PROVIDER_NETFLIX.slug,
  provider_name: PROVIDER_NETFLIX.name,
  source_id: "44444444-4444-4444-8444-444444444441",
  source_key: "tmdb",
  country_code: "IT",
  media_type: "MOVIE",
  kind: "CATALOG",
  origin: "OFFICIAL",
  date_basis: "PROVIDER_OFFICIAL",
  description: null,
  filters: { with_genres: "28" },
  quality_flags: {},
  provider_names: [PROVIDER_NETFLIX.name],
  is_local_filter: false,
  is_multi_provider: false,
  offer_types: ["FLATRATE"],
  sort_mode: "provider",
  is_active: true,
  last_valid_snapshot_id: null,
  latest_snapshot: null,
  last_valid_snapshot: null,
};

export const SOURCE_COLLECTION_PRIME: Collection = {
  ...SOURCE_COLLECTION_NETFLIX,
  id: "33333333-3333-4333-8333-333333333332",
  slug: "prime-film-azione",
  name: "Prime film azione",
  provider_id: PROVIDER_PRIME.id,
  provider_slug: PROVIDER_PRIME.slug,
  provider_name: PROVIDER_PRIME.name,
  provider_names: [PROVIDER_PRIME.name],
};

export const TARGET: Target = {
  id: "55555555-5555-4555-8555-555555555551",
  remote_list_id: "9012",
  remote_slug: "azione-combinata",
  remote_url: "https://mdblist.com/lists/e2e/azione-combinata",
  name: "Azione combinata",
  mediatype: "MOVIE",
  private: true,
  item_count: 40,
  last_verified_at: "2026-01-02T09:00:00Z",
  last_remote_read_at: "2026-01-02T09:00:00Z",
  capabilities: {},
};

export const BINDING: Binding = {
  id: "66666666-6666-4666-8666-666666666661",
  collection_id: SOURCE_COLLECTION_NETFLIX.id,
  target_id: TARGET.id,
  collection: SOURCE_COLLECTION_NETFLIX,
  target: TARGET,
  media_type: "MOVIE",
  mode: "MIRROR",
  schedule: "MANUAL",
  schedule_time: null,
  schedule_cron: "0 4 * * *",
  schedule_interval_hours: null,
  max_removal_pct: 10,
  max_removal_abs: 50,
  max_remove_count: 50,
  max_remove_percent: 10,
  thresholds: { max_removal_pct: 10, max_removal_abs: 50 },
  preserve_order: false,
  reorder_enabled: false,
  schedule_policy: "ALWAYS_APPROVE",
  require_review: true,
  enabled: true,
  policy_version: "planning-v1",
  policy_accepted_at: "2026-01-02T09:00:00Z",
  created_at: "2026-01-02T09:00:00Z",
  next_run_at: null,
  last_run_id: null,
};

export const DRY_RUN_ID = "77777777-7777-4777-8777-777777777771";

export const TO_ADD_SAMPLE = ["Dune: Parte due", "Oppenheimer", "Il cavaliere oscuro"];
export const TO_REMOVE_SAMPLE = ["Vecchio titolo A", "Vecchio titolo B"];

/** Dry-run concluso: nessuna scrittura remota, diff e soglie già calcolate. */
export const DRY_RUN: Run = {
  id: DRY_RUN_ID,
  binding_id: BINDING.id,
  target_id: TARGET.id,
  status: "SUCCEEDED",
  mode: "MIRROR",
  is_dry_run: true,
  trigger: "MANUAL",
  snapshot_id: "88888888-8888-4888-8888-888888888881",
  plan_hash: "plan-hash-e2e",
  snapshot_hash: "snapshot-hash-e2e",
  order_enforced: true,
  warnings: [],
  counters: {
    planned: 5,
    applied: 0,
    skipped: 0,
    not_found: 0,
    failed: 0,
    uncertain: 0,
  },
  source_item_count: 40,
  remote_item_count: 40,
  to_add_count: 3,
  to_remove_count: 2,
  added_count: 0,
  removed_count: 0,
  failed_count: 0,
  uncertain_count: 0,
  threshold_breached: false,
  requires_approval: false,
  approved_at: null,
  started_at: "2026-01-02T10:00:00Z",
  finished_at: "2026-01-02T10:00:05Z",
  abort_reason: null,
  error_code: null,
  error_message: null,
  summary: {
    to_add_count: 3,
    to_remove_count: 2,
    unchanged_count: 35,
    unresolved_count: 1,
    thresholds: {
      breached: false,
      reasons: [],
      observed_removals: 2,
      observed_additions: 3,
      remote_count: 40,
      max_removal_absolute: 50,
      max_removal_percent: 10,
      max_addition_percent: 50,
    },
    to_add_sample: TO_ADD_SAMPLE,
    to_remove_sample: TO_REMOVE_SAMPLE,
  },
  collection_name: SOURCE_COLLECTION_NETFLIX.name,
  provider_name: PROVIDER_NETFLIX.name,
  target_name: TARGET.name,
  idempotency_key: null,
  reconcile_required: false,
  parent_run_id: null,
  created_at: "2026-01-02T10:00:00Z",
};

export const NOTIFICATION_EVENTS = [
  "RUN_PENDING_APPROVAL",
  "RUN_FAILED",
  "RUN_UNCERTAIN",
  "AUTH_ERROR",
  "SUMMARY",
];

export function notificationChannel(overrides: Partial<NotificationChannel> = {}): NotificationChannel {
  return {
    id: "99999999-9999-4999-8999-999999999991",
    name: "Webhook Ops",
    kind: "WEBHOOK",
    enabled: true,
    events: [...NOTIFICATION_EVENTS],
    config: {},
    secret_configured: true,
    masked_hint: "https://hooks…/abc",
    last_sent_at: null,
    last_status: null,
    last_error: null,
    retry_count: 0,
    next_retry_at: null,
    created_at: "2026-01-02T09:00:00Z",
    updated_at: "2026-01-02T09:00:00Z",
    ...overrides,
  };
}

export const SETTINGS: SettingsOut = {
  items: [
    { key: "app_timezone", value: "Europe/Rome", description: "Fuso orario", updated_at: null },
    { key: "sync_batch_size", value: 100, description: "Batch", updated_at: null },
    {
      key: "sync_max_removal_absolute",
      value: 50,
      description: "Soglia assoluta",
      updated_at: null,
    },
    {
      key: "sync_max_removal_percent",
      value: 10,
      description: "Soglia percentuale",
      updated_at: null,
    },
    {
      key: "sync_max_addition_percent",
      value: 50,
      description: "Soglia aggiunte",
      updated_at: null,
    },
    {
      key: "notifications_summary_enabled",
      value: false,
      description: "Riepilogo",
      updated_at: null,
    },
    { key: "notifications_summary_hour", value: 8, description: "Ora riepilogo", updated_at: null },
  ],
};

export const DASHBOARD: DashboardResponse = {
  counters: {
    media: 1280,
    collections: 2,
    valid_snapshots: 2,
    providers: 2,
    bindings: 1,
  },
  alerts: [],
  recent_snapshots: [],
  recent_jobs: [],
  recent_sync_runs: [],
  sources: [],
  api_usage: {
    tmdb: { hour: 0, today: 12, estimated_per_hour: 0, estimated_per_day: 100 },
    mdblist: { hour: 0, today: 3, estimated_per_hour: 0, estimated_per_day: 24 },
    active_bindings: 1,
  },
};

export const SYSTEM_STATUS: SystemStatus = {
  health: { api: true, database: true, redis: true, worker: true, tmdb: "OK", mdblist: "OK" },
  queues: {},
  runs: {},
  api_usage: {},
  backup: {
    status: "ok",
    message: null,
    last_valid_at: "2026-01-02T03:00:00Z",
    last_backup_at: "2026-01-02T03:00:00Z",
    next_backup_at: "2026-01-03T03:00:00Z",
    age_hours: 7,
    size_bytes: 2048,
    file: "backup.sql.gz",
    error: null,
  },
  pending_approvals: 0,
  upcoming: [],
  version: "0.1.0",
  environment: "test",
};

/**
 * Configurazione esportabile: provider, collezioni, binding e impostazioni,
 * senza credenziali (l'export non deve contenere segreti).
 */
export const CONFIG_EXPORT = {
  version: 1,
  exported_at: "2026-01-02T12:00:00Z",
  providers: [
    {
      slug: PROVIDER_NETFLIX.slug,
      name: PROVIDER_NETFLIX.name,
      kind: PROVIDER_NETFLIX.kind,
      country_code: PROVIDER_NETFLIX.country_code,
      tmdb_provider_id: PROVIDER_NETFLIX.tmdb_provider_id,
      mapping_verified: true,
    },
    {
      slug: PROVIDER_PRIME.slug,
      name: PROVIDER_PRIME.name,
      kind: PROVIDER_PRIME.kind,
      country_code: PROVIDER_PRIME.country_code,
      tmdb_provider_id: PROVIDER_PRIME.tmdb_provider_id,
      mapping_verified: true,
    },
  ],
  collections: [
    {
      slug: SOURCE_COLLECTION_NETFLIX.slug,
      name: SOURCE_COLLECTION_NETFLIX.name,
      provider_slug: PROVIDER_NETFLIX.slug,
      media_type: "MOVIE",
      kind: "CATALOG",
      filters: { with_genres: "28" },
    },
  ],
  bindings: [
    {
      collection_slug: SOURCE_COLLECTION_NETFLIX.slug,
      target_name: TARGET.name,
      media_type: "MOVIE",
      mode: "MIRROR",
      schedule: "MANUAL",
      thresholds: { max_removal_pct: 10, max_removal_abs: 50 },
    },
  ],
  settings: {
    app_timezone: "Europe/Rome",
    sync_batch_size: 100,
    sync_max_removal_absolute: 50,
    sync_max_removal_percent: 10,
    sync_max_addition_percent: 50,
  },
};

/** Sessione autenticata: la shell (`/app`) la richiede a ogni mount. */
export function mockAuthenticatedSession(api: ApiMock): void {
  api.json("GET", "/api/auth/session", SESSION);
}

/**
 * Endpoint letti dalla shell e dalla dashboard. Va registrato dopo le rotte
 * specifiche del test: la prima rotta registrata che combacia vince.
 */
export function mockAppShell(api: ApiMock): void {
  api.json("GET", "/api/dashboard", DASHBOARD);
  api.json("GET", "/api/system/status", SYSTEM_STATUS);
  api.json("GET", "/api/bindings", { items: [], total: 0, page: 1, page_size: 25, has_more: false });
  api.json("GET", "/api/runs", { items: [], total: 0, page: 1, page_size: 25, has_more: false });
}
