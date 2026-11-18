import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useProviders, useRuns } from "../api/queries";
import type { Run, RunStatus } from "../api/types";
import { DataTable, type Column } from "../components/ui/data-table";
import {
  EmptyState,
  ErrorState,
  StaleBanner,
  TableSkeleton,
} from "../components/ui/feedback";
import { Card, Field, PageHeader, Select } from "../components/ui/primitives";
import { RunStatusPill } from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import { formatNumber } from "../lib/format";
import { RUN_STATUS_LABELS } from "../lib/status";

const columns: Column<Run>[] = [
  {
    key: "id",
    header: "Run",
    render: (run) => (
      <Link to={`/app/runs/${run.id}`} className="font-mono text-xs text-accent underline">
        {run.id.slice(0, 8)}
      </Link>
    ),
  },
  { key: "provider", header: "Provider", render: (run) => run.provider_name ?? "—" },
  { key: "collection", header: "Collezione", render: (run) => run.collection_name ?? "—" },
  { key: "target", header: "Lista", render: (run) => run.target_name ?? "—" },
  {
    key: "status",
    header: "Stato",
    render: (run) => <RunStatusPill status={run.status} />,
  },
  { key: "mode", header: "Modo", render: (run) => run.mode },
  {
    key: "dry",
    header: "Dry-run",
    render: (run) => (
      <span className={run.is_dry_run ? "text-warning" : "text-ink-muted"}>
        {run.is_dry_run ? "Sì" : "No"}
      </span>
    ),
  },
  {
    key: "to_add",
    header: "Da aggiungere",
    render: (run) => <span className="tabular-nums">+{formatNumber(run.to_add_count)}</span>,
  },
  {
    key: "to_remove",
    header: "Da rimuovere",
    render: (run) => (
      <span className="tabular-nums">−{formatNumber(run.to_remove_count)}</span>
    ),
  },
  {
    key: "created",
    header: "Creato",
    render: (run) => <Timestamp value={run.created_at} className="text-xs" />,
  },
];

const STATUSES: RunStatus[] = [
  "PENDING",
  "PREFLIGHT",
  "PLANNING",
  "AWAITING_APPROVAL",
  "APPLYING",
  "VERIFYING",
  "SUCCEEDED",
  "PARTIAL",
  "FAILED",
  "BLOCKED",
  "CANCELLED",
];

export default function RunsPage() {
  const [searchParams] = useSearchParams();
  const statusParam = searchParams.get("status") ?? "";
  const [providerId, setProviderId] = useState("");
  const [status, setStatus] = useState(statusParam);
  const [mediaType, setMediaType] = useState("");
  useEffect(() => {
    setStatus(statusParam);
  }, [statusParam]);
  const providers = useProviders("IT");
  const runs = useRuns({ providerId, status, mediaType });

  return (
    <>
      <PageHeader
        eyebrow="Cronologia"
        title="Run di sincronizzazione"
        description="Ogni run mostra il piano, le soglie e le operazioni applicate alla lista MDBList."
      />

      <Card className="mb-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field id="run-provider" label="Provider">
            <Select
              id="run-provider"
              value={providerId}
              onChange={(event) => setProviderId(event.target.value)}
            >
              <option value="">Tutti</option>
              {(providers.data ?? []).map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="run-status" label="Stato">
            <Select
              id="run-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">Tutti</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {RUN_STATUS_LABELS[value]}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="run-media" label="Tipo media">
            <Select
              id="run-media"
              value={mediaType}
              onChange={(event) => setMediaType(event.target.value)}
            >
              <option value="">Tutti</option>
              <option value="MOVIE">Film</option>
              <option value="SHOW">Serie TV</option>
            </Select>
          </Field>
        </div>
      </Card>

      {runs.isPending ? <TableSkeleton /> : null}
      {runs.isError ? (
        <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
      ) : null}
      {runs.isSuccess ? (
        <>
          <StaleBanner updatedAt={runs.dataUpdatedAt} />
          {runs.data.items.length === 0 ? (
            <EmptyState
              title="Nessun run"
              description="Modifica i filtri o avvia una sync da un binding."
            />
          ) : (
            <Card>
              <DataTable
                caption="Cronologia dei run di sincronizzazione"
                columns={columns}
                rows={runs.data.items}
                rowKey={(run) => run.id}
              />
            </Card>
          )}
        </>
      ) : null}
    </>
  );
}
