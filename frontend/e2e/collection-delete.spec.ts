import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  PROVIDER_NETFLIX,
  SOURCE_COLLECTION_NETFLIX,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

const COLLECTION_PATH = `/api/collections/${SOURCE_COLLECTION_NETFLIX.id}`;

test("elimina una collezione dalla tabella", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  let collections = [SOURCE_COLLECTION_NETFLIX];
  api.json("GET", "/api/providers", { items: [PROVIDER_NETFLIX], total: 1 });
  api.on("GET", "/api/collections", () => ({
    body: { items: collections, total: collections.length },
  }));
  api.on("DELETE", COLLECTION_PATH, () => {
    collections = [];
    return { status: 204 };
  });
  mockAppShell(api);
  await api.install();
  let dialogMessage = "";
  page.on("dialog", (dialog) => {
    dialogMessage = dialog.message();
    void dialog.accept();
  });

  await page.goto("/app/collections");
  const table = page.locator("table");
  const button = table.getByTestId(`collection-delete-${SOURCE_COLLECTION_NETFLIX.slug}`);
  await expect(button).toBeVisible();
  await button.click();

  await expect(
    table.getByTestId(`collection-delete-${SOURCE_COLLECTION_NETFLIX.slug}`),
  ).toHaveCount(0);
  expect(dialogMessage).toContain("liste MDBList remote");
  expect(api.callsTo("DELETE", COLLECTION_PATH)).toHaveLength(1);
});

test("elimina una collezione dalla card mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  let collections = [SOURCE_COLLECTION_NETFLIX];
  api.json("GET", "/api/providers", { items: [PROVIDER_NETFLIX], total: 1 });
  api.on("GET", "/api/collections", () => ({
    body: { items: collections, total: collections.length },
  }));
  api.on("DELETE", COLLECTION_PATH, () => {
    collections = [];
    return { status: 204 };
  });
  mockAppShell(api);
  await api.install();
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto("/app/collections");
  const cards = page.locator("ul");
  const button = cards.getByTestId(`collection-delete-card-${SOURCE_COLLECTION_NETFLIX.slug}`);
  await expect(button).toBeVisible();
  await button.click();

  await expect(
    cards.getByTestId(`collection-delete-card-${SOURCE_COLLECTION_NETFLIX.slug}`),
  ).toHaveCount(0);
  expect(api.callsTo("DELETE", COLLECTION_PATH)).toHaveLength(1);
});

test("elimina una collezione dal dettaglio e torna all'elenco", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  let deleted = false;
  api.json("GET", "/api/providers", { items: [PROVIDER_NETFLIX], total: 1 });
  api.json("GET", "/api/collections", {
    items: [SOURCE_COLLECTION_NETFLIX],
    total: 1,
  });
  api.json("GET", COLLECTION_PATH, SOURCE_COLLECTION_NETFLIX);
  api.json("GET", `${COLLECTION_PATH}/snapshots`, {
    items: [],
    total: 0,
    page: 1,
    page_size: 50,
  });
  api.on("DELETE", COLLECTION_PATH, () => {
    deleted = true;
    return { status: 204 };
  });
  mockAppShell(api);
  await api.install();
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto(`/app/collections/${SOURCE_COLLECTION_NETFLIX.id}`);
  await expect(
    page.getByRole("heading", { name: SOURCE_COLLECTION_NETFLIX.name, level: 1 }),
  ).toBeVisible();
  await page.getByTestId(`collection-delete-${SOURCE_COLLECTION_NETFLIX.slug}`).click();

  await expect(page).toHaveURL(/\/app\/collections$/);
  expect(deleted).toBe(true);
  expect(api.callsTo("DELETE", COLLECTION_PATH)).toHaveLength(1);
});
