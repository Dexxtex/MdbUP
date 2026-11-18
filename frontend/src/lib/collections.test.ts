import { describe, expect, it } from "vitest";
import type { Binding, Collection } from "../api/types";
import {
  bindingCollectionName,
  bindingScheduleLabel,
  bindingThresholds,
  collectionProviderName,
} from "./collections";

function collection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: "col-1",
    slug: "netflix-it-movie",
    name: "Netflix IT — Film",
    provider_id: "provider-1",
    provider_slug: "netflix",
    provider_name: "Netflix",
    source_id: "source-1",
    source_key: "tmdb",
    country_code: "IT",
    media_type: "MOVIE",
    kind: "CATALOG",
    origin: "AGGREGATOR",
    date_basis: "UNKNOWN",
    description: null,
    filters: {},
    quality_flags: {},
    provider_names: ["Netflix"],
    is_local_filter: false,
    is_multi_provider: false,
    offer_types: ["FLATRATE"],
    sort_mode: "popularity.desc",
    is_active: true,
    ...overrides,
  };
}

function binding(overrides: Partial<Binding> = {}): Binding {
  return {
    id: "binding-1",
    collection_id: "col-1",
    target_id: "target-1",
    media_type: "MOVIE",
    mode: "MIRROR",
    schedule: "MANUAL",
    schedule_cron: "0 3 * * *",
    schedule_interval_hours: null,
    max_removal_pct: 10,
    max_removal_abs: 50,
    max_remove_count: 50,
    max_remove_percent: 10,
    thresholds: { max_removal_pct: 10, max_removal_abs: 50 },
    preserve_order: false,
    reorder_enabled: true,
    schedule_policy: "AUTO_APPLY_IF_SAFE",
    require_review: true,
    enabled: true,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("collectionProviderName", () => {
  it("usa provider_name risolto dal backend", () => {
    expect(collectionProviderName(collection())).toBe("Netflix");
  });

  it("ricade su slug e poi sull'id quando il provider non è risolto", () => {
    expect(collectionProviderName(collection({ provider_name: null }))).toBe("netflix");
    expect(
      collectionProviderName(collection({ provider_name: null, provider_slug: null })),
    ).toBe("provider-1");
  });
});

describe("bindingThresholds", () => {
  it("legge le soglie piatte di BindingOut", () => {
    expect(bindingThresholds(binding())).toEqual({ percent: 10, absolute: 50 });
  });
});

describe("bindingCollectionName", () => {
  it("usa il nome della collezione annidata, altrimenti l'id abbreviato", () => {
    expect(bindingCollectionName(binding({ collection: collection() }))).toBe(
      "Netflix IT — Film",
    );
    expect(bindingCollectionName(binding())).toBe("col-1");
  });
});

describe("bindingScheduleLabel", () => {
  it("formatta manuale, intervallo e cron", () => {
    expect(bindingScheduleLabel(binding({ schedule: "MANUAL" }))).toBe("Manuale");
    expect(
      bindingScheduleLabel(
        binding({ schedule: "INTERVAL", schedule_interval_hours: 6 }),
      ),
    ).toBe("Ogni 6 ore");
    expect(
      bindingScheduleLabel(
        binding({ schedule: "CRON", schedule_cron: "0 4 * * *" }),
      ),
    ).toBe("Cron: 0 4 * * *");
  });
});
