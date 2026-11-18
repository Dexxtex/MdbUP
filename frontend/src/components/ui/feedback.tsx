import type { ReactNode } from "react";
import { describeApiError } from "../../lib/errors";
import { cn } from "../../lib/cn";
import { Button } from "./primitives";
import { IconAlert, IconCheck, IconDot } from "./icons";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "animate-pulse rounded-md bg-surface-muted motion-reduce:animate-none",
        className,
      )}
    />
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-live="polite">
      <span className="sr-only">Caricamento dei dati in corso…</span>
      <Skeleton className="h-10 w-full" />
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 p-8 text-center">
      {icon ? (
        <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-line bg-surface-muted text-ink-muted">
          {icon}
        </div>
      ) : null}
      <p className="text-base font-medium text-ink">{title}</p>
      {description ? (
        <p className="mx-auto mt-1 max-w-md text-sm text-ink-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const presentation = describeApiError(error);
  return (
    <div
      role="alert"
      className="rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm text-ink"
    >
      <p className="flex items-center gap-2 font-semibold text-danger">
        <IconAlert />
        {presentation.title}
      </p>
      <p className="mt-1 text-ink">{presentation.message}</p>
      {presentation.requestId ? (
        <p className="mt-1 text-xs text-ink-muted">
          Codice richiesta: <code className="font-mono">{presentation.requestId}</code>
        </p>
      ) : null}
      {onRetry && presentation.retryable ? (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Riprova
        </Button>
      ) : null}
    </div>
  );
}

export function StaleBanner({
  updatedAt,
  thresholdMs = 60_000,
  label = "Dati non aggiornati",
}: {
  updatedAt?: number;
  thresholdMs?: number;
  label?: string;
}) {
  if (!updatedAt) return null;
  const age = Date.now() - updatedAt;
  if (age <= thresholdMs) return null;
  const minutes = Math.round(age / 60_000);
  return (
    <div
      role="status"
      className="mb-4 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-ink"
    >
      <span className="font-medium text-warning">{label}:</span> ultimo aggiornamento{" "}
      {minutes <= 0 ? "pochi secondi" : `${minutes} minuti`} fa.
    </div>
  );
}

export function InlineNotice({
  tone = "info",
  children,
}: {
  tone?: "info" | "success" | "warning" | "danger";
  children: ReactNode;
}) {
  const styles = {
    info: "border-accent/40 bg-accent-soft text-ink",
    success: "border-success/40 bg-success-soft text-ink",
    warning: "border-warning/40 bg-warning-soft text-ink",
    danger: "border-danger/40 bg-danger-soft text-ink",
  } as const;
  const Icon = tone === "info" ? IconDot : tone === "success" ? IconCheck : IconAlert;
  return (
    <div
      role="status"
      className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm", styles[tone])}
    >
      <span
        className={cn(
          "mt-0.5 shrink-0",
          tone === "info" && "text-accent",
          tone === "success" && "text-success",
          tone === "warning" && "text-warning",
          tone === "danger" && "text-danger",
        )}
      >
        <Icon />
      </span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
