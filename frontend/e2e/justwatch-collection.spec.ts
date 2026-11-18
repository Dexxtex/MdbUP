import { expect, test } from "@playwright/test";
import type { Collection } from "../src/api/types";
import { ApiMock } from "./support/api-mock";
import {
  GENRES,
  JUSTWATCH_COLLECTION_ID,
  JUSTWATCH_EPISODE_EVENTS,
  JUSTWATCH_ITEM,
  JUSTWATCH_PREVIEW_ID,
  JUSTWATCH_SNAPSHOT,
  JUSTWATCH_SNAPSHOT_ID,
  PROVIDER_APPLE_TV,
  PROVIDER_PARAMOUNT_UNMAPPED,
  justwatchCollection,
  justwatchPreview,
  mockAppShell,
  mockAuthenticatedSession,
  mockSources,
} from "./support/fixtures";

const CREATED_NAME = "Apple TV+ film";
const CREATED_SLUG = "justwatch-apple-tv-film";

/** Campi del payload TMDb/locale che una collezione JustWatch non deve inviare. */
const TMDB_ONLY_FIELDS = [
  "source_collection_id",
  "source_collection_ids",
  "shared_snapshot_collection_id",
  "window_days",
  "min_vote_average",
  "min_vote_count",
  "original_language",
  "local_sort_by",
  "exclude_genre_ids",
];

