import type {
  DashboardSourceRow,
  HealthState,
  SystemStatus,
  SystemStatusService,
} from "../api/types";

export interface HealthItem {
  key: "api" | "worker" | "tmdb" | "mdblist";
  label: string;
  state: HealthState;
  detail: string;
}

const OK_VALUES = new Set(["ok", "healthy", "up", "connected", "ready", "online"]);
const DEGRADED_VALUES = new Set(["degraded", "warning", "slow", "partial"]);
const ERROR_VALUES = new Set([
  "error",
  "down",
  "failed",
  "unavailable",
  "offline",
  "missing_credential",
  "missing",
]);

export function healthStateFromValue(value?: string | null): HealthState {
  if (!value) return "unknown";
  const normalized = value.toLowerCase();
  if (OK_VALUES.has(normalized)) return "ok";
  if (DEGRADED_VALUES.has(normalized)) return "degraded";
  if (ERROR_VALUES.has(normalized)) return "error";
  return "unknown";
}

function fromService(service: SystemStatusService | null | undefined): HealthState {
  return service ? healthStateFromValue(service.status) : "unknown";
}

function serviceDetail(
  service: SystemStatusService | null | undefined,
  fallback: string,
): string {
  if (!service) return fallback;
  return service.message ?? service.status ?? fallback;
}

function fromSource(
  sources: readonly DashboardSourceRow[] | undefined,
  needle: string,
): HealthState {
  const source = sources?.find((item) => item.key.toLowerCase().includes(needle));
  if (!source) return "unknown";
  switch (source.status) {
    case "OK":
      return "ok";
    case "DEGRADED":
      return "degraded";
    case "ERROR":
      return "error";
    default:
      return "unknown";
  }
}

function pickService(
  status: SystemStatus | null,
  keys: readonly string[],
): SystemStatusService | null | undefined {
  if (!status) return undefined;
  for (const key of keys) {
    const candidate = status[key];
    if (candidate && typeof candidate === "object") {
      return candidate as SystemStatusService;
    }
    const check = status.checks?.[key];
    if (check) return check;
  }
  return undefined;
}

/**
 * Quattro indicatori del topbar. `system/status` è la fonte primaria; se manca
 * (endpoint non ancora rilasciato) TMDb/MDBList ricadono sullo stato delle fonti
 * della dashboard e il worker resta "sconosciuto" invece di risultare guasto.
 */
export function deriveHealth({
  apiState,
  status,
  sources,
}: {
  apiState: HealthState;
  status: SystemStatus | null;
  sources?: readonly DashboardSourceRow[];
}): HealthItem[] {
  const health = status?.health;
  const worker = pickService(status, ["worker", "celery"]);
  const tmdb = status?.integrations?.tmdb ?? pickService(status, ["tmdb"]);
  const mdblist = status?.integrations?.mdblist ?? pickService(status, ["mdblist"]);
  const workerState: HealthState =
    health?.worker === true
      ? "ok"
      : health?.worker === false
        ? "error"
        : fromService(worker);
  const tmdbState: HealthState = health?.tmdb
    ? healthStateFromValue(health.tmdb)
    : tmdb
      ? fromService(tmdb)
      : fromSource(sources, "tmdb");
  const mdblistState: HealthState = health?.mdblist
    ? healthStateFromValue(health.mdblist)
    : mdblist
      ? fromService(mdblist)
      : fromSource(sources, "mdblist");

  return [
    {
      key: "api",
      label: "API",
      state: apiState,
      detail: apiState === "ok" ? "Sessione attiva" : "Sessione non disponibile",
    },
    {
      key: "worker",
      label: "Worker",
      state: workerState,
      detail: serviceDetail(worker, "Stato del worker Celery non disponibile"),
    },
    {
      key: "tmdb",
      label: "TMDb",
      state: tmdbState,
      detail: serviceDetail(tmdb, "Stato TMDb non disponibile"),
    },
    {
      key: "mdblist",
      label: "MDBList",
      state: mdblistState,
      detail: serviceDetail(mdblist, "Stato MDBList non disponibile"),
    },
  ];
}

export const HEALTH_STATE_LABELS: Record<HealthState, string> = {
  ok: "Operativo",
  degraded: "Degradato",
  error: "Errore",
  unknown: "Sconosciuto",
};
