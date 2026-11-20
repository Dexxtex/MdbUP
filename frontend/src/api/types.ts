/**
 * Tipi delle risposte API.
 *
 * I payload sono generati dal backend in `schema.d.ts` (`npm run api:generate`
 * da `openapi.json`): qui si esportano gli alias usati dalla UI, così un campo
 * inventato non compila. Restano scritti a mano solo:
 * - le enumerazioni che il backend serializza come `str` (`app/domain/enums.py`);
 * - le righe `dict` della dashboard, prodotte da `app/services/dashboard.py`;
 * - `AppSettings`, la forma piatta usata dai form.
 */

import type { components } from "./schema";

type Schemas = components["schemas"];

/* Enumerazioni presenti nello schema OpenAPI. */
export type MediaType = Schemas["MediaType"];
export type CollectionOrigin = Schemas["CollectionOrigin"];
export type CollectionKind = Schemas["CollectionKind"];

/* Enumerazioni serializzate come `str` dal backend (app/domain/enums.py). */
export type DateBasis =
  | "PROVIDER_OFFICIAL"
  | "AGGREGATOR_FIRST_SEEN"
  | "APP_FIRST_SEEN"
  | "UNKNOWN";

export type OfferType = "FLATRATE" | "RENT" | "BUY" | "ADS" | "FREE";

export type SnapshotStatus =
  | "RUNNING"
  | "COMPLETE"
  | "INCOMPLETE"
  | "FAILED"
  | "CANCELLED";

export type SnapshotQuality = "CLEAN" | "WARNINGS" | "ANOMALY";

export type SourceStatus =
  | "UNCONFIGURED"
  | "OK"
  | "DEGRADED"
  | "ERROR"
  | "DISABLED";

type SourceType = "API" | "DATA_EXPORT" | "MANUAL_CSV";

type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "RETRY"
  | "CANCELLED";

/* Sync: target, binding, preview, run (`app/api/schemas_sync.py`). */
export type SyncMode = Schemas["SyncMode"];
export type RunStatus = Schemas["SyncRunStatus"];
type OperationAction = Schemas["SyncOperationAction"];
export type OperationStatus = Schemas["SyncOperationStatus"];
export type ScheduleFrequency = "MANUAL" | "DAILY" | "WEEKLY" | "INTERVAL" | "CRON";

/** `CredentialOut.kind` è una stringa: i valori sono quelli di `CredentialKind`. */
export type CredentialKind = "TMDB" | "MDBLIST" | "TVDB" | "JUSTWATCH";

export type CredentialStatus = Schemas["CredentialOut"]["status"];

/** `DashboardAlertOut.severity`: il backend usa minuscole. */
export type AlertSeverity = "info" | "warning" | "error";

/** Categorie dell'envelope errore; `NETWORK` è aggiunta solo dal client. */
export type ErrorCategory =
  | "AUTH"
  | "VALIDATION"
  | "SOURCE"
  | "TARGET"
  | "POLICY"
  | "CONFLICT"
  | "INTERNAL"
  | "NETWORK";

export interface ErrorEnvelope {
  error: {
    code: string;
    category: ErrorCategory;
    message: string;
    retryable: boolean;
    retry_after_s?: number;
    request_id?: string;
    details?: Record<string, unknown>;
  };
}

/* Auth (`app/api/schemas.py`). */
export type User = Schemas["UserOut"];
export type SessionResponse = Schemas["SessionOut"];

/* Provider (`app/api/schemas_catalog.py`). */
/**
 * Fase 9 aggiunge la verifica JustWatch per media type. I campi sono opzionali
 * nel tipo UI per retrocompatibilità con fixture e backend precedenti;
 * `justwatch_verified` resta il fallback.
 */
export type Provider = Omit<
  Schemas["ProviderOut"],
  "justwatch_movie_verified" | "justwatch_tv_verified"
> & {
  justwatch_movie_verified?: boolean;
  justwatch_tv_verified?: boolean;
  tvdb_company_id?: string | null;
};
export type ProviderList = Schemas["ProviderListOut"];

/**
 * `SourceOut.justwatch` è un dizionario libero nel contratto OpenAPI. I campi
 * tipizzati sono quelli prodotti da `app/services/sources.py`; il backend
 * include solo i mapping verificati, senza un flag per riga.
 */
