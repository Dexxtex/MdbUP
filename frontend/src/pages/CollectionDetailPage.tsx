import { Link, useParams } from "react-router-dom";
import { useAcquireCollection } from "../api/mutations";
import { useCollection, useCollectionSnapshots } from "../api/queries";
import type { Snapshot } from "../api/types";
import { DateBasisBadge, OriginBadge } from "../components/ui/badges";
import { DataTable, type Column } from "../components/ui/data-table";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  StaleBanner,
  TableSkeleton,
} from "../components/ui/feedback";
import { Button, Card, PageHeader } from "../components/ui/primitives";
import {
  SnapshotQualityPill,
  SnapshotStatusPill,
} from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import { collectionProviderName } from "../lib/collections";
import { formatNumber } from "../lib/format";

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

export default function CollectionDetailPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const collection = useCollection(collectionId);
  const snapshots = useCollectionSnapshots(collectionId);
  const acquire = useAcquireCollection(collectionId ?? "");

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
            <DateBasisBadge dateBasis={data.date_basis} source={data.source_key} />
            <span className="inline-flex items-center rounded-full border border-line bg-surface-muted px-2.5 py-0.5 text-xs text-ink-muted">
              {data.kind}
            </span>
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

        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Dettagli</h2>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Fonte</dt>
              <dd className="mt-1 text-sm text-ink">{data.source_key ?? "—"}</dd>
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
