// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderSuggest, type SuggestProvider } from "./provider-suggest";

afterEach(cleanup);

const PROVIDERS: SuggestProvider[] = [
  { name: "Netflix", slug: "netflix", kind: "FLATRATE" },
  { name: "Prime Video", slug: "prime-video", kind: "FLATRATE" },
  { name: "RaiPlay", slug: "raiplay", kind: "FREE" },
];

/** Il componente è controllato: il test fa da genitore con il proprio stato. */
function renderSuggest(providers: readonly SuggestProvider[] = PROVIDERS, initial = "") {
  const onChange = vi.fn();
  function Harness() {
    const [value, setValue] = useState(initial);
    return (
      <ProviderSuggest
        id="provider-search"
        value={value}
        onChange={(text) => {
          onChange(text);
          setValue(text);
        }}
        providers={providers}
      />
    );
  }
  render(<Harness />);
  return { input: screen.getByRole("combobox") as HTMLInputElement, onChange };
}

describe("ProviderSuggest", () => {
  it("al focus elenca i provider presenti", () => {
    const { input } = renderSuggest();
    fireEvent.focus(input);
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("listbox", { name: "Provider presenti" })).toBeTruthy();
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Netflix",
      "Prime Video",
      "RaiPlay",
    ]);
  });

  it("senza provider non mostra alcun menu", () => {
    const { input } = renderSuggest([]);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "net" } });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("filtra per nome, slug e tipo", () => {
    const { input } = renderSuggest();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "prime" } });
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Prime Video",
    ]);
    fireEvent.change(input, { target: { value: "free" } });
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["RaiPlay"]);
    fireEvent.change(input, { target: { value: "raiplay" } });
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["RaiPlay"]);
  });

  it("se il filtro non trova nulla il menu sparisce, senza messaggi vuoti", () => {
    const { input } = renderSuggest();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zzz" } });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });

  it("scegliere una voce scrive il nome e notifica il cambio", () => {
    const { input, onChange } = renderSuggest();
    fireEvent.focus(input);
    fireEvent.mouseDown(screen.getByRole("option", { name: "Prime Video" }));
    expect(onChange).toHaveBeenCalledWith("Prime Video");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("naviga con le frecce e conferma con Invio", () => {
    const { input, onChange } = renderSuggest();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("Prime Video");
  });

  it("Escape chiude il menu senza toccare la ricerca", () => {
    const { input, onChange } = renderSuggest(PROVIDERS, "net");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
