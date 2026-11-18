import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApproveRun, useCancelRun, useStartRun } from "../../hooks/mutations";
import { useRun } from "../../hooks/queries";
import type { RunStatus } from "../../api/types";
import { formatNumber } from "../../lib/format";
import { ErrorState, InlineNotice } from "../ui/feedback";
import { Button, Field, Input } from "../ui/primitives";
import { RunStatusPill } from "../ui/status-pill";
import { Timestamp } from "../ui/time";
import { useToast } from "../ui/toast";

type PendingAction = "approve" | "reject" | "retry";

/**
 * Un run in attesa di approvazione o fallito richiede un'azione esplicita: le
 * conferme restano inline (niente modale) e l'approvazione usa il `plan_hash`
 * letto dal dettaglio, così un piano cambiato nel frattempo viene rifiutato.
 */
export function AttentionRunCard({
  runId,
  status,
  createdAt,
}: {
  runId: string;
  status: RunStatus;
  createdAt: string;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const run = useRun(runId);
  const approve = useApproveRun(runId);
  const cancel = useCancelRun(runId);
  const startRun = useStartRun();
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [note, setNote] = useState("");

  const data = run.data;
  const planHash = data?.plan_hash ?? null;

  const onApprove = () => {
    approve.mutate(
      { plan_hash: planHash ?? "", note: note.trim() || undefined },
      {
        onSuccess: () => {
          setPending(null);
          setNote("");
          toast.notify({ tone: "success", title: "Piano approvato" });
        },
      },
    );
  };

  const onReject = () => {
    cancel.mutate(undefined, {
      onSuccess: () => {
        setPending(null);
        toast.notify({ tone: "info", title: "Piano scartato" });
      },
    });
  };

  const onRetry = () => {
    if (!data) return;
    startRun.mutate(
      { bindingId: data.binding_id, dryRun: false },
      {
        onSuccess: (result) => {
          toast.notify({ tone: "info", title: "Nuovo run avviato" });
          navigate(`/app/runs/${result.run_id}`);
        },
      },
    );
  };

  return (
    <article className="rounded-lg border border-line bg-surface-elevated p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <RunStatusPill status={status} />
          <Link
            to={`/app/runs/${runId}`}
            className="font-mono text-xs text-accent underline"
          >
            {runId.slice(0, 8)}
          </Link>
        </div>
        <Timestamp value={createdAt} className="text-xs text-ink-muted" />
      </div>

      {data ? (
        <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
          <div>
            <dt className="text-ink-faint">Da aggiungere</dt>
            <dd className="font-medium tabular-nums text-ink">
              +{formatNumber(data.to_add_count)}
            </dd>
          </div>
          <div>
            <dt className="text-ink-faint">Da rimuovere</dt>
            <dd className="font-medium tabular-nums text-ink">
              −{formatNumber(data.to_remove_count)}
            </dd>
          </div>
          <div>
            <dt className="text-ink-faint">Soglia</dt>
            <dd className="font-medium text-ink">
              {data.threshold_breached ? "Superata" : "Rispettata"}
            </dd>
          </div>
        </dl>
      ) : run.isError ? (
        <p className="mt-3 text-xs text-ink-muted">
          Dettaglio non disponibile:{" "}
          <Link to={`/app/runs/${runId}`} className="text-accent underline">
            apri il run
          </Link>
          .
        </p>
      ) : (
        <p className="mt-3 text-xs text-ink-faint">Caricamento del piano…</p>
      )}

      {approve.isError ? (
        <div className="mt-3">
          <ErrorState error={approve.error} />
        </div>
      ) : null}
      {cancel.isError ? (
        <div className="mt-3">
          <ErrorState error={cancel.error} />
        </div>
      ) : null}
      {startRun.isError ? (
        <div className="mt-3">
          <ErrorState error={startRun.error} />
        </div>
      ) : null}

      {pending === null ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {status === "AWAITING_APPROVAL" ? (
            <>
              <Button size="sm" onClick={() => setPending("approve")}>
                Approva
              </Button>
              <Button size="sm" variant="danger" onClick={() => setPending("reject")}>
                Scarta
              </Button>
            </>
          ) : null}
          {status === "FAILED" ? (
            <Button
              size="sm"
              onClick={() => setPending("retry")}
              disabled={!data}
              busy={startRun.isPending}
            >
              Riprova
            </Button>
          ) : null}
          <Link
            to={`/app/runs/${runId}`}
            className="inline-flex min-h-9 items-center rounded-md px-3 text-xs font-medium text-ink-muted hover:text-ink"
          >
            Apri dettaglio
          </Link>
        </div>
      ) : null}

      {pending === "approve" ? (
        <div className="mt-3 space-y-3 rounded-md border border-line bg-surface p-3">
          <p className="text-xs text-ink-muted">
            L&apos;approvazione è legata all&apos;hash del piano corrente.
          </p>
          {!planHash ? (
            <InlineNotice tone="warning">
              Piano non ancora disponibile: attendi la fine della pianificazione.
            </InlineNotice>
          ) : null}
          <Field id={`approval-note-${runId}`} label="Nota (facoltativa)">
            <Input
              id={`approval-note-${runId}`}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              busy={approve.isPending}
              disabled={!planHash}
              onClick={onApprove}
            >
              Conferma approvazione
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setPending(null)}>
              Annulla
            </Button>
          </div>
        </div>
      ) : null}

      {pending === "reject" ? (
        <div className="mt-3 space-y-3 rounded-md border border-danger/40 bg-danger-soft p-3">
          <p className="text-xs text-ink">
            Il run verrà annullato: nessuna operazione sarà inviata a MDBList.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="danger" busy={cancel.isPending} onClick={onReject}>
              Conferma scarto
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setPending(null)}>
              Annulla
            </Button>
          </div>
        </div>
      ) : null}

      {pending === "retry" ? (
        <div className="mt-3 space-y-3 rounded-md border border-warning/40 bg-warning-soft p-3">
          <p className="text-xs text-ink">
            Verrà creato un nuovo run con lo stesso binding. Il piano richiederà di nuovo
            approvazione se supera le soglie.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" busy={startRun.isPending} onClick={onRetry}>
              Conferma riprova
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setPending(null)}>
              Annulla
            </Button>
          </div>
        </div>
      ) : null}
    </article>
  );
}
