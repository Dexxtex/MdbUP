import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import { mockAppShell, mockAuthenticatedSession } from "./support/fixtures";

const CANDIDATES = {
  items: [
    {
      key: "tmdb:8",
      name: "Netflix",
      suggested_slug: "netflix",
      sources: ["tmdb"],
      source_key: "tmdb",
      tmdb_movie_id: "8",
      tmdb_tv_id: "213",
      justwatch_short_name: null,
      justwatch_technical_name: null,
      justwatch_monetization_types: ["FLATRATE"],
      tvdb_company_id: null,
      logo_url: null,
      justwatch_provider_id: null,
    },
    {
      key: "justwatch:dnp",
      name: "Disney+",
      suggested_slug: "disney-plus",
      sources: ["justwatch"],
      source_key: "justwatch",
      tmdb_movie_id: null,
      tmdb_tv_id: null,
      justwatch_short_name: "dnp",
      justwatch_technical_name: "disneyplus",
      justwatch_monetization_types: ["FLATRATE"],
      tvdb_company_id: null,
      logo_url: null,
      justwatch_provider_id: null,
    },
  ],
  sources: [
    { source_key: "tmdb", status: "OK", message: "", count: 1 },
    { source_key: "justwatch", status: "OK", message: "", count: 1 },
    { source_key: "tvdb", status: "MANUAL_ONLY", message: "", count: 0 },
  ],
  total: 2,
};

test("ricerca e menù a tendina del catalogo sono un unico controllo", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.on("GET", "/api/providers/catalog", () => ({ body: CANDIDATES }));
  api.on("GET", "/api/providers", () => ({ body: { items: [], total: 0 } }));
  api.on("GET", "/api/collections", () => ({ body: { items: [], total: 0 } }));
  await api.install();

  await page.goto("/app/providers");
  await page.getByRole("button", { name: "Aggiungi provider" }).click();

  const picker = page.getByLabel("Cerca o scegli un provider");
  await expect(picker).toBeVisible();
  await expect(page.getByLabel("Provider disponibili")).toHaveCount(0); // niente select separata

  // i campi ID manuali non ci sono più: senza scelta dal catalogo non si crea nulla
  await expect(page.getByLabel("ID TMDb per i film")).toHaveCount(0);
  await expect(page.getByLabel("Codice breve")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Crea provider" })).toBeDisabled();
  await expect(page.getByText("Scegli prima un provider dal catalogo")).toBeVisible();

  await picker.click();
  const listbox = page.getByRole("listbox", { name: "Provider disponibili" });
  await expect(listbox).toBeVisible();
  await expect(listbox.getByRole("group", { name: "TMDb" })).toBeVisible();
  await expect(listbox.getByRole("group", { name: "JustWatch" })).toBeVisible();

  await picker.fill("disney");
  await expect(listbox.getByRole("option")).toHaveCount(1);
  await listbox.getByRole("option", { name: "Disney+" }).click();

  // la scelta compila l'identità del provider
  await expect(page.getByLabel("Identificativo (slug)")).toHaveValue("disney-plus");
  await expect(page.getByRole("button", { name: "Crea provider" })).toBeEnabled();
  await expect(page.getByLabel("Nome del provider")).toHaveValue("Disney+");

  // il catalogo è chiesto per il paese selezionato, non per IT fisso
  await page.getByLabel("Paese").click();
  await page.getByLabel("Paese").fill("germania");
  await page.getByRole("option", { name: "DE — Germania" }).click();
  await expect
    .poll(() =>
      api.calls
        .filter((call) => call.pathname === "/api/providers/catalog")
        .map((call) => call.search),
    )
    .toContain("?country=DE");
});
