import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAcquireCollection, useCreatePreview } from "../api/mutations";
import {
  useCollection,
  useCollectionEpisodeEvents,
  useCollectionSnapshots,
  usePreview,
  useSnapshotItems,
} from "../api/queries";
import type { EpisodeEvent, Snapshot, SnapshotItem } from "../api/types";
import {
  CollectionSourceBadge,
  DateBasisBadge,
  OriginBadge,
  UpcomingBadge,
} from "../components/ui/badges";
import { DataTable, type Column } from "../components/ui/data-table";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  StaleBanner,
  TableSkeleton,
} from "../components/ui/feedback";
import { Button, Card, PageHeader } from "../components/ui/primitives";
import { StatusPill } from "../components/ui/status-pill";
import {
  SnapshotQualityPill,
  SnapshotStatusPill,
} from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import {
  collectionKindLabel,
  collectionProviderName,
  collectionSourceLabel,
  collectionSourceTone,
  isUpcomingCollection,
} from "../lib/collections";
import { formatNumber } from "../lib/format";
import {
  availabilityStatusLabel,
  availabilityStatusTone,
  isJustWatchSource,
} from "../lib/justwatch";

const snapshotColumns: Column<Snapshot>[] = [
  {
    key: "status",
    header: "Stato",
    render: (snapshot) => <SnapshotStatusPill status={snapshot.status} />,
  },
  {
    key: "quality",
    header: "Qualità",
    render: (snapshot) => <SnapshotQualityPill quality={snapshot.quality} />,
  },
  {
    key: "valid",
    header: "Valido",
    render: (snapshot) => (
      <span className={snapshot.is_valid ? "text-success" : "text-ink-faint"}>
        {snapshot.is_valid ? "Sì" : "No"}
      </span>
    ),
  },
  {
    key: "items",
    header: "Elementi",
    render: (snapshot) => (
      <span className="tabular-nums">{formatNumber(snapshot.items_count)}</span>
    ),
  },
  {
    key: "unresolved",
    header: "Non risolti",
    render: (snapshot) => (
      <span className="tabular-nums">{formatNumber(snapshot.unresolved_count)}</span>
    ),
  },
  {
    key: "pages",
    header: "Pagine",
    render: (snapshot) => (
      <span className="tabular-nums">
        {formatNumber(snapshot.pages_fetched)} / {formatNumber(snapshot.pages_expected ?? 0)}
      </span>
    ),
  },
  {
    key: "started",
    header: "Avviato",
    render: (snapshot) => <Timestamp value={snapshot.started_at} className="text-xs" />,
  },
  {
    key: "finished",
    header: "Concluso",
    render: (snapshot) => <Timestamp value={snapshot.finished_at} className="text-xs" />,
  },
];

const episodeColumns: Column<EpisodeEvent>[] = [
  {
    key: "event",
    header: "Evento",
    render: (event) =>
      event.event_type === "SEASON_ADDED"
        ? "Stagione aggiunta"
        : event.event_type === "SEASON_REMOVED"
          ? "Stagione rimossa"
          : event.event_type === "EPISODE_ADDED"
            ? "Episodio aggiunto"
            : event.event_type === "EPISODE_REMOVED"
              ? "Episodio rimosso"
              : event.event_type,
  },
  {
    key: "title",
    header: "Titolo",
    render: (event) => event.title ?? event.media_id.slice(0, 8),
  },
  {
    key: "season",
    header: "Stagione",
    render: (event) => <span className="tabular-nums">{event.season_number}</span>,
  },
  {
    key: "episode",
    header: "Episodio",
    render: (event) => (
      <span className="tabular-nums">{event.episode_number ?? "—"}</span>
    ),
  },
  {
    key: "occurred",
    header: "Rilevato",
    render: (event) => <Timestamp value={event.occurred_at} className="text-xs" />,
  },
];

