import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  CATALOG_CHANGES,
  PROVIDER_NETFLIX,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

test("la pagina Cambi Catalogo filtra il feed e mostra i contatori", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  api.json("GET", "/api/providers", { items: [PROVIDER_NETFLIX], total: 1 });
  api.on("GET", "/api/catalog-changes", (call) => {
    const direction = new URLSearchParams(call.search).get("direction");
    if (direction === "REMOVED") {
      return {
        body: {
          ...CATALOG_CHANGES,
          items: [{ ...CATALOG_CHANGES.items[0], direction: "REMOVED" }],
        },
      };
    }
    return { body: CATALOG_CHANGES };
  });
  mockAppShell(api);
  await api.install();

  await page.goto("/app/catalog-changes");
  await expect(page.getByTestId("catalog-changes")).toBeVisible();
  await expect(page.getByTestId("catalog-counter-added-today")).toContainText("42");
  await expect(page.getByTestId("catalog-counter-removed-today")).toContainText("18");

  const feed = page.getByTestId("catalog-change-feed");
  await expect(feed).toContainText("Dune: Parte due");
  await expect(feed).toContainText("Entrato");
  await expect(feed).toContainText("Fonte: JustWatch (Aggregatore)");

  await page.getByTestId("catalog-window-7d").click();
  await expect
    .poll(() =>
      api.callsTo("GET", "/api/catalog-changes").some((call) => call.search.includes("window=7d")),
    )
    .toBe(true);

  await page.locator("#catalog-direction").selectOption("REMOVED");
  await expect
    .poll(() =>
      api.callsTo("GET", "/api/catalog-changes").some((call) => call.search.includes("direction=REMOVED")),
    )
    .toBe(true);
  await expect(feed).toContainText("Uscito");

  await page.locator("#catalog-search").fill("Dune");
  await expect
    .poll(() =>
      api.callsTo("GET", "/api/catalog-changes").some((call) => call.search.includes("search=Dune")),
    )
    .toBe(true);
  expect(api.unmatched).toEqual([]);
});
