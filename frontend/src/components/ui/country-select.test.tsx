// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { COUNTRIES } from "../../lib/countries";
import { CountrySelect } from "./country-select";

// Niente @testing-library/jest-dom in questo repo: si usano le assertion base.
// `globals` non è attivo, quindi il cleanup automatico non gira: lo facciamo qui.
afterEach(cleanup);
function renderSelect(value = "IT", onChange = vi.fn()) {
  render(<CountrySelect id="country" value={value} onChange={onChange} />);
  return { input: screen.getByRole("combobox") as HTMLInputElement, onChange };
}

function optionLabels(): string[] {
  return screen.getAllByRole("option").map((option) => option.textContent ?? "");
}

describe("CountrySelect", () => {
  it("mostra il paese selezionato quando è chiuso", () => {
    const { input } = renderSelect();
    expect(input.value).toBe("IT — Italia");
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("apre la listbox con tutti i paesi al focus", () => {
    const { input } = renderSelect();
    fireEvent.focus(input);
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(screen.getAllByRole("option")).toHaveLength(COUNTRIES.length);
    expect(optionLabels()).toContain("IT — Italia");
  });

  it("filtra per nome ignorando accenti e maiuscole", () => {
    const { input } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "germa" } });
    expect(optionLabels()).toEqual(["DE — Germania"]);
  });

  it("filtra anche per codice ISO", () => {
    const { input } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "fr" } });
    // il filtro è substring sul nome + prefisso sul codice: "fr" prende anche
    // "Francese/Francesi" e "Sudafrica"
    expect(optionLabels()).toEqual([
      "FR — Francia",
      "GF — Guyana Francese",
      "PF — Polinesia Francese",
      "CF — Repubblica Centrafricana",
      "ZA — Sudafrica",
      "TF — Terre Australi Francesi",
    ]);
  });

  it("seleziona con un click e notifica il codice", () => {
    const { input, onChange } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "giappone" } });
    fireEvent.mouseDown(screen.getByRole("option"));
    expect(onChange).toHaveBeenCalledWith("JP");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("naviga con le frecce e conferma con Invio", () => {
    const { input, onChange } = renderSelect();
    fireEvent.focus(input);
    // "guinea" è volutamente ambiguo: 4 paesi, così le frecce hanno senso
    fireEvent.change(input, { target: { value: "guinea" } });
    expect(optionLabels()).toEqual([
      "GN — Guinea",
      "GQ — Guinea Equatoriale",
      "GW — Guinea-Bissau",
      "PG — Papua Nuova Guinea",
    ]);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("GQ");
  });

  it("Escape chiude senza cambiare il paese", () => {
    const { input, onChange } = renderSelect();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("dice quando nessun paese corrisponde", () => {
    const { input } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zzzz" } });
    expect(screen.getByText("Nessun paese corrisponde alla ricerca.")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });

  it("non aggiunge il paese selezionato quando il filtro lo esclude", () => {
    const { input } = renderSelect("IT");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "germania" } });
    expect(optionLabels()).toEqual(["DE — Germania"]);
  });
});