const snapshotItemColumns: Column<SnapshotItem>[] = [
  {
    key: "position",
    header: "#",
    render: (item) => <span className="tabular-nums">{item.position}</span>,
  },
  {
    key: "title",
    header: "Titolo",
    render: (item) => (
      <div className="flex flex-col gap-0.5">
        <span className="font-medium text-ink">
          {item.title ?? item.source_item_id ?? item.tmdb_id ?? "—"}
        </span>
        {item.release_year ? (
          <span className="text-xs text-ink-muted">{item.release_year}</span>
        ) : null}
      </div>
    ),
  },
  {
    key: "availability",
    header: "Disponibilità",
    render: (item) => (
      <StatusPill
        label={availabilityStatusLabel(item.availability_status)}
        tone={availabilityStatusTone(item.availability_status)}
        code={item.availability_status ?? undefined}
      />
    ),
  },
  {
    key: "offers",
    header: "Offerte",
    render: (item) =>
      item.source_offer_types.length > 0 ? item.source_offer_types.join(", ") : "—",
  },
  {
    key: "date",
    header: "Data",
    render: (item) =>
      item.source_date_created ? (
        <Timestamp value={item.source_date_created} className="text-xs" />
      ) : (
        <span className="text-xs text-ink-muted">—</span>
      ),
  },
];

