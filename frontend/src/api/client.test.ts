import { describe, expect, it } from "vitest";
import { ApiError, pageItems, readCsrfToken } from "./client";

describe("pageItems", () => {
  it("accetta una lista semplice", () => {
    expect(pageItems([1, 2, 3])).toEqual([1, 2, 3]);
  });

  it("accetta una pagina con items", () => {
    expect(pageItems({ items: ["a", "b"] })).toEqual(["a", "b"]);
  });

  it("restituisce una lista vuota per payload assenti", () => {
    expect(pageItems(null)).toEqual([]);
    expect(pageItems(undefined)).toEqual([]);
    expect(pageItems({})).toEqual([]);
  });
});

describe("readCsrfToken", () => {
  it("restituisce null senza document (ambiente non browser)", () => {
    expect(readCsrfToken()).toBeNull();
  });
});

describe("ApiError", () => {
  it("espone status e categoria e riconosce il 401", () => {
    const error = new ApiError({
      status: 401,
      code: "UNAUTHENTICATED",
      category: "AUTH",
      message: "no",
      retryable: false,
    });
    expect(error.isUnauthorized).toBe(true);
    expect(error.category).toBe("AUTH");
  });
});
