import { describe, expect, it } from "vitest";

import { COUNTRIES, DEFAULT_COUNTRY, countryLabel, countryName } from "./countries";

describe("COUNTRIES", () => {
  it("copre i codici ISO 3166-1 alpha-2 assegnati", () => {
    expect(COUNTRIES.length).toBe(249);
  });

  it("usa solo codici di 2 lettere maiuscole e senza duplicati", () => {
    const codes = COUNTRIES.map((country) => country.code);
    expect(new Set(codes).size).toBe(codes.length);
    for (const code of codes) {
      expect(code).toMatch(/^[A-Z]{2}$/);
    }
  });

  it("ha un nome non vuoto per ogni paese ed è ordinata per nome", () => {
    for (const country of COUNTRIES) {
      expect(country.name.trim().length).toBeGreaterThan(0);
    }
    const names = COUNTRIES.map((country) => country.name.toLowerCase());
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)));
  });

  it("contiene il paese predefinito con il nome italiano", () => {
    expect(COUNTRIES.some((country) => country.code === DEFAULT_COUNTRY)).toBe(true);
    expect(countryName(DEFAULT_COUNTRY)).toBe("Italia");
  });
});

describe("countryName / countryLabel", () => {
  it("normalizza minuscole e spazi", () => {
    expect(countryName(" it ")).toBe("Italia");
    expect(countryName("de")).toBe("Germania");
  });

  it("restituisce il codice per un paese sconosciuto", () => {
    expect(countryName("zz")).toBe("ZZ");
  });

  it("compone l'etichetta ISO + nome", () => {
    expect(countryLabel("fr")).toBe("FR — Francia");
    expect(countryLabel("ZZ")).toBe("ZZ — ZZ");
  });
});
