import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useStartRun, useUpdateBinding } from "../api/mutations";
import { useBindings } from "../api/queries";
import type { Binding, ScheduleFrequency, SyncMode } from "../api/types";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
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
import { StatusPill } from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import {
  bindingCollectionName,
  bindingScheduleLabel,
  bindingTargetName,
  bindingThresholds,
} from "../lib/collections";
import { formatNumber, formatPercent } from "../lib/format";
import {
  IconArrowRight,
  IconLayers,
  IconLink,
  IconPause,
  IconPlay,
  IconSearch,
} from "../components/ui/icons";
import { useToast } from "../components/ui/toast";

const SCHEDULE_OPTIONS: { value: ScheduleFrequency; label: string }[] = [
  { value: "MANUAL", label: "Manuale" },
  { value: "INTERVAL", label: "Ogni N ore" },
  { value: "CRON", label: "Cron" },
  { value: "DAILY", label: "Giornaliero" },
  { value: "WEEKLY", label: "Settimanale" },
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
      <p className="mt-1 truncate text-xs text-ink-muted">{subtitle}</p>
    </div>
  );
}

function BindingCard({
  binding,
  onDryRun,
  onRun,
  runBusy,
}: {
  binding: Binding;
  onDryRun: (binding: Binding) => void;
  onRun: (binding: Binding) => void;
  runBusy: boolean;
}) {
  const toast = useToast();
  const update = useUpdateBinding(binding.id);
  const [confirmMirror, setConfirmMirror] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const { percent, absolute } = bindingThresholds(binding);

  const patch = (payload: Parameters<typeof update.mutate>[0], message: string) => {
    update.mutate(payload, {
      onSuccess: () => toast.notify({ tone: "success", title: message }),
    });
  };

  const onModeChange = (next: SyncMode) => {
    if (next === "MIRROR" && binding.mode === "APPEND_ONLY") {
      setConfirmMirror(true);
      return;
    }
    patch({ mode: next }, `Modalità aggiornata: ${next}`);
  };

  const onScheduleChange = (next: ScheduleFrequency) => {
    patch(
      {
        schedule: next,
        ...(next === "DAILY" || next === "WEEKLY"
          ? { schedule_time: binding.schedule_time ?? "04:00" }
          : {}),
        ...(next === "INTERVAL"
          ? { schedule_interval_hours: binding.schedule_interval_hours ?? 24 }
          : {}),
        ...(next === "CRON" ? { schedule_cron: binding.schedule_cron || "0 4 * * *" } : {}),
      },
      "Pianificazione aggiornata",
    );
  };

  const lastSnapshot = binding.collection?.last_valid_snapshot ?? null;

  return (
    <article
      data-testid={`binding-card-${binding.id}`}
      className="rounded-xl border border-line bg-surface p-4 shadow-card sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-ink">
            {bindingCollectionName(binding)}
            <span className="mx-2 text-ink-faint">→</span>
            {bindingTargetName(binding)}
          </h2>
          <p className="text-xs text-ink-muted">
            {binding.media_type === "MOVIE" ? "Film" : "Serie"} ·{" "}
            {bindingScheduleLabel(binding)}
            {binding.next_run_at ? (
              <>
                {" "}
                · prossima <Timestamp value={binding.next_run_at} className="text-xs" />
              </>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill
            label={binding.mode}
            tone={binding.mode === "MIRROR" ? "warning" : "info"}
            code={binding.mode}
          />
          <StatusPill
            label={binding.enabled ? "Attivo" : "In pausa"}
            tone={binding.enabled ? "success" : "neutral"}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <PipelineNode
          title="Snapshot"
          subtitle={
            lastSnapshot
              ? `${formatNumber(lastSnapshot.items_count)} elementi · ${lastSnapshot.status}`
              : "Nessuno snapshot valido"
          }
          icon={<IconLayers />}
        />
        <span className="hidden items-center text-ink-faint sm:flex" aria-hidden="true">
          <IconArrowRight />
        </span>
        <PipelineNode
          title="Diff engine"
          subtitle={`${binding.mode} · soglie ${formatPercent(percent)} / ${formatNumber(
            absolute,
          )}`}
          icon={<IconArrowRight />}
        />
        <span className="hidden items-center text-ink-faint sm:flex" aria-hidden="true">
          <IconArrowRight />
        </span>
        <PipelineNode
          title="MDBList"
          subtitle={`${bindingTargetName(binding)}${
            binding.target?.item_count != null
              ? ` · ${formatNumber(binding.target.item_count)} elementi`
              : ""
          }`}
          icon={<IconLink />}
        />
      </div>

      <div className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field id={`mode-${binding.id}`} label="Modalità">
          <Select
            id={`mode-${binding.id}`}
            value={binding.mode}
            disabled={update.isPending}
            onChange={(event) => onModeChange(event.target.value as SyncMode)}
          >
            <option value="MIRROR">MIRROR</option>
            <option value="APPEND_ONLY">APPEND_ONLY</option>
          </Select>
        </Field>
        <Field id={`schedule-${binding.id}`} label="Pianificazione">
          <Select
            id={`schedule-${binding.id}`}
            value={binding.schedule}
            disabled={update.isPending}
            onChange={(event) => onScheduleChange(event.target.value as ScheduleFrequency)}
          >
            {SCHEDULE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex items-end">
          <Button
            variant="secondary"
            size="sm"
            className="w-full"
            busy={update.isPending}
            onClick={() =>
              patch(
                { enabled: !binding.enabled },
                binding.enabled ? "Binding in pausa" : "Binding riattivato",
              )
            }
          >
            {binding.enabled ? <IconPause /> : <IconPlay />}
            {binding.enabled ? "Metti in pausa" : "Riattiva"}
          </Button>
        </div>
        <div className="flex items-end">
          <Link
            to={`/app/bindings/${binding.id}/edit`}
            className="inline-flex min-h-9 w-full items-center justify-center rounded-md border border-line bg-surface px-3 text-xs font-medium text-ink hover:bg-surface-muted"
          >
            Modifica soglie
          </Link>
        </div>
      </div>

      {update.isError ? (
        <div className="mt-3">
          <ErrorState error={update.error} />
        </div>
      ) : null}

      {confirmMirror ? (
        <div className="mt-3 space-y-3 rounded-md border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm text-ink">
            Passare da APPEND_ONLY a MIRROR abilita le rimozioni dalla lista MDBList:
            gli elementi non presenti nella collezione verranno rimossi (entro le soglie).
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="danger"
              busy={update.isPending}
              onClick={() => {
                patch({ mode: "MIRROR" }, "Modalità aggiornata: MIRROR");
                setConfirmMirror(false);
              }}
            >
              Conferma MIRROR
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirmMirror(false)}>
              Annulla
            </Button>
          </div>
        </div>
      ) : null}

      {confirmRun ? (
        <div className="mt-3 space-y-3 rounded-md border border-warning/40 bg-warning-soft p-3">
          <p className="text-sm text-ink">
            Avviare una sync reale? Il piano verrà calcolato e richiederà approvazione se
            supera le soglie.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              busy={runBusy}
              onClick={() => {
                setConfirmRun(false);
                onRun(binding);
              }}
            >
              Conferma esecuzione
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirmRun(false)}>
              Annulla
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="secondary"
          busy={runBusy}
          onClick={() => onDryRun(binding)}
          data-testid={`binding-dry-run-${binding.id}`}
        >
          Dry-run
        </Button>
        <Button size="sm" busy={runBusy} onClick={() => setConfirmRun(true)}>
          Esegui
        </Button>
      </div>
    </article>
  );
}

export default function BindingsPage() {
  const bindings = useBindings();
  const startRun = useStartRun();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "paused">("all");

  const onDryRun = async (binding: Binding) => {
    try {
      const result = await startRun.mutateAsync({ bindingId: binding.id, dryRun: true });
      navigate(`/app/runs/${result.run_id}`);
    } catch {
      // L'errore è mostrato sopra la lista.
    }
  };

  const onRun = async (binding: Binding) => {
    try {
      const result = await startRun.mutateAsync({ bindingId: binding.id, dryRun: false });
      navigate(`/app/runs/${result.run_id}`);
    } catch {
      // L'errore è mostrato sopra la lista.
    }
  };

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (bindings.data ?? []).filter((binding) => {
      if (statusFilter === "active" && !binding.enabled) return false;
      if (statusFilter === "paused" && binding.enabled) return false;
      if (!needle) return true;
      return (
        bindingCollectionName(binding).toLowerCase().includes(needle) ||
        bindingTargetName(binding).toLowerCase().includes(needle)
      );
    });
  }, [bindings.data, query, statusFilter]);

  return (
    <>
      <PageHeader
        eyebrow="Sincronizzazione"
        title="Binding"
        description="Pipeline snapshot → diff engine → lista MDBList, con soglie e pianificazione modificabili inline."
        actions={
          <Link
            to="/app/bindings/new"
            className="inline-flex min-h-11 items-center rounded-md bg-accent px-4 text-sm font-medium text-accent-contrast hover:bg-accent-strong"
          >
            Nuovo binding
          </Link>
        }
      />

      <Card className="mb-6">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <Field id="binding-search" label="Cerca binding">
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
                <IconSearch />
              </span>
              <Input
                id="binding-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Collezione o lista MDBList…"
                className="pl-9"
              />
            </div>
          </Field>
          <div className="flex flex-wrap gap-2">
            <ToggleChip pressed={statusFilter === "all"} onClick={() => setStatusFilter("all")}>
              Tutti
            </ToggleChip>
            <ToggleChip
              pressed={statusFilter === "active"}
              onClick={() => setStatusFilter("active")}
            >
              Attivi
            </ToggleChip>
            <ToggleChip
              pressed={statusFilter === "paused"}
              onClick={() => setStatusFilter("paused")}
            >
              In pausa
            </ToggleChip>
          </div>
        </div>
      </Card>

      {startRun.isError ? (
        <div className="mb-4">
          <ErrorState error={startRun.error} />
        </div>
      ) : null}

      {bindings.isPending ? <TableSkeleton /> : null}

      {bindings.isError ? (
        <ErrorState error={bindings.error} onRetry={() => void bindings.refetch()} />
      ) : null}

      {bindings.isSuccess ? (
        <>
          <StaleBanner updatedAt={bindings.dataUpdatedAt} />
          {bindings.data.length === 0 ? (
            <EmptyState
              icon={<IconLink />}
              title="Nessun binding"
              description="Crea un binding per sincronizzare una collezione con una lista MDBList."
              action={
                <Link
                  to="/app/bindings/new"
                  className="inline-flex min-h-11 items-center rounded-md bg-accent px-4 text-sm font-medium text-accent-contrast hover:bg-accent-strong"
                >
                  Crea il primo binding
                </Link>
              }
            />
          ) : filtered.length === 0 ? (
            <InlineNotice tone="info">
              Nessun binding corrisponde ai filtri selezionati.
            </InlineNotice>
          ) : (
            <div className="space-y-4">
              {filtered.map((binding) => (
                <BindingCard
                  key={binding.id}
                  binding={binding}
                  onDryRun={onDryRun}
                  onRun={onRun}
                  runBusy={
                    startRun.isPending && startRun.variables?.bindingId === binding.id
                  }
                />
              ))}
            </div>
          )}
        </>
      ) : null}
    </>
  );
}
