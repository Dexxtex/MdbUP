import { useDeferredValue, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useCatalogChanges, useProviders } from "../hooks/queries";
import type {
  CatalogChangeDirection,
  CatalogChangeItem,
  CatalogChangeWindow,
  MediaType,
} from "../api/types";
import {
  CatalogChangeDirectionBadge,
  EpisodeEventBadge,
} from "../components/ui/badges";
import {
  EmptyState,
  ErrorState,
  StaleBanner,
  TableSkeleton,
} from "../components/ui/feedback";
import {
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  ToggleChip,
} from "../components/ui/primitives";
import {
  CATALOG_CHANGE_DIRECTIONS,
  CATALOG_CHANGE_WINDOWS,
  catalogChangeSourceLabel,
  catalogChangeSourceName,
  catalogChangeWindowLabel,
} from "../lib/catalog-changes";
import { formatDateTime, formatNumber } from "../lib/format";
import { IconArrowRight, IconSearch } from "../components/ui/icons";

function shortId(value: string | null): string {
  return value ? value.slice(0, 8) : "—";
}

function CounterCard({
  label,
  value,
  tone,
  sign,
  testId,
}: {
  label: string;
  value: number;
  tone: "success" | "danger" | "neutral";
  sign?: "+" | "−";
  testId: string;
}) {
  const toneClass =
    tone === "success"
      ? "text-success"
      : tone === "danger"
        ? "text-danger"
        : "text-ink";
  return (
    <Card className="p-4" testId={testId}>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`}>
        {sign ? `${sign}${formatNumber(value)}` : formatNumber(value)}
      </p>
    </Card>
  );
}

function CatalogChangeCard({ item }: { item: CatalogChangeItem }) {
  const title = item.title ?? "Titolo non disponibile";
  const detectedLabel = formatDateTime(item.detected_at_rome ?? item.detected_at);
  return (
    <article
      data-testid="catalog-change-card"
      className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4 shadow-card"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CatalogChangeDirectionBadge direction={item.direction} />
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
          <span>{item.media_type === "MOVIE" ? "Film" : "Serie"}</span>
          {item.episode_event_type ? (
            <EpisodeEventBadge eventType={item.episode_event_type as import("../api/types").EpisodeEventType} />
          ) : null}
        </div>
      </div>

      <div className="min-w-0">
        <h3 className="truncate text-base font-semibold text-ink" title={title}>
          {title}
          {item.year ? (
            <span className="ml-2 text-sm font-normal text-ink-muted">{item.year}</span>
          ) : null}
        </h3>
        <p className="mt-0.5 text-sm text-ink-muted">
          {item.provider_name} · {catalogChangeSourceName(item)}
        </p>
      </div>

      <div className="mt-auto space-y-1 border-t border-line pt-3 text-xs text-ink-muted">
        <p className="font-medium text-ink">Rilevato da snapshot</p>
        <p className="font-mono text-ink">{shortId(item.current_snapshot_id)}</p>
        <p>
          <time dateTime={item.detected_at}>{detectedLabel}</time>
        </p>
        <p className="text-ink">{catalogChangeSourceLabel(item)}</p>
        {item.collection_id ? (
          <Link
            to={`/app/collections/${item.collection_id}`}
            className="inline-flex items-center gap-1 font-medium text-accent underline"
          >
            {item.collection_name ?? "Apri collezione"}
            <IconArrowRight />
          </Link>
        ) : null}
      </div>
    </article>
  );
}

export default function CatalogChangesPage() {
  const [window, setWindow] = useState<CatalogChangeWindow>("24h");
  const [providerId, setProviderId] = useState("");
  const [mediaType, setMediaType] = useState<"" | MediaType>("");
  const [sourceKey, setSourceKey] = useState("");
  const [direction, setDirection] = useState<"" | CatalogChangeDirection>("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const deferredSearch = useDeferredValue(search);
  const providers = useProviders("IT");
  const changes = useCatalogChanges({
    window,
    providerId,
    mediaType,
    sourceKey,
    direction,
    search: deferredSearch,
    page,
    pageSize: 50,
  });

  useEffect(() => {
    setPage(1);
  }, [window, providerId, mediaType, sourceKey, direction, deferredSearch]);

  const data = changes.data;
  const counters = data?.counters;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const hasFilters = Boolean(
    providerId || mediaType || sourceKey || direction || deferredSearch.trim(),
  );

  return (
    <>
      <PageHeader
        eyebrow="Cambi catalogo"
        title="Cambi Catalogo IT"
        description="Entrate e uscite rilevate confrontando gli snapshot consecutivi delle collezioni italiane."
        testId="catalog-changes-header"
        actions={
          <Button
            variant="secondary"
            onClick={() => void changes.refetch()}
            busy={changes.isFetching}
          >
            Aggiorna
          </Button>
        }
      />
      {data ? <StaleBanner updatedAt={changes.dataUpdatedAt} /> : null}

      <div data-testid="catalog-changes" className="space-y-6">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <CounterCard
            label="Entrati oggi"
            value={counters?.added_today ?? 0}
            tone="success"
            sign="+"
            testId="catalog-counter-added-today"
          />
          <CounterCard
            label="Usciti oggi"
            value={counters?.removed_today ?? 0}
            tone="danger"
            sign="−"
            testId="catalog-counter-removed-today"
          />
          <CounterCard
            label={`Entrati · ${catalogChangeWindowLabel(window)}`}
            value={counters?.added_window ?? 0}
            tone="neutral"
            sign="+"
            testId="catalog-counter-added-window"
          />
          <CounterCard
            label={`Usciti · ${catalogChangeWindowLabel(window)}`}
            value={counters?.removed_window ?? 0}
            tone="neutral"
            sign="−"
            testId="catalog-counter-removed-window"
          />
        </div>

        <Card>
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-xs font-medium text-ink-muted">Periodo</p>
              <div className="flex flex-wrap gap-2">
                {CATALOG_CHANGE_WINDOWS.map((option) => (
                  <ToggleChip
                    key={option.value}
                    testId={`catalog-window-${option.value}`}
                    pressed={window === option.value}
                    onClick={() => setWindow(option.value)}
                  >
                    {option.label}
                  </ToggleChip>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field id="catalog-provider" label="Provider">
                <Select
                  id="catalog-provider"
                  value={providerId}
                  onChange={(event) => setProviderId(event.target.value)}
                >
                  <option value="">Tutti i provider</option>
                  {(providers.data ?? []).map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id="catalog-media" label="Tipo">
                <Select
                  id="catalog-media"
                  value={mediaType}
                  onChange={(event) =>
                    setMediaType(event.target.value as "" | MediaType)
                  }
                >
                  <option value="">Film e serie</option>
                  <option value="MOVIE">Film</option>
                  <option value="SHOW">Serie</option>
                </Select>
              </Field>
              <Field id="catalog-source" label="Fonte">
                <Select
                  id="catalog-source"
                  value={sourceKey}
                  onChange={(event) => setSourceKey(event.target.value)}
                >
                  <option value="">JustWatch e TMDb</option>
                  <option value="justwatch">JustWatch</option>
                  <option value="tmdb">TMDb</option>
                </Select>
              </Field>
              <Field id="catalog-direction" label="Direzione">
                <Select
                  id="catalog-direction"
                  value={direction}
                  onChange={(event) =>
                    setDirection(event.target.value as "" | CatalogChangeDirection)
                  }
                >
                  <option value="">Tutti</option>
                  {CATALOG_CHANGE_DIRECTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <Field id="catalog-search" label="Cerca titolo">
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
                  <IconSearch />
                </span>
                <Input
                  id="catalog-search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Titolo del film o della serie…"
                  className="pl-9"
                />
              </div>
            </Field>
          </div>
        </Card>

        {changes.isPending ? <TableSkeleton rows={5} /> : null}
        {changes.isError ? (
          <ErrorState error={changes.error} onRetry={() => void changes.refetch()} />
        ) : null}

        {changes.isSuccess && data ? (
          <>
            {data.items.length === 0 ? (
              <EmptyState
                title="Nessun cambio nel periodo"
                description={
                  hasFilters
                    ? "Prova ad allargare il periodo o a rimuovere alcuni filtri."
                    : "Nessun titolo è entrato o uscito dai cataloghi osservati."
                }
                action={
                  hasFilters ? (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setProviderId("");
                        setMediaType("");
                        setSourceKey("");
                        setDirection("");
                        setSearch("");
                      }}
                    >
                      Azzera i filtri
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <div
                data-testid="catalog-change-feed"
                className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
              >
                {data.items.map((item) => (
                  <CatalogChangeCard
                    key={`${item.media_id}-${item.collection_id}-${item.direction}-${item.detected_at}`}
                    item={item}
                  />
                ))}
              </div>
            )}

            {data.total > data.page_size ? (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-ink-muted">
                  {formatNumber(data.total)} cambi · pagina {data.page} di {totalPages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    Precedente
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  >
                    Successiva
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </>
  );
}
