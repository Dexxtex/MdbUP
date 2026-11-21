import type {
  Binding,
  CatalogChangeResponse,
  Collection,
  DashboardResponse,
  EpisodeEventList,
  NotificationChannel,
  Preview,
  Provider,
  Run,
  SessionResponse,
  SettingsOut,
  Snapshot,
  SnapshotItem,
  Source,
  SourceList,
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
  justwatch_provider_id: "8",
  justwatch_verified: true,
  justwatch_movie_verified: true,
  justwatch_tv_verified: true,
  justwatch_monetization_types: ["FLATRATE"],
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
  justwatch_provider_id: "119",
  justwatch_verified: true,
  justwatch_movie_verified: true,
  justwatch_tv_verified: true,
  justwatch_monetization_types: ["FLATRATE"],
  collections_count: 1,
  movie_collections: 1,
  show_collections: 0,
};

export const PROVIDER_APPLE_TV: Provider = {
  id: "22222222-2222-4222-8222-222222222223",
  slug: "apple-tv-plus",
  name: "Apple TV+",
  kind: "FLATRATE",
  logo_url: null,
  website_url: null,
  country_code: "IT",
  tmdb_provider_id: "350",
  tmdb_provider_id_movie: "350",
  tmdb_provider_id_tv: "350",
  mapping_verified: true,
  mapping_verified_movie: true,
  mapping_verified_tv: true,
  justwatch_provider_id: "2243",
  justwatch_verified: true,
  justwatch_movie_verified: true,
  justwatch_tv_verified: true,
  justwatch_monetization_types: ["FLATRATE"],
  collections_count: 1,
  movie_collections: 1,
  show_collections: 0,
};

/**
 * Mapping TMDb verificato ma nessun package JustWatch: il builder JustWatch
 * deve escluderlo (`hasJustWatchMapping`).
 */
