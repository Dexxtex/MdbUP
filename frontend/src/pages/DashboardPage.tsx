import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  useBindings,
  useCatalogChanges,
  useDashboard,
  useRuns,
  useSources,
  useSystemStatus,
} from "../hooks/queries";
import type {
  AlertSeverity,
  DashboardAlert,
  DashboardApiProviderUsage,
  DashboardJobRow,
  DashboardSnapshotRow,
  DashboardSourceRow,
  DashboardSyncRunRow,
} from "../api/types";
import { AttentionRunCard } from "../components/dashboard/attention-runs";
import { CatalogChangeDirectionBadge } from "../components/ui/badges";
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
  RunStatusPill,
  SnapshotQualityPill,
  SnapshotStatusPill,
  SourceStatusPill,
} from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import { catalogChangeSourceLabel } from "../lib/catalog-changes";
import { bindingScheduleLabel } from "../lib/collections";
import { formatDate, formatNumber } from "../lib/format";
import { justWatchThrottleLabel } from "../lib/justwatch";

const severityStyles: Record<AlertSeverity, string> = {
  info: "border-accent/40 bg-accent-soft",
  warning: "border-warning/40 bg-warning-soft",
  error: "border-danger/40 bg-danger-soft",
};

const severityLabels: Record<AlertSeverity, string> = {
  info: "Informazione",
  warning: "Avviso",
  error: "Errore",
};

/** `DashboardAlertOut.severity` è una stringa: le severità note sono minuscole. */
function alertSeverity(alert: DashboardAlert): AlertSeverity {
  return alert.severity === "error" || alert.severity === "warning"
    ? alert.severity
    : "info";
}

function KpiCard({
  label,
  value,
  hint,
  footer,
  testId,
}: {
  label: string;
  value: string;
  hint?: string;
  footer?: ReactNode;
  testId?: string;
}) {
  return (
    <Card className="p-4 sm:p-5" testId={testId}>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums tracking-tight text-ink">
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
      {footer ? <div className="mt-3">{footer}</div> : null}
    </Card>
  );
}

function UsageMeter({
  label,
  usage,
}: {
  label: string;
  usage: DashboardApiProviderUsage;
}) {
  const estimate = usage.estimated_per_day ?? 0;
  const fill = estimate > 0 ? Math.min(100, Math.round((usage.today / estimate) * 100)) : 0;
  return (
    <div className="rounded-lg border border-line bg-surface-elevated p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-ink">{label}</p>
        <p className="text-xs text-ink-muted">
          <span className="tabular-nums text-ink">{formatNumber(usage.today)}</span> /{" "}
          <span className="tabular-nums">{formatNumber(estimate)}</span> oggi
        </p>
      </div>
      <div
        role="meter"
        aria-label={`Richieste ${label} di oggi rispetto alla stima giornaliera`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={fill}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted"
      >
        <progress className="meter" value={fill} max={100} aria-hidden="true" />
      </div>
      <p className="mt-1.5 text-xs text-ink-faint">
        Ultima ora {formatNumber(usage.hour)} · stima {formatNumber(usage.estimated_per_hour)}
        /ora
      </p>
    </div>
  );
}

const syncRunColumns: Column<DashboardSyncRunRow>[] = [
  {
    key: "run",
    header: "Sync",
    render: (run) => (
      <Link to={`/app/runs/${run.id}`} className="font-mono text-xs text-accent underline">
        {run.id.slice(0, 8)}
      </Link>
    ),
  },
  {
    key: "status",
    header: "Stato",
    render: (run) => <RunStatusPill status={run.status} />,
  },
  { key: "mode", header: "Modo", render: (run) => run.mode },
  { key: "media", header: "Tipo", render: (run) => run.media_type },
  {
    key: "created",
    header: "Creato",
    render: (run) => <Timestamp value={run.created_at} className="text-xs" />,
  },
  {
    key: "finished",
    header: "Concluso",
    render: (run) => <Timestamp value={run.finished_at} className="text-xs" />,
  },
];

const snapshotColumns: Column<DashboardSnapshotRow>[] = [
  {
    key: "collection",
    header: "Collezione",
    render: (snapshot) => (
      <Link
        to={`/app/collections/${snapshot.collection_id}`}
        className="font-mono text-xs text-accent underline"
      >
        {snapshot.collection_id.slice(0, 8)}
      </Link>
    ),
  },
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
    key: "items",
    header: "Elementi",
    render: (snapshot) => (
      <span className="tabular-nums">{formatNumber(snapshot.items_count)}</span>
    ),
  },
  {
    key: "finished",
    header: "Concluso",
    render: (snapshot) => <Timestamp value={snapshot.finished_at} className="text-xs" />,
  },
];

