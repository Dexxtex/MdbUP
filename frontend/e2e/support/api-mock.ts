import type { Page, Request, Route } from "@playwright/test";
import type { ErrorCategory } from "../../src/api/types";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/** Richiesta `/api/**` registrata dal router: è la base delle asserzioni sui payload. */
export interface RecordedCall {
  method: HttpMethod;
  pathname: string;
  search: string;
  headers: Record<string, string>;
  body: unknown;
}

export interface MockResponse {
  status?: number;
  body?: unknown;
}

export type MockHandler = (call: RecordedCall) => MockResponse | Promise<MockResponse>;

interface MockRoute {
  method: HttpMethod;
  path: string | RegExp;
  handler: MockHandler;
}

/** Envelope errore unico (`docs/phase1/07-frontend-api.md` §6). */
export function errorEnvelope(
  code: string,
  category: ErrorCategory,
  message: string,
  extra: {
    retryable?: boolean;
    retry_after_s?: number;
    details?: Record<string, unknown>;
  } = {},
): Record<string, unknown> {
  return {
    error: {
      code,
      category,
      message,
      retryable: extra.retryable ?? false,
      ...(extra.retry_after_s != null ? { retry_after_s: extra.retry_after_s } : {}),
      ...(extra.details ? { details: extra.details } : {}),
    },
  };
}

function matches(route: MockRoute, call: RecordedCall): boolean {
  if (route.method !== call.method) return false;
  return typeof route.path === "string"
    ? route.path === call.pathname
    : route.path.test(call.pathname);
}

async function recordCall(request: Request): Promise<RecordedCall> {
  const url = new URL(request.url());
  const postData = request.postData();
  let body: unknown;
  if (postData) {
    try {
      body = JSON.parse(postData);
    } catch {
      body = postData;
    }
  }
  return {
    method: request.method() as HttpMethod,
    pathname: url.pathname,
    search: url.search,
    headers: request.headers(),
    body,
  };
}

/**
 * Router minimale per l'unico `page.route` della suite. Il filtro è un predicato
 * sul pathname e non il glob `**` + `/api/` + `**`: quel glob intercetta anche i
 * moduli del dev server (`/src/api/client.ts`) e romperebbe il boot della UI.
 * La prima rotta registrata che combacia vince, quindi le rotte specifiche
 * vanno registrate prima di `mockAppShell`. Una richiesta senza rotta non esce
 * mai verso la rete: riceve un 404 e finisce in `unmatched`, così un test può
 * dimostrare che la UI non ha chiamato endpoint non previsti.
 */
export class ApiMock {
  private readonly page: Page;
  private readonly routes: MockRoute[] = [];
  readonly calls: RecordedCall[] = [];
  readonly unmatched: RecordedCall[] = [];

  constructor(page: Page) {
    this.page = page;
  }

  on(method: HttpMethod, path: string | RegExp, handler: MockHandler): this {
    this.routes.push({ method, path, handler });
    return this;
  }

  json(method: HttpMethod, path: string | RegExp, body: unknown, status = 200): this {
    return this.on(method, path, () => ({ status, body }));
  }

  /** Chiamate andate a buon fine per un endpoint (path esatto, query ignorata). */
  callsTo(method: HttpMethod, path: string): RecordedCall[] {
    return this.calls.filter((call) => call.method === method && call.pathname === path);
  }

  /** Chiamate che modificano stato: la UI non deve scrivere senza che il test lo preveda. */
  mutations(): RecordedCall[] {
    return this.calls.filter((call) => call.method !== "GET");
  }

  async install(): Promise<void> {
    await this.page.route(
      (url) => url.pathname.startsWith("/api/"),
      (route) => this.handle(route),
    );
  }

  private async handle(route: Route): Promise<void> {
    const call = await recordCall(route.request());
    const routeMatch = this.routes.find((candidate) => matches(candidate, call));
    if (!routeMatch) {
      this.unmatched.push(call);
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify(
          errorEnvelope("RESOURCE_NOT_FOUND", "VALIDATION", "Risorsa non trovata."),
        ),
      });
      return;
    }

    this.calls.push(call);
    const response = await routeMatch.handler(call);
    const status = response.status ?? 200;
    if (status === 204 || status === 205) {
      await route.fulfill({ status });
      return;
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(response.body ?? null),
    });
  }
}
