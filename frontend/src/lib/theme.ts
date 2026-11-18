export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "mdbup-theme";

/** Sottoinsieme di `Storage` usato dal tema: nei test basta un oggetto in memoria. */
export interface ThemeStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** Sottoinsieme di `HTMLElement` sufficiente ad applicare il tema. */
export interface ThemeRoot {
  classList: { toggle(token: string, force?: boolean): void };
  setAttribute(name: string, value: string): void;
  style: { colorScheme: string };
}

export function isTheme(value: unknown): value is Theme {
  return value === "dark" || value === "light";
}

/** Il tema scuro è il default: un valore assente o corrotto non lo cambia. */
export function resolveTheme(stored: string | null | undefined): Theme {
  return stored === "light" ? "light" : "dark";
}

export function readStoredTheme(storage: ThemeStorage | null): Theme {
  if (!storage) return "dark";
  try {
    return resolveTheme(storage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "dark";
  }
}

export function storeTheme(storage: ThemeStorage | null, theme: Theme): void {
  if (!storage) return;
  try {
    storage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage pieno o disabilitato: il tema resta valido per la sessione.
  }
}

export function nextTheme(theme: Theme): Theme {
  return theme === "dark" ? "light" : "dark";
}

export function applyTheme(theme: Theme, root: ThemeRoot): void {
  root.classList.toggle("dark", theme === "dark");
  root.classList.toggle("light", theme === "light");
  root.setAttribute("data-theme", theme);
  root.style.colorScheme = theme;
}

/** `localStorage` può lanciare (Safari privato, iframe sandbox): qui è opzionale. */
export function browserThemeStorage(): ThemeStorage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.localStorage;
  } catch {
    return null;
  }
}
