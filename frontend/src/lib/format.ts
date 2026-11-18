/**
 * Tutti gli orari sono mostrati nel fuso dell'app (Europe/Rome). Il valore UTC e
 * l'età relativa restano disponibili nel tooltip (`<Timestamp />`).
 */
export const APP_TIME_ZONE = "Europe/Rome";

const dateTimeFormatter = new Intl.DateTimeFormat("it-IT", {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: APP_TIME_ZONE,
});

const dateFormatter = new Intl.DateTimeFormat("it-IT", {
  dateStyle: "medium",
  timeZone: APP_TIME_ZONE,
});

const utcFormatter = new Intl.DateTimeFormat("it-IT", {
  dateStyle: "short",
  timeStyle: "medium",
  timeZone: "UTC",
});

const numberFormatter = new Intl.NumberFormat("it-IT");

const relativeFormatter = new Intl.RelativeTimeFormat("it-IT", { numeric: "auto" });

function toDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value?: string | null): string {
  const date = toDate(value);
  return date ? dateTimeFormatter.format(date) : "—";
}

export function formatDate(value?: string | null): string {
  const date = toDate(value);
  return date ? dateFormatter.format(date) : "—";
}

export function formatDateTimeUtc(value?: string | null): string {
  const date = toDate(value);
  return date ? `${utcFormatter.format(date)} UTC` : "—";
}

export function formatRelative(value?: string | null, now: number = Date.now()): string {
  const date = toDate(value);
  if (!date) return "—";
  const deltaSeconds = Math.round((date.getTime() - now) / 1000);
  const absolute = Math.abs(deltaSeconds);
  if (absolute < 45) return "adesso";
  if (absolute < 60 * 60) {
    return relativeFormatter.format(Math.round(deltaSeconds / 60), "minute");
  }
  if (absolute < 60 * 60 * 24) {
    return relativeFormatter.format(Math.round(deltaSeconds / 3600), "hour");
  }
  return relativeFormatter.format(Math.round(deltaSeconds / 86_400), "day");
}

export function formatNumber(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return numberFormatter.format(value);
}

export function formatPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${numberFormatter.format(value)}%`;
}

export function formatBytes(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Math.max(0, value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const rounded = size >= 10 || unit === 0 ? Math.round(size) : Math.round(size * 10) / 10;
  return `${numberFormatter.format(rounded)} ${units[unit]}`;
}

export function formatDuration(startedAt?: string | null, finishedAt?: string | null): string {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  if (Number.isNaN(start)) return "—";
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (Number.isNaN(end)) return "—";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${seconds % 60} s`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}
