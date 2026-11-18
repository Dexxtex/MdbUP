import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import type { Binding, Collection, Provider } from "../api/types";
import {
  bindingCollectionName,
  bindingScheduleLabel,
  bindingTargetName,
  bindingThresholds,
  collectionKindLabel,
  collectionProviderName,
  collectionSourceLabel,
  collectionSourceTone,
  isUpcomingCollection,
} from "./collections";
import { describeApiError, fieldErrors } from "./errors";
import {
  availabilityStatusLabel,
  availabilityStatusTone,
  isVerifiedJustWatchProvider,
  justWatchCacheTtlLabel,
  justWatchPolicyError,
  justWatchThrottleLabel,
  justWatchCapabilityList,
} from "./justwatch";

function error(overrides: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) {
  return new ApiError({
    status: 400,
    code: "X",
    category: "INTERNAL",
    message: "m",
    retryable: false,
    ...overrides,
  });
}

describe("error branches", () => {
  it("mappa conflitti, rete, validazione e fonte", () => {
    expect(describeApiError(error({ category: "VALIDATION" })).title).toBe("Dati non validi");
    expect(describeApiError(error({ category: "SOURCE" })).title).toBe("Errore della fonte");
    expect(describeApiError(error({ category: "CONFLICT" })).title).toBe("Operazione già in corso");
    expect(describeApiError(error({ category: "NETWORK" })).title).toBe("Connessione assente");
  });

  it("mappa policy senza dettagli e target senza retry", () => {
    expect(describeApiError(error({ category: "POLICY" })).message).toContain("soglie");
    expect(describeApiError(error({ category: "TARGET" })).message).toContain("più tardi");
  });

  it("mappa source not available e policy JustWatch", () => {
    expect(describeApiError(error({ code: "SOURCE_NOT_AVAILABLE", message: "" })).message).toContain(
      "seed",
    );
    expect(describeApiError(error({ code: "SOURCE_NOT_AVAILABLE", message: "custom" })).message).toBe(
      "custom",
    );
    expect(describeApiError(error({ code: "JUSTWATCH_POLICY_NOT_ACCEPTED" })).title).toContain(
      "Policy",
    );
  });

  it("fieldErrors ignora valori non stringa e details non oggetto", () => {
    expect(fieldErrors(error({ details: { fields: { a: 1, b: "ok" } } }))).toEqual({ b: "ok" });
    expect(fieldErrors(error({ details: { fields: null } }))).toEqual({});
  });
});

const collection = {
  provider_name: null,
  provider_slug: null,
  provider_id: "123456789",
  source_label: null,
  source_key: "justwatch",
  kind: "UPCOMING",
  max_removal_pct: 1,
  max_removal_abs: 2,
} as unknown as Collection;

const binding = {
  collection: null,
  collection_id: "abcdefghijk",
  target: null,
  target_id: "zyxwvutsrqp",
  max_removal_pct: 3,
  max_removal_abs: 4,
  schedule: "INTERVAL",
  schedule_interval_hours: 6,
  schedule_cron: "0 1 * * *",
  schedule_time: null,
} as unknown as Binding;

describe("collection helpers", () => {
  it("usa fallback provider, binding e target", () => {
    expect(collectionProviderName(collection)).toBe("123456789");
    expect(bindingCollectionName(binding)).toBe("abcdefgh");
    expect(bindingTargetName(binding)).toBe("zyxwvuts");
    expect(bindingThresholds(binding)).toEqual({ percent: 3, absolute: 4 });
  });

  it("etichette e toni delle collezioni", () => {
    expect(collectionKindLabel("CATALOG")).toBe("Catalogo");
    expect(collectionKindLabel("CATALOG" as never)).toBe("Catalogo");
    expect(collectionSourceLabel(collection)).toBe("JustWatch");
    expect(collectionSourceTone(collection)).toBe("warning");
    expect(isUpcomingCollection(collection)).toBe(true);
  });

  it("etichette schedule", () => {
    expect(bindingScheduleLabel(binding)).toBe("Ogni 6 ore");
    expect(bindingScheduleLabel({ ...binding, schedule: "MANUAL" } as Binding)).toBe("Manuale");
    expect(bindingScheduleLabel({ ...binding, schedule: "CRON" } as Binding)).toContain("Cron");
    expect(bindingScheduleLabel({ ...binding, schedule: "DAILY" } as Binding)).toContain("Giornaliero");
    expect(bindingScheduleLabel({ ...binding, schedule: "WEEKLY" } as Binding)).toContain("Settimanale");
  });
});

