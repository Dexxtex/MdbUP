import type { CollectionKind, Provider } from "../api/types";
import type { Tone } from "./status";

/** Tipi di collezione che il backend JustWatch accetta (`_JUSTWATCH_KINDS`). */
export const JUSTWATCH_KINDS: readonly CollectionKind[] = [
  "CATALOG",
  "RECENTLY_ADDED",
  "UPCOMING",
  "CHART",
];

export function isJustWatchSource(sourceKey?: string | null): boolean {
  return sourceKey === "justwatch";
}

export function isVerifiedJustWatchProvider(provider: Provider): boolean {
  return provider.justwatch_verified === true && Boolean(provider.justwatch_provider_id);
}

export interface JustWatchCapability {
  key: CollectionKind;
  label: string;
  enabled: boolean;
}

const CAPABILITY_LABELS: Record<string, string> = {
  CATALOG: "Catalogo",
  RECENTLY_ADDED: "Novità",
  UPCOMING: "In arrivo",
  CHART: "Classifiche",
};

/** Capacità dichiarate da `SourceOut.justwatch.supported_kinds`. */
export function justWatchCapabilityList(
  supportedKinds: readonly string[] | null | undefined,
): JustWatchCapability[] {
  const supported = new Set(supportedKinds ?? []);
  return JUSTWATCH_KINDS.map((key) => ({
    key,
    label: CAPABILITY_LABELS[key] ?? key,
    enabled: supported.has(key),
  }));
}

/** `throttle_ms` è il minimo intervallo tra due richieste JustWatch. */
export function justWatchThrottleLabel(throttleMs?: number | null): string {
  if (throttleMs == null || throttleMs <= 0) return "—";
  const perSecond = 1000 / throttleMs;
  return perSecond >= 1
    ? `${Number(perSecond.toFixed(2))} req/s`
    : `${Math.round(throttleMs)} ms tra richieste`;
}

export function justWatchCacheTtlLabel(seconds?: number | null): string {
  if (seconds == null || seconds <= 0) return "—";
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Number((seconds / 3600).toFixed(1))} h`;
}

export const AVAILABILITY_STATUS_LABELS: Record<string, string> = {
  CURRENT: "Disponibile",
  UPCOMING: "In arrivo",
  LEAVING: "In uscita",
};

export const AVAILABILITY_STATUS_TONES: Record<string, Tone> = {
  CURRENT: "success",
  UPCOMING: "info",
  LEAVING: "warning",
};

export function availabilityStatusLabel(status?: string | null): string {
  if (!status) return "Stato non disponibile";
  return AVAILABILITY_STATUS_LABELS[status] ?? status;
}

export function availabilityStatusTone(status?: string | null): Tone {
  if (!status) return "neutral";
  return AVAILABILITY_STATUS_TONES[status] ?? "neutral";
}

/** Messaggio UI quando manca l'accettazione esplicita della policy JustWatch. */
export function justWatchPolicyError(
  sourceKey: string | null | undefined,
  accepted: boolean,
): string | null {
  if (!isJustWatchSource(sourceKey) || accepted) return null;
  return "Per le collezioni JustWatch devi accettare esplicitamente la policy dell'aggregatore.";
}

/** Il binding JustWatch nasce disabilitato: serve un dry-run riuscito. */
export function justWatchBindingNotice(): string {
  return "Sync MDBList disabilitata di default: solo snapshot e preview; dry-run obbligatorio prima del primo run reale.";
}

export function justWatchDryRunMessage(): string {
  return "Dry-run richiesto: esegui e completa un dry-run con successo per questo binding prima del run reale.";
}
