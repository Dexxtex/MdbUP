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
});
