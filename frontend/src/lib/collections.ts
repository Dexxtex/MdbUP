import type { Binding, Collection } from "../api/types";

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
