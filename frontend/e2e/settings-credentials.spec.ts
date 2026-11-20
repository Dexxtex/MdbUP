import { expect, test } from "@playwright/test";
import { ApiMock } from "./support/api-mock";
import { mockAppShell, mockAuthenticatedSession } from "./support/fixtures";

const missing = {
  configured: false,
  masked_hint: null,
  key_version: null,
  status: "MISSING",
  updated_at: null,
  last_verified_at: null,
};

test("la sezione Credenziali espone anche TheTVDB", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);
  api.json("GET", "/api/credentials", {
    items: [
      { kind: "TMDB", ...missing },
      { kind: "MDBLIST", ...missing },
      { kind: "TVDB", ...missing },
      { kind: "JUSTWATCH", ...missing, status: "UNAVAILABLE" },
    ],
  });
  await api.install();

  await page.goto("/app/settings?tab=credentials");
  await expect(page.getByRole("heading", { name: "Credenziali delle fonti" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "TheTVDB" })).toBeVisible();
  await expect(page.getByText("API key per company ID").first()).toBeVisible();
});
