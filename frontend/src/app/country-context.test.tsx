// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { CountryProvider, CountryUrlSync, useCountry } from "./country-context";

const STORAGE_KEY = "mdbup.country";

const originalStorage = Object.getOwnPropertyDescriptor(window, "localStorage");

function stubStorage(initial: Record<string, string> = {}, behaviour: "ok" | "throw" = "ok") {
  const data = new Map(Object.entries(initial));
  const storage = {
    getItem: (key: string) => {
      if (behaviour === "throw") throw new DOMException("blocked", "SecurityError");
      return data.get(key) ?? null;
    },
    setItem: (key: string, value: string) => {
      if (behaviour === "throw") throw new DOMException("blocked", "SecurityError");
      data.set(key, value);
    },
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
    key: () => null,
    get length() {
      return data.size;
    },
  };
  Object.defineProperty(window, "localStorage", { value: storage, configurable: true });
  return data;
}

let renders = 0;
function Probe() {
  renders += 1;
  const location = useLocation();
  const { country, setCountry } = useCountry();
  return (
    <div>
      <p data-testid="probe">{`${country}|${location.search}`}</p>
      <button type="button" data-testid="pick-fr" onClick={() => setCountry("FR")}>
        FR
      </button>
      <button type="button" data-testid="pick-it" onClick={() => setCountry("IT")}>
        IT
      </button>
    </div>
  );
}

function mount(entry: string) {
  renders = 0;
  render(
    <StrictMode>
      <MemoryRouter initialEntries={[entry]}>
        <CountryProvider>
          <CountryUrlSync />
          <Probe />
        </CountryProvider>
      </MemoryRouter>
    </StrictMode>,
  );
  return () => document.querySelector('[data-testid="probe"]')?.textContent ?? "";
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  // ripristino lo stato originale: nessun effetto sui test successivi
  if (originalStorage) Object.defineProperty(window, "localStorage", originalStorage);
});

describe("CountryProvider + CountryUrlSync", () => {
  it("storage DE e URL ?country=FR convergono su FR senza loop", async () => {
    stubStorage({ [STORAGE_KEY]: "DE" });
    const state = mount("/app/collections?country=FR");

    await waitFor(() => expect(state()).toContain("FR"));
    const settled = renders;
    await new Promise((resolve) => setTimeout(resolve, 300));

    expect(renders).toBe(settled);
    expect(state()).toBe("FR|?country=FR");
  });

  it("un link ?country=FR vince sulla preferenza salvata e finisce nell'URL", async () => {
    stubStorage({ [STORAGE_KEY]: "DE" });
    const state = mount("/app/collections?country=FR");
    await waitFor(() => expect(state()).toBe("FR|?country=FR"));
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("FR");
  });

  it("con una preferenza salvata e URL senza paese, l'URL viene allineato", async () => {
    stubStorage({ [STORAGE_KEY]: "DE" });
    const state = mount("/app/runs");
    await waitFor(() => expect(state()).toBe("DE|?country=DE"));
    const settled = renders;
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(renders).toBe(settled);
  });

  it("scegliere un paese lo scrive nell'URL; tornare al default lo toglie", async () => {
    stubStorage();
    const state = mount("/app/collections");
    await waitFor(() => expect(state()).toBe("IT|"));

    fireEvent.click(screen.getByTestId("pick-fr"));
    await waitFor(() => expect(state()).toBe("FR|?country=FR"));

    fireEvent.click(screen.getByTestId("pick-it"));
    await waitFor(() => expect(state()).toBe("IT|"));
  });

  it("se localStorage lancia l'app parte comunque, con il default", async () => {
    stubStorage({}, "throw");
    const state = mount("/app/collections");

    await waitFor(() => expect(state()).toBe("IT|"));
  });
});
