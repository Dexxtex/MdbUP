import type { AppSettings, SettingItem, SettingsPatchRequest } from "./types";

/**
 * `GET /settings` risponde `SettingsOut{items:[{key,value,…}]}`: la UI lavora su
 * un oggetto piatto indicizzato per chiave (es. `app_timezone`).
 */
export function settingsFromItems(items: readonly SettingItem[]): AppSettings {
  const settings: AppSettings = {};
  for (const item of items) settings[item.key] = item.value;
  return settings;
}

/**
 * `PATCH /settings` vuole `{items:{key:value}}`. Il backend rifiuta con
 * `VALIDATION_UNKNOWN_SETTING` ogni chiave fuori da `SETTING_SPECS`, quindi si
 * inviano solo i campi valorizzati.
 */
export function settingsPatch(values: Partial<AppSettings>): SettingsPatchRequest {
  const items: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) items[key] = value;
  }
  return { items };
}
