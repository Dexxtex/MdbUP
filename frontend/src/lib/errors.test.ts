import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { describeApiError, fieldErrors, isUnauthorized } from "./errors";

function apiError(init: Partial<ConstructorParameters<typeof ApiError>[0]> = {}): ApiError {
  return new ApiError({
    status: 400,
    code: "TEST",
    category: "INTERNAL",
    message: "raw server message",
    retryable: false,
    ...init,
  });
}

describe("describeApiError", () => {
  it("mappa POLICY con soglia e valore osservato", () => {
    const presentation = describeApiError(
      apiError({
        status: 409,
        code: "THRESHOLDS_EXCEEDED",
        category: "POLICY",
        details: { observed: 120, threshold: 50 },
      }),
    );
    expect(presentation.title).toBe("Operazione bloccata dalle soglie");
    expect(presentation.message).toContain("120");
    expect(presentation.message).toContain("50");
    expect(presentation.retryable).toBe(false);
  });

  it("mappa TARGET con retry_after", () => {
    const presentation = describeApiError(
      apiError({ status: 429, category: "TARGET", retryable: true, retryAfterS: 42 }),
    );
    expect(presentation.title).toBe("Errore MDBList");
    expect(presentation.message).toContain("42");
  });

  it("mappa AUTH come sessione scaduta", () => {
    const presentation = describeApiError(apiError({ status: 401, category: "AUTH" }));
    expect(presentation.title).toBe("Sessione scaduta");
  });

  it("mappa il rate limit di login con il countdown di retry_after", () => {
    const presentation = describeApiError(
      apiError({
        status: 429,
        code: "AUTH_RATE_LIMITED",
        category: "AUTH",
        retryable: true,
        retryAfterS: 60,
      }),
    );
    expect(presentation.title).toBe("Troppi tentativi");
    expect(presentation.message).toBe(
      "Troppi tentativi di accesso. Riprova tra 60 secondi.",
    );
    expect(presentation.retryable).toBe(true);
  });

  it("mappa il rate limit di login senza retry_after", () => {
    const presentation = describeApiError(
      apiError({
        status: 429,
        code: "AUTH_RATE_LIMITED",
        category: "AUTH",
        retryable: true,
      }),
    );
    expect(presentation.title).toBe("Troppi tentativi");
    expect(presentation.message).toBe("Troppi tentativi di accesso. Riprova più tardi.");
  });

  it("mappa un errore non ApiError come INTERNAL", () => {
    const presentation = describeApiError(new Error("boom"));
    expect(presentation.category).toBe("INTERNAL");
    expect(presentation.title).toBe("Errore imprevisto");
  });

  it("non mostra il messaggio grezzo del server", () => {
    const presentation = describeApiError(
      apiError({ status: 500, category: "INTERNAL", requestId: "req_1" }),
    );
    expect(presentation.message).not.toContain("raw server message");
    expect(presentation.message).toContain("req_1");
  });

  it("spiega DRY_RUN_REQUIRED per un binding senza dry-run", () => {
    const presentation = describeApiError(
      apiError({ status: 409, code: "DRY_RUN_REQUIRED", category: "CONFLICT" }),
    );
    expect(presentation.title).toBe("Dry-run richiesto");
    expect(presentation.message).toContain("dry-run");
    expect(presentation.message).toContain("run reale");
    expect(presentation.retryable).toBe(false);
  });

  it("spiega PROVIDER_RUN_ACTIVE e propone un retry dopo la sync", () => {
    const presentation = describeApiError(
      apiError({ status: 409, code: "PROVIDER_RUN_ACTIVE", category: "CONFLICT" }),
    );
    expect(presentation.title).toBe("Sincronizzazione in corso");
    expect(presentation.message).toContain("sync");
    expect(presentation.retryable).toBe(true);
  });

  it("spiega COLLECTION_RUN_ACTIVE per una collezione in sync", () => {
    const presentation = describeApiError(
      apiError({ status: 409, code: "COLLECTION_RUN_ACTIVE", category: "CONFLICT" }),
    );
    expect(presentation.title).toBe("Sincronizzazione in corso");
    expect(presentation.message).toContain("questa collezione");
    expect(presentation.retryable).toBe(true);
  });

  it("riconosce ORDER_NOT_ENFORCED come avviso, non errore rosso", () => {
    const presentation = describeApiError(
      apiError({ status: 200, code: "ORDER_NOT_ENFORCED", category: "TARGET" }),
    );
    expect(presentation.title).toBe("Ordine non applicato");
    expect(presentation.retryable).toBe(false);
  });

  it("distingue PROVIDER_ALREADY_EXISTS dal generico conflitto", () => {
    const presentation = describeApiError(
      apiError({ status: 409, code: "PROVIDER_ALREADY_EXISTS", category: "CONFLICT" }),
    );
    expect(presentation.title).toBe("Provider già esistente");
    expect(presentation.message).toContain("slug");
    expect(presentation.message).not.toContain("operazione è in corso");
    expect(presentation.retryable).toBe(false);
  });

  it("distingue MAPPING_ALREADY_EXISTS dal generico conflitto", () => {
    const presentation = describeApiError(
      apiError({ status: 409, code: "MAPPING_ALREADY_EXISTS", category: "CONFLICT" }),
    );
    expect(presentation.title).toBe("ID già associato");
    expect(presentation.message).toContain("provider");
    expect(presentation.message).not.toContain("operazione è in corso");
    expect(presentation.retryable).toBe(false);
  });

  it("mantiene il testo generico per gli altri conflitti", () => {
    const presentation = describeApiError(
      apiError({ status: 409, code: "COLLECTION_EXISTS", category: "CONFLICT" }),
    );
    expect(presentation.title).toBe("Operazione già in corso");
  });
});

describe("fieldErrors", () => {
  it("estrae gli errori di campo da details.fields", () => {
    const errors = fieldErrors(
      apiError({ status: 422, category: "VALIDATION", details: { fields: { email: "Non valida" } } }),
    );
    expect(errors).toEqual({ email: "Non valida" });
  });

  it("restituisce un oggetto vuoto senza details", () => {
    expect(fieldErrors(apiError())).toEqual({});
  });
});

describe("isUnauthorized", () => {
  it("riconosce il 401", () => {
    expect(isUnauthorized(apiError({ status: 401 }))).toBe(true);
    expect(isUnauthorized(apiError({ status: 500 }))).toBe(false);
    expect(isUnauthorized(new Error("x"))).toBe(false);
  });
});