const jobColumns: Column<DashboardJobRow>[] = [
  { key: "task", header: "Task", render: (job) => job.task_name },
  { key: "status", header: "Stato", render: (job) => job.status },
  {
    key: "created",
    header: "Creato",
    render: (job) => <Timestamp value={job.created_at} className="text-xs" />,
  },
  {
    key: "finished",
    header: "Concluso",
    render: (job) => <Timestamp value={job.finished_at} className="text-xs" />,
  },
  {
    key: "error",
    header: "Errore",
    render: (job) => job.error_code ?? "—",
  },
];

const sourceColumns: Column<DashboardSourceRow>[] = [
  { key: "source", header: "Fonte", render: (source) => source.name },
  {
    key: "status",
    header: "Stato",
    render: (source) => <SourceStatusPill status={source.status} />,
  },
  {
    key: "message",
    header: "Messaggio",
    render: (source) => source.status_message ?? "—",
  },
  {
    key: "checked",
    header: "Ultima verifica",
    render: (source) => <Timestamp value={source.last_healthcheck_at} className="text-xs" />,
  },
];

export default function DashboardPage() {
  const dashboard = useDashboard();
  const bindings = useBindings();
  const runs = useRuns({});
  const systemStatus = useSystemStatus();
  const sourcesQuery = useSources();
  const catalogChanges = useCatalogChanges({ window: "24h", pageSize: 5 });

  if (dashboard.isPending) {
    return (
      <>
        <PageHeader title="Dashboard" testId="dashboard-header" />
        <TableSkeleton rows={6} />
      </>
    );
  }

  if (dashboard.isError) {
    return (
      <>
        <PageHeader title="Dashboard" testId="dashboard-header" />
        <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
      </>
    );
  }

  const data = dashboard.data;
  const counters = data.counters;
  const alerts = data.alerts ?? [];
  const recentSyncRuns = data.recent_sync_runs ?? [];
  const recentSnapshots = data.recent_snapshots ?? [];
  const recentJobs = data.recent_jobs ?? [];
  const sources = data.sources ?? [];
  const usage = data.api_usage;

  const bindingList = bindings.data ?? [];
  const activeBindings = bindingList.filter((binding) => binding.enabled);
  const pausedBindings = bindingList.length - activeBindings.length;
  const syncedTitles = bindingList.reduce(
    (total, binding) => total + (binding.target?.item_count ?? 0),
    0,
  );
  const runList = runs.data?.items ?? [];
  const attentionRuns = (runList.length > 0 ? runList : recentSyncRuns).filter(
    (run) => run.status === "AWAITING_APPROVAL" || run.status === "FAILED",
  );
  const upcoming = bindingList
    .filter((binding) => binding.next_run_at)
    .sort((a, b) => (a.next_run_at ?? "").localeCompare(b.next_run_at ?? ""))
    .slice(0, 6);

  const backup = systemStatus.data?.backup ?? null;
  const justwatchSource = (sourcesQuery.data ?? []).find(
    (source) => source.key === "justwatch",
  );
  const justwatch = justwatchSource?.justwatch ?? null;
  const catalogAcquisitions = [...(systemStatus.data?.catalog_acquisitions ?? [])].sort(
    (a, b) => a.next_acquire_at.localeCompare(b.next_acquire_at),
  );
  const recentChanges = catalogChanges.data?.items ?? [];
  const changeCounters = catalogChanges.data?.counters;
  const apiToday = (usage.tmdb.today ?? 0) + (usage.mdblist.today ?? 0);
  const apiEstimate =
    (usage.tmdb.estimated_per_day ?? 0) + (usage.mdblist.estimated_per_day ?? 0);

  return (
    <>
      <PageHeader
        eyebrow="Panoramica"
        title="Dashboard"
        description="Cosa richiede attenzione adesso, cosa è pianificato e quanto costano le fonti."
        testId="dashboard-header"
        actions={
          <Button
            variant="secondary"
            onClick={() => void dashboard.refetch()}
            busy={dashboard.isFetching}
          >
            Aggiorna
          </Button>
        }
      />
      <StaleBanner updatedAt={dashboard.dataUpdatedAt} />

      <div data-testid="dashboard" className="space-y-6">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Titoli nelle liste"
            value={formatNumber(syncedTitles)}
            hint={`${formatNumber(counters.media)} in catalogo · ${formatNumber(
              counters.collections,
            )} collezioni`}
            testId="kpi-titles"
          />
          <KpiCard
            label="Binding attivi"
            value={formatNumber(activeBindings.length)}
            hint={`${formatNumber(pausedBindings)} in pausa · ${formatNumber(
              bindingList.length,
            )} totali`}
            testId="kpi-bindings"
          />
          <KpiCard
            label="Richieste API oggi"
            value={formatNumber(apiToday)}
            hint={`Stima ${formatNumber(Math.round(apiEstimate))}/giorno`}
            testId="kpi-api-usage"
          />
          <KpiCard
            label="Ultimo backup"
            value={
              backup?.last_valid_at ?? backup?.last_backup_at
                ? formatDate(backup.last_valid_at ?? backup.last_backup_at)
                : "—"
            }
            hint={
              backup?.last_valid_at ?? backup?.last_backup_at
                ? undefined
                : "Stato backup non disponibile (endpoint /system/status)"
            }
            footer={
              backup?.last_valid_at ?? backup?.last_backup_at ? (
                <Timestamp
                  value={backup.last_valid_at ?? backup.last_backup_at}
                  className="text-sm"
                />
              ) : null
            }
            testId="kpi-backup"
          />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card testId="dashboard-catalog-changes">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-ink">Ultimi cambi catalogo IT</h2>
                <p className="text-sm text-ink-muted">
                  Entrate e uscite rilevate nelle ultime 24 ore.
                </p>
              </div>
              <Link
                to="/app/catalog-changes"
                className="text-sm font-medium text-accent underline"
              >
                Apri Cambi Catalogo IT
              </Link>
            </div>

            {changeCounters ? (
              <p className="mb-3 flex flex-wrap gap-3 text-sm">
                <span className="font-semibold text-success">
                  +{formatNumber(changeCounters.added_today)} entrati
                </span>
                <span className="font-semibold text-danger">
                  −{formatNumber(changeCounters.removed_today)} usciti
                </span>
              </p>
            ) : null}

            {catalogChanges.isPending ? <TableSkeleton rows={2} /> : null}
            {catalogChanges.isError ? (
              <InlineNotice tone="info">
                Endpoint cambi catalogo non disponibile in questa versione del backend.
              </InlineNotice>
            ) : null}
            {catalogChanges.isSuccess && recentChanges.length === 0 ? (
              <p className="text-sm text-ink-muted">Nessun cambio nelle ultime 24 ore.</p>
            ) : null}
            {recentChanges.length > 0 ? (
              <ul className="space-y-2">
                {recentChanges.map((change) => (
                  <li
                    key={`${change.media_id}-${change.collection_id}-${change.direction}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-surface-elevated px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">
                        {change.title ?? change.media_id.slice(0, 8)}
                        {change.year ? (
                          <span className="ml-1 text-xs font-normal text-ink-muted">
                            {change.year}
                          </span>
                        ) : null}
                      </p>
                      <p className="text-xs text-ink-muted">
                        {change.provider_name} · {catalogChangeSourceLabel(change)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <CatalogChangeDirectionBadge direction={change.direction} />
                      <Timestamp value={change.detected_at} className="text-xs" />
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>

          <Card testId="dashboard-catalog-acquisitions">
            <h2 className="text-lg font-semibold text-ink">Acquisizioni scaglionate 24h</h2>
            <p className="mb-3 text-sm text-ink-muted">
              Prossime acquisizioni dei cataloghi pianificate nelle prossime 24 ore.
            </p>
            {systemStatus.isPending ? <TableSkeleton rows={2} /> : null}
            {systemStatus.isSuccess && catalogAcquisitions.length === 0 ? (
              <p className="text-sm text-ink-muted">
                Nessuna acquisizione programmata: abilita la pianificazione del catalogo
                nelle impostazioni dei connettori.
              </p>
            ) : null}
            {catalogAcquisitions.length > 0 ? (
              <ol className="space-y-3">
                {catalogAcquisitions.map((acquisition) => (
                  <li key={acquisition.collection_id} className="flex gap-3">
                    <div className="mt-1 flex flex-col items-center">
                      <span className="h-2 w-2 rounded-full bg-accent" />
                      <span className="mt-1 h-full w-px flex-1 bg-line" />
                    </div>
                    <div className="min-w-0 flex-1 pb-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="truncate text-sm font-medium text-ink">
                          {acquisition.collection_name}
                        </p>
                        <Timestamp value={acquisition.next_acquire_at} className="text-xs" />
                      </div>
                      <p className="text-xs text-ink-muted">{acquisition.provider_name}</p>
                    </div>
                  </li>
                ))}
              </ol>
            ) : null}
          </Card>
        </div>

        <Card testId="attention-runs">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-ink">Richiede attenzione</h2>
              <p className="text-sm text-ink-muted">
                Run in attesa di approvazione o falliti: nessuna scrittura avviene senza il
                tuo consenso.
              </p>
            </div>
            <Link
              to="/app/runs?status=AWAITING_APPROVAL"
              className="text-sm font-medium text-accent underline"
            >
              Apri la coda
            </Link>
          </div>
          {attentionRuns.length === 0 ? (
            <InlineNotice tone="success">
              Nessun run bloccato o fallito: la coda è pulita.
            </InlineNotice>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {attentionRuns.slice(0, 4).map((run) => (
                <AttentionRunCard
                  key={run.id}
                  runId={run.id}
                  status={run.status}
                  createdAt={run.created_at}
                />
              ))}
            </div>
          )}
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <h2 className="text-lg font-semibold text-ink">Prossime sincronizzazioni</h2>
            <p className="mb-3 text-sm text-ink-muted">
              Prossime esecuzioni pianificate dai binding attivi.
            </p>
            {upcoming.length === 0 ? (
              <EmptyState
                title="Nessuna esecuzione pianificata"
                description="Imposta una frequenza su un binding per vedere la timeline."
                action={
                  <Link
                    to="/app/bindings"
                    className="text-sm font-medium text-accent underline"
                  >
                    Vai ai binding
                  </Link>
                }
              />
            ) : (
              <ol className="space-y-3">
                {upcoming.map((binding) => (
                  <li key={binding.id} className="flex gap-3">
                    <div className="mt-1 flex flex-col items-center">
                      <span className="h-2 w-2 rounded-full bg-accent" />
                      <span className="mt-1 h-full w-px flex-1 bg-line" />
                    </div>
                    <div className="min-w-0 flex-1 pb-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="truncate text-sm font-medium text-ink">
                          {binding.collection?.name ?? binding.collection_id.slice(0, 8)}
                        </p>
                        <Timestamp value={binding.next_run_at} className="text-xs" />
                      </div>
                      <p className="text-xs text-ink-muted">
                        {bindingScheduleLabel(binding)} · {binding.mode} ·{" "}
                        {binding.target?.name ?? binding.target_id.slice(0, 8)}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-ink">Richieste API</h2>
            <p className="mb-3 text-sm text-ink-muted">
              Conteggio reale di oggi rispetto alla stima dei binding attivi.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <UsageMeter label="TMDb" usage={usage.tmdb} />
              <UsageMeter label="MDBList" usage={usage.mdblist} />
            </div>
            <p className="mt-3 text-xs text-ink-faint">
              Stima basata su {formatNumber(usage.active_bindings)} binding attivi e sulle
              dimensioni degli snapshot; il conteggio “oggi” è reale.
            </p>
          </Card>

          <Card testId="dashboard-justwatch-metrics">
            <h2 className="text-lg font-semibold text-ink">JustWatch</h2>
            <p className="mb-3 text-sm text-ink-muted">
              Throttle, richieste e cache della fonte aggregatore.
            </p>
            {justwatch ? (
              <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <div className="rounded-md border border-line bg-surface-elevated px-3 py-2">
                  <dt className="text-xs text-ink-faint">Throttle</dt>
                  <dd className="text-sm font-semibold tabular-nums text-ink">
                    {justWatchThrottleLabel(justwatch.throttle_ms)}
                  </dd>
                </div>
                <div className="rounded-md border border-line bg-surface-elevated px-3 py-2">
                  <dt className="text-xs text-ink-faint">Richieste oggi</dt>
                  <dd className="text-sm font-semibold tabular-nums text-ink">
                    {formatNumber(justwatch.requests_today)}
                  </dd>
                </div>
                <div className="rounded-md border border-line bg-surface-elevated px-3 py-2">
                  <dt className="text-xs text-ink-faint">Richieste ora</dt>
                  <dd className="text-sm font-semibold tabular-nums text-ink">
                    {formatNumber(justwatch.requests_hour)}
                  </dd>
                </div>
                <div className="rounded-md border border-line bg-surface-elevated px-3 py-2">
                  <dt className="text-xs text-ink-faint">Cache hit</dt>
                  <dd className="text-sm font-semibold tabular-nums text-ink">
                    {formatNumber(justwatch.cache_hits)}
                  </dd>
                </div>
                <div className="rounded-md border border-line bg-surface-elevated px-3 py-2">
                  <dt className="text-xs text-ink-faint">Cache miss</dt>
                  <dd className="text-sm font-semibold tabular-nums text-ink">
                    {formatNumber(justwatch.cache_misses)}
                  </dd>
                </div>
                <div className="rounded-md border border-line bg-surface-elevated px-3 py-2">
                  <dt className="text-xs text-ink-faint">Mapping IT</dt>
                  <dd className="text-sm font-semibold tabular-nums text-ink">
                    {formatNumber(justwatch.mappings.length)}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="text-sm text-ink-muted">
                Dati runtime JustWatch non disponibili.
              </p>
            )}
          </Card>
        </div>

        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Avvisi</h2>
          {alerts.length === 0 ? (
            <p className="text-sm text-ink-muted">Nessun avviso attivo.</p>
          ) : (
            <ul className="space-y-2">
              {alerts.map((alert) => {
                const severity = alertSeverity(alert);
                return (
                  <li
                    key={`${alert.code}-${alert.message}`}
                    className={`rounded-md border px-3 py-2 text-sm text-ink ${severityStyles[severity]}`}
                  >
                    <span className="font-semibold">{severityLabels[severity]}:</span>{" "}
                    {alert.message}
                    <span className="ml-2 font-mono text-xs text-ink-faint">
                      ({alert.code})
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Sync recenti</h2>
          {recentSyncRuns.length === 0 ? (
            <EmptyState
              title="Nessun sync eseguito"
              description="Crea un binding per iniziare a sincronizzare una collezione."
            />
          ) : (
            <DataTable
              caption="Ultimi sync eseguiti"
              columns={syncRunColumns}
              rows={recentSyncRuns}
              rowKey={(run) => run.id}
            />
          )}
        </Card>

        <div className="grid gap-6 xl:grid-cols-2">
          <Card>
            <h2 className="mb-3 text-lg font-semibold text-ink">Snapshot recenti</h2>
            {recentSnapshots.length === 0 ? (
              <EmptyState
                title="Nessuno snapshot"
                description="Acquisisci una collezione per creare il primo snapshot."
              />
            ) : (
              <DataTable
                caption="Ultimi snapshot acquisiti"
                columns={snapshotColumns}
                rows={recentSnapshots}
                rowKey={(snapshot) => snapshot.id}
              />
            )}
          </Card>

          <Card>
            <h2 className="mb-3 text-lg font-semibold text-ink">Stato delle fonti</h2>
            {sources.length === 0 ? (
              <p className="text-sm text-ink-muted">Nessuna fonte configurata.</p>
            ) : (
              <DataTable
                caption="Stato delle fonti"
                columns={sourceColumns}
                rows={sources}
                rowKey={(source) => source.id}
              />
            )}
          </Card>
        </div>

        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Job recenti</h2>
          {recentJobs.length === 0 ? (
            <p className="text-sm text-ink-muted">Nessun job eseguito.</p>
          ) : (
            <DataTable
              caption="Ultimi job eseguiti"
              columns={jobColumns}
              rows={recentJobs}
              rowKey={(job) => job.id}
            />
          )}
        </Card>
      </div>
    </>
  );
}
