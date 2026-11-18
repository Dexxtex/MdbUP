import { describe, expect, it } from "vitest";
import {
  formatBytes,
  formatDateTime,
  formatDateTimeUtc,
  formatRelative,
} from "./format";

describe("orari", () => {
  it("mostra gli orari nel fuso Europe/Rome", () => {
    // 12:00 UTC = 13:00 a Roma (CET, gennaio).
    expect(formatDateTime("2024-01-15T12:00:00Z")).toContain("13:00");
  });

  it("espone il valore UTC per il tooltip", () => {
    const utc = formatDateTimeUtc("2024-01-15T12:00:00Z");
    expect(utc).toContain("12:00");
    expect(utc).toContain("UTC");
  });

  it("gestisce valori assenti o non validi", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("non-una-data")).toBe("—");
    expect(formatDateTimeUtc(undefined)).toBe("—");
  });
});

describe("formatRelative", () => {
  const now = new Date("2024-01-15T12:00:00Z").getTime();

  it("descrive minuti, ore e giorni", () => {
    expect(formatRelative("2024-01-15T11:58:00Z", now)).toContain("2");
    expect(formatRelative("2024-01-15T09:00:00Z", now)).toContain("3");
    expect(formatRelative("2024-01-12T12:00:00Z", now)).toContain("3");
  });

  it("usa 'adesso' per differenze minime", () => {
    expect(formatRelative("2024-01-15T12:00:10Z", now)).toBe("adesso");
  });
});

describe("formatBytes", () => {
  it("formatta le dimensioni del backup", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(null)).toBe("—");
  });
});
