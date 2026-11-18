import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../api/client";
import {
  useCreateNotificationChannel,
  useDeleteNotificationChannel,
  useTestNotificationChannel,
  useUpdateNotificationChannel,
} from "../api/mutations";
import { useNotificationChannels, useSystemStatus } from "../api/queries";
import type {
  NotificationChannel,
  NotificationKind,
  NotificationTestOut,
} from "../api/types";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  TableSkeleton,
} from "../components/ui/feedback";
import {
  Button,
  Card,
  Checkbox,
  Field,
  Input,
  Select,
} from "../components/ui/primitives";
import { StatusPill } from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import { useToast } from "../components/ui/toast";
import { formatBytes } from "../lib/format";
import { changePasswordSchema, type ChangePasswordValues } from "../lib/validation";
import { IconBell, IconDatabase, IconDownload, IconServer, IconUpload } from "../components/ui/icons";

const NOTIFICATION_EVENTS: { value: string; label: string }[] = [
  { value: "RUN_PENDING_APPROVAL", label: "Run in attesa di approvazione" },
  { value: "RUN_FAILED", label: "Run fallito" },
  { value: "RUN_UNCERTAIN", label: "Operazioni remote incerte" },
  { value: "AUTH_ERROR", label: "Credenziale TMDb/MDBList rifiutata" },
  { value: "SUMMARY", label: "Riepilogo periodico" },
];