interface JustWatchMapping {
  provider_slug: string;
  provider_name: string;
  external_id: string | null;
  technical_name: string | null;
  clear_name: string | null;
  monetization_types: string[];
  collections_count: number;
}

interface JustWatchSourceInfo {
  throttle_ms: number | null;
  cache_ttl_seconds: number | null;
  cache_max_entries: number | null;
  cache_hits: number;
  cache_misses: number;
  requests_hour: number;
  requests_today: number;
  mappings: JustWatchMapping[];
  supported_kinds: string[];
  supported_offer_types: string[];
}

/**
 * `SourceOut.capabilities` è un dizionario libero: qui le chiavi note
 * (docs/phases/phase-01.md §4.3).
 */
interface SourceCapabilities {
  catalog?: boolean;
  recently_added?: boolean;
  upcoming?: boolean;
  charts?: boolean;
  ordering?: boolean;
  added_dates?: boolean;
  seasons_episodes?: boolean;
  full_pagination?: boolean;
  data_export?: boolean;
  requires_credentials?: boolean;
  requires_contract?: boolean;
}

/**
 * Il backend dichiara queste colonne come `str` in OpenAPI, ma i valori sono
 * quelli di `app/domain/enums.py`: la UI li restringe una volta qui.
 */
export type Source = Omit<
  Schemas["SourceOut"],
  "status" | "type" | "origin_default" | "capabilities" | "justwatch"
> & {
  status: SourceStatus;
  type: SourceType;
  origin_default: CollectionOrigin;
  capabilities: SourceCapabilities;
  justwatch?: JustWatchSourceInfo | null;
};
export type SourceList = Omit<Schemas["SourceListOut"], "items"> & {
  items: Source[];
};

/* Collezioni e snapshot (`app/api/schemas_catalog.py`). */
export type Snapshot = Omit<Schemas["SnapshotOut"], "status" | "quality"> & {
  status: SnapshotStatus;
  quality: SnapshotQuality;
};
export type SnapshotList = Omit<Schemas["SnapshotListOut"], "items"> & {
  items: Snapshot[];
};
type AvailabilityStatus = "CURRENT" | "UPCOMING" | "LEAVING";

/** Fonte predefinita del builder, persistita in `settings.default_source`. */
export type DefaultSource = "justwatch" | "tmdb";

/** Fonte selezionabile nel builder: TMDb, JustWatch o combinata locale. */
export type BuilderSource = "tmdb" | "justwatch" | "combined";

/** Modalità di combinazione per `source_key=combined`. */
export type CombineMode = "UNION" | "INTERSECTION";

export type SnapshotItem = Omit<
  Schemas["SnapshotItemOut"],
  "availability_status" | "date_basis"
> & {
  availability_status?: AvailabilityStatus | null;
  date_basis: DateBasis;
};
export type SnapshotItemList = Omit<Schemas["SnapshotItemListOut"], "items"> & {
  items: SnapshotItem[];
};

export type EpisodeEventType =
  | "SEASON_ADDED"
  | "SEASON_REMOVED"
  | "EPISODE_ADDED"
  | "EPISODE_REMOVED";

export type EpisodeEvent = Omit<Schemas["EpisodeEventOut"], "event_type"> & {
  event_type: EpisodeEventType;
};
export type EpisodeEventList = Omit<Schemas["EpisodeEventListOut"], "items"> & {
  items: EpisodeEvent[];
};

export type Collection = Omit<
  Schemas["CollectionOut"],
  | "media_type"
  | "kind"
  | "origin"
  | "date_basis"
  | "offer_types"
  | "latest_snapshot"
  | "last_valid_snapshot"
> & {
  media_type: MediaType;
  kind: CollectionKind;
  origin: CollectionOrigin;
  date_basis: DateBasis;
  /** Attribuzione calcolata dal backend (es. "Classifica JustWatch"). */
  source_label?: string | null;
  offer_types: OfferType[];
  latest_snapshot?: Snapshot | null;
  last_valid_snapshot?: Snapshot | null;
};
export type CollectionList = Omit<Schemas["CollectionListOut"], "items"> & {
  items: Collection[];
};