export const PROVIDER_PARAMOUNT_UNMAPPED: Provider = {
  id: "22222222-2222-4222-8222-222222222224",
  slug: "paramount-plus",
  name: "Paramount+",
  kind: "FLATRATE",
  logo_url: null,
  website_url: null,
  country_code: "IT",
  tmdb_provider_id: "531",
  tmdb_provider_id_movie: "531",
  tmdb_provider_id_tv: "531",
  mapping_verified: true,
  mapping_verified_movie: true,
  mapping_verified_tv: true,
  justwatch_provider_id: null,
  justwatch_verified: false,
  justwatch_movie_verified: false,
  justwatch_tv_verified: false,
  justwatch_monetization_types: [],
  collections_count: 0,
  movie_collections: 0,
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

/* Fase 8 — fonte JustWatch: aggregatore, nessuna data ufficiale di aggiunta. */

const SOURCE_TMDB: Source = {
  id: "44444444-4444-4444-8444-444444444441",
  key: "tmdb",
  name: "TMDb",
  type: "API",
  base_url: "https://api.themoviedb.org/3",
  status: "OK",
  status_message: null,
  is_official: true,
  origin_default: "OFFICIAL",
  requires_contract: true,
  capabilities: {
    catalog: true,
    recently_added: true,
    charts: false,
    added_dates: true,
    full_pagination: true,
    requires_credentials: true,
  },
  credential_configured: true,
  connector_available: true,
  justwatch: null,
  last_healthcheck_at: "2026-01-02T08:30:00Z",
  last_success_at: "2026-01-02T08:30:00Z",
};

const SOURCE_JUSTWATCH: Source = {
  id: "44444444-4444-4444-8444-444444444442",
  key: "justwatch",
  name: "JustWatch",
  type: "API",
  base_url: "https://apis.justwatch.com",
  status: "OK",
  status_message: null,
  is_official: false,
  origin_default: "AGGREGATOR",
  requires_contract: false,
  capabilities: {
    catalog: true,
    recently_added: true,
    upcoming: true,
    charts: true,
    ordering: false,
    added_dates: false,
    seasons_episodes: true,
    full_pagination: true,
    requires_credentials: false,
  },
  credential_configured: false,
  connector_available: true,
  justwatch: {
    throttle_ms: 1000,
    cache_ttl_seconds: 300,
    cache_max_entries: 500,
    cache_hits: 12,
    cache_misses: 3,
    requests_hour: 4,
    requests_today: 41,
    mappings: [
      {
        provider_slug: PROVIDER_APPLE_TV.slug,
        provider_name: PROVIDER_APPLE_TV.name,
        external_id: PROVIDER_APPLE_TV.justwatch_provider_id ?? null,
        technical_name: "apple_tv_plus",
        clear_name: "Apple TV Plus",
        monetization_types: [...PROVIDER_APPLE_TV.justwatch_monetization_types],
        collections_count: 1,
      },
    ],
    supported_kinds: ["CATALOG", "RECENTLY_ADDED", "UPCOMING", "CHART"],
    supported_offer_types: ["FLATRATE"],
  },
  last_healthcheck_at: "2026-01-02T08:30:00Z",
  last_success_at: "2026-01-02T08:30:00Z",
};

const SOURCES: SourceList = { items: [SOURCE_TMDB, SOURCE_JUSTWATCH] };

export const JUSTWATCH_SNAPSHOT_ID = "88888888-8888-4888-8888-888888888882";

export const JUSTWATCH_SNAPSHOT: Snapshot = {
  id: JUSTWATCH_SNAPSHOT_ID,
  status: "COMPLETE",
  quality: "CLEAN",
  is_valid: true,
  started_at: "2026-01-03T04:00:00Z",
  finished_at: "2026-01-03T04:02:00Z",
  pages_expected: 1,
  pages_fetched: 1,
  items_count: 42,
  resolved_count: 40,
  unresolved_count: 2,
  duplicate_count: 0,
  error_count: 0,
  checksum: "checksum-justwatch-e2e",
  invalid_reason: null,
};

export const JUSTWATCH_ITEM: SnapshotItem = {
  position: 1,
  media_id: "99999999-9999-4999-8999-999999999991",
  media_type: "MOVIE",
  tmdb_id: 693134,
  imdb_id: null,
  title: "Dune: Parte due",
  release_year: 2024,
  resolution_status: "RESOLVED",
  resolution_error: null,
  source_item_id: "jw-movie-693134",
  date_basis: "UNKNOWN",
  source_date_created: null,
  availability_status: "CURRENT",
  source_offer_types: ["FLATRATE"],
};

export const JUSTWATCH_COLLECTION_ID = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1";

/**
 * Collezione JustWatch: `source_label` è l'attribuzione calcolata dal backend
 * (aggregatore per CATALOG/RECENTLY_ADDED/UPCOMING, classifica per CHART).
 */
export function justwatchCollection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: JUSTWATCH_COLLECTION_ID,
    slug: "justwatch-apple-tv-film",
    name: "Apple TV+ film",
    provider_id: PROVIDER_APPLE_TV.id,
    provider_slug: PROVIDER_APPLE_TV.slug,
    provider_name: PROVIDER_APPLE_TV.name,
    source_id: SOURCE_JUSTWATCH.id,
    source_key: "justwatch",
    country_code: "IT",
    media_type: "MOVIE",
    kind: "CATALOG",
    origin: "AGGREGATOR",
    date_basis: "UNKNOWN",
    source_label: "Fonte: JustWatch (Aggregatore)",
    description: null,
    filters: {},
    quality_flags: {},
    provider_names: [PROVIDER_APPLE_TV.name],
    is_local_filter: false,
    is_multi_provider: false,
    offer_types: ["FLATRATE"],
    sort_mode: "provider",
    is_active: true,
    last_valid_snapshot_id: JUSTWATCH_SNAPSHOT_ID,
    latest_snapshot: JUSTWATCH_SNAPSHOT,
    last_valid_snapshot: JUSTWATCH_SNAPSHOT,
    ...overrides,
  };
}

export const JUSTWATCH_PREVIEW_ID = "dddddddd-dddd-4ddd-8ddd-ddddddddddd1";

