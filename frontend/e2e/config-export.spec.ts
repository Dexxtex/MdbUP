import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import { CONFIG_EXPORT, mockAppShell, mockAuthenticatedSession } from "./support/fixtures";

/** Chiavi e valori che un export di configurazione non deve mai contenere. */
const FORBIDDEN = /ciphertext|api[_-]?key|password|secret|token/i;

function collectKeys(value: unknown, path = "$"): { path: string; key: string }[] {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => collectKeys(item, `${path}[${index}]`));
  }
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, child]) => [
      { path: `${path}.${key}`, key },
      ...collectKeys(child, `${path}.${key}`),
    ]);
  }
  return [];
}

function collectStrings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(collectStrings);
  if (value && typeof value === "object") return Object.values(value).flatMap(collectStrings);
  return [];
}

test("l'export della configurazione è scaricabile e senza segreti", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.json("GET", "/api/config/export", CONFIG_EXPORT);
  await api.install();

  await page.goto("/app/settings?tab=portability");

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("export-button").click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(/^mdbup-config-\d{4}-\d{2}-\d{2}\.json$/);

  const filePath = await download.path();
  expect(filePath).not.toBeNull();
  const parsed = JSON.parse(await readFile(filePath!, "utf8")) as Record<string, unknown>;

  expect(parsed.providers).toHaveLength(2);
  expect(parsed.collections).toHaveLength(1);
  expect(parsed.bindings).toHaveLength(1);
  expect(parsed.settings).toMatchObject({
    app_timezone: "Europe/Rome",
    sync_batch_size: 100,
  });

  const leakedKeys = collectKeys(parsed)
    .filter((entry) => FORBIDDEN.test(entry.key))
    .map((entry) => entry.path);
  expect(leakedKeys).toEqual([]);

  const leakedValues = collectStrings(parsed).filter((value) => FORBIDDEN.test(value));
  expect(leakedValues).toEqual([]);

  await expect(page.getByText("Configurazione esportata senza segreti.")).toBeVisible();
  expect(api.unmatched).toEqual([]);
});