describe("justwatch helpers", () => {
  const provider = {
    justwatch_verified: false,
    justwatch_movie_verified: true,
    justwatch_tv_verified: false,
    justwatch_provider_id: "8",
  } as unknown as Provider;

  it("verifica provider per media type", () => {
    expect(isVerifiedJustWatchProvider(provider, "MOVIE")).toBe(true);
    expect(isVerifiedJustWatchProvider(provider, "SHOW")).toBe(false);
    expect(isVerifiedJustWatchProvider({ ...provider, justwatch_tv_verified: true } as Provider, "SHOW")).toBe(true);
  });

  it("capability, throttle, cache e availability", () => {
    expect(justWatchCapabilityList(undefined).every((item) => !item.enabled)).toBe(true);
    expect(justWatchThrottleLabel(1000)).toContain("req/s");
    expect(justWatchThrottleLabel(2000)).toContain("ms");
    expect(justWatchThrottleLabel(null)).toBe("—");
    expect(justWatchCacheTtlLabel(30)).toBe("30 s");
    expect(justWatchCacheTtlLabel(120)).toContain("min");
    expect(justWatchCacheTtlLabel(7200)).toContain("h");
    expect(justWatchCacheTtlLabel(0)).toBe("—");
    expect(availabilityStatusLabel("CURRENT")).toBe("Disponibile");
    expect(availabilityStatusLabel("OTHER")).toBe("OTHER");
    expect(availabilityStatusLabel(null)).toContain("non disponibile");
    expect(availabilityStatusTone("CURRENT")).toBe("success");
    expect(availabilityStatusTone("OTHER")).toBe("neutral");
  });

  it("policy JustWatch", () => {
    expect(justWatchPolicyError("justwatch", false)).toContain("policy");
    expect(justWatchPolicyError("justwatch", true)).toBeNull();
    expect(justWatchPolicyError("tmdb", false)).toBeNull();
  });
});

describe("additional branches", () => {
  it("copre etichette di fallback", () => {
    expect(bindingScheduleLabel({ ...binding, schedule: "DAILY", schedule_time: null } as Binding)).toBe(
      "Giornaliero",
    );
    expect(bindingScheduleLabel({ ...binding, schedule: "WEEKLY", schedule_time: "10:00" } as Binding)).toBe(
      "Settimanale 10:00",
    );
    expect(bindingScheduleLabel({ ...binding, schedule: "OTHER" } as unknown as Binding)).toBe("OTHER");
    expect(collectionKindLabel("OTHER" as never)).toBe("OTHER");
  });

  it("copre source label e tone neutri", () => {
    expect(
      collectionSourceLabel({ ...collection, source_label: "Label", source_key: null } as Collection),
    ).toBe("Label");
    expect(collectionSourceLabel({ ...collection, source_label: "—", source_key: null } as Collection)).toBe("—");
    expect(collectionSourceTone({ ...collection, source_key: null } as Collection)).toBe("neutral");
    expect(collectionSourceTone({ ...collection, source_key: "tmdb" } as Collection)).toBe("info");
  });

  it("copre policy e throttle con valori limite", () => {
    expect(justWatchPolicyError(null, false)).toBeNull();
    expect(justWatchThrottleLabel(5000)).toContain("ms");
    expect(justWatchCacheTtlLabel(null)).toBe("—");
    expect(justWatchThrottleLabel(1)).toContain("req/s");
  });
});

describe("final branch coverage", () => {
  it("copre label assente e descrizione vuota", () => {
    expect(
      collectionSourceLabel({ ...collection, source_label: null, source_key: null } as Collection),
    ).toBe("—");
    expect(collectionSourceTone({ ...collection, source_key: null } as Collection)).toBe("neutral");
  });

  it("copre schedule MANUAL e INTERVAL senza ore", () => {
    expect(bindingScheduleLabel({ ...binding, schedule: "MANUAL" } as Binding)).toBe("Manuale");
    expect(
      bindingScheduleLabel({ ...binding, schedule: "INTERVAL", schedule_interval_hours: null } as Binding),
    ).toBe("Ogni ? ore");
  });
});
