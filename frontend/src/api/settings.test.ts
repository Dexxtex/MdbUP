import { describe, expect, it } from "vitest";
import { settingsFromItems, settingsPatch } from "./settings";
import type { SettingItem } from "./types";

function item(key: string, value: unknown): SettingItem {
  return { key, value, description: "", updated_at: null };
}

describe("settingsFromItems", () => {
  it("appiattisce SettingsOut.items sull'oggetto usato dai form", () => {
    const settings = settingsFromItems([
      item("app_timezone", "Europe/Rome"),
      item("sync_batch_size", 100),
    ]);
    expect(settings.app_timezone).toBe("Europe/Rome");
    expect(settings.sync_batch_size).toBe(100);
  });

  it("non inventa chiavi assenti", () => {
    expect(settingsFromItems([])).toEqual({});
  });
});

describe("settingsPatch", () => {
  it("avvolge i valori in items, la forma richiesta da PATCH /settings", () => {
    expect(settingsPatch({ app_timezone: "Europe/Rome", sync_batch_size: 50 })).toEqual({
      items: { app_timezone: "Europe/Rome", sync_batch_size: 50 },
    });
  });

  it("omette i campi non valorizzati", () => {
    expect(settingsPatch({ app_timezone: undefined, sync_batch_size: 50 })).toEqual({
      items: { sync_batch_size: 50 },
    });
  });
});