test("crea una collezione JustWatch CATALOG e ne verifica la preview source-only", async ({
  page,
}) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockSources(api);
  api.json("GET", "/api/providers", {
    items: [PROVIDER_PARAMOUNT_UNMAPPED, PROVIDER_APPLE_TV],
    total: 2,
  });
  api.json("GET", "/api/genres", GENRES);

  // La lista si popola solo dopo la POST: il test verifica anche il refresh.
  let collections: Collection[] = [];
  api.on("GET", "/api/collections", () => ({
    body: { items: collections, total: collections.length },
  }));
  api.on("POST", "/api/collections", () => {
    collections = [justwatchCollection({ name: CREATED_NAME, slug: CREATED_SLUG })];
    return { body: collections[0] };
  });

  api.json("GET", `/api/collections/${JUSTWATCH_COLLECTION_ID}`, justwatchCollection());
  api.json("GET", `/api/collections/${JUSTWATCH_COLLECTION_ID}/snapshots`, {
    items: [JUSTWATCH_SNAPSHOT],
    total: 1,
    page: 1,
    page_size: 25,
  });
  api.json("GET", `/api/snapshots/${JUSTWATCH_SNAPSHOT_ID}/items`, {
    items: [JUSTWATCH_ITEM],
    total: 1,
    page: 1,
    page_size: 50,
  });
  api.json("POST", "/api/previews", { preview_id: JUSTWATCH_PREVIEW_ID });
  api.json("GET", `/api/previews/${JUSTWATCH_PREVIEW_ID}`, justwatchPreview());
  mockAppShell(api);
  await api.install();

  await page.goto("/app/collections/new");
  await expect(page.getByTestId("collection-builder")).toBeVisible();

  await page.getByTestId("builder-source-justwatch").click();

  // Solo il provider con mapping JustWatch verificato resta selezionabile.
  const providerSelect = page.locator("#collection-provider");
  await expect(providerSelect.locator("option")).toHaveText([
    "Seleziona…",
    PROVIDER_APPLE_TV.name,
  ]);
  await expect(page.locator("#collection-kind option")).toHaveText([
    "Catalogo",
    "Novità",
    "In arrivo",
    "Classifica",
  ]);

  await providerSelect.selectOption(PROVIDER_APPLE_TV.id);
  await page.getByTestId("media-type-MOVIE").click();
  await expect(page.getByTestId("media-type-MOVIE")).toHaveAttribute("aria-pressed", "true");
  await page.locator("#collection-kind").selectOption("CATALOG");

  // Il builder JustWatch espone la modalità flatrate (default) e "tutte".
  await expect(page.getByTestId("justwatch-offer-flatrate")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByTestId("justwatch-offer-all").click();
  await page.getByTestId("justwatch-offer-flatrate").click();

  const criteria = page.getByTestId("collection-criteria-preview");
  await expect(criteria).toContainText("JustWatch");
  await expect(criteria).toContainText(PROVIDER_APPLE_TV.name);
  await expect(criteria).toContainText("Flatrate");

  await page.locator("#collection-name").fill(CREATED_NAME);
  await page.locator("#collection-slug").fill(CREATED_SLUG);
  await page.getByTestId("collection-submit").click();
  await expect(page).toHaveURL(/\/app\/collections$/);

  const creates = api.callsTo("POST", "/api/collections");
  expect(creates).toHaveLength(1);
  expect(creates[0].body).toMatchObject({
    source_key: "justwatch",
    provider_id: PROVIDER_APPLE_TV.id,
    media_type: "MOVIE",
    kind: "CATALOG",
    name: CREATED_NAME,
    slug: CREATED_SLUG,
    offer_types: ["FLATRATE"],
    monetization_type: "FLATRATE",
    genre_ids: [],
    is_active: true,
  });
  const payload = creates[0].body as Record<string, unknown>;
  for (const field of TMDB_ONLY_FIELDS) {
    expect(payload).not.toHaveProperty(field);
  }

  // `DataTable` rende sia la card mobile sia la tabella desktop: stesso badge due volte.
  await expect(page.locator("[data-source-label]").first()).toHaveText(
    "Fonte: JustWatch (Aggregatore)",
  );

  await page.getByRole("table").getByRole("link", { name: "Apri" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/collections/${JUSTWATCH_COLLECTION_ID}$`));
  await expect(page.getByRole("heading", { name: CREATED_NAME })).toBeVisible();
  await expect(page.locator("[data-source-label]").first()).toHaveText(
    "Fonte: JustWatch (Aggregatore)",
  );

  const itemRow = page.getByRole("row").filter({ hasText: "Dune: Parte due" });
  await expect(itemRow).toContainText("Disponibile");
  await expect(itemRow).toContainText("FLATRATE");

  await page.getByTestId("source-only-preview").click();
  await expect(page.getByTestId("source-preview-state")).toContainText("READY");
  await expect(page.getByTestId("source-preview-to-add")).toHaveText("+12");
  await expect(page.getByTestId("source-preview-to-remove")).toHaveText("−0");
  await expect(page.getByText("Nessuna scrittura remota", { exact: true })).toBeVisible();

  const previews = api.callsTo("POST", "/api/previews");
  expect(previews).toHaveLength(1);
  expect(previews[0].body).toEqual({ collection_id: JUSTWATCH_COLLECTION_ID });

  // La preview source-only non tocca target MDBList né avvia run.
  expect(api.calls.filter((call) => call.pathname.startsWith("/api/targets"))).toEqual([]);
  expect(api.calls.filter((call) => call.pathname.endsWith("/episode-events"))).toEqual([]);
  expect(api.mutations().map((call) => `${call.method} ${call.pathname}`)).toEqual([
    "POST /api/collections",
    "POST /api/previews",
  ]);
  expect(api.unmatched).toEqual([]);
});

test("la classifica JustWatch è attribuita all'aggregatore e la preview può essere bloccata", async ({
  page,
}) => {
  const chartId = "cccccccc-cccc-4ccc-8ccc-ccccccccccc2";
  const blockedPreviewId = "dddddddd-dddd-4ddd-8ddd-ddddddddddd2";
  const chart = justwatchCollection({
    id: chartId,
    slug: "justwatch-classifica-film",
    name: "Classifica JustWatch film",
    kind: "CHART",
    source_label: "Classifica JustWatch",
  });

  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockSources(api);
  api.json("GET", "/api/providers", { items: [PROVIDER_APPLE_TV], total: 1 });
  api.json("GET", "/api/collections", { items: [chart], total: 1 });
  api.json("GET", `/api/collections/${chartId}`, chart);
  api.json("GET", `/api/collections/${chartId}/snapshots`, {
    items: [JUSTWATCH_SNAPSHOT],
    total: 1,
    page: 1,
    page_size: 25,
  });
  api.json("GET", `/api/snapshots/${JUSTWATCH_SNAPSHOT_ID}/items`, {
    items: [JUSTWATCH_ITEM],
    total: 1,
    page: 1,
    page_size: 50,
  });
  api.json("POST", "/api/previews", { preview_id: blockedPreviewId });
  api.json(
    "GET",
    `/api/previews/${blockedPreviewId}`,
    justwatchPreview({
      id: blockedPreviewId,
      state: "BLOCKED",
      counts: {
        to_add: 0,
        to_remove: 38,
        unchanged: 4,
        unresolved: 2,
        unmapped_remote: 0,
        remote_duplicates: 0,
      },
      blocked: { reason: "MAX_REMOVALS_EXCEEDED", threshold: 50, observed: 120 },
    }),
  );
  mockAppShell(api);
  await api.install();

  await page.goto("/app/collections");
  await expect(page.locator("[data-source-label]").first()).toHaveText("Classifica JustWatch");

  await page.getByRole("table").getByRole("link", { name: "Apri" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/collections/${chartId}$`));
  await expect(page.locator("[data-source-label]").first()).toHaveText("Classifica JustWatch");

  await page.getByTestId("source-only-preview").click();
  await expect(page.getByTestId("source-preview-state")).toContainText("BLOCKED");
  await expect(page.getByTestId("source-preview-to-add")).toHaveText("+0");
  await expect(page.getByTestId("source-preview-to-remove")).toHaveText("−38");
  await expect(page.getByTestId("source-preview-blocked")).toContainText(
    "Anteprima bloccata: MAX_REMOVALS_EXCEEDED (osservato 120, soglia 50)",
  );

  expect(api.mutations().map((call) => `${call.method} ${call.pathname}`)).toEqual([
    "POST /api/previews",
  ]);
  expect(api.unmatched).toEqual([]);
});

