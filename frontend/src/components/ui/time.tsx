import { cn } from "../../lib/cn";
import { formatDateTime, formatDateTimeUtc, formatRelative } from "../../lib/format";

/**
 * Orario nel fuso dell'app (Europe/Rome); il tooltip mostra il valore UTC e
 * l'età relativa, così il dato resta verificabile senza cambiare fuso alla UI.
 */
export function Timestamp({
  value,
  className,
  withRelative = true,
}: {
  value?: string | null;
  className?: string;
  withRelative?: boolean;
}) {
  if (!value) return <span className="text-ink-faint">—</span>;
  const relative = withRelative ? formatRelative(value) : null;
  const title = `UTC: ${formatDateTimeUtc(value)}${relative ? ` · ${relative}` : ""}`;
  return (
    <time
      dateTime={value}
      title={title}
      className={cn("tabular-nums text-ink", className)}
    >
      {formatDateTime(value)}
    </time>
  );
}
