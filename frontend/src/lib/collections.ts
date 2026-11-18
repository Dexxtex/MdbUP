import type { Binding, Collection, CollectionKind } from "../api/types";
import { isJustWatchSource } from "./justwatch";
import { sourceLabel, type Tone } from "./status";

/**
 * `CollectionOut` porta `provider_name`/`provider_slug` già risolti dal backend:
 * il fallback sull'id serve solo se il provider è stato rimosso.
 */
export function collectionProviderName(collection: Collection): string {
  return collection.provider_name ?? collection.provider_slug ?? collection.provider_id;
}

export function bindingCollectionName(binding: Binding): string {
  return binding.collection?.name ?? binding.collection_id.slice(0, 8);
}

export function bindingTargetName(binding: Binding): string {
  if (binding.target?.name) return binding.target.name;
  return binding.target_id.slice(0, 8);
}

const COLLECTION_KIND_LABELS: Record<CollectionKind, string> = {
  CATALOG: "Catalogo",
  RECENTLY_ADDED: "Novità",
  CUSTOM_FILTER: "Combinata locale",
  CHART: "Classifica",
  UPCOMING: "In arrivo",
};

export function collectionKindLabel(kind: CollectionKind): string {
  return COLLECTION_KIND_LABELS[kind] ?? kind;
}

/**
 * `source_label` è già l'attribuzione calcolata dal backend (es. "Classifica
 * JustWatch"): usarla evita di ricostruire in UI un'etichetta ambigua.
 */
export function collectionSourceLabel(collection: Collection): string {
  return (
    collection.source_label ??
    sourceLabel(collection.source_key) ??
    collection.source_key ??
    "—"
  );
}

export function collectionSourceTone(collection: Collection): Tone {
  if (isJustWatchSource(collection.source_key)) return "warning";
  return collection.source_key ? "info" : "neutral";
}

export function isUpcomingCollection(collection: Collection): boolean {
  return collection.kind === "UPCOMING";
}

/** `BindingOut` espone le soglie sia piatte sia in `thresholds`: la UI usa le piatte. */
export function bindingThresholds(binding: Binding): {
  percent: number;
  absolute: number;
} {
  return { percent: binding.max_removal_pct, absolute: binding.max_removal_abs };
}

/** Etichetta leggibile per le pianificazioni supportate dal backend. */
export function bindingScheduleLabel(binding: Binding): string {
  switch (binding.schedule) {
    case "MANUAL":
      return "Manuale";
    case "INTERVAL":
      return `Ogni ${binding.schedule_interval_hours ?? "?"} ore`;
    case "CRON":
      return `Cron: ${binding.schedule_cron}`;
    case "DAILY":
      return `Giornaliero ${binding.schedule_time ?? ""}`.trim();
    case "WEEKLY":
      return `Settimanale ${binding.schedule_time ?? ""}`.trim();
    default:
      return binding.schedule;
  }
}