function NotificationChannelCard({ channel }: { channel: NotificationChannel }) {
  const toast = useToast();
  const update = useUpdateNotificationChannel(channel.id);
  const remove = useDeleteNotificationChannel();
  const test = useTestNotificationChannel();
  const [result, setResult] = useState<NotificationTestOut | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [name, setName] = useState(channel.name);
  const [events, setEvents] = useState<string[]>(channel.events);
  const [enabled, setEnabled] = useState(channel.enabled);
  const [secret, setSecret] = useState("");

  useEffect(() => {
    setName(channel.name);
    setEvents(channel.events);
    setEnabled(channel.enabled);
  }, [channel]);

  const onSave = () => {
    update.mutate(
      {
        name: name.trim(),
        events,
        enabled,
        ...(secret.trim() ? { secret: secret.trim() } : {}),
      },
      {
        onSuccess: () => {
          setEditing(false);
          setSecret("");
          toast.notify({ tone: "success", title: "Canale aggiornato" });
        },
      },
    );
  };

  return (
    <Card testId={`notification-channel-${channel.id}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold text-ink">
            {channel.name}
            <span className="text-xs font-normal text-ink-muted">({channel.kind})</span>
            <StatusPill
              label={channel.enabled ? "Attivo" : "Disattivato"}
              tone={channel.enabled ? "success" : "neutral"}
            />
          </h3>
          <p className="mt-1 text-sm text-ink-muted">{channel.events.join(", ")}</p>
          <p className="mt-1 text-xs text-ink-muted">
            Segreto:{" "}
            <span className="font-mono text-ink">
              {channel.secret_configured ? channel.masked_hint : "non configurato"}
            </span>
            {channel.last_status ? ` · ultimo invio: ${channel.last_status}` : ""}
            {channel.last_error ? ` · ${channel.last_error}` : ""}
          </p>
          {channel.retry_count != null || channel.next_retry_at ? (
            <p className="mt-1 text-xs text-warning">
              {channel.retry_count != null
                ? `Tentativi di consegna: ${channel.retry_count}`
                : "Consegna in retry"}
              {channel.next_retry_at ? (
                <>
                  {" "}
                  · prossimo tentativo{" "}
                  <Timestamp value={channel.next_retry_at} className="text-xs text-warning" />
                </>
              ) : null}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setEditing((value) => !value)}
            data-testid={`channel-edit-${channel.id}`}
          >
            {editing ? "Chiudi modifica" : "Modifica"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => test.mutate(channel.id, { onSuccess: setResult })}
            busy={test.isPending}
            data-testid={`channel-test-${channel.id}`}
          >
            Invia prova
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              update.mutate(
                { enabled: !channel.enabled },
                {
                  onSuccess: () =>
                    toast.notify({
                      tone: "success",
                      title: channel.enabled ? "Canale disattivato" : "Canale attivato",
                    }),
                },
              )
            }
            busy={update.isPending}
          >
            {channel.enabled ? "Disattiva" : "Attiva"}
          </Button>
          {confirmDelete ? (
            <>
              <Button
                variant="danger"
                size="sm"
                onClick={() =>
                  remove.mutate(channel.id, {
                    onSuccess: () => toast.notify({ tone: "info", title: "Canale eliminato" }),
                  })
                }
                busy={remove.isPending}
              >
                Conferma eliminazione
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                Annulla
              </Button>
            </>
          ) : (
            <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
              Elimina
            </Button>
          )}
        </div>
      </div>

      {test.isError ? <ErrorState error={test.error} /> : null}
      {update.isError ? <ErrorState error={update.error} /> : null}
      {remove.isError ? <ErrorState error={remove.error} /> : null}
      {result ? (
        <div className="mt-3" data-testid={`channel-test-result-${channel.id}`}>
          <InlineNotice tone={result.ok ? "success" : "warning"}>
            {result.message}
            {result.latency_ms != null ? ` · ${result.latency_ms} ms` : ""}
          </InlineNotice>
        </div>
      ) : null}

      {editing ? (
        <form
          className="mt-4 space-y-4 border-t border-line pt-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSave();
          }}
          noValidate
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id={`channel-name-${channel.id}`} label="Nome">
              <Input
                id={`channel-name-${channel.id}`}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <Field
              id={`channel-secret-${channel.id}`}
              label="Sostituisci segreto (facoltativo)"
              hint="Lascia vuoto per mantenere il segreto attuale."
            >
              <Input
                id={`channel-secret-${channel.id}`}
                type="password"
                autoComplete="off"
                value={secret}
                onChange={(event) => setSecret(event.target.value)}
              />
            </Field>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-ink">Eventi</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {NOTIFICATION_EVENTS.map((event) => (
                <Checkbox
                  key={event.value}
                  id={`channel-${channel.id}-event-${event.value}`}
                  label={event.label}
                  checked={events.includes(event.value)}
                  onChange={(changeEvent) =>
                    setEvents((current) =>
                      changeEvent.target.checked
                        ? [...current, event.value]
                        : current.filter((value) => value !== event.value),
                    )
                  }
                />
              ))}
            </div>
          </fieldset>
          <Checkbox
            id={`channel-enabled-${channel.id}`}
            label="Canale attivo"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              size="sm"
              busy={update.isPending}
              data-testid={`channel-save-${channel.id}`}
            >
              Salva canale
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setEditing(false);
                setSecret("");
              }}
            >
              Annulla
            </Button>
          </div>
        </form>
      ) : null}
    </Card>
  );
}

export function NotificationsSection() {
  const toast = useToast();
  const channels = useNotificationChannels();
  const create = useCreateNotificationChannel();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<NotificationKind>("WEBHOOK");
  const [secret, setSecret] = useState("");
  const [chatId, setChatId] = useState("");
  const [events, setEvents] = useState<string[]>(
    NOTIFICATION_EVENTS.map((event) => event.value),
  );

  const onSubmit = async () => {
    try {
      await create.mutateAsync({
        name: name.trim(),
        kind,
        secret,
        events,
        config: kind === "TELEGRAM" ? { chat_id: chatId.trim() } : {},
        enabled: true,
      });
      setName("");
      setSecret("");
      setChatId("");
      setShowForm(false);
      toast.notify({ tone: "success", title: "Canale creato" });
    } catch {
      // L'errore è mostrato dall'ErrorState.
    }
  };

  return (
    <section aria-labelledby="notifications-heading">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="notifications-heading" className="text-lg font-semibold text-ink">
          Canali di notifica
        </h2>
        <Button
          variant="secondary"
          onClick={() => setShowForm((value) => !value)}
          data-testid="notification-new"
        >
          {showForm ? "Chiudi" : "Nuovo canale"}
        </Button>
      </div>
      <p className="mb-4 text-sm text-ink-muted">
        Webhook, Telegram o Discord. Vengono inviati solo gli eventi selezionati; i segreti
        sono cifrati e non vengono mai restituiti dall&apos;API.
      </p>

      {showForm ? (
        <Card className="mb-4">
          <form
            data-testid="notification-form"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              void onSubmit();
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="notification-name" label="Nome">
                <Input
                  id="notification-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field id="notification-kind" label="Tipo">
                <Select
                  id="notification-kind"
                  value={kind}
                  onChange={(event) => setKind(event.target.value as NotificationKind)}
                >
                  <option value="WEBHOOK">Webhook generico</option>
                  <option value="TELEGRAM">Telegram</option>
                  <option value="DISCORD">Discord</option>
                </Select>
              </Field>
              <Field
                id="notification-secret"
                label={kind === "TELEGRAM" ? "Token bot" : "URL webhook"}
                hint="Salvato cifrato; non viene mostrato dopo il salvataggio."
              >
                <Input
                  id="notification-secret"
                  type="password"
                  autoComplete="off"
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                />
              </Field>
              {kind === "TELEGRAM" ? (
                <Field id="notification-chat" label="Chat ID">
                  <Input
                    id="notification-chat"
                    value={chatId}
                    onChange={(event) => setChatId(event.target.value)}
                  />
                </Field>
              ) : null}
            </div>
            <fieldset className="mt-4">
              <legend className="text-sm font-medium text-ink">Eventi</legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {NOTIFICATION_EVENTS.map((event) => (
                  <Checkbox
                    key={event.value}
                    id={`notification-event-${event.value}`}
                    label={event.label}
                    checked={events.includes(event.value)}
                    onChange={(changeEvent) =>
                      setEvents((current) =>
                        changeEvent.target.checked
                          ? [...current, event.value]
                          : current.filter((value) => value !== event.value),
                      )
                    }
                  />
                ))}
              </div>
            </fieldset>
            {create.isError ? <ErrorState error={create.error} /> : null}
            <div className="mt-4">
              <Button type="submit" busy={create.isPending} data-testid="notification-submit">
                Crea canale
              </Button>
            </div>
          </form>
        </Card>
      ) : null}

      {channels.isPending ? <TableSkeleton rows={2} /> : null}
      {channels.isError ? (
        <ErrorState error={channels.error} onRetry={() => void channels.refetch()} />
      ) : null}
      {channels.isSuccess && channels.data.length === 0 ? (
        <EmptyState
          icon={<IconBell />}
          title="Nessun canale di notifica"
          description="Aggiungi un webhook, un bot Telegram o un webhook Discord per ricevere gli avvisi."
        />
      ) : null}
      {channels.isSuccess ? (
        <div className="space-y-4">
          {channels.data.map((channel) => (
            <NotificationChannelCard key={channel.id} channel={channel} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function SystemStatusCard() {
  const status = useSystemStatus();
  const data = status.data;
  const backup = data?.backup ?? null;
  const health = data?.health ?? null;
  const overall =
    data == null
      ? null
      : health == null
        ? (data.status ?? "Sconosciuto")
        : Object.values(health).every((value) => value === true || value === "OK")
          ? "ok"
          : "degraded";

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <IconServer />
            Backup e manutenzione
          </h2>
          <p className="text-sm text-ink-muted">
            Stato di worker, database e ultimo backup letto da{" "}
            <code className="font-mono text-xs">GET /api/system/status</code>.
          </p>
        </div>
        {status.isPending ? (
          <StatusPill label="Verifica…" tone="neutral" />
        ) : data ? (
          <StatusPill
            label={overall ?? "Sconosciuto"}
            tone={
              overall === "ok"
                ? "success"
                : overall === "degraded"
                  ? "warning"
                  : "neutral"
            }
            code={overall ?? undefined}
          />
        ) : (
          <StatusPill label="Sconosciuto" tone="neutral" />
        )}
      </div>

      {status.isError ? (
        <div className="mt-3">
          <ErrorState error={status.error} onRetry={() => void status.refetch()} />
        </div>
      ) : null}

      {!status.isPending && !status.isError && !data ? (
        <div className="mt-3">
          <InlineNotice tone="info">
            Endpoint di stato non disponibile: backup e worker non sono verificabili da
            questa versione del backend.
          </InlineNotice>
        </div>
      ) : null}

      {data ? (
        <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Worker</dt>
            <dd className="mt-1">
              <StatusPill
                label={
                  health?.worker === true
                    ? "ok"
                    : health?.worker === false
                      ? "error"
                      : (data.worker?.status ?? data.celery?.status ?? "Sconosciuto")
                }
                tone={
                  health?.worker === true ||
                  (data.worker?.status ?? data.celery?.status) === "ok"
                    ? "success"
                    : health?.worker === false ||
                        (data.worker?.status ?? data.celery?.status) === "error"
                      ? "danger"
                      : (data.worker?.status ?? data.celery?.status) === "degraded"
                        ? "warning"
                        : "neutral"
                }
              />
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Database</dt>
            <dd className="mt-1 flex items-center gap-2 text-sm text-ink">
              <IconDatabase />
              {health?.database === true
                ? "ok"
                : health?.database === false
                  ? "error"
                  : (data.database?.status ?? "Sconosciuto")}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Ultimo backup</dt>
            <dd className="mt-1 text-sm">
              <Timestamp value={backup?.last_valid_at ?? backup?.last_backup_at} />
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Prossimo backup</dt>
            <dd className="mt-1 text-sm">
              <Timestamp value={backup?.next_backup_at} />
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Dimensione</dt>
            <dd className="mt-1 text-sm tabular-nums text-ink">
              {formatBytes(backup?.size_bytes)}
              {backup?.age_hours != null ? (
                <span className="ml-2 text-xs text-ink-faint">
                  {backup.age_hours.toFixed(1)} h fa
                </span>
              ) : null}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Versione</dt>
            <dd className="mt-1 text-sm text-ink">{data.version ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Ambiente</dt>
            <dd className="mt-1 text-sm text-ink">{data.environment ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-faint">Backup</dt>
            <dd className="mt-1 text-sm text-ink">{backup?.status ?? "—"}</dd>
          </div>
        </dl>
      ) : null}
    </Card>
  );
}

export function ConfigPortabilitySection() {
  const fileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const exportConfig = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const payload = await apiFetch<Record<string, unknown>>("/config/export");
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `mdbup-config-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage("Configurazione esportata senza segreti.");
      toast.notify({ tone: "success", title: "Configurazione esportata" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Esportazione non riuscita.");
    } finally {
      setBusy(false);
    }
  };

  const importConfig = async (file: File) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const parsed = JSON.parse(await file.text()) as Record<string, unknown>;
      const result = await apiFetch<Record<string, number>>("/config/import", {
        method: "POST",
        body: parsed,
      });
      setMessage(
        `Import completato: ${result.providers} provider, ${result.collections} collezioni, ${result.bindings} binding, ${result.settings} impostazioni.`,
      );
      toast.notify({ tone: "success", title: "Configurazione importata" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import non riuscito.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <Card>
      <h2 className="text-lg font-semibold text-ink">Portabilità configurazione</h2>
      <p className="mt-1 text-sm text-ink-muted">
        Esporta/importa provider, mapping, collezioni, binding e pianificazioni in JSON.
        Credenziali e segreti non sono mai inclusi; l&apos;import è un upsert e non cancella
        dati esistenti.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          onClick={exportConfig}
          busy={busy}
          data-testid="export-button"
        >
          <IconDownload />
          Esporta JSON
        </Button>
        <Button variant="secondary" onClick={() => fileRef.current?.click()} busy={busy}>
          <IconUpload />
          Importa JSON
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void importConfig(file);
          }}
        />
      </div>
      {message ? (
        <div className="mt-3">
          <InlineNotice tone="success">{message}</InlineNotice>
        </div>
      ) : null}
      {error ? (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </Card>
  );
}

export function ChangePasswordSection() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await apiFetch<void>("/auth/change-password", {
        method: "POST",
        body: {
          current_password: values.currentPassword,
          new_password: values.newPassword,
        },
      });
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cambio password non riuscito.");
    }
  });

  return (
    <Card>
      <h2 className="text-lg font-semibold text-ink">Cambio password</h2>
      <p className="mt-1 text-sm text-ink-muted">
        Dopo il cambio tutte le sessioni vengono revocate e dovrai accedere di nuovo.
      </p>
      <form onSubmit={onSubmit} noValidate className="mt-4 grid gap-4 sm:grid-cols-3">
        <Field
          id="current-password"
          label="Password attuale"
          error={errors.currentPassword?.message}
        >
          <Input
            id="current-password"
            type="password"
            autoComplete="current-password"
            {...register("currentPassword")}
          />
        </Field>
        <Field id="new-password" label="Nuova password" error={errors.newPassword?.message}>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            {...register("newPassword")}
          />
        </Field>
        <Field
          id="confirm-password"
          label="Conferma nuova password"
          error={errors.confirmPassword?.message}
        >
          <Input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            {...register("confirmPassword")}
          />
        </Field>
        {error ? (
          <p className="text-sm text-danger sm:col-span-3" role="alert">
            {error}
          </p>
        ) : null}
        <div className="sm:col-span-3">
          <Button type="submit" busy={isSubmitting}>
            Cambia password
          </Button>
        </div>
      </form>
    </Card>
  );
}
