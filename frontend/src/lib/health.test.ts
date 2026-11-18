import { describe, expect, it } from "vitest";
import type { DashboardSourceRow, SystemStatus } from "../api/types";
import { deriveHealth, healthStateFromValue } from "./health";

function source(key: string, status: DashboardSourceRow["status"]): DashboardSourceRow {
  return {
    id: key,
    key,
    name: key,
    status,
    status_message: null,
    last_healthcheck_at: null,
  };
}

describe("healthStateFromValue", () => {
  it("riconosce gli stati noti senza distinzione di maiuscole", () => {
    expect(healthStateFromValue("OK")).toBe("ok");
    expect(healthStateFromValue("healthy")).toBe("ok");
    expect(healthStateFromValue("degraded")).toBe("degraded");
    expect(healthStateFromValue("ERROR")).toBe("error");
    expect(healthStateFromValue("down")).toBe("error");
  });

  it("tratta i valori assenti o ignoti come sconosciuti", () => {
    expect(healthStateFromValue(null)).toBe("unknown");
    expect(healthStateFromValue(undefined)).toBe("unknown");
    expect(healthStateFromValue("boh")).toBe("unknown");
  });
});

describe("deriveHealth", () => {
  it("ricade sulle fonti della dashboard quando system/status non c'è", () => {
    const items = deriveHealth({
      apiState: "ok",
      status: null,
      sources: [source("tmdb", "OK"), source("mdblist", "ERROR")],
    });
    const byKey = Object.fromEntries(items.map((item) => [item.key, item.state]));
    expect(byKey.api).toBe("ok");
    expect(byKey.worker).toBe("unknown");
    expect(byKey.tmdb).toBe("ok");
    expect(byKey.mdblist).toBe("error");
  });

  it("preferisce i servizi di system/status", () => {
    const status: SystemStatus = {
      status: "degraded",
      worker: { status: "ok", message: "2 worker attivi" },
      integrations: {
        tmdb: { status: "degraded", message: "latenza alta" },
        mdblist: { status: "ok" },
      },
    };
    const items = deriveHealth({ apiState: "ok", status, sources: [] });
    const byKey = Object.fromEntries(items.map((item) => [item.key, item]));
    expect(byKey.worker.state).toBe("ok");
    expect(byKey.worker.detail).toBe("2 worker attivi");
    expect(byKey.tmdb.state).toBe("degraded");
    expect(byKey.mdblist.state).toBe("ok");
  });

  it("legge la shape Phase 7 con health booleano e stati servizio", () => {
    const status: SystemStatus = {
      health: {
        api: true,
        database: true,
        redis: true,
        worker: true,
        tmdb: "OK",
        mdblist: "MISSING_CREDENTIAL",
      },
    };
    const items = deriveHealth({ apiState: "ok", status, sources: [] });
    const byKey = Object.fromEntries(items.map((item) => [item.key, item.state]));
    expect(byKey.worker).toBe("ok");
    expect(byKey.tmdb).toBe("ok");
    expect(byKey.mdblist).toBe("error");
  });

  it("marca l'API in errore quando la sessione fallisce", () => {
    const items = deriveHealth({ apiState: "error", status: null });
    expect(items.find((item) => item.key === "api")?.state).toBe("error");
  });
});
