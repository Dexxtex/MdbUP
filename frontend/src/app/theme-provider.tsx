import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  applyTheme,
  browserThemeStorage,
  nextTheme,
  readStoredTheme,
  storeTheme,
  type Theme,
} from "../lib/theme";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() =>
    readStoredTheme(browserThemeStorage()),
  );

  const setTheme = useCallback((value: Theme) => setThemeState(value), []);

  const toggleTheme = useCallback(
    () => setThemeState((current) => nextTheme(current)),
    [],
  );

  useEffect(() => {
    storeTheme(browserThemeStorage(), theme);
  }, [theme]);

  // `useLayoutEffect` applica il tema prima del paint quando React monta.
  useLayoutEffect(() => {
    if (typeof document === "undefined") return;
    applyTheme(theme, document.documentElement);
  }, [theme]);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme deve essere usato dentro ThemeProvider");
  }
  return context;
}