test("una serie JustWatch mostra gli eventi stagione/episodio e gli item con disponibilità", async ({
  page,
}) => {
  const showId = "cccccccc-cccc-4ccc-8ccc-ccccccccccc3";
  const show = justwatchCollection({
    id: showId,
    slug: "justwatch-apple-tv-serie",
    name: "Apple TV+ serie",
    media_type: "SHOW",
    kind: "RECENTLY_ADDED",
    date_basis: "APP_FIRST_SEEN",
    provider_names: [PROVIDER_APPLE_TV.name],
  });

  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  api.json("GET", `/api/collections/${showId}`, show);
  api.json("GET", `/api/collections/${showId}/snapshots`, {
    items: [JUSTWATCH_SNAPSHOT],
    total: 1,
    page: 1,
    page_size: 25,
  });
  api.json("GET", `/api/snapshots/${JUSTWATCH_SNAPSHOT_ID}/items`, {
    items: [{ ...JUSTWATCH_ITEM, media_type: "SHOW", title: "Severance (2022)" }],
    total: 1,
    page: 1,
    page_size: 50,
  });
  api.json("GET", `/api/collections/${showId}/episode-events`, JUSTWATCH_EPISODE_EVENTS);
  mockAppShell(api);
  await api.install();

  await page.goto(`/app/collections/${showId}`);
  await expect(page.getByRole("heading", { name: "Apple TV+ serie" })).toBeVisible();
  await expect(page.locator("[data-source-label]").first()).toHaveText(
    "Fonte: JustWatch (Aggregatore)",
  );

  await expect(
    page.getByRole("heading", { name: "Eventi stagioni ed episodi" }),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "Nuova stagione" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Nuovo episodio" })).toBeVisible();

  const itemRow = page.getByRole("row").filter({ hasText: "Severance (2022)" });
  await expect(itemRow).toContainText("Disponibile");
  await expect(itemRow).toContainText("FLATRATE");
  expect(
    api.calls.filter((call) => call.pathname === `/api/collections/${showId}/episode-events`),
  ).toHaveLength(1);
  expect(api.mutations()).toEqual([]);
  expect(api.unmatched).toEqual([]);
});
