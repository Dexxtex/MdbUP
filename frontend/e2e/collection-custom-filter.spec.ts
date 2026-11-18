import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  GENRES,
  PROVIDER_NETFLIX,
  PROVIDER_PRIME,
  SOURCE_COLLECTION_NETFLIX,
  SOURCE_COLLECTION_PRIME,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

const CREATED_COLLECTION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1";

test("crea una collezione CUSTOM_FILTER multi-provider dalla UI", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  api.json("GET", "/api/providers", {
    items: [PROVIDER_NETFLIX, PROVIDER_PRIME],
    total: 2,
  });
  api.json("GET", "/api/genres", GENRES);
  api.json("GET", "/api/collections", {
    items: [SOURCE_COLLECTION_NETFLIX, SOURCE_COLLECTION_PRIME],
    total: 2,
  });
  api.json("POST", "/api/collections", {
    ...SOURCE_COLLECTION_NETFLIX,
    id: CREATED_COLLECTION_ID,
    name: "Combinata azione",
    slug: "combinata-azione",
    kind: "CUSTOM_FILTER",
    is_local_filter: true,
    is_multi_provider: true,
  });
  mockAppShell(api);
  await api.install();

  await page.goto("/app/collections/new");
  await expect(page.getByTestId("collection-builder")).toBeVisible();

  await page.locator("#collection-kind").selectOption("CUSTOM_FILTER");
  await page.getByTestId("media-type-MOVIE").click();

  await page.getByTestId(`source-collection-${SOURCE_COLLECTION_NETFLIX.id}`).click();
  await page.getByTestId(`source-collection-${SOURCE_COLLECTION_PRIME.id}`).click();
  await page.getByTestId("genre-28").click();

  await page.locator("#local-vote-average").fill("7.5");
  await page.locator("#local-vote-count").fill("500");
  await page.locator("#local-year-from").fill("2000");
  await page.locator("#local-year-to").fill("2024");
  await page.locator("#local-language").fill("it");

  await page.locator("#collection-name").fill("Combinata azione");
  await page.locator("#collection-slug").fill("combinata-azione");

  await expect(page.getByTestId("collection-criteria-preview")).toContainText(
    "Combinata multi-provider",
  );
  await expect(page.getByTestId("collection-criteria-preview")).toContainText(
    "Netflix film azione + Prime film azione",
  );

  await page.getByTestId("collection-submit").click();

  await expect(page).toHaveURL(/\/app\/collections$/);

  const creates = api.callsTo("POST", "/api/collections");
  expect(creates).toHaveLength(1);
  expect(creates[0].body).toMatchObject({
    media_type: "MOVIE",
    name: "Combinata azione",
    slug: "combinata-azione",
    kind: "CUSTOM_FILTER",
    genre_ids: [28],
    source_collection_ids: [SOURCE_COLLECTION_NETFLIX.id, SOURCE_COLLECTION_PRIME.id],
    min_vote_average: 7.5,
    min_vote_count: 500,
    year_from: 2000,
    year_to: 2024,
    original_language: "it",
    local_sort_by: "vote_average.desc",
    is_active: true,
  });
  expect(creates[0].body).not.toHaveProperty("provider_id");
  expect(api.unmatched).toEqual([]);
});
