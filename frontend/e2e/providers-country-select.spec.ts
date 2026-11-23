import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import { PROVIDER_NETFLIX, mockAppShell, mockAuthenticatedSession } from "./support/fixtures";

test("il paese si cerca per nome o ISO e pilota le query", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.on("GET", "/api/providers", () => ({ body: { items: [PROVIDER_NETFLIX], total: 1 } }));
  api.on("GET", "/api/collections", () => ({ body: { items: [], total: 0 } }));
  await api.install();

  await page.goto("/app/providers");

  const combobox = page.getByLabel("Paese");
  await expect(combobox).toHaveValue("IT — Italia");
  await expect(combobox).toHaveAttribute("aria-expanded", "false");

  // apre l'elenco: 249 paesi con ISO e nome accanto
  await combobox.click();
  await expect(combobox).toHaveAttribute("aria-expanded", "true");
  const listbox = page.getByRole("listbox", { name: "Paesi disponibili" });
  await expect(listbox.getByRole("option")).toHaveCount(249);
  await expect(listbox.getByRole("option", { name: "IT — Italia" })).toBeVisible();

  // il filtro accetta il nome (senza accenti/maiuscole) e restringe l'elenco
  await combobox.fill("germa");
  await expect(listbox.getByRole("option")).toHaveCount(1);
  await listbox.getByRole("option", { name: "DE — Germania" }).click();

  await expect(combobox).toHaveValue("DE — Germania");
  await expect
    .poll(() =>
      api.calls.filter((call) => call.pathname === "/api/providers").map((call) => call.search),
    )
    .toContain("?country=DE");

  // la matrice confronta i provider del paese scelto, non "italiani" a priori
  await expect(
    page.getByRole("table", { name: "Matrice comparativa dei provider — Germania" }),
  ).toBeVisible();

  // e il filtro funziona anche per codice ISO
  await combobox.click();
  await combobox.fill("fr");
  await page.getByRole("option", { name: "FR — Francia" }).click();
  await expect(combobox).toHaveValue("FR — Francia");
  await expect
    .poll(() =>
      api.calls.filter((call) => call.pathname === "/api/providers").map((call) => call.search),
    )
    .toContain("?country=FR");

  // il connettore JustWatch non sta più nella pagina Provider (è nella Guida)
  await expect(page.getByTestId("justwatch-connector")).toHaveCount(0);

  // vista tabella: la caption riflette il paese corrente
  await page.getByRole("button", { name: "Tabella" }).click();
  await expect(page.getByRole("table", { name: "Provider per il paese FR" })).toBeVisible();
});
