import { expect, test } from "@playwright/test";
import { ApiMock, errorEnvelope } from "./support/api-mock";
import {
  CSRF_TOKEN,
  SESSION,
  SETTINGS,
  UNAUTHORIZED,
  USER,
  mockAppShell,
  mockAuthenticatedSession,
} from "./support/fixtures";

test.describe("Autenticazione, CSRF e rate limit", () => {
  test("il login crea la sessione e apre la dashboard", async ({ page }) => {
    const api = new ApiMock(page);
    let authenticated = false;
    api.on("GET", "/api/auth/session", () =>
      authenticated ? { body: SESSION } : { status: 401, body: UNAUTHORIZED },
    );
    api.on("POST", "/api/auth/login", () => {
      authenticated = true;
      return { body: SESSION };
    });
    mockAppShell(api);
    await api.install();

    await page.goto("/login");
    await page.getByTestId("login-email").fill(USER.email);
    await page.getByTestId("login-password").fill("correct-horse-battery");
    await page.getByTestId("login-submit").click();

    await expect(page).toHaveURL(/\/app$/);
    await expect(page.getByTestId("dashboard")).toBeVisible();
    await expect(page.getByTestId("app-nav")).toBeVisible();
    await expect(page.getByTestId("nav-dashboard")).toBeVisible();

    const logins = api.callsTo("POST", "/api/auth/login");
    expect(logins).toHaveLength(1);
    expect(logins[0].body).toEqual({
      email: USER.email,
      password: "correct-horse-battery",
    });
    expect(api.unmatched).toEqual([]);
  });

  test("una mutazione invia X-CSRF-Token letto dal cookie", async ({
    page,
    context,
    baseURL,
  }) => {
    await context.addCookies([{ name: "mdbsync-csrf", value: CSRF_TOKEN, url: baseURL! }]);

    const api = new ApiMock(page);
    mockAuthenticatedSession(api);
    mockAppShell(api);
    api.json("GET", "/api/settings", SETTINGS);
    api.json("PATCH", "/api/settings", SETTINGS);
    await api.install();

    await page.goto("/app/settings?tab=maintenance");
    await expect(page.getByRole("heading", { name: "Parametri operativi" })).toBeVisible();
    await page.getByRole("button", { name: "Salva impostazioni" }).click();

    await expect(page.getByTestId("toast")).toContainText("Impostazioni salvate");

    const patches = api.callsTo("PATCH", "/api/settings");
    expect(patches).toHaveLength(1);
    expect(patches[0].headers["x-csrf-token"]).toBe(CSRF_TOKEN);
    expect(patches[0].body).toEqual({
      items: {
        app_timezone: "Europe/Rome",
        sync_batch_size: 100,
        sync_max_removal_absolute: 50,
        sync_max_removal_percent: 10,
        sync_max_addition_percent: 50,
        notifications_summary_enabled: false,
        notifications_summary_hour: 8,
      },
    });
    expect(api.unmatched).toEqual([]);
  });

  test("il sesto tentativo di login mostra l'errore di rate limit", async ({ page }) => {
    const api = new ApiMock(page);
    api.json("GET", "/api/auth/session", UNAUTHORIZED, 401);
    let attempts = 0;
    api.on("POST", "/api/auth/login", () => {
      attempts += 1;
      if (attempts <= 5) {
        return {
          status: 401,
          body: errorEnvelope(
            "AUTH_INVALID_CREDENTIALS",
            "AUTH",
            "Credenziali non valide.",
          ),
        };
      }
      return {
        status: 429,
        body: errorEnvelope("AUTH_RATE_LIMITED", "AUTH", "Troppi tentativi. Riprova più tardi.", {
          retryable: true,
          retry_after_s: 60,
        }),
      };
    });
    await api.install();

    await page.goto("/login");
    await page.getByTestId("login-email").fill(USER.email);

    for (let attempt = 1; attempt <= 5; attempt += 1) {
      await page.getByTestId("login-password").fill("wrong-password");
      await page.getByTestId("login-submit").click();
      await expect(page.getByRole("alert")).toContainText("Sessione scaduta");
    }

    await page.getByTestId("login-password").fill("wrong-password");
    await page.getByTestId("login-submit").click();

    const rateLimitAlert = page.getByRole("alert");
    await expect(rateLimitAlert).toContainText("Troppi tentativi");
    await expect(rateLimitAlert).toContainText("Riprova tra 60 secondi");
    await expect(page).toHaveURL(/\/login$/);

    const logins = api.callsTo("POST", "/api/auth/login");
    expect(logins).toHaveLength(6);
    expect(logins[5].body).toEqual({ email: USER.email, password: "wrong-password" });
    expect(api.unmatched).toEqual([]);
  });
});
