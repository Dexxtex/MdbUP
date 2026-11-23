import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import { mockAppShell, mockAuthenticatedSession } from "./support/fixtures";

test("la Guida apre il contenuto con icona compatta e titolo visibile", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  await api.install();

  await page.goto("/app");
  const icon = page.getByTestId("nav-help").locator("svg");
  const iconBox = await icon.boundingBox();
  expect(iconBox?.width).toBe(16);
  expect(iconBox?.height).toBe(16);

  await page.getByTestId("nav-help").click();
  await expect(page).toHaveURL(/\/app\/help$/);
  await expect(page.getByTestId("help-page")).toBeVisible();

  const title = page.getByRole("heading", { name: "Guida", level: 1 });
  await expect(title).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);

  const titleBox = await title.boundingBox();
  const headerBox = await page.locator("header").first().boundingBox();
  expect(titleBox?.y).toBeGreaterThan((headerBox?.y ?? 0) + (headerBox?.height ?? 0));

  // il connettore JustWatch vive qui, con i dati runtime della fonte
  const connector = page.getByTestId("help-justwatch-connector");
  await expect(connector).toBeVisible();
  await expect(connector.getByRole("heading", { name: "JustWatch", exact: true })).toBeVisible();
  // valori reali della card: throttle 1000 ms -> "1 req/s", cache 300 s -> "5 min"
  await expect(connector.getByText("1 req/s")).toBeVisible();
  await expect(connector.getByText("5 min")).toBeVisible();
  await expect(connector.getByText("Apple TV+").first()).toBeVisible();

  // e la Guida spiega paese e ricerca provider, non solo i binding
  await expect(page.getByRole("heading", { name: "Connettore JustWatch" })).toBeVisible();
  await expect(page.getByText(/scegli prima il paese/)).toBeVisible();
  await expect(page.getByText(/Cerca provider/)).toBeVisible();
});
