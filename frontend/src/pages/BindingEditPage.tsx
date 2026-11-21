import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useUpdateBinding } from "../hooks/mutations";
import { useBinding } from "../hooks/queries";
import type { ScheduleFrequency, SyncMode } from "../api/types";
import { ErrorState, InlineNotice, TableSkeleton } from "../components/ui/feedback";
import {
  Button,
  Card,
  Checkbox,
  Field,
  Input,
  PageHeader,
  Select,
} from "../components/ui/primitives";
import { useToast } from "../components/ui/toast";
import { isJustWatchSource, justWatchBindingNotice } from "../lib/justwatch";

const SCHEDULE_OPTIONS: { value: ScheduleFrequency; label: string }[] = [
  { value: "MANUAL", label: "Manuale" },
  { value: "INTERVAL", label: "Ogni N ore" },
  { value: "CRON", label: "Espressione cron" },
  { value: "DAILY", label: "Giornaliero" },
  { value: "WEEKLY", label: "Settimanale" },
];

export default function BindingEditPage() {
  const { bindingId } = useParams<{ bindingId: string }>();
  const binding = useBinding(bindingId);
  const update = useUpdateBinding(bindingId ?? "");
  const navigate = useNavigate();
  const toast = useToast();

  const [mode, setMode] = useState<SyncMode>("MIRROR");
  const [schedule, setSchedule] = useState<ScheduleFrequency>("MANUAL");
  const [scheduleTime, setScheduleTime] = useState("04:00");
  const [intervalHours, setIntervalHours] = useState("24");
  const [cron, setCron] = useState("0 4 * * *");
  const [maxRemoveCount, setMaxRemoveCount] = useState("50");
  const [maxRemovePercent, setMaxRemovePercent] = useState("10");
  const [enabled, setEnabled] = useState(true);
  const [targetPrivate, setTargetPrivate] = useState(false);
  const [policyVersion, setPolicyVersion] = useState("planning-v1");
  const [policyAccepted, setPolicyAccepted] = useState(true);
  const [mirrorConfirmed, setMirrorConfirmed] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    const data = binding.data;
    if (!data) return;
    setMode(data.mode);
    setSchedule(data.schedule);
    setScheduleTime(data.schedule_time ?? "04:00");
    setIntervalHours(String(data.schedule_interval_hours ?? 24));
    setCron(data.schedule_cron || "0 4 * * *");
    setMaxRemoveCount(String(data.max_remove_count ?? data.max_removal_abs));
    setMaxRemovePercent(String(data.max_remove_percent ?? data.max_removal_pct));
    setEnabled(data.enabled);
    setTargetPrivate(Boolean(data.target?.private));
    setPolicyVersion(data.policy_version ?? "planning-v1");
    setPolicyAccepted(Boolean(data.policy_accepted_at));
  }, [binding.data]);

  if (binding.isPending) {
    return (
      <>
        <PageHeader title="Modifica binding" />
        <TableSkeleton rows={4} />
      </>
    );
  }

  if (binding.isError) {
    return (
      <>
        <PageHeader title="Modifica binding" />
        <ErrorState error={binding.error} onRetry={() => void binding.refetch()} />
      </>
    );
  }

  const data = binding.data;
  if (!data) return null;

  const isJustWatch = isJustWatchSource(data.collection?.source_key);
  const switchingToMirror = data.mode === "APPEND_ONLY" && mode === "MIRROR";

  const onSave = () => {
    setFormError(null);
    const count = Number(maxRemoveCount);
    const percent = Number(maxRemovePercent);
    if (!Number.isFinite(count) || count < 0) {
      setFormError("Il numero massimo di rimozioni deve essere un intero non negativo.");
      return;
    }
    if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
      setFormError("La percentuale massima di rimozioni deve essere tra 0 e 100.");
      return;
    }
    if (mode === "MIRROR" && count === 0 && percent === 0) {
      setFormError("MIRROR richiede almeno una soglia di rimozione positiva.");
      return;
    }
    if (switchingToMirror && !mirrorConfirmed) {
      setFormError(
        "Conferma il passaggio da APPEND_ONLY a MIRROR: da quel momento il sync può rimuovere elementi.",
      );
      return;
    }
    if (enabled && !policyAccepted) {
      setFormError("Accetta la policy prima di abilitare il binding.");
      return;
    }
    if (enabled && !data.enabled) {
      setFormError(
        "L'abilitazione richiede un dry-run completato con successo: usa la pagina Binding per il dry-run.",
      );
      return;
    }
    if (schedule === "INTERVAL") {
      const hours = Number(intervalHours);
      if (!Number.isFinite(hours) || hours < 1 || hours > 720) {
        setFormError("L'intervallo deve essere tra 1 e 720 ore.");
        return;
      }
    }
    if (schedule === "CRON" && !cron.trim()) {
      setFormError("Inserisci un'espressione cron.");
      return;
    }
    const targetPrivateChanged = targetPrivate !== Boolean(data.target?.private);
    const payload = {
      mode,
      schedule,
      enabled,
      target_private: targetPrivateChanged ? targetPrivate : undefined,
      max_remove_count: count,
      max_remove_percent: percent,
      policy_version: policyAccepted ? policyVersion : undefined,
      ...(schedule === "INTERVAL"
        ? { schedule_interval_hours: Number(intervalHours) }
        : {}),
      ...(schedule === "CRON" ? { schedule_cron: cron.trim() } : {}),
      ...(schedule === "DAILY" || schedule === "WEEKLY"
        ? { schedule_time: scheduleTime }
        : {}),
    };
    update.mutate(payload, {
      onSuccess: () => {
        toast.notify({ tone: "success", title: "Binding aggiornato" });
        navigate("/app/bindings");
      },
    });
  };

  return (
    <>
      <PageHeader
        eyebrow="Binding"
        title="Modifica binding"
        description={`${data.collection?.name ?? data.collection_id.slice(0, 8)} → ${
          data.target?.name ?? data.target_id.slice(0, 8)
        }`}
        actions={
          <Link
            to="/app/bindings"
            className="inline-flex min-h-11 items-center rounded-md border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-muted"
          >
            Annulla
          </Link>
        }
      />

      {update.isError ? (
        <div className="mb-4">
          <ErrorState error={update.error} />
        </div>
      ) : null}
      {formError ? (
        <div className="mb-4">
          <InlineNotice tone="danger">{formError}</InlineNotice>
        </div>
      ) : null}

      <div className="mb-4">
        <InlineNotice tone="warning">
          Il binding resta in pausa finché non esegui un dry-run con successo. Un run reale
          senza dry-run risponde DRY_RUN_REQUIRED.
          {isJustWatch ? ` ${justWatchBindingNotice()}` : ""}
        </InlineNotice>
      </div>

      <Card>
        <div className="grid gap-6 lg:grid-cols-2">
          <Field id="binding-mode" label="Modalità di sincronizzazione">
            <Select
              id="binding-mode"
              value={mode}
              onChange={(event) => {
                setMode(event.target.value as SyncMode);
                setMirrorConfirmed(false);
              }}
            >
              <option value="MIRROR">MIRROR — rispecchia la collezione</option>
              <option value="APPEND_ONLY">APPEND_ONLY — solo aggiunte</option>
            </Select>
          </Field>

          <Field id="binding-schedule" label="Pianificazione">
            <Select
              id="binding-schedule"
              value={schedule}
              onChange={(event) => setSchedule(event.target.value as ScheduleFrequency)}
            >
              {SCHEDULE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          {schedule === "INTERVAL" ? (
            <Field
              id="binding-interval"
              label="Intervallo (ore)"
              hint="La prossima esecuzione parte dopo questo intervallo."
            >
              <Input
                id="binding-interval"
                type="number"
                min={1}
                max={720}
                value={intervalHours}
                onChange={(event) => setIntervalHours(event.target.value)}
              />
            </Field>
          ) : null}

          {schedule === "CRON" ? (
            <Field
              id="binding-cron"
              label="Espressione cron"
              hint="Formato a 5 campi, es. 0 4 * * * (ogni giorno alle 04:00)."
            >
              <Input
                id="binding-cron"
                value={cron}
                onChange={(event) => setCron(event.target.value)}
              />
            </Field>
          ) : null}

          {schedule === "DAILY" || schedule === "WEEKLY" ? (
            <Field id="binding-time" label="Ora di esecuzione">
              <Input
                id="binding-time"
                type="time"
                value={scheduleTime}
                onChange={(event) => setScheduleTime(event.target.value)}
              />
            </Field>
          ) : null}

          <Field
            id="binding-max-count"
            label="Max rimozioni (numero)"
            hint="Blocca il piano se MIRROR deve rimuovere più di questo numero."
          >
            <Input
              id="binding-max-count"
              type="number"
              min={0}
              max={100000}
              value={maxRemoveCount}
              onChange={(event) => setMaxRemoveCount(event.target.value)}
            />
          </Field>

          <Field
            id="binding-max-percent"
            label="Max rimozioni (%)"
            hint="Percentuale calcolata sugli elementi remoti attuali."
          >
            <Input
              id="binding-max-percent"
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={maxRemovePercent}
              onChange={(event) => setMaxRemovePercent(event.target.value)}
            />
          </Field>

          <Field id="binding-policy-version" label="Policy version">
            <Input
              id="binding-policy-version"
              value={policyVersion}
              onChange={(event) => setPolicyVersion(event.target.value)}
            />
          </Field>
        </div>

        {switchingToMirror ? (
          <div className="mt-6 rounded-md border border-danger/40 bg-danger-soft p-4">
            <p className="text-sm font-medium text-ink">
              Passaggio da APPEND_ONLY a MIRROR
            </p>
            <p className="mt-1 text-sm text-ink">
              MIRROR rimuove dalla lista MDBList gli elementi non presenti nella collezione,
              entro le soglie configurate. L&apos;operazione è tracciata nel run.
            </p>
            <div className="mt-3">
              <Checkbox
                id="binding-mirror-confirm"
                label="Confermo il passaggio a MIRROR e l'abilitazione delle rimozioni."
                checked={mirrorConfirmed}
                onChange={(event) => setMirrorConfirmed(event.target.checked)}
              />
            </div>
          </div>
        ) : null}

        <div className="mt-6 space-y-4 border-t border-line pt-4">
          <Checkbox
            id="binding-enabled"
            label="Binding attivo (richiede un dry-run completato)"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <Checkbox
            id="binding-policy"
            label="Policy accettata (necessaria per abilitare)"
            checked={policyAccepted}
            onChange={(event) => setPolicyAccepted(event.target.checked)}
          />
          <Checkbox
            id="binding-private"
            label="Lista MDBList privata"
            checked={targetPrivate}
            onChange={(event) => setTargetPrivate(event.target.checked)}
          />
          <p className="text-xs text-ink-muted">
            La modifica della visibilità usa l&apos;endpoint MDBList{" "}
            <code className="font-mono">PUT /lists/{"{id}"}</code> e non tocca gli elementi
            della lista.
          </p>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button onClick={onSave} busy={update.isPending}>
            Salva modifiche
          </Button>
          <Button variant="secondary" onClick={() => navigate("/app/bindings")}>
            Annulla
          </Button>
        </div>
      </Card>
    </>
  );
}
