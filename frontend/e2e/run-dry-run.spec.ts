import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import {
  BINDING,
  DRY_RUN,
  DRY_RUN_ID,
  TO_ADD_SAMPLE,
  TO_REMOVE_SAMPLE,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

test("il dry-run di un binding mostra il diff senza scritture remote", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  api.json("GET", "/api/bindings", {
    items: [BINDING],
    total: 1,
    page: 1,
    page_size: 25,
    has_more: false,
  });
  api.json("POST", `/api/bindings/${BINDING.id}/runs`, {
    run_id: DRY_RUN_ID,
    job_id: null,
    status: "PENDING",
  });
  api.json("GET", `/api/runs/${DRY_RUN_ID}`, DRY_RUN);
  api.json("GET", `/api/runs/${DRY_RUN_ID}/operations`, {
    items: [],
    total: 0,
    page: 1,
    page_size: 100,
    has_more: false,
  });
  mockAppShell(api);
  await api.install();

  await page.goto("/app/bindings");
  await page.getByTestId(`binding-dry-run-${BINDING.id}`).click();

  await expect(page).toHaveURL(new RegExp(`/app/runs/${DRY_RUN_ID}$`));
  await expect(page.getByTestId("run-diff")).toBeVisible();
  await expect(page.getByTestId("run-count-add")).toHaveText("+3");
  await expect(page.getByTestId("run-count-remove")).toHaveText("−2");

  const absolute = page.getByTestId("run-threshold-absolute");
  await expect(absolute).toContainText("2 / 50");
  await expect(absolute.getByRole("meter")).toHaveAttribute("aria-valuenow", "4");

  const percent = page.getByTestId("run-threshold-percent");
  await expect(percent).toContainText("5% / 10%");
  await expect(percent.getByRole("meter")).toHaveAttribute("aria-valuenow", "50");

  await expect(page.getByTestId("run-sample-item")).toHaveText(TO_REMOVE_SAMPLE);
  await page.getByTestId("run-sample-tab-add").click();
  await expect(page.getByTestId("run-sample-item")).toHaveText(TO_ADD_SAMPLE);

  const starts = api.callsTo("POST", `/api/bindings/${BINDING.id}/runs`);
  expect(starts).toHaveLength(1);
  expect(starts[0].body).toMatchObject({ dry_run: true });
  expect(typeof (starts[0].body as { idempotency_key?: unknown }).idempotency_key).toBe(
    "string",
  );

  // Nessuna scrittura reale: l'unica mutazione è l'avvio del dry-run.
  expect(api.mutations()).toHaveLength(1);
  expect(api.unmatched).toEqual([]);
});
