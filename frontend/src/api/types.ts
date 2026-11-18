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

export type SourceType = "API" | "DATA_EXPORT" | "MANUAL_CSV";

export type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "RETRY"
  | "CANCELLED";

/* Sync: target, binding, preview, run (`app/api/schemas_sync.py`). */
export type SyncMode = Schemas["SyncMode"];
export type RunStatus = Schemas["SyncRunStatus"];
export type OperationAction = Schemas["SyncOperationAction"];
export type OperationStatus = Schemas["SyncOperationStatus"];
export type SchedulePolicy = Schemas["SchedulePolicy"];
export type ScheduleFrequency = "MANUAL" | "DAILY" | "WEEKLY" | "INTERVAL" | "CRON";
export type PreviewState = Schemas["PreviewOut"]["state"];

/** `CredentialOut.kind` è una stringa: i valori sono quelli di `CredentialKind`. */
export type CredentialKind = "TMDB" | "MDBLIST" | "JUSTWATCH";

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
export type Provider = Schemas["ProviderOut"];
export type ProviderList = Schemas["ProviderListOut"];

/**
 * `SourceOut.capabilities` è un dizionario libero: qui le chiavi note
 * (docs/phase1/07-frontend-api.md §4.3).
 */
export interface SourceCapabilities {
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
  "status" | "type" | "origin_default" | "capabilities"
> & {
  status: SourceStatus;
  type: SourceType;
  origin_default: CollectionOrigin;
  capabilities: SourceCapabilities;
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
export type SnapshotItem = Schemas["SnapshotItemOut"];

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
  offer_types: OfferType[];
  latest_snapshot?: Snapshot | null;
  last_valid_snapshot?: Snapshot | null;
};
export type CollectionList = Omit<Schemas["CollectionListOut"], "items"> & {
  items: Collection[];
};

export type AcquireOut = Schemas["AcquireOut"];

/* Dashboard (`app/api/schemas_catalog.py` + `app/services/dashboard.py`). */
export type DashboardCounters = Schemas["DashboardOut"]["counters"];
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
  schedule_policy: SchedulePolicy;
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
export type RunList = Omit<Schemas["RunListOut"], "items"> & {
  items: Run[];
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

export interface SystemStatusHealth {
  api?: boolean;
  database?: boolean;
  redis?: boolean;
  worker?: boolean;
  tmdb?: string;
  mdblist?: string;
}

export interface SystemStatusBackup {
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

export interface SystemStatusUpcoming {
  binding_id: string;
  collection_name: string;
  target_name: string;
  next_run_at: string;
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