export type AcquireOut = Schemas["AcquireOut"];
export type SourceHealthcheck = Schemas["SourceHealthcheckOut"];

/* Cambi catalogo (`GET /api/catalog-changes`, Fase 9). */
export type CatalogChangeWindow = "24h" | "7d" | "14d" | "30d";

/** Enumerazione backend serializzata come stringa (stile enums.py). */
export type CatalogChangeDirection = "ADDED" | "REMOVED";

export interface CatalogChangeItem {
  id: string;
  media_id: string;
  title: string | null;
  year: number | null;
  media_type: MediaType;
  provider_id: string;
  provider_slug: string | null;
  provider_name: string;
  source_key: string;
  source_label: string;
  direction: CatalogChangeDirection;
  detected_at: string;
  detected_at_rome: string | null;
  collection_id: string | null;
  collection_name: string | null;
  collection_slug: string | null;
  previous_snapshot_id: string | null;
  current_snapshot_id: string | null;
  season_number: number | null;
  episode_number: number | null;
  episode_event_type: EpisodeEventType | null;
}

interface CatalogChangeCounters {
  added_today: number;
  removed_today: number;
  added_window: number;
  removed_window: number;
}

export interface CatalogChangeResponse {
  items: CatalogChangeItem[];
  total: number;
  page: number;
  page_size: number;
  window: CatalogChangeWindow;
  generated_at: string;
  counters: CatalogChangeCounters;
}

/* Dashboard (`app/api/schemas_catalog.py` + `app/services/dashboard.py`). */
type DashboardCounters = Schemas["DashboardOut"]["counters"];
export type DashboardAlert = Schemas["DashboardAlertOut"];

/** Riga di `DashboardOut.recent_snapshots`. */
export interface DashboardSnapshotRow {
  id: string;
  collection_id: string;
  status: SnapshotStatus;
  quality: SnapshotQuality;
  is_valid: boolean;
  items_count: number;
  started_at: string;
  finished_at: string | null;
}

/** Riga di `DashboardOut.recent_jobs`. */
export interface DashboardJobRow {
  id: string;
  task_name: string;
  status: JobStatus;
  created_at: string;
  finished_at: string | null;
  error_code: string | null;
}

/** Riga di `DashboardOut.recent_sync_runs`. */
export interface DashboardSyncRunRow {
  id: string;
  status: RunStatus;
  mode: SyncMode;
  media_type: MediaType;
  created_at: string;
  finished_at: string | null;
}

/** Riga di `DashboardOut.sources`. */
export interface DashboardSourceRow {
  id: string;
  key: string;
  name: string;
  status: SourceStatus;
  status_message: string | null;
  last_healthcheck_at: string | null;
}

export interface DashboardApiProviderUsage {
  hour: number;
  today: number;
  estimated_per_hour: number;
  estimated_per_day: number;
}

export interface DashboardResponse {
  counters: DashboardCounters;
  alerts: DashboardAlert[];
  recent_snapshots: DashboardSnapshotRow[];
  recent_jobs: DashboardJobRow[];
  recent_sync_runs: DashboardSyncRunRow[];
  sources: DashboardSourceRow[];
  api_usage: {
    tmdb: DashboardApiProviderUsage;
    mdblist: DashboardApiProviderUsage;
    active_bindings: number;
  };
}

/* Impostazioni e credenziali (`app/api/schemas.py`). */
export type SettingItem = Schemas["SettingItemOut"];
export type SettingsOut = Schemas["SettingsOut"];
export type SettingsPatchRequest = Schemas["SettingsPatchRequest"];

/**
 * Impostazioni applicative in forma piatta: è la forma usata da form e UI.
 * Il wire format è `SettingsOut.items` (vedi `settingsFromItems` in
 * `api/settings.ts`); le chiavi sono quelle di `SETTING_SPECS` del backend.
 */
export interface AppSettings {
  app_timezone?: string;
  default_source?: DefaultSource;
  catalog_schedule_enabled?: boolean;
  sync_batch_size?: number;
  sync_max_removal_absolute?: number;
  sync_max_removal_percent?: number;
  sync_max_addition_percent?: number;
  notifications_summary_enabled?: boolean;
  notifications_summary_hour?: number;
  [key: string]: unknown;
}

