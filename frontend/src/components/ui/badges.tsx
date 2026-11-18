import type {
  CatalogChangeDirection,
  CollectionOrigin,
  DateBasis,
  EpisodeEventType,
} from "../../api/types";
import {
  catalogChangeDirectionLabel,
  catalogChangeDirectionSign,
  catalogChangeDirectionTone,
  episodeEventLabel,
  episodeEventTone,
} from "../../lib/catalog-changes";
import { cn } from "../../lib/cn";
import { originPresentation, type Tone } from "../../lib/status";
import { IconBuilding, IconFilter, IconLayers, IconNode } from "./icons";

const toneStyles: Record<Tone, string> = {
  neutral: "border-line bg-surface-muted text-ink-muted",
  info: "border-accent/40 bg-accent-soft text-accent",
  success: "border-success/40 bg-success-soft text-success",
  warning: "border-warning/40 bg-warning-soft text-warning",
  danger: "border-danger/40 bg-danger-soft text-danger",
};

export function OriginBadge({
  origin,
  source,
  multiProvider = false,
}: {
  origin: CollectionOrigin;
  source?: string | null;
  multiProvider?: boolean;
}) {
  const presentation = originPresentation(origin, source, multiProvider);
  const Icon =
    origin === "OFFICIAL"
      ? IconBuilding
      : origin === "AGGREGATOR"
        ? IconNode
        : multiProvider
          ? IconLayers
          : IconFilter;

  return (
    <span
      data-origin={origin}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        toneStyles[presentation.tone],
      )}
    >
      <Icon />
      {presentation.label}
    </span>
  );
}

export function CatalogChangeDirectionBadge({
  direction,
}: {
  direction: CatalogChangeDirection;
}) {
  const tone = catalogChangeDirectionTone(direction);
  return (
    <span
      data-direction={direction}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        toneStyles[tone],
      )}
    >
      <span aria-hidden="true">{catalogChangeDirectionSign(direction)}</span>
      {catalogChangeDirectionLabel(direction)}
    </span>
  );
}

/** Badge per gli eventi stagione/episodio rilevati dalla fonte. */
export function EpisodeEventBadge({ eventType }: { eventType: EpisodeEventType }) {
  const tone = episodeEventTone(eventType);
  return (
    <span
      data-event-type={eventType}
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        toneStyles[tone],
      )}
    >
      {episodeEventLabel(eventType)}
    </span>
  );
}

export function CollectionSourceBadge({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: Tone;
}) {
  return (
    <span
      data-source-label={label}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        toneStyles[tone],
      )}
    >
      {label}
    </span>
  );
}

/** Badge per `CollectionKind.UPCOMING`: il contenuto non è ancora disponibile. */
export function UpcomingBadge() {
  return (
    <span
      data-kind="UPCOMING"
      className="inline-flex items-center rounded-full border border-warning/40 bg-warning-soft px-2.5 py-0.5 text-xs font-medium text-warning"
    >
      In arrivo
    </span>
  );
}

const dateBasisLabels: Record<DateBasis, string> = {
  PROVIDER_OFFICIAL: "Data dichiarata dal provider",
  AGGREGATOR_FIRST_SEEN: "Prima osservazione dell'aggregatore",
  APP_FIRST_SEEN: "Prima osservazione dell'app (non ufficiale)",
  UNKNOWN: "Data di aggiunta non disponibile",
};

const dateBasisStyles: Record<DateBasis, string> = {
  PROVIDER_OFFICIAL: "border-line bg-surface-muted text-ink",
  AGGREGATOR_FIRST_SEEN: "border-warning/40 bg-warning-soft text-warning",
  APP_FIRST_SEEN: "border-line bg-surface text-ink-muted",
  UNKNOWN: "border-dashed border-line-strong bg-surface text-ink-faint",
};

/**
 * `AGGREGATOR_FIRST_SEEN` è una data osservata dall'aggregatore, non dal
 * provider: il nome della fonte va mostrato, altrimenti l'etichetta attribuisce
 * la data a un aggregatore che non è quello in uso (docs/phase1/07-frontend-api.md §2.2).
 */
export function DateBasisBadge({
  dateBasis,
  source,
}: {
  dateBasis: DateBasis;
  source?: string | null;
}) {
  const label =
    dateBasis === "AGGREGATOR_FIRST_SEEN" && source
      ? `Prima osservazione ${source} (aggregatore)`
      : dateBasisLabels[dateBasis];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs",
        dateBasisStyles[dateBasis],
      )}
    >
      {label}
    </span>
  );
}
