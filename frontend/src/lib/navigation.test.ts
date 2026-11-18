import { describe, expect, it } from "vitest";
import { safeNextPath } from "./navigation";

describe("safeNextPath", () => {
  it("mantiene i path relativi interni", () => {
    expect(safeNextPath("/app/runs/abc")).toBe("/app/runs/abc");
    expect(safeNextPath("/app?step=2")).toBe("/app?step=2");
  });

  it("rifiuta URL assoluti e protocol-relative", () => {
    expect(safeNextPath("https://evil.example/app")).toBe("/app");
    expect(safeNextPath("//evil.example/app")).toBe("/app");
    expect(safeNextPath("/\\evil.example/app")).toBe("/app");
    expect(safeNextPath("evil.example")).toBe("/app");
  });

  it("usa il fallback quando il parametro manca", () => {
    expect(safeNextPath(null)).toBe("/app");
    expect(safeNextPath("")).toBe("/app");
    expect(safeNextPath(undefined, "/app/bindings")).toBe("/app/bindings");
  });
});