export type Credential = Schemas["CredentialOut"];
export type CredentialList = Omit<Schemas["CredentialListOut"], "items"> & {
  items: Credential[];
};
export type CredentialVerifyOut = Schemas["CredentialVerifyOut"];

/* Notifiche (`app/api/schemas_notifications.py`). */
export type NotificationKind = "WEBHOOK" | "TELEGRAM" | "DISCORD";
/**
 * `retry_count`/`next_retry_at` sono opzionali: il backend li espone quando il
 * canale ha una consegna in retry, quindi la UI non può assumerli sempre.
 */
export type NotificationChannel = Schemas["NotificationChannelOut"] & {
  retry_count?: number | null;
  next_retry_at?: string | null;
};
export type NotificationChannelList = Omit<
  Schemas["NotificationChannelListOut"],
  "items"
> & { items: NotificationChannel[] };
export type NotificationTestOut = Schemas["NotificationTestOut"];

/* Sync: target, binding, preview e run (`app/api/schemas_sync.py`). */
export type Target = Omit<Schemas["TargetOut"], "mediatype"> & {
  mediatype: MediaType;
};
export type TargetList = Omit<Schemas["TargetListOut"], "items"> & {
  items: Target[];
};

export interface BindingThresholds {
  max_removal_pct: number;
  max_removal_abs: number;
  max_remove_count?: number;
  max_remove_percent?: number;
  max_addition_pct?: number;
}

export type Binding = Omit<
  Schemas["BindingOut"],
  "collection" | "target" | "media_type" | "mode" | "schedule" | "schedule_policy"
> & {
  collection?: Collection | null;
  target?: Target | null;
  media_type: MediaType;
  mode: SyncMode;
  schedule: ScheduleFrequency;
  schedule_policy: "AUTO_APPLY_IF_SAFE" | "ALWAYS_APPROVE" | "DRY_RUN_ONLY";
};
export type BindingList = Omit<Schemas["BindingListOut"], "items"> & {
  items: Binding[];
};

export type Preview = Schemas["PreviewOut"];

/** Sottoinsieme tipizzato di `RunOut.summary` (`app/services/planning.py`). */
export interface RunThresholdSummary {
  breached?: boolean;
  reasons?: string[];
  removal_ratio?: number;
  addition_ratio?: number;
  observed_removals?: number;
  observed_additions?: number;
  remote_count?: number;
  max_removal_absolute?: number;
  max_removal_percent?: number;
  max_addition_percent?: number;
}

export interface RunSummary {
  blocked?: boolean;
  block_reason?: string | null;
  to_add_count?: number;
  to_remove_count?: number;
  unchanged_count?: number;
  unresolved_count?: number;
  thresholds?: RunThresholdSummary;
  to_add_sample?: string[];
  to_remove_sample?: string[];
  unresolved_sample?: unknown[];
  unmapped_remote_sample?: string[];
  remote_duplicates_sample?: string[];
  suppressed_sample?: string[];
  [key: string]: unknown;
}

export type Run = Omit<Schemas["RunOut"], "status" | "mode" | "summary"> & {
  status: RunStatus;
  mode: SyncMode;
  summary?: RunSummary;
};
export type Operation = Omit<Schemas["OperationOut"], "action" | "status"> & {
  action: OperationAction;
  status: OperationStatus;
};
export type OperationList = Omit<Schemas["OperationListOut"], "items"> & {
  items: Operation[];
};

/* Stato di sistema (`GET /api/system/status`). */
export type HealthState = "ok" | "degraded" | "error" | "unknown";

/** Servizio generico: il backend può aggiungere campi senza rompere la UI. */
export interface SystemStatusService {
  status?: string | null;
  message?: string | null;
  latency_ms?: number | null;
  last_checked_at?: string | null;
  last_heartbeat_at?: string | null;
}

interface SystemStatusHealth {
  api?: boolean;
  database?: boolean;
  redis?: boolean;
  worker?: boolean;
  tmdb?: string;
  mdblist?: string;
}

