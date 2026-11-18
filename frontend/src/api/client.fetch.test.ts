// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

function response(status: number, body: unknown, contentType = "application/json") {
  if (status === 204 || status === 205) {
    return new Response(null, { status });
  }
  return new Response(contentType === "application/json" ? JSON.stringify(body) : String(body), {
    status,
    headers: { "content-type": contentType },
  });
}

describe("apiFetch", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    document.cookie = "mdbsync-csrf=csrf-token";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "mdbsync-csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("esegue GET con credenziali e restituisce il JSON", async () => {
    fetchMock.mockResolvedValue(response(200, { ok: true }));
    await expect(apiFetch("/dashboard")).resolves.toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/dashboard");
    expect(init.credentials).toBe("include");
    expect(init.headers).toMatchObject({ Accept: "application/json" });
  });

  it("invia corpo JSON e token CSRF sui metodi non safe", async () => {
    fetchMock.mockResolvedValue(response(204, null));
    await expect(apiFetch("/collections", { method: "POST", body: { name: "x" } })).resolves.toBeUndefined();
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBe('{"name":"x"}');
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-token");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("normalizza l'envelope di errore", async () => {
    fetchMock.mockResolvedValue(
      response(422, {
        error: {
          code: "VALIDATION_ERROR",
          category: "VALIDATION",
          message: "bad",
          retryable: false,
          request_id: "req_1",
          details: { field: "name" },
        },
      }),
    );
    await expect(apiFetch("/x")).rejects.toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      requestId: "req_1",
      category: "VALIDATION",
    });
  });

  it("usa il fallback quando l'errore non ha envelope", async () => {
    fetchMock.mockResolvedValue(response(500, "boom", "text/plain"));
    const error = await apiFetch("/x").catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 500, code: "HTTP_500", retryable: true });
  });

  it("converte un errore di rete in NETWORK_ERROR", async () => {
    fetchMock.mockRejectedValue(new TypeError("offline"));
    await expect(apiFetch("/x")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
      category: "NETWORK",
      retryable: true,
    });
  });

  it("rilancia l'abort senza mascherarlo", async () => {
    const abort = new Error("aborted");
    abort.name = "AbortError";
    fetchMock.mockRejectedValue(abort);
    await expect(apiFetch("/x")).rejects.toBe(abort);
  });

  it("gestisce JSON invalido e risposte 205", async () => {
    fetchMock.mockResolvedValue(new Response("not-json", { status: 200, headers: { "content-type": "application/json" } }));
    await expect(apiFetch("/x")).resolves.toBeNull();
    fetchMock.mockResolvedValue(response(205, null));
    await expect(apiFetch("/x")).resolves.toBeUndefined();
  });


});
