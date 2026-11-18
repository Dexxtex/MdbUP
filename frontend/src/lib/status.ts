import type {
  CollectionOrigin,
  OperationStatus,
  RunStatus,
  SnapshotQuality,
  SnapshotStatus,
  SourceStatus,
} from "../api/types";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export const RUN_STATUS_TONES: Record<RunStatus, Tone> = {
  PENDING: "neutral",
  PREFLIGHT: "info",
  PLANNING: "info",
  AWAITING_APPROVAL: "warning",
  APPLYING: "info",
  VERIFYING: "info",
  SUCCEEDED: "success",
  PARTIAL: "warning",
  FAILED: "danger",
  BLOCKED: "warning",
  CANCELLED: "neutral",
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  PENDING: "In coda",
  PREFLIGHT: "Preflight",
  PLANNING: "Pianificazione",
  AWAITING_APPROVAL: "In attesa di approvazione",
  APPLYING: "Applicazione",
  VERIFYING: "Verifica",
  SUCCEEDED: "Completato",
  PARTIAL: "Parziale",
  FAILED: "Fallito",
  BLOCKED: "Bloccato",
  CANCELLED: "Annullato",
};

export const SNAPSHOT_STATUS_TONES: Record<SnapshotStatus, Tone> = {
  RUNNING: "info",
  COMPLETE: "success",
  INCOMPLETE: "warning",
  FAILED: "danger",
  CANCELLED: "neutral",
};

export const SNAPSHOT_STATUS_LABELS: Record<SnapshotStatus, string> = {
  RUNNING: "In corso",
  COMPLETE: "Completo",
  INCOMPLETE: "Incompleto",
  FAILED: "Fallito",
  CANCELLED: "Annullato",
};

export const SNAPSHOT_QUALITY_TONES: Record<SnapshotQuality, Tone> = {
  CLEAN: "success",
  WARNINGS: "warning",
  ANOMALY: "danger",
};

export const SNAPSHOT_QUALITY_LABELS: Record<SnapshotQuality, string> = {
  CLEAN: "Pulito",
  WARNINGS: "Con avvisi",
  ANOMALY: "Anomalia",
};

export const OPERATION_STATUS_TONES: Record<OperationStatus, Tone> = {
  PENDING: "neutral",
  IN_FLIGHT: "info",
  SUCCEEDED: "success",
  FAILED: "danger",
  UNCERTAIN: "warning",
  SKIPPED: "neutral",
};

export const OPERATION_STATUS_LABELS: Record<OperationStatus, string> = {
  PENDING: "In attesa",
  IN_FLIGHT: "In corso",
  SUCCEEDED: "Riuscita",
  FAILED: "Fallita",
  UNCERTAIN: "Incerta",
  SKIPPED: "Saltata",
};

export const SOURCE_STATUS_TONES: Record<SourceStatus, Tone> = {
  UNCONFIGURED: "neutral",
  OK: "success",
  DEGRADED: "warning",
  ERROR: "danger",
  DISABLED: "neutral",
};

export const SOURCE_STATUS_LABELS: Record<SourceStatus, string> = {
  UNCONFIGURED: "Non configurata",
  OK: "OK",
  DEGRADED: "Degradata",
  ERROR: "Errore",
  DISABLED: "Disabilitata",
};

export const TONE_LABELS: Record<Tone, string> = {
  neutral: "Neutro",
  info: "In corso",
  success: "Positivo",
  warning: "Richiede attenzione",
  danger: "Errore",
};

export interface OriginPresentation {
  label: string;
  tone: Tone;
}

const SOURCE_LABELS: Record<string, string> = {
  tmdb: "TMDb",
  justwatch: "JustWatch",
};

export function sourceLabel(source?: string | null): string | null {
  if (!source) return null;
  return SOURCE_LABELS[source.toLowerCase()] ?? source;
}

/**
 * `AGGREGATOR` non basta: la data/raccolta va attribuita alla fonte realmente
 * usata (TMDb o JustWatch), altrimenti l'etichetta è ambigua.
 */
export function originPresentation(
  origin: CollectionOrigin,
  source?: string | null,
  multiProvider = false,
): OriginPresentation {
  if (origin === "OFFICIAL") return { label: "Ufficiale", tone: "info" };
  if (origin === "AGGREGATOR") {
    const label = sourceLabel(source);
    return {
      label: label ? `Aggregatore ${label}` : "Aggregatore",
      tone: "warning",
    };
  }
  return {
    label: multiProvider ? "Multi-provider" : "Filtro locale",
    tone: "neutral",
  };
}
