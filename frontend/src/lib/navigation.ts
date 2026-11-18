/**
 * `next` arriva dalla query string (`/login?next=…`) e viene passato a
 * `navigate()`: un URL assoluto o protocol-relative farebbe fare al browser un
 * redirect cross-origin dopo il login (open redirect). Si accettano solo path
 * relativi che iniziano con `/` e non con `//` — né con `/\`, che i browser
 * normalizzano a `//`.
 */
export function safeNextPath(
  raw: string | null | undefined,
  fallback = "/app",
): string {
  if (!raw) return fallback;
  if (!raw.startsWith("/")) return fallback;
  if (raw.startsWith("//") || raw.startsWith("/\\")) return fallback;
  return raw;
}
