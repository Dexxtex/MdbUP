import { expect, test } from "@playwright/test";
import type { NotificationChannel } from "../src/api/types";
import { ApiMock } from "./support/api-mock";
import {
  NOTIFICATION_EVENTS,
  mockAppShell,
  mockAuthenticatedSession,
  notificationChannel,
} from "./support/fixtures";

const CHANNEL_ID = "99999999-9999-4999-8999-999999999991";
const WEBHOOK_URL = "https://hooks.example.test/ops";
const ROTATED_WEBHOOK_URL = "https://hooks.example.test/ops-rotated";

test("crea, modifica e prova un canale di notifica", async ({ page }) => {
  const api = new ApiMock(page);
  mockAuthenticatedSession(api);
  mockAppShell(api);

  let channels: NotificationChannel[] = [];
  api.on("GET", "/api/notifications/channels", () => ({
    body: { items: channels, total: channels.length },
  }));
  api.on("POST", "/api/notifications/channels", (call) => {
    const payload = call.body as {
      name: string;
      events: string[];
      enabled: boolean;
    };
    channels = [
      notificationChannel({
        id: CHANNEL_ID,
        name: payload.name,
        events: payload.events,
        enabled: payload.enabled,
      }),
    ];
    return { body: channels[0] };
  });
  api.on("PATCH", `/api/notifications/channels/${CHANNEL_ID}`, (call) => {
    const payload = call.body as { name: string; events: string[]; enabled: boolean };
    channels = channels.map((channel) => ({
      ...channel,
      name: payload.name,
      events: payload.events,
      enabled: payload.enabled,
      updated_at: "2026-01-02T11:00:00Z",
    }));
    return { body: channels[0] };
  });
  api.on("POST", `/api/notifications/channels/${CHANNEL_ID}/test`, () => ({
    body: {
      ok: true,
      status_code: 200,
      message: "Webhook di prova consegnato.",
      latency_ms: 42,
    },
  }));
  await api.install();

  await page.goto("/app/settings?tab=notifications");

  await page.getByTestId("notification-new").click();
  await expect(page.getByTestId("notification-form")).toBeVisible();
  await page.locator("#notification-name").fill("Webhook Ops");
  await page.locator("#notification-secret").fill(WEBHOOK_URL);
  await page.getByTestId("notification-submit").click();

  await expect(
    page.getByTestId("toast").filter({ hasText: "Canale creato" }),
  ).toBeVisible();

  const creates = api.callsTo("POST", "/api/notifications/channels");
  expect(creates).toHaveLength(1);
  expect(creates[0].body).toEqual({
    name: "Webhook Ops",
    kind: "WEBHOOK",
    secret: WEBHOOK_URL,
    events: NOTIFICATION_EVENTS,
    config: {},
    enabled: true,
  });

  const card = page.getByTestId(`notification-channel-${CHANNEL_ID}`);
  await expect(card).toContainText("Webhook Ops");
  await card.getByTestId(`channel-edit-${CHANNEL_ID}`).click();

  await page.locator(`#channel-name-${CHANNEL_ID}`).fill("Webhook Ops v2");
  await page.locator(`#channel-${CHANNEL_ID}-event-SUMMARY`).uncheck();
  await page.locator(`#channel-enabled-${CHANNEL_ID}`).uncheck();
  await page.locator(`#channel-secret-${CHANNEL_ID}`).fill(ROTATED_WEBHOOK_URL);
  await page.getByTestId(`channel-save-${CHANNEL_ID}`).click();

  await expect(
    page.getByTestId("toast").filter({ hasText: "Canale aggiornato" }),
  ).toBeVisible();

  const patches = api.callsTo("PATCH", `/api/notifications/channels/${CHANNEL_ID}`);
  expect(patches).toHaveLength(1);
  expect(patches[0].body).toEqual({
    name: "Webhook Ops v2",
    events: NOTIFICATION_EVENTS.filter((event) => event !== "SUMMARY"),
    enabled: false,
    secret: ROTATED_WEBHOOK_URL,
  });

  await page.getByTestId(`channel-test-${CHANNEL_ID}`).click();

  const result = page.getByTestId(`channel-test-result-${CHANNEL_ID}`);
  await expect(result).toContainText("Webhook di prova consegnato.");
  await expect(result).toContainText("42 ms");
  expect(api.callsTo("POST", `/api/notifications/channels/${CHANNEL_ID}/test`)).toHaveLength(1);
  expect(api.unmatched).toEqual([]);
});
