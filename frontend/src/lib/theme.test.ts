import { describe, expect, it } from "vitest";
import {
  THEME_STORAGE_KEY,
  applyTheme,
  nextTheme,
  readStoredTheme,
  resolveTheme,
  storeTheme,
  type ThemeRoot,
  type ThemeStorage,
} from "./theme";

function memoryStorage(initial: Record<string, string> = {}): ThemeStorage & {
  values: Record<string, string>;
} {
  const values = { ...initial };
  return {
    values,
    getItem: (key) => (key in values ? values[key] : null),
    setItem: (key, value) => {
      values[key] = value;
    },
  };
}

function fakeRoot(): ThemeRoot & {
  classes: Record<string, boolean>;
  attributes: Record<string, string>;
} {
  const classes: Record<string, boolean> = {};
  const attributes: Record<string, string> = {};
  return {
    classes,
    attributes,
    classList: {
      toggle: (token, force) => {
        classes[token] = force ?? !classes[token];
      },
    },
    setAttribute: (name, value) => {
      attributes[name] = value;
    },
    style: { colorScheme: "" },
  };
}

describe("resolveTheme", () => {
  it("usa il tema scuro come default", () => {
    expect(resolveTheme(null)).toBe("dark");
    expect(resolveTheme(undefined)).toBe("dark");
    expect(resolveTheme("")).toBe("dark");
    expect(resolveTheme("qualcosa")).toBe("dark");
  });

  it("accetta solo il valore light esplicito", () => {
    expect(resolveTheme("light")).toBe("light");
  });
});

describe("persistenza del tema", () => {
  it("legge il tema salvato in localStorage", () => {
    const storage = memoryStorage({ [THEME_STORAGE_KEY]: "light" });
    expect(readStoredTheme(storage)).toBe("light");
  });

  it("scrive e rilegge la preferenza", () => {
    const storage = memoryStorage();
    storeTheme(storage, "light");
    expect(storage.values[THEME_STORAGE_KEY]).toBe("light");
    expect(readStoredTheme(storage)).toBe("light");
  });

  it("torna al default se lo storage lancia", () => {
    const storage: ThemeStorage = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(readStoredTheme(storage)).toBe("dark");
    expect(() => storeTheme(storage, "light")).not.toThrow();
  });

  it("senza storage resta il tema scuro", () => {
    expect(readStoredTheme(null)).toBe("dark");
  });
});

describe("applyTheme", () => {
  it("attiva la classe del tema e imposta data-theme/color-scheme", () => {
    const root = fakeRoot();
    applyTheme("light", root);
    expect(root.classes).toEqual({ dark: false, light: true });
    expect(root.attributes["data-theme"]).toBe("light");
    expect(root.style.colorScheme).toBe("light");

    applyTheme("dark", root);
    expect(root.classes).toEqual({ dark: true, light: false });
    expect(root.style.colorScheme).toBe("dark");
  });

  it("nextTheme alterna i due temi", () => {
    expect(nextTheme("dark")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
  });
});
