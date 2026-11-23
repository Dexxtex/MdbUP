// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TvdbCompanySelect } from "./tvdb-company-select";

const useTvdbCompanies = vi.fn();
vi.mock("../../hooks/queries", () => ({
  useTvdbCompanies: (query: string) => useTvdbCompanies(query),
}));

const NETFLIX = {
  company_id: "2120",
  name: "Netflix",
  company_type: "Production Company",
  slug: "netflix",
  country: "us",
};

afterEach(cleanup);
beforeEach(() => {
  useTvdbCompanies.mockReset();
  useTvdbCompanies.mockReturnValue({ data: undefined, isFetching: false, isError: false });
});

/** Il campo è controllato: il test fa da genitore, come la pagina. */
function renderSelect(initial = "") {
  const onChange = vi.fn();
  function Harness() {
    const [value, setValue] = useState(initial);
    return (
      <TvdbCompanySelect
        id="provider-tvdb-company"
        value={value}
        onChange={(companyId) => {
          onChange(companyId);
          setValue(companyId);
        }}
      />
    );
  }
  render(<Harness />);
  return { input: screen.getByRole("combobox") as HTMLInputElement, onChange };
}

describe("TvdbCompanySelect", () => {
  it("sotto i 2 caratteri non apre il menù e suggerisce di scrivere", async () => {
    // il componente passa sempre la query all'hook: è l'hook a non fare la
    // richiesta sotto i 2 caratteri (enabled). Qui conta la UI.
    const { input } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "n" } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(screen.getByText("Scrivi almeno 2 lettere per cercare.")).toBeTruthy();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(useTvdbCompanies).toHaveBeenLastCalledWith("n");
  });

  it("mostra i risultati della ricerca e li rende selezionabili", async () => {
    useTvdbCompanies.mockReturnValue({ data: { items: [NETFLIX], total: 1 }, isFetching: false, isError: false });
    const { input, onChange } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "netf" } });
    await new Promise((resolve) => setTimeout(resolve, 350));

    const listbox = screen.getByRole("listbox", { name: "Company TheTVDB" });
    expect(listbox).toBeTruthy();
    fireEvent.mouseDown(screen.getByRole("option"));
    expect(onChange).toHaveBeenCalledWith("2120");
  });

  it("quando è chiuso il campo contiene l'ID e il nome compare a parte", async () => {
    useTvdbCompanies.mockReturnValue({
      data: { items: [NETFLIX], total: 1 },
      isFetching: false,
      isError: false,
    });
    const { input } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "netf" } });
    await waitFor(() => expect(screen.getByRole("option")).toBeTruthy());
    fireEvent.mouseDown(screen.getByRole("option"));
    expect(input.value).toBe("2120");
    expect(screen.getByText("Selezionato: Netflix")).toBeTruthy();
  });

  it("dice quando non trova nulla", async () => {
    useTvdbCompanies.mockReturnValue({ data: { items: [], total: 0 }, isFetching: false, isError: false });
    const { input } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zzz" } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(screen.getByText(/Nessuna company trovata/)).toBeTruthy();
  });

  it("segnala la credenziale mancante", async () => {
    useTvdbCompanies.mockReturnValue({ data: undefined, isFetching: false, isError: true });
    const { input } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "netf" } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(screen.getByText(/controlla la credenziale TheTVDB/)).toBeTruthy();
  });

  it("naviga con le frecce e conferma con Invio", async () => {
    useTvdbCompanies.mockReturnValue({
      data: { items: [NETFLIX, { ...NETFLIX, company_id: "3543", name: "Netflix Studios" }], total: 2 },
      isFetching: false,
      isError: false,
    });
    const { input, onChange } = renderSelect();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "netf" } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("3543");
  });
});
