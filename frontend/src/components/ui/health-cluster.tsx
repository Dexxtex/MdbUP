import { useDashboard, useSession, useSystemStatus } from "../../api/queries";
import type { HealthState } from "../../api/types";
import { cn } from "../../lib/cn";
import { HEALTH_STATE_LABELS, deriveHealth } from "../../lib/health";

const dotStyles: Record<HealthState, string> = {
  ok: "bg-success",
  degraded: "bg-warning",
  error: "bg-danger",
  unknown: "bg-ink-faint",
};

export function HealthCluster({ className }: { className?: string }) {
  const session = useSession();
  const dashboard = useDashboard();
  const systemStatus = useSystemStatus();

  const apiState: HealthState = session.isSuccess
    ? "ok"
    : session.isError
      ? "error"
      : "unknown";
  const items = deriveHealth({
    apiState,
    status: systemStatus.data ?? null,
    sources: dashboard.data?.sources,
  });

  return (
    <ul
      data-testid="health-cluster"
      aria-label="Stato dei servizi"
      className={cn("flex items-center gap-3", className)}
    >
      {items.map((item) => (
        <li
          key={item.key}
          title={`${item.label}: ${HEALTH_STATE_LABELS[item.state]} — ${item.detail}`}
          className="flex items-center gap-1.5 text-xs text-ink-muted"
        >
          <span
            aria-hidden="true"
            className={cn("h-2 w-2 rounded-full", dotStyles[item.state])}
          />
          <span className="hidden xl:inline">{item.label}</span>
          <span className="sr-only">
            {item.label}: {HEALTH_STATE_LABELS[item.state]}
          </span>
        </li>
      ))}
    </ul>
  );
}