/** Preview source-only: nessun target MDBList, solo il piano dalla fonte. */
export function justwatchPreview(overrides: Partial<Preview> = {}): Preview {
  return {
    id: JUSTWATCH_PREVIEW_ID,
    state: "READY",
    counts: {
      to_add: 12,
      to_remove: 0,
      unchanged: 30,
      unresolved: 2,
      unmapped_remote: 0,
      remote_duplicates: 0,
    },
    blocked: null,
    sample: {},
    snapshot_id: JUSTWATCH_SNAPSHOT_ID,
    snapshot_hash: "snapshot-hash-justwatch-e2e",
    plan_hash: "plan-hash-justwatch-e2e",
    order_enforced: false,
    generated_at: "2026-01-03T05:00:00Z",
    warnings: [],
    ...overrides,
  };
}

export const JUSTWATCH_EPISODE_EVENTS: EpisodeEventList = {
  items: [
    {
      media_id: "99999999-9999-4999-8999-999999999992",
      title: "Severance",
      event_type: "SEASON_ADDED",
      season_number: 2,
      episode_number: null,
      occurred_at: "2026-01-03T04:01:00Z",
      source_key: "justwatch",
    },
    {
      media_id: "99999999-9999-4999-8999-999999999992",
      title: "Severance",
      event_type: "EPISODE_ADDED",
      season_number: 2,
      episode_number: 3,
      occurred_at: "2026-01-03T04:01:00Z",
      source_key: "justwatch",
    },
  ],
  total: 2,
};

const TARGET: Target = {
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
    { key: "default_source", value: "justwatch", description: "Fonte predefinita", updated_at: null },
    {
      key: "catalog_schedule_enabled",
      value: true,
      description: "Pianificazione catalogo",
      updated_at: null,
    },
  ],
};

export const CATALOG_CHANGES: CatalogChangeResponse = {
  items: [
    {
      media_id: "acacacac-acac-4cac-8cac-acacacacacac",
      title: "Dune: Parte due",
      year: 2024,
      media_type: "MOVIE",
      provider_id: PROVIDER_NETFLIX.id,
      provider_slug: PROVIDER_NETFLIX.slug,
      provider_name: PROVIDER_NETFLIX.name,
      source_key: "justwatch",
      source_label: "Fonte: JustWatch (Aggregatore)",
      direction: "ADDED",
      detected_at: "2026-01-03T04:02:00Z",
      detected_at_rome: "2026-01-03T05:02:00+01:00",
      collection_id: JUSTWATCH_COLLECTION_ID,
      collection_name: "Apple TV+ film",
      collection_slug: "justwatch-apple-tv-film",
      previous_snapshot_id: "88888888-8888-4888-8888-888888888881",
      current_snapshot_id: JUSTWATCH_SNAPSHOT_ID,
      season_number: null,
      episode_number: null,
      episode_event_type: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
  window: "24h",
  generated_at: "2026-01-03T05:00:00Z",
  counters: {
    added_today: 42,
    removed_today: 18,
    added_window: 42,
    removed_window: 18,
  },
};

const DASHBOARD: DashboardResponse = {
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

const SYSTEM_STATUS: SystemStatus = {
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
  catalog_acquisitions: [
    {
      collection_id: JUSTWATCH_COLLECTION_ID,
      collection_name: "Apple TV+ film",
      provider_name: PROVIDER_APPLE_TV.name,
      next_acquire_at: "2026-01-03T06:00:00Z",
    },
  ],
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

/**
 * `GET /api/sources`: il builder lo legge per i mapping JustWatch verificati.
 * Va registrato prima di `mockAppShell` come le altre rotte specifiche.
 */
export function mockSources(api: ApiMock): void {
  api.json("GET", "/api/sources", SOURCES);
}

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
  api.json("GET", "/api/sources", SOURCES);
  api.json("GET", "/api/catalog-changes", CATALOG_CHANGES);
  api.json("GET", "/api/settings", SETTINGS);
  api.json("GET", "/api/bindings", { items: [], total: 0, page: 1, page_size: 25, has_more: false });
  api.json("GET", "/api/runs", { items: [], total: 0, page: 1, page_size: 25, has_more: false });
}
