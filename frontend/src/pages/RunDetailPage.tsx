import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useApproveRun, useCancelRun } from "../api/mutations";
import { isActiveRun, useRun, useRunOperations } from "../api/queries";
import type { Operation, OperationStatus } from "../api/types";
import { DataTable, type Column } from "../components/ui/data-table";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  TableSkeleton,
} from "../components/ui/feedback";
import {
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  Textarea,
  ToggleChip,
} from "../components/ui/primitives";
import { OperationStatusPill, RunStatusPill } from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import { useToast } from "../components/ui/toast";
import { formatDuration, formatNumber, formatPercent } from "../lib/format";
import { filterSamples, removalUsage, runSummary } from "../lib/run-summary";
import {
  IconArrowRight,
  IconLayers,
  IconLink,
  IconSearch,
} from "../components/ui/icons";

const operationStatuses: OperationStatus[] = [
  "PENDING",
  "IN_FLIGHT",
  "SUCCEEDED",
  "FAILED",
  "UNCERTAIN",
  "SKIPPED",
];

const operationColumns: Column<Operation>[] = [
  { key: "action", header: "Azione", render: (operation) => operation.action },
  {
    key: "media",
    header: "Titolo",
    render: (operation) =>
      operation.media?.title
        ? `${operation.media.title}${operation.media.year ? ` (${operation.media.year})` : ""}`
        : (operation.media_id ?? "—"),
  },
  {
    key: "status",
    header: "Stato",
    render: (operation) => <OperationStatusPill status={operation.status} />,
  },
  {
    key: "attempt",
    header: "Tentativi",
    render: (operation) => (
      <span className="tabular-nums">{operation.attempt}</span>
    ),
  },
  {
    key: "updated",
    header: "Aggiornato",
    render: (operation) => <Timestamp value={operation.updated_at} className="text-xs" />,
  },
];

function PipelineNode({
  title,
  subtitle,
  icon,
}: {
  title: string;
  subtitle: string;
  icon: ReactNode;
}) {
  return (
    <div className="min-w-0 flex-1 rounded-lg border border-line bg-surface-elevated p-3">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-ink">
        <span className="text-accent">{icon}</span>
        {title}
      </p>
      <p className="mt-1 text-xs text-ink-muted">{subtitle}</p>
    </div>
  );
}

