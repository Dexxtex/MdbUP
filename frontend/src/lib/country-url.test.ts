import { describe, expect, it } from "vitest";

import { COUNTRY_PARAM, countryFromSearch, isValidCountry, normalizeCountry, withCountry } from "./country-url";

describe("normalizeCountry", () => {
  it("normalizza in maiuscolo senza spazi", () => {
    expect(normalizeCountry(" de ")).toBe("DE");
    expect(normalizeCountry("it")).toBe("IT");
  });

  it("rifiuta valori che non sono coppie di lettere", () => {
    expect(normalizeCountry("XYZ")).toBeNull();
    expect(normalizeCountry("d1")).toBeNull();
    expect(normalizeCountry("")).toBeNull();
    expect(normalizeCountry(null)).toBeNull();
    expect(normalizeCountry(undefined)).toBeNull();
  });
});

describe("isValidCountry", () => {
  it("accetta solo due lettere", () => {
    expect(isValidCountry("it")).toBe(true);
    expect(isValidCountry("ita")).toBe(false);
  });
});

describe("withCountry", () => {
  it("non tocca i path per il paese predefinito o non valido", () => {
    expect(withCountry("/app/x", "IT")).toBe("/app/x");
    expect(withCountry("/app/x", "abc")).toBe("/app/x");
    expect(withCountry("/app/x", "")).toBe("/app/x");
  });

  it("aggiunge il paese a un path con query esistente", () => {
    expect(withCountry("/app/collections?provider=abc", "de")).toBe(
      "/app/collections?provider=abc&country=DE",
    );
  });

  it("aggiunge il paese a un path senza query", () => {
    expect(withCountry("/app/runs", "FR")).toBe("/app/runs?country=FR");
  });

  it("normalizza spazi nel codice", () => {
    expect(withCountry("/app/x", " de ")).toBe("/app/x?country=DE");
  });
});

describe("countryFromSearch", () => {
  it("legge e normalizza il parametro", () => {
    expect(countryFromSearch("?country=de")).toBe("DE");
    expect(countryFromSearch(`?${COUNTRY_PARAM}=FR&step=2`)).toBe("FR");
  });

  it("restituisce null se manca o non è valido", () => {
    expect(countryFromSearch("")).toBeNull();
    expect(countryFromSearch("?step=2")).toBeNull();
    expect(countryFromSearch("?country=XYZ")).toBeNull();
    expect(countryFromSearch("?country=")).toBeNull();
  });
});
