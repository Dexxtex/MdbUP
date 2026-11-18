import type { Run, RunSummary, RunThresholdSummary } from "../api/types";

export function runSummary(run: Run | undefined): RunSummary {
  return run?.summary ?? {};
}

export interface RemovalUsage {
  observed: number;
  maxAbsolute: number;
  maxPercent: number;
  /** Percentuale osservata sul totale remoto (0-100). */
  observedPercent: number;
  /** Riempimento della barra assoluta (0-100). */
  absoluteFill: number;
  /** Riempimento della barra percentuale (0-100). */
  percentFill: number;
  overAbsolute: boolean;
  overPercent: boolean;
  breached: boolean;
}

/**
 * `summary.thresholds` è scritto da `threshold_summary` nel backend: i campi
 * possono mancare su run vecchi o non pianificati, quindi i default sono 0.
 */
export function removalUsage(thresholds: RunThresholdSummary | undefined): RemovalUsage {
  const observed = thresholds?.observed_removals ?? 0;
  const maxAbsolute = thresholds?.max_removal_absolute ?? 0;
  const maxPercent = thresholds?.max_removal_percent ?? 0;
  const remoteCount = thresholds?.remote_count ?? 0;
  const observedPercent =
    remoteCount > 0 ? Math.round((observed / remoteCount) * 1000) / 10 : 0;
  const absoluteFill =
    maxAbsolute > 0 ? Math.min(100, Math.round((observed / maxAbsolute) * 100)) : 0;
  const percentFill =
    maxPercent > 0 ? Math.min(100, Math.round((observedPercent / maxPercent) * 100)) : 0;
  const overAbsolute = maxAbsolute > 0 && observed > maxAbsolute;
  const overPercent = maxPercent > 0 && observedPercent > maxPercent;
  return {
    observed,
    maxAbsolute,
    maxPercent,
    observedPercent,
    absoluteFill,
    percentFill,
    overAbsolute,
    overPercent,
    breached: Boolean(thresholds?.breached) || overAbsolute || overPercent,
  };
}

export function filterSamples(
  samples: readonly string[] | undefined,
  query: string,
): readonly string[] {
  const list = samples ?? [];
  const needle = query.trim().toLowerCase();
  if (!needle) return list;
  return list.filter((sample) => sample.toLowerCase().includes(needle));
}
