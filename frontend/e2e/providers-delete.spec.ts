import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  PROVIDER_NETFLIX,
  PROVIDER_PARAMOUNT_UNMAPPED,
  SOURCE_COLLECTION_NETFLIX,
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

test("elimina l'ultimo provider insieme alle sue collezioni locali", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  let providers = [PROVIDER_NETFLIX];
  let dialogMessage = "";
  api.on("GET", "/api/providers", () => ({
    body: { items: providers, total: providers.length },
  }));
  api.on("GET", "/api/collections", () => ({ body: { items: [], total: 0 } }));
  api.on("DELETE", `/api/providers/${PROVIDER_NETFLIX.id}`, () => {
    providers = [];
    return { status: 204 };
  });
  await api.install();
  page.on("dialog", (dialog) => {
    dialogMessage = dialog.message();
    void dialog.accept();
  });

  await page.goto("/app/providers");
  const card = page.getByTestId("provider-card-netflix");
  await expect(card).toBeVisible();
  await card.getByTestId("provider-delete-netflix").click();

  await expect(card).toHaveCount(0);
  expect(dialogMessage).toContain("collezioni locali");
  expect(api.callsTo("DELETE", `/api/providers/${PROVIDER_NETFLIX.id}`)).toHaveLength(1);
});

test("elimina la collezione direttamente dalla card del provider", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  let collections = [SOURCE_COLLECTION_NETFLIX];
  api.on("GET", "/api/providers", () => ({
    body: { items: [PROVIDER_NETFLIX], total: 1 },
  }));
  api.on("GET", "/api/collections", () => ({
    body: { items: collections, total: collections.length },
  }));
  api.on("DELETE", `/api/collections/${SOURCE_COLLECTION_NETFLIX.id}`, () => {
    collections = [];
    return { status: 204 };
  });
  mockAppShell(api);
  await api.install();
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto("/app/providers");
  const card = page.getByTestId("provider-card-netflix");
  const button = card.getByTestId(
    `provider-collection-delete-${SOURCE_COLLECTION_NETFLIX.slug}`,
  );
  await expect(button).toBeVisible();
  await button.click();

  await expect(button).toHaveCount(0);
  await expect(card.getByText("Nessuna collezione locale.")).toBeVisible();
  expect(
    api.callsTo("DELETE", `/api/collections/${SOURCE_COLLECTION_NETFLIX.id}`),
  ).toHaveLength(1);
});
