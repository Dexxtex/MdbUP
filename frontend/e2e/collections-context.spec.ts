import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  PROVIDER_NETFLIX,
  PROVIDER_PRIME,
  SOURCE_COLLECTION_NETFLIX,
  SOURCE_COLLECTION_PRIME,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

test("le collezioni mantengono il contesto del provider nell'URL", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.on("GET", "/api/providers", () => ({
    body: { items: [PROVIDER_NETFLIX, PROVIDER_PRIME], total: 2 },
  }));
  api.on("GET", "/api/collections", () => ({
    body: { items: [SOURCE_COLLECTION_NETFLIX], total: 1 },
  }));
  await api.install();

  // arrivo dal link della card provider, con il paese nel link
  await page.goto(`/app/collections?provider=${PROVIDER_NETFLIX.id}&country=DE`);

  const context = page.getByTestId("collections-context");
  await expect(context).toContainText(`Collezioni di ${PROVIDER_NETFLIX.name}`);
  // il paese compare nell'etichetta del filtro (non cablato "Italia")
  await expect(page.getByLabel("Provider — Germania")).toBeVisible();
  await expect(page.getByLabel("Provider — Germania")).toHaveValue(PROVIDER_NETFLIX.id);

  // i filtri scrivono nell'URL: refresh e link condiviso restano coerenti
  await page.getByLabel("Tipo").selectOption("MOVIE");
  await expect.poll(() => new URL(page.url()).searchParams.get("media")).toBe("MOVIE");
  await expect.poll(() => new URL(page.url()).searchParams.get("provider")).toBe(
    PROVIDER_NETFLIX.id,
  );

  await page.reload();
  await expect(page.getByLabel("Tipo")).toHaveValue("MOVIE");
  await expect(page.getByLabel("Provider — Germania")).toHaveValue(PROVIDER_NETFLIX.id);
  await expect(page.getByTestId("collections-context")).toBeVisible();

  // e la riga di contesto si toglie, lasciando la lista completa
  // "Tutte le collezioni" azzera tutti i filtri, non solo il provider
  await page.getByRole("button", { name: "Tutte le collezioni" }).click();
  await expect(page.getByLabel("Provider — Germania")).toHaveValue("");
  await expect(page.getByLabel("Tipo")).toHaveValue("");
  await expect(page.getByTestId("collections-context")).toHaveCount(0);
  await expect.poll(() => new URL(page.url()).searchParams.get("provider")).toBeNull();
  await expect.poll(() => new URL(page.url()).searchParams.get("media")).toBeNull();
  expect(api.unmatched).toEqual([]);
});

test("il paese scelto in Provider vale anche per Collezioni", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  // il mock dipende dal paese: così l'asserzione distingue "DE" da un IT cablato
  api.on("GET", "/api/providers", (call) => ({
    body: {
      items: call.search.includes("country=DE") ? [PROVIDER_PRIME] : [PROVIDER_NETFLIX],
      total: 1,
    },
  }));
  api.on("GET", "/api/collections", () => ({
    body: { items: [SOURCE_COLLECTION_PRIME], total: 1 },
  }));
  await api.install();

  await page.goto("/app/providers");
  await page.getByLabel("Paese").click();
  await page.getByLabel("Paese").fill("germania");
  await page.getByRole("option", { name: "DE — Germania" }).click();

  await page.getByTestId("nav-collections").click();
  await expect(page).toHaveURL(/\/app\/collections/);

  // Collezioni elenca i provider del paese del contesto: con "IT" cablato
  // il mock restituirebbe Netflix e questa asserzione fallirebbe.
  const providerFilter = page.getByLabel("Provider — Germania");
  await expect(providerFilter).toContainText(PROVIDER_PRIME.name);
  await expect(providerFilter).not.toContainText(PROVIDER_NETFLIX.name);
  expect(api.unmatched).toEqual([]);
});

test("il paese viaggia nell'URL e sopravvive alla navigazione", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.on("GET", "/api/providers", () => ({
    body: { items: [PROVIDER_PRIME], total: 1 },
  }));
  api.on("GET", "/api/collections", () => ({
    body: { items: [SOURCE_COLLECTION_PRIME], total: 1 },
  }));
  await api.install();

  // link condiviso: il paese arriva dall'URL, non dal localStorage
  await page.goto("/app/collections?country=DE");
  await expect
    .poll(() =>
      api.calls
        .filter((call) => call.pathname === "/api/providers")
        .map((call) => call.search),
    )
    .toContain("?country=DE");

  // il contesto resta nell'URL e viene riportato nei link di navigazione
  await expect.poll(() => new URL(page.url()).searchParams.get("country")).toBe("DE");
  await page.getByTestId("nav-providers").click();
  await expect(page).toHaveURL(/\?country=DE/);
  await expect(page.getByLabel("Paese")).toHaveValue("DE — Germania");

  // tornando al paese predefinito l'URL torna pulito
  await page.getByLabel("Paese").click();
  await page.getByLabel("Paese").fill("italia");
  await page.getByRole("option", { name: "IT — Italia" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("country")).toBeNull();
  expect(api.unmatched).toEqual([]);
});
