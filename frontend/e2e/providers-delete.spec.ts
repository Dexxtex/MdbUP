import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  PROVIDER_NETFLIX,
  PROVIDER_PARAMOUNT_UNMAPPED,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

test("elimina un provider senza collezioni direttamente dalla card", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  let providers = [PROVIDER_PARAMOUNT_UNMAPPED];
  api.on("GET", "/api/providers", () => ({ body: { items: providers, total: providers.length } }));
  api.on("GET", "/api/collections", () => ({ body: { items: [], total: 0 } }));
  api.on("DELETE", `/api/providers/${PROVIDER_PARAMOUNT_UNMAPPED.id}`, () => {
    providers = [];
    return { status: 204 };
  });
  await api.install();
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto("/app/providers");
  const card = page.getByTestId("provider-card-paramount-plus");
  await expect(card).toBeVisible();
  await card.getByTestId("provider-delete-paramount-plus").click();

  await expect(card).toHaveCount(0);
  expect(api.callsTo("DELETE", `/api/providers/${PROVIDER_PARAMOUNT_UNMAPPED.id}`)).toHaveLength(1);
});

test("il provider usato da collezioni non è eliminabile dalla card", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.on("GET", "/api/providers", () => ({
    body: { items: [PROVIDER_NETFLIX], total: 1 },
  }));
  api.on("GET", "/api/collections", () => ({ body: { items: [], total: 0 } }));
  await api.install();

  await page.goto("/app/providers");
  const button = page.getByTestId("provider-delete-netflix");
  await expect(button).toBeDisabled();
  await expect(button).toHaveAttribute("title", /collezioni/i);
  expect(api.callsTo("DELETE", `/api/providers/${PROVIDER_NETFLIX.id}`)).toHaveLength(0);
});
