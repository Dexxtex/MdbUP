import type { ErrorCategory, ErrorEnvelope } from "./types";

const DEFAULT_BASE_URL = "/api";
const CSRF_HEADER = "X-CSRF-Token";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL
).replace(/\/+$/, "");

/**
 * Il cookie CSRF è non-HttpOnly per design (double submit). In produzione ha il
 * prefisso `__Host-`, in sviluppo no: si accettano entrambi i nomi.
 */
const CSRF_COOKIE_NAMES: readonly string[] = [
  import.meta.env.VITE_CSRF_COOKIE_NAME,
  "__Host-mdbsync-csrf",
  "mdbsync-csrf",
].filter((name): name is string => typeof name === "string" && name.length > 0);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const entry = part.trim();
    if (entry.startsWith(prefix)) {
      return decodeURIComponent(entry.slice(prefix.length));
    }
  }
  return null;
}

export function readCsrfToken(): string | null {
  for (const name of CSRF_COOKIE_NAMES) {
    const value = readCookie(name);
    if (value) return value;
  }
  return null;
}

export interface ApiErrorInit {
  status: number;
  code: string;
  category: ErrorCategory;
  message: string;
  retryable: boolean;
  requestId?: string;
  retryAfterS?: number;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly category: ErrorCategory;
  readonly retryable: boolean;
  readonly requestId?: string;
  readonly retryAfterS?: number;
  readonly details?: Record<string, unknown>;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.category = init.category;
    this.retryable = init.retryable;
    this.requestId = init.requestId;
    this.retryAfterS = init.retryAfterS;
    this.details = init.details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiRequestInit {
  method?: HttpMethod;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function isSafeMethod(method: HttpMethod): boolean {
  return method === "GET";
}

function extractEnvelope(payload: unknown): ErrorEnvelope["error"] | null {
  if (typeof payload !== "object" || payload === null) return null;
  const candidate = (payload as { error?: unknown }).error;
  if (typeof candidate !== "object" || candidate === null) return null;
  const envelope = candidate as Partial<ErrorEnvelope["error"]>;
  if (typeof envelope.code !== "string") return null;
  return {
    code: envelope.code,
    category: (envelope.category ?? "INTERNAL") as ErrorCategory,
    message: typeof envelope.message === "string" ? envelope.message : "",
    retryable: Boolean(envelope.retryable),
    retry_after_s: envelope.retry_after_s,
    request_id: envelope.request_id,
    details: envelope.details,
  };
}

function categoryFromStatus(status: number): ErrorCategory {
  if (status === 401 || status === 403) return "AUTH";
  if (status === 404 || status === 409) return "CONFLICT";
  if (status === 422) return "VALIDATION";
  if (status >= 500) return "INTERNAL";
  return "INTERNAL";
}

function toApiError(response: Response, payload: unknown): ApiError {
  const envelope = extractEnvelope(payload);
  if (envelope) {
    return new ApiError({
      status: response.status,
      code: envelope.code,
      category: envelope.category,
      message: envelope.message,
      retryable: envelope.retryable,
      requestId: envelope.request_id,
      retryAfterS: envelope.retry_after_s,
      details: envelope.details,
    });
  }
  return new ApiError({
    status: response.status,
    code: `HTTP_${response.status}`,
    category: categoryFromStatus(response.status),
    message: response.statusText,
    retryable: response.status >= 500,
  });
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "AbortError"
  );
}

/**
 * Unico punto di accesso HTTP: cookie di sessione inclusi, CSRF sui metodi non
 * sicuri, envelope errore normalizzato. Nessun token viene salvato nel browser.
 */
export async function apiFetch<T>(
  path: string,
  init: ApiRequestInit = {},
): Promise<T> {
  const method = init.method ?? "GET";
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...init.headers,
  };

  let body: string | undefined;
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.body);
  }

  if (!isSafeMethod(method)) {
    const csrf = readCsrfToken();
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: "include",
      headers,
      body,
      signal: init.signal,
    });
  } catch (cause) {
    if (isAbortError(cause)) throw cause;
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      category: "NETWORK",
      message: "Impossibile raggiungere il server.",
      retryable: true,
    });
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text();

  if (!response.ok) throw toApiError(response, payload);

  return payload as T;
}

/** Normalizza liste e pagine: due contratti documentati convivono (array | Page). */
export function pageItems<T>(payload: T[] | { items?: T[] } | null | undefined): T[] {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.items)) return payload.items;
  return [];
}
