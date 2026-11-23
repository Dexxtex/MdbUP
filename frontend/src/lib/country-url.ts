import { DEFAULT_COUNTRY } from "./countries";

/** Il paese è parte dello stato condiviso: lo teniamo nell'URL per link riproducibili. */
export const COUNTRY_PARAM = "country";

export function isValidCountry(code: string | null | undefined): code is string {
  return typeof code === "string" && /^[A-Z]{2}$/.test(code.trim().toUpperCase());
}

/** Normalizza in `XX` o restituisce `null`: unico posto per regex e trim. */
export function normalizeCountry(code: string | null | undefined): string | null {
  if (typeof code !== "string") return null;
  const normalized = code.trim().toUpperCase();
  return /^[A-Z]{2}$/.test(normalized) ? normalized : null;
}

/**
 * Aggiunge `?country=` a un percorso interno, solo quando il paese non è quello
 * predefinito: gli URL italiani restano puliti, quelli esteri viaggiano con il
 * loro contesto.
 */
export function withCountry(to: string, country: string): string {
  const normalized = normalizeCountry(country);
  if (normalized === null || normalized === DEFAULT_COUNTRY) return to;

  const [path, search = ""] = to.split("?");
  const params = new URLSearchParams(search);
  params.set(COUNTRY_PARAM, normalized);
  return `${path}?${params.toString()}`;
}

/** Legge il paese da una query string già normalizzata. */
export function countryFromSearch(search: string): string | null {
  return normalizeCountry(new URLSearchParams(search).get(COUNTRY_PARAM));
}
