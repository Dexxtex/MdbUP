import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  PROVIDER_NETFLIX,
  PROVIDER_PARAMOUNT_UNMAPPED,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

test("Cerca provider apre il menu dei provider presenti e filtra la pagina", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  const providers = [PROVIDER_NETFLIX, PROVIDER_PARAMOUNT_UNMAPPED];
  api.on("GET", "/api/providers", () => ({ body: { items: providers, total: providers.length } }));
  api.on("GET", "/api/collections", () => ({ body: { items: [], total: 0 } }));
  await api.install();

  await page.goto("/app/providers");

  const search = page.getByLabel("Cerca provider");
  await search.click();
  const listbox = page.getByRole("listbox", { name: "Provider presenti" });
  await expect(listbox).toBeVisible();
  await expect(listbox.getByRole("option")).toHaveCount(2);
  await expect(listbox.getByRole("option", { name: PROVIDER_NETFLIX.name })).toBeVisible();

  // il menu propone le voci e la scelta filtra la pagina
  await listbox.getByRole("option", { name: PROVIDER_PARAMOUNT_UNMAPPED.name }).click();
  await expect(search).toHaveValue(PROVIDER_PARAMOUNT_UNMAPPED.name);
  await expect(page.getByTestId(`provider-card-${PROVIDER_PARAMOUNT_UNMAPPED.slug}`)).toBeVisible();
  await expect(page.getByTestId(`provider-card-${PROVIDER_NETFLIX.slug}`)).toHaveCount(0);
});

test("senza provider il menu non esiste", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.on("GET", "/api/providers", () => ({ body: { items: [], total: 0 } }));
  api.on("GET", "/api/collections", () => ({ body: { items: [], total: 0 } }));
  await api.install();

  await page.goto("/app/providers");

  const search = page.getByLabel("Cerca provider");
  await search.click();
  await expect(search).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("listbox")).toHaveCount(0);
  await expect(page.getByRole("option")).toHaveCount(0);
  // nessun messaggio "vuoto" al posto del menu
  await expect(page.getByText("Provider presenti")).toHaveCount(0);
});
