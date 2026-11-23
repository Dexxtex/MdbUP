import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { DEFAULT_COUNTRY } from "../lib/countries";
import { COUNTRY_PARAM, countryFromSearch, normalizeCountry } from "../lib/country-url";

const STORAGE_KEY = "mdbup.country";

interface CountryContextValue {
  country: string;
  setCountry: (code: string) => void;
}

const CountryContext = createContext<CountryContextValue | null>(null);

/**
 * Precedenza: `?country=` nell'URL (link condiviso), poi la preferenza salvata,
 * poi il default. `localStorage` può lanciare (Safari privato, iframe sandbox):
 * qui è opzionale e non deve impedire l'avvio dell'app.
 */
function readInitialCountry(): string {
  if (typeof window === "undefined") return DEFAULT_COUNTRY;
  const fromUrl = countryFromSearch(window.location.search);
  if (fromUrl !== null) return fromUrl;
  try {
    return normalizeCountry(window.localStorage.getItem(STORAGE_KEY)) ?? DEFAULT_COUNTRY;
  } catch {
    return DEFAULT_COUNTRY;
  }
}

function storeCountry(country: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, country);
  } catch {
    // Preferenza non persistita: il contesto resta valido per la sessione.
  }
}

/**
 * Il paese è una dimensione condivisa: si sceglie una volta e vale per
 * provider, collezioni, run e cambi catalogo. Tenuto in localStorage perché
 * non è dato di dominio ma una preferenza di consultazione.
 */
export function CountryProvider({ children }: { children: ReactNode }) {
  const [country, setCountryState] = useState(readInitialCountry);

  useEffect(() => {
    storeCountry(country);
  }, [country]);

  const setCountry = useCallback((code: string) => {
    const normalized = normalizeCountry(code);
    if (normalized !== null) setCountryState(normalized);
  }, []);

  const value = useMemo(() => ({ country, setCountry }), [country, setCountry]);
  return <CountryContext.Provider value={value}>{children}</CountryContext.Provider>;
}

export function useCountry(): CountryContextValue {
  const context = useContext(CountryContext);
  if (context === null) {
    throw new Error("useCountry deve essere usato dentro <CountryProvider>.");
  }
  return context;
}

/**
 * Tiene il paese allineato all'URL: legge `?country=` all'ingresso (link
 * condiviso) e lo riscrive quando cambia, così la vista è riproducibile.
 * Sta dentro il Router perché usa i search params.
 */
export function CountryUrlSync() {
  const { country, setCountry } = useCountry();
  const location = useLocation();
  const [, setSearchParams] = useSearchParams();
  const fromUrl = countryFromSearch(location.search);

  // Ultimi valori osservati (`undefined` = mai visti, quindi primo giro).
  // Serve a decidere UNA direzione per volta: se è cambiato l'URL vince l'URL,
  // se è cambiato il paese si scrive l'URL. Senza questa distinzione i due
  // valori si sovrascrivono a vicenda (storage DE + link ?country=FR = loop).
  const lastCountry = useRef<string | undefined>(undefined);
  const lastUrl = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    const urlChanged = fromUrl !== lastUrl.current;
    const countryChanged = country !== lastCountry.current;
    lastUrl.current = fromUrl;
    lastCountry.current = country;

    function writeUrl(code?: string) {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (code === undefined || code === DEFAULT_COUNTRY) next.delete(COUNTRY_PARAM);
          else next.set(COUNTRY_PARAM, code);
          return next;
        },
        { replace: true },
      );
    }

    // L'URL impone un paese diverso da quello in memoria: vince l'URL.
    if (urlChanged && fromUrl !== null && fromUrl !== country) {
      setCountry(fromUrl);
      return;
    }
    // L'URL è cambiato e non ha il paese: lo si riporta (invariante).
    if (urlChanged && fromUrl === null && country !== DEFAULT_COUNTRY) {
      writeUrl(country);
      return;
    }
    // L'utente ha scelto un paese: si riflette nell'URL.
    if (countryChanged) {
      const desired = country === DEFAULT_COUNTRY ? null : country;
      if (desired !== fromUrl) writeUrl(country);
    }
  }, [country, fromUrl, setCountry, setSearchParams]);

  return null;
}