export default function CollectionDetailPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const collection = useCollection(collectionId);
  const snapshots = useCollectionSnapshots(collectionId);
  const acquire = useAcquireCollection(collectionId ?? "");
  const [sourcePreviewId, setSourcePreviewId] = useState<string | undefined>();
  const createSourcePreview = useCreatePreview();
  const sourcePreview = usePreview(sourcePreviewId);
  const latestSnapshotId =
    collection.data?.latest_snapshot?.id ?? collection.data?.last_valid_snapshot?.id;
  const showJustWatchData = isJustWatchSource(collection.data?.source_key);
  const snapshotItems = useSnapshotItems(showJustWatchData ? latestSnapshotId : undefined);
  const showEpisodeEvents =
    collection.data?.media_type === "SHOW" && showJustWatchData;
  const episodeEvents = useCollectionEpisodeEvents(collectionId, 50, showEpisodeEvents);

  if (collection.isPending) {
    return (
      <>
        <PageHeader title="Collezione" />
        <TableSkeleton rows={4} />
      </>
    );
  }

  if (collection.isError) {
    return (
      <>
        <PageHeader title="Collezione" />
        <ErrorState error={collection.error} onRetry={() => void collection.refetch()} />
      </>
    );
  }

  const data = collection.data;
  const latest = data.latest_snapshot ?? data.last_valid_snapshot ?? null;
  const snapshotRows = snapshots.data ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Collezione"
        title={data.name}
        description={`${collectionProviderName(data)} · ${
          data.media_type === "MOVIE" ? "Film" : "Serie"
        }`}
        meta={
          <>
            <OriginBadge
              origin={data.origin}
              source={data.source_key}
              multiProvider={data.is_multi_provider}
            />
            <CollectionSourceBadge
              label={collectionSourceLabel(data)}
              tone={collectionSourceTone(data)}
            />
            <DateBasisBadge dateBasis={data.date_basis} source={data.source_key} />
            <span className="inline-flex items-center rounded-full border border-line bg-surface-muted px-2.5 py-0.5 text-xs text-ink-muted">
              {collectionKindLabel(data.kind)}
            </span>
            {isUpcomingCollection(data) ? <UpcomingBadge /> : null}
            <span
              className={
                data.is_active
                  ? "inline-flex items-center rounded-full border border-success/40 bg-success-soft px-2.5 py-0.5 text-xs text-success"
                  : "inline-flex items-center rounded-full border border-line bg-surface-muted px-2.5 py-0.5 text-xs text-ink-muted"
              }
            >
              {data.is_active ? "Attiva" : "Disattivata"}
            </span>
          </>
        }
        actions={
          <>
            <Link
              to={`/app/collections/${data.id}/edit`}
              className="inline-flex min-h-11 items-center rounded-md border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-muted"
            >
              Modifica
            </Link>
            <Button
              variant="secondary"
              onClick={() => {
                void createSourcePreview
                  .mutateAsync({ collection_id: data.id })
                  .then((result) => setSourcePreviewId(result.preview_id))
                  .catch(() => undefined);
              }}
              busy={createSourcePreview.isPending}
              data-testid="source-only-preview"
            >
              Anteprima source-only
            </Button>
            <Button onClick={() => acquire.mutate()} busy={acquire.isPending}>
              Acquisisci snapshot
            </Button>
          </>
        }
      />
      <StaleBanner updatedAt={collection.dataUpdatedAt} />

      {acquire.isSuccess ? (
        <div className="mb-4">
          <InlineNotice>
            Acquisizione avviata: lo snapshot comparirà in questa pagina al termine.
          </InlineNotice>
        </div>
      ) : null}
      {acquire.isError ? (
        <div className="mb-4">
          <ErrorState error={acquire.error} />
        </div>
      ) : null}

      <Card className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-ink">Anteprima source-only</h2>
            <p className="text-sm text-ink-muted">
              Calcola il piano dalla fonte senza target MDBList: nessuna scrittura remota,
              nessuna lista modificata.
            </p>
          </div>
          <StatusPill label="Nessuna scrittura remota" tone="neutral" />
        </div>

        {createSourcePreview.isError ? (
          <div className="mt-3">
            <ErrorState error={createSourcePreview.error} />
          </div>
        ) : null}
        {sourcePreview.isError ? (
          <div className="mt-3">
            <ErrorState
              error={sourcePreview.error}
              onRetry={() => void sourcePreview.refetch()}
            />
          </div>
        ) : null}
        {sourcePreviewId && sourcePreview.isPending ? <TableSkeleton rows={2} /> : null}
        {sourcePreview.data ? (
          <div className="mt-4 rounded-md border border-line bg-surface-elevated p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-ink">Stato anteprima</span>
              <span data-testid="source-preview-state">
                <StatusPill
                  label={sourcePreview.data.state}
                  tone={
                    sourcePreview.data.state === "READY"
                      ? "success"
                      : sourcePreview.data.state === "BLOCKED"
                        ? "warning"
                        : sourcePreview.data.state === "FAILED"
                          ? "danger"
                          : "info"
                  }
                  code={sourcePreview.data.state}
                />
              </span>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Da aggiungere</dt>
                <dd
                  className="text-lg font-semibold text-ink"
                  data-testid="source-preview-to-add"
                >
                  +{formatNumber(sourcePreview.data.counts.to_add)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Da rimuovere</dt>
                <dd
                  className="text-lg font-semibold text-ink"
                  data-testid="source-preview-to-remove"
                >
                  −{formatNumber(sourcePreview.data.counts.to_remove)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Invariati</dt>
                <dd className="text-lg font-semibold text-ink">
                  {formatNumber(sourcePreview.data.counts.unchanged)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Non risolti</dt>
                <dd className="text-lg font-semibold text-ink">
                  {formatNumber(sourcePreview.data.counts.unresolved)}
                </dd>
              </div>
            </dl>
            {sourcePreview.data.blocked ? (
              <p className="mt-3 text-sm text-warning" data-testid="source-preview-blocked">
                Anteprima bloccata: {sourcePreview.data.blocked.reason}
                {sourcePreview.data.blocked.observed != null &&
                sourcePreview.data.blocked.threshold != null
                  ? ` (osservato ${sourcePreview.data.blocked.observed}, soglia ${sourcePreview.data.blocked.threshold})`
                  : ""}
              </p>
            ) : null}
          </div>
        ) : null}
      </Card>

      <div className="space-y-6">
        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Snapshot corrente</h2>
          {latest ? (
            <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-faint">Stato</dt>
                <dd className="mt-1">
                  <SnapshotStatusPill status={latest.status} />
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-faint">Qualità</dt>
                <dd className="mt-1">
                  <SnapshotQualityPill quality={latest.quality} />
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-faint">Elementi</dt>
                <dd className="mt-1 text-sm tabular-nums text-ink">
                  {formatNumber(latest.items_count)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-faint">
                  Non risolti
                </dt>
                <dd className="mt-1 text-sm tabular-nums text-ink">
                  {formatNumber(latest.unresolved_count)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-faint">Concluso</dt>
                <dd className="mt-1 text-sm">
                  <Timestamp value={latest.finished_at} />
                </dd>
              </div>
              {latest.invalid_reason ? (
                <div className="sm:col-span-2 lg:col-span-4">
                  <dt className="text-xs uppercase tracking-wide text-ink-faint">
                    Motivo non valido
                  </dt>
                  <dd className="mt-1 text-sm text-ink">{latest.invalid_reason}</dd>
                </div>
              ) : null}
            </dl>
          ) : (
            <EmptyState
              title="Nessuno snapshot disponibile"
              description="Acquisisci uno snapshot per abilitare i binding su questa collezione."
              action={
                <Button onClick={() => acquire.mutate()} busy={acquire.isPending}>
                  Acquisisci snapshot
                </Button>
              }
            />
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Storico snapshot</h2>
          {snapshots.isPending ? <TableSkeleton rows={3} /> : null}
          {snapshots.isError ? (
            <ErrorState error={snapshots.error} onRetry={() => void snapshots.refetch()} />
          ) : null}
          {snapshots.isSuccess && snapshotRows.length === 0 ? (
            <EmptyState
              title="Nessuno snapshot"
              description="Acquisisci uno snapshot dalla fonte per iniziare."
            />
          ) : null}
          {snapshots.isSuccess && snapshotRows.length > 0 ? (
            <DataTable
              caption="Storico degli snapshot della collezione"
              columns={snapshotColumns}
              rows={snapshotRows}
              rowKey={(snapshot) => snapshot.id}
            />
          ) : null}
        </Card>

        {showJustWatchData ? (
        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Item dello snapshot</h2>
          {snapshotItems.isPending ? <TableSkeleton rows={3} /> : null}
          {snapshotItems.isError ? (
            <ErrorState
              error={snapshotItems.error}
              onRetry={() => void snapshotItems.refetch()}
            />
          ) : null}
          {snapshotItems.isSuccess && snapshotItems.data.items.length === 0 ? (
            <EmptyState
              title="Nessun item"
              description="Lo snapshot corrente non contiene elementi."
            />
          ) : null}
          {snapshotItems.isSuccess && snapshotItems.data.items.length > 0 ? (
            <>
              <DataTable
                caption="Item dello snapshot con disponibilità e offerte"
                columns={snapshotItemColumns}
                rows={snapshotItems.data.items}
                rowKey={(item) => `${item.position}-${item.media_id ?? item.source_item_id ?? ""}`}
              />
              {isJustWatchSource(data.source_key) &&
              snapshotItems.data.items.some((item) => item.date_basis === "UNKNOWN") ? (
                <p className="mt-3 text-xs text-ink-muted">
                  Date non disponibili dalla fonte: JustWatch non dichiara la data di
                  aggiunta degli item.
                </p>
              ) : null}
            </>
          ) : null}
        </Card>
        ) : null}

        {showEpisodeEvents ? (
          <Card>
            <h2 className="mb-3 text-lg font-semibold text-ink">
              Eventi stagioni ed episodi
            </h2>
            {episodeEvents.isPending ? <TableSkeleton rows={3} /> : null}
            {episodeEvents.isError ? (
              <ErrorState
                error={episodeEvents.error}
                onRetry={() => void episodeEvents.refetch()}
              />
            ) : null}
            {episodeEvents.isSuccess && episodeEvents.data.items.length === 0 ? (
              <EmptyState
                title="Nessun evento stagione/episodio"
                description="Gli eventi compaiono dopo le acquisizioni JustWatch delle serie."
              />
            ) : null}
            {episodeEvents.isSuccess && episodeEvents.data.items.length > 0 ? (
              <DataTable
                caption="Eventi stagione ed episodio rilevati dalla fonte"
                columns={episodeColumns}
                rows={episodeEvents.data.items}
                rowKey={(event) =>
                  `${event.media_id}-${event.event_type}-${event.season_number}-${event.episode_number ?? ""}`
                }
              />
            ) : null}
          </Card>
        ) : null}

        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Dettagli</h2>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Fonte</dt>
              <dd className="mt-1 text-sm text-ink">{collectionSourceLabel(data)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Paese</dt>
              <dd className="mt-1 text-sm text-ink">{data.country_code}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">
                Tipi di offerta
              </dt>
              <dd className="mt-1 text-sm text-ink">
                {data.offer_types.length > 0 ? data.offer_types.join(", ") : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">
                Ordinamento
              </dt>
              <dd className="mt-1 text-sm text-ink">{data.sort_mode}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Slug</dt>
              <dd className="mt-1 font-mono text-sm text-ink">{data.slug}</dd>
            </div>
          </dl>
        </Card>
      </div>

      <p className="mt-6 text-sm text-ink-muted">
        <Link to="/app/collections" className="font-medium text-accent underline">
          Torna alle collezioni
        </Link>
      </p>
    </>
  );
}