function ThresholdMeter({
  label,
  value,
  max,
  fill,
  breach,
  suffix,
  testId,
}: {
  label: string;
  value: string;
  max: string;
  fill: number;
  breach: boolean;
  suffix?: string;
  testId: string;
}) {
  return (
    <div data-testid={testId}>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium text-ink">{label}</span>
        <span className="tabular-nums text-ink-muted">
          <span className={breach ? "text-danger" : "text-ink"}>{value}</span> / {max}
          {suffix}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={fill}
        className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-muted"
      >
        <progress
          className={breach ? "meter meter-danger" : "meter"}
          value={fill}
          max={100}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

function SampleInspector({
  toAdd,
  toRemove,
}: {
  toAdd: string[];
  toRemove: string[];
}) {
  const [tab, setTab] = useState<"add" | "remove">("remove");
  const [query, setQuery] = useState("");
  const samples = tab === "add" ? toAdd : toRemove;
  const filtered = filterSamples(samples, query);

  return (
    <div className="mt-5 border-t border-line pt-4" data-testid="run-sample">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Campione del piano</h3>
        <div className="flex gap-2">
          <ToggleChip
            pressed={tab === "remove"}
            onClick={() => setTab("remove")}
            testId="run-sample-tab-remove"
          >
            Rimozioni ({formatNumber(toRemove.length)})
          </ToggleChip>
          <ToggleChip
            pressed={tab === "add"}
            onClick={() => setTab("add")}
            testId="run-sample-tab-add"
          >
            Aggiunte ({formatNumber(toAdd.length)})
          </ToggleChip>
        </div>
      </div>

      <div className="relative mt-3">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
          <IconSearch />
        </span>
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Cerca nel campione…"
          aria-label="Cerca nel campione del piano"
          className="pl-9"
        />
      </div>

      {samples.length === 0 ? (
        <p className="mt-3 text-xs text-ink-muted">
          Nessun elemento in questo gruppo per il piano corrente.
        </p>
      ) : filtered.length === 0 ? (
        <p className="mt-3 text-xs text-ink-muted">
          Nessun risultato per “{query}” nel campione.
        </p>
      ) : (
        <ul
          className="mt-3 max-h-56 space-y-1 overflow-y-auto pr-1"
          data-testid="run-sample-list"
        >
          {filtered.map((sample) => (
            <li
              key={sample}
              data-testid="run-sample-item"
              className="rounded border border-line bg-surface px-2 py-1 font-mono text-xs text-ink"
            >
              {sample}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-ink-faint">
        Il campione mostra i primi elementi del piano; i conteggi sopra sono completi.
      </p>
    </div>
  );
}

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const run = useRun(runId);
  const runIsActive = run.data ? isActiveRun(run.data.status) : false;
  const operations = useRunOperations(runId, runIsActive);
  const approve = useApproveRun(runId ?? "");
  const cancel = useCancelRun(runId ?? "");
  const toast = useToast();
  const [statusFilter, setStatusFilter] = useState("");
  const [confirmingApproval, setConfirmingApproval] = useState(false);
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [approvalNote, setApprovalNote] = useState("");

  if (run.isPending) {
    return (
      <>
        <PageHeader title="Dettaglio sync" />
        <TableSkeleton rows={5} />
      </>
    );
  }

  if (run.isError) {
    return (
      <>
        <PageHeader title="Dettaglio sync" />
        <ErrorState error={run.error} onRetry={() => void run.refetch()} />
      </>
    );
  }

  const data = run.data;
  const counters = data.counters;
  const active = isActiveRun(data.status);
  const summary = runSummary(data);
  const usage = removalUsage(summary.thresholds);
  const rows = (operations.data ?? []).filter(
    (operation) => !statusFilter || operation.status === statusFilter,
  );

  const onApprove = () => {
    approve.mutate(
      {
        plan_hash: data.plan_hash ?? "",
        note: approvalNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setConfirmingApproval(false);
          toast.notify({ tone: "success", title: "Piano approvato" });
        },
      },
    );
  };

  const onReject = () => {
    cancel.mutate(undefined, {
      onSuccess: () => {
        setConfirmingReject(false);
        toast.notify({ tone: "info", title: "Piano scartato" });
      },
    });
  };

  return (
    <>
      <PageHeader
        eyebrow="Run"
        title={`Sync ${data.id.slice(0, 8)}`}
        description={`Binding ${data.binding_id.slice(0, 8)}`}
        meta={
          <>
            <RunStatusPill status={data.status} />
            <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
              avviato <Timestamp value={data.started_at} className="text-xs" />
            </span>
            <span className="inline-flex items-center rounded-full border border-line bg-surface-muted px-2.5 py-0.5 text-xs text-ink-muted">
              {data.mode}
            </span>
            {data.is_dry_run ? (
              <span className="inline-flex items-center rounded-full border border-warning/40 bg-warning-soft px-2.5 py-0.5 text-xs text-warning">
                Dry-run
              </span>
            ) : null}
          </>
        }
        actions={
          <>
            {data.status === "AWAITING_APPROVAL" ? (
              <>
                <Button onClick={() => setConfirmingApproval(true)}>Approva piano</Button>
                <Button
                  variant="danger"
                  onClick={() => setConfirmingReject(true)}
                  busy={cancel.isPending}
                >
                  Scarta piano
                </Button>
              </>
            ) : null}
            {active && data.status !== "AWAITING_APPROVAL" ? (
              <Button variant="danger" onClick={() => cancel.mutate()} busy={cancel.isPending}>
                Annulla
              </Button>
            ) : null}
          </>
        }
      />

      <div
        aria-live="polite"
        aria-busy={run.isFetching}
        className="mb-4 text-sm text-ink-muted"
      >
        {active
          ? "Aggiornamento automatico ogni 2 secondi finché il sync è in corso."
          : "Sync concluso: aggiornamento automatico disattivato."}
      </div>

      {approve.isError ? (
        <div className="mb-4">
          <ErrorState error={approve.error} />
        </div>
      ) : null}
      {cancel.isError ? (
        <div className="mb-4">
          <ErrorState error={cancel.error} />
        </div>
      ) : null}
      {approve.isSuccess ? (
        <div className="mb-4">
          <InlineNotice tone="success">
            Approvazione inviata: il piano verrà applicato a breve.
          </InlineNotice>
        </div>
      ) : null}
      {cancel.isSuccess ? (
        <div className="mb-4">
          <InlineNotice tone="info">
            Piano scartato: il run è stato annullato senza scritture remote.
          </InlineNotice>
        </div>
      ) : null}

      {confirmingApproval ? (
        <Card className="mb-6">
          <h2 className="text-lg font-semibold text-ink">Conferma approvazione</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Il piano verrà applicato alla lista MDBList. L&apos;approvazione è legata
            all&apos;hash del piano corrente: se il piano cambia, la richiesta viene
            rifiutata.
          </p>
          <div className="mt-4 max-w-md">
            <Field id="approval-note" label="Nota (facoltativa)">
              <Textarea
                id="approval-note"
                value={approvalNote}
                onChange={(event) => setApprovalNote(event.target.value)}
                rows={2}
              />
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              busy={approve.isPending}
              onClick={onApprove}
              disabled={!data.plan_hash}
            >
              Conferma approvazione
            </Button>
            <Button variant="secondary" onClick={() => setConfirmingApproval(false)}>
              Annulla
            </Button>
          </div>
          {!data.plan_hash ? (
            <p className="mt-2 text-sm text-danger">
              Il piano non è ancora disponibile: attendi che il sync completi la
              pianificazione.
            </p>
          ) : null}
        </Card>
      ) : null}

      {confirmingReject ? (
        <Card className="mb-6">
          <h2 className="text-lg font-semibold text-ink">Scarta il piano</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Il run verrà annullato e nessuna operazione verrà inviata a MDBList. Il piano
            resta nella cronologia come annullato.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="danger" busy={cancel.isPending} onClick={onReject}>
              Conferma scarto
            </Button>
            <Button variant="secondary" onClick={() => setConfirmingReject(false)}>
              Annulla
            </Button>
          </div>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Pipeline</h2>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
            <PipelineNode
              title="Snapshot"
              subtitle={`${formatNumber(data.source_item_count)} elementi · ${
                data.snapshot_id.slice(0, 8)
              }`}
              icon={<IconLayers />}
            />
            <span className="hidden items-center text-ink-faint sm:flex" aria-hidden="true">
              <IconArrowRight />
            </span>
            <PipelineNode
              title="Diff engine"
              subtitle={`+${formatNumber(data.to_add_count)} / −${formatNumber(
                data.to_remove_count,
              )} · ${data.mode}`}
              icon={<IconArrowRight />}
            />
            <span className="hidden items-center text-ink-faint sm:flex" aria-hidden="true">
              <IconArrowRight />
            </span>
            <PipelineNode
              title="MDBList"
              subtitle={`${formatNumber(data.remote_item_count)} elementi remoti · ${
                data.target_id.slice(0, 8)
              }`}
              icon={<IconLink />}
            />
          </div>
        </Card>

        <Card testId="run-diff">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-ink">Soglie di rimozione</h2>
              <p className="text-sm text-ink-muted">
                Confronto tra rimozioni previste e massimo consentito dal binding.
              </p>
            </div>
            {usage.breached ? (
              <span className="rounded-full border border-danger/40 bg-danger-soft px-2.5 py-0.5 text-xs font-medium text-danger">
                Soglia superata
              </span>
            ) : (
              <span className="rounded-full border border-success/40 bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success">
                Entro le soglie
              </span>
            )}
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <ThresholdMeter
              testId="run-threshold-absolute"
              label="Rimozioni assolute"
              value={formatNumber(usage.observed)}
              max={formatNumber(usage.maxAbsolute)}
              fill={usage.absoluteFill}
              breach={usage.overAbsolute}
            />
            <ThresholdMeter
              testId="run-threshold-percent"
              label="Rimozioni percentuali"
              value={formatPercent(usage.observedPercent)}
              max={formatPercent(usage.maxPercent)}
              fill={usage.percentFill}
              breach={usage.overPercent}
            />
          </div>

          {usage.maxAbsolute === 0 && usage.maxPercent === 0 ? (
            <div className="mt-3">
              <InlineNotice tone="info">
                Soglie non presenti nel piano: il run non espone il massimo di rimozioni
                consentito.
              </InlineNotice>
            </div>
          ) : null}

          {usage.breached && (summary.thresholds?.reasons ?? []).length > 0 ? (
            <div className="mt-3">
              <InlineNotice tone="warning">
                Motivi: {(summary.thresholds?.reasons ?? []).join(", ")}
              </InlineNotice>
            </div>
          ) : null}

          <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Da aggiungere</dt>
              <dd
                className="text-lg font-semibold tabular-nums text-success"
                data-testid="run-count-add"
              >
                +{formatNumber(data.to_add_count)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Da rimuovere</dt>
              <dd
                className="text-lg font-semibold tabular-nums text-danger"
                data-testid="run-count-remove"
              >
                −{formatNumber(data.to_remove_count)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Invariati</dt>
              <dd className="text-lg font-semibold tabular-nums text-ink">
                {formatNumber(summary.unchanged_count ?? 0)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Non risolti</dt>
              <dd className="text-lg font-semibold tabular-nums text-warning">
                {formatNumber(summary.unresolved_count ?? 0)}
              </dd>
            </div>
          </dl>

          <SampleInspector
            toAdd={summary.to_add_sample ?? []}
            toRemove={summary.to_remove_sample ?? []}
          />
        </Card>

        <Card>
          <h2 className="mb-3 text-lg font-semibold text-ink">Riepilogo</h2>
          <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Stato</dt>
              <dd className="mt-1">
                <RunStatusPill status={data.status} />
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Durata</dt>
              <dd className="mt-1 text-sm tabular-nums text-ink">
                {formatDuration(data.started_at, data.finished_at)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Pianificate</dt>
              <dd className="mt-1 text-sm tabular-nums text-ink">
                {formatNumber(counters.planned ?? 0)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Applicate</dt>
              <dd className="mt-1 text-sm tabular-nums text-ink">
                {formatNumber(counters.applied ?? 0)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Saltate</dt>
              <dd className="mt-1 text-sm tabular-nums text-ink">
                {formatNumber(counters.skipped ?? 0)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Non trovate</dt>
              <dd className="mt-1 text-sm tabular-nums text-ink">
                {formatNumber(counters.not_found ?? 0)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Fallite</dt>
              <dd className="mt-1 text-sm tabular-nums text-danger">
                {formatNumber(counters.failed ?? 0)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-faint">Incerte</dt>
              <dd className="mt-1 text-sm tabular-nums text-warning">
                {formatNumber(counters.uncertain ?? 0)}
              </dd>
            </div>
          </dl>

          <div className="mt-4 space-y-2 text-sm text-ink-muted">
            <p>
              Ordine applicato:{" "}
              <strong className="text-ink">
                {data.order_enforced ? "sì" : "non confermato"}
              </strong>
            </p>
            {data.reconcile_required ? (
              <InlineNotice tone="warning">
                Riconciliazione richiesta: rileggi la lista prima di un nuovo sync.
              </InlineNotice>
            ) : null}
            {(data.warnings ?? []).length > 0 ? (
              <InlineNotice tone="warning">
                Avvisi: {(data.warnings ?? []).join(", ")}
              </InlineNotice>
            ) : null}
            {data.status === "PARTIAL" ? (
              <InlineNotice tone="warning">
                Sync parziale: alcune operazioni non sono state confermate. Controlla le
                operazioni incerte prima di riprendere.
              </InlineNotice>
            ) : null}
            {data.error_message || data.error_code ? (
              <details className="rounded-md border border-line bg-surface p-3">
                <summary className="cursor-pointer text-sm font-medium text-ink">
                  Dettaglio tecnico
                </summary>
                <p className="mt-2 text-xs text-ink-muted">
                  {data.error_code ? `${data.error_code}: ` : ""}
                  {data.error_message ?? "—"}
                </p>
              </details>
            ) : null}
          </div>
        </Card>

        <Card>
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <h2 className="text-lg font-semibold text-ink">Operazioni</h2>
            <div className="w-full sm:w-56">
              <Field id="operation-status" label="Filtra per stato">
                <Select
                  id="operation-status"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                >
                  <option value="">Tutte</option>
                  {operationStatuses.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>

          {operations.isPending ? <TableSkeleton rows={4} /> : null}
          {operations.isError ? (
            <ErrorState error={operations.error} onRetry={() => void operations.refetch()} />
          ) : null}
          {operations.isSuccess && rows.length === 0 ? (
            <EmptyState
              title="Nessuna operazione"
              description="Nessuna operazione corrisponde al filtro selezionato."
            />
          ) : null}
          {operations.isSuccess && rows.length > 0 ? (
            <DataTable
              caption="Operazioni del sync"
              columns={operationColumns}
              rows={rows}
              rowKey={(operation) => operation.id}
            />
          ) : null}
        </Card>
      </div>

      <p className="mt-6 text-sm text-ink-muted">
        <Link to="/app/bindings" className="font-medium text-accent underline">
          Torna ai binding
        </Link>
      </p>
    </>
  );
}