interface SystemStatusBackup {
  status?: string | null;
  message?: string | null;
  last_valid_at?: string | null;
  last_backup_at?: string | null;
  next_backup_at?: string | null;
  age_hours?: number | null;
  size_bytes?: number | null;
  file?: string | null;
  error?: string | null;
}

interface SystemStatusUpcoming {
  binding_id: string;
  collection_name: string;
  target_name: string;
  next_run_at: string;
}

/** Acquisizione catalogo scaglionata nelle prossime 24 ore (Fase 9). */
interface SystemStatusCatalogAcquisition {
  collection_id: string;
  collection_name: string;
  provider_name: string;
  next_acquire_at: string;
}

interface SystemStatusStorage {
  snapshot_bytes?: number | null;
  run_bytes?: number | null;
  total_bytes?: number | null;
  database_bytes?: number | null;
  snapshot_rows?: number | null;
  snapshot_item_rows?: number | null;
  run_rows?: number | null;
  size_supported?: boolean | null;
}

export interface SystemStatus {
  /** Shape of GET /api/system/status (Phase 7 backend). */
  health?: SystemStatusHealth | null;
  queues?: Record<string, number> | null;
  runs?: Record<string, number> | null;
  api_usage?: Record<string, { hour?: number; today?: number }> | null;
  backup?: SystemStatusBackup | null;
  pending_approvals?: number | null;
  upcoming?: SystemStatusUpcoming[] | null;
  catalog_acquisitions?: SystemStatusCatalogAcquisition[] | null;
  storage?: SystemStatusStorage | null;
  /** Legacy/tolerant fields kept for older fixtures. */
  status?: string | null;
  version?: string | null;
  environment?: string | null;
  worker?: SystemStatusService | null;
  celery?: SystemStatusService | null;
  database?: SystemStatusService | null;
  integrations?: {
    tmdb?: SystemStatusService | null;
    mdblist?: SystemStatusService | null;
  } | null;
  checks?: Record<string, SystemStatusService> | null;
  [key: string]: unknown;
}

/* Risposte 202 delle azioni di sync. */
export type JobAccepted = Schemas["JobAcceptedOut"];
export type RunAccepted = Schemas["RunAcceptedOut"];
export type PreviewAccepted = Schemas["PreviewAcceptedOut"];


export interface CollectionCreatePayload {
  provider_id?: string;
  source_key?: "tmdb" | "justwatch" | "combined";
  combine_mode?: CombineMode;
  media_type: string;
  name: string;
  slug: string;
  kind: string;
  offer_types?: OfferType[];
  genre_ids: number[];
  monetization_type: string;
  window_days?: number;
  source_collection_id?: string;
  source_collection_ids?: string[];
  shared_snapshot_collection_id?: string;
  exclude_genre_ids?: number[];
  min_vote_average?: number;
  min_vote_count?: number;
  year_from?: number;
  year_to?: number;
  original_language?: string;
  local_sort_by?: string;
  description?: string;
  is_active?: boolean;
}


export interface ProviderCreatePayload {
  slug: string;
  name: string;
  kind: "SVOD" | "TVOD" | "AVOD" | "TVE" | "STORE" | "CINEMA" | "CHANNEL";
  logo_url?: string;
  website_url?: string;
  tmdb_movie_id?: string;
  tmdb_tv_id?: string;
  justwatch_short_name?: string;
  justwatch_technical_name?: string;
  justwatch_monetization_types: string[];
  tvdb_company_id?: string;
}

export type ProviderSourceKey = "tmdb" | "justwatch" | "tvdb";

export interface ProviderCandidate {
  key: string;
  name: string;
  suggested_slug: string;
  sources: ProviderSourceKey[];
  tmdb_movie_id: string | null;
  tmdb_tv_id: string | null;
  justwatch_short_name: string | null;
  justwatch_technical_name: string | null;
  justwatch_monetization_types: string[];
  tvdb_company_id: string | null;
  logo_url: string | null;
  country_code: string | null;
  available_in_country: boolean | null;
}

export interface ProviderCatalogSource {
  source_key: ProviderSourceKey;
  status: string;
  message: string;
  count: number;
}

export interface ProviderCatalog {
  items: ProviderCandidate[];
  sources: ProviderCatalogSource[];
  total: number;
}
