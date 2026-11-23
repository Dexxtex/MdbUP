// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";

import { ProviderCatalogPicker } from "./provider-catalog-picker";

afterEach(cleanup);

type Item = { key: string; name: string };

const GROUPS: { source: string; label: string; items: Item[] }[] = [
  {
    source: "tmdb",
    label: "TMDb",
    items: [
      { key: "netflix", name: "Netflix" },
      { key: "disney", name: "Disney+" },
    ],
  },
  { source: "justwatch", label: "JustWatch", items: [{ key: "raiplay", name: "RaiPlay" }] },
];

/** Controllato: il test fa da genitore, come la pagina. */
function renderPicker(groups = GROUPS) {
  const onSelect = vi.fn();
  function Harness() {
    const [query, setQuery] = useState("");
    const visible = groups
      .map((group) => ({
        ...group,
        items: group.items.filter((item) =>
          item.name.toLowerCase().includes(query.toLowerCase()),
        ),
      }))
      .filter((group) => group.items.length > 0);
    return (
      <ProviderCatalogPicker
        id="provider-catalog-search"
        value={query}
        onChange={setQuery}
        groups={visible}
        onSelect={onSelect}
      />
    );
  }
  render(<Harness />);
  return { input: screen.getByRole("combobox") as HTMLInputElement, onSelect };
}

describe("ProviderCatalogPicker", () => {
  it("apre il menu raggruppato per fonte", () => {
    const { input } = renderPicker();
    fireEvent.focus(input);
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("listbox", { name: "Provider disponibili" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "TMDb" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "JustWatch" })).toBeTruthy();
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Netflix",
      "Disney+",
      "RaiPlay",
    ]);
  });

  it("filtra mentre si scrive e mantiene i gruppi", () => {
    const { input } = renderPicker();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "dis" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Disney+"]);
    expect(screen.queryByRole("group", { name: "JustWatch" })).toBeNull();

    fireEvent.change(input, { target: { value: "rai" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["RaiPlay"]);
  });

  it("senza candidati non mostra alcun menu", () => {
    const { input } = renderPicker([]);
    fireEvent.focus(input);
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("se il filtro non trova nulla il menu sparisce", () => {
    const { input } = renderPicker();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zzz" } });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("sceglie con il click e chiude il menu", () => {
    const { input, onSelect } = renderPicker();
    fireEvent.focus(input);
    fireEvent.mouseDown(screen.getByRole("option", { name: "Disney+" }));
    expect(onSelect).toHaveBeenCalledWith({ key: "disney", name: "Disney+" });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("naviga con le frecce e conferma con Invio", () => {
    const { input, onSelect } = renderPicker();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith({ key: "disney", name: "Disney+" });
  });

  it("Escape chiude senza scegliere", () => {
    const { input, onSelect } = renderPicker();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
