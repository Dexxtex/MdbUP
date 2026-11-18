import { describe, expect, it } from "vitest";
import type { Provider } from "../api/types";
import {
  availabilityStatusLabel,
  availabilityStatusTone,
  isJustWatchSource,
  isVerifiedJustWatchProvider,
  justWatchCacheTtlLabel,
  justWatchCapabilityList,
  justWatchPolicyError,
  justWatchThrottleLabel,
} from "./justwatch";

function provider(overrides: Partial<Provider> = {}): Provider {
  return {
    id: "provider-1",
    slug: "netflix",
    name: "Netflix",
    kind: "FLATRATE",
    logo_url: null,
    website_url: null,
    country_code: "IT",
    tmdb_provider_id: "8",
    tmdb_provider_id_movie: "8",
    tmdb_provider_id_tv: "8",
    mapping_verified: true,
    mapping_verified_movie: true,
    mapping_verified_tv: true,
    justwatch_provider_id: "8",
    justwatch_verified: true,
    justwatch_monetization_types: ["FLATRATE"],
    collections_count: 1,
    movie_collections: 1,
    show_collections: 0,
    ...overrides,
  };
}

describe("capacity JustWatch", () => {
  it("mappa i kind supportati nelle capacità mostrate in UI", () => {
    const capabilities = justWatchCapabilityList(["CATALOG", "UPCOMING", "CHART"]);
    expect(capabilities.map((item) => item.label)).toEqual([
      "Catalogo",
      "Novità",
      "In arrivo",
      "Classifiche",
    ]);
    expect(capabilities.map((item) => item.enabled)).toEqual([
      true,
      false,
      true,
      true,
    ]);
  });

  it("formatta throttle, cache TTL e fonte", () => {
    expect(justWatchThrottleLabel(1000)).toBe("1 req/s");
    expect(justWatchThrottleLabel(null)).toBe("—");
    expect(justWatchCacheTtlLabel(3600)).toBe("1 h");
    expect(isJustWatchSource("justwatch")).toBe(true);
    expect(isJustWatchSource("tmdb")).toBe(false);
  });

  it("riconosce un provider con mapping JustWatch verificato", () => {
    expect(isVerifiedJustWatchProvider(provider())).toBe(true);
    expect(
      isVerifiedJustWatchProvider(
        provider({ justwatch_verified: false, justwatch_provider_id: null }),
      ),
    ).toBe(false);
  });
});

describe("stato disponibilità JustWatch", () => {
  it("traduce CURRENT/UPCOMING/LEAVING e il vuoto", () => {
    expect(availabilityStatusLabel("CURRENT")).toBe("Disponibile");
    expect(availabilityStatusLabel("UPCOMING")).toBe("In arrivo");
    expect(availabilityStatusLabel("LEAVING")).toBe("In uscita");
    expect(availabilityStatusLabel(null)).toBe("Stato non disponibile");
  });

  it("assegna toni semantici", () => {
    expect(availabilityStatusTone("CURRENT")).toBe("success");
    expect(availabilityStatusTone("UPCOMING")).toBe("info");
    expect(availabilityStatusTone("LEAVING")).toBe("warning");
    expect(availabilityStatusTone(null)).toBe("neutral");
  });
});

describe("policy binding JustWatch", () => {
  it("richiede l'accettazione esplicita solo per JustWatch", () => {
    expect(justWatchPolicyError("justwatch", false)).toContain("policy");
    expect(justWatchPolicyError("justwatch", true)).toBeNull();
    expect(justWatchPolicyError("tmdb", false)).toBeNull();
  });
});
