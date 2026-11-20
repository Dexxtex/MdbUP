import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import {
  useDeleteCredential,
  useHealthcheckSource,
  useSaveCredential,
  useUpdateSettings,
  useVerifyCredential,
} from "../hooks/mutations";
import { useCredentials, useSettings, useSources } from "../hooks/queries";
import type {
  AppSettings,
  Credential,
  CredentialKind,
  CredentialStatus,
  CredentialVerifyOut,
  DefaultSource,
} from "../api/types";
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
  Checkbox,
  Field,
  Input,
  PageHeader,
  ToggleChip,
} from "../components/ui/primitives";
import { StatusPill } from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import { useToast } from "../components/ui/toast";
import { cn } from "../lib/cn";
import { resolveDefaultSource } from "../lib/collection-builder";
import {
  ChangePasswordSection,
  ConfigPortabilitySection,
  NotificationsSection,
  SystemStatusCard,
} from "./SettingsSections";
import {
  credentialSchema,
  settingsSchema,
  type CredentialValues,
  type SettingsValues,
} from "../lib/validation";
import {
  IconBell,
  IconDatabase,
  IconDownload,
  IconLink,
  IconShield,
} from "../components/ui/icons";
import { JustWatchConnectorCard } from "../components/justwatch/connector-card";

type SettingsTab = "credentials" | "connectors" | "notifications" | "maintenance" | "portability";

const TABS: { id: SettingsTab; label: string; icon: ReactNode }[] = [
  { id: "credentials", label: "Credenziali & Sicurezza", icon: <IconShield /> },
  { id: "connectors", label: "Connettori", icon: <IconLink /> },
  { id: "notifications", label: "Notifiche & Retry", icon: <IconBell /> },
  { id: "maintenance", label: "Backup & Manutenzione", icon: <IconDatabase /> },
  { id: "portability", label: "Portabilità JSON", icon: <IconDownload /> },
];

function isSettingsTab(value: string | null): value is SettingsTab {
  return (
    value === "credentials" ||
    value === "connectors" ||
    value === "notifications" ||
    value === "maintenance" ||
    value === "portability"
  );
}

interface CredentialKindConfig {
  kind: CredentialKind;
  label: string;
  description: string;
  available: boolean;
}

/** `CredentialOut.status`: `UNAVAILABLE` è una fonte senza contratto, non una chiave mancante. */
const credentialStatusLabels: Record<CredentialStatus, string> = {
  CONFIGURED: "Configurata",
  MISSING: "Non configurata",
  UNAVAILABLE: "Non disponibile",
};

const CREDENTIAL_KINDS: CredentialKindConfig[] = [
  {
    kind: "TMDB",
    label: "TMDb",
    description: "Token Bearer della fonte TMDb (aggregatore, nessuna data di aggiunta).",
    available: true,
  },
  {
    kind: "MDBLIST",
    label: "MDBList",
    description: "API key per leggere e aggiornare le liste di destinazione.",
    available: true,
  },
  {
    kind: "TVDB",
    label: "TheTVDB",
    description:
      "API key per company ID e metadati TVDB; TheTVDB non dichiara la disponibilità per paese.",
    available: true,
  },
  {
    kind: "JUSTWATCH",
    label: "JustWatch",
    description: "Non disponibile: manca un contratto di accesso ai dati.",
    available: false,
  },
];

function toFormValues(settings: AppSettings | undefined): SettingsValues {
  const numberOr = (value: unknown, fallback: number): number =>
    typeof value === "number" ? value : fallback;
  return {
    timezone:
      typeof settings?.app_timezone === "string" ? settings.app_timezone : "Europe/Rome",
    syncBatchSize: numberOr(settings?.sync_batch_size, 100),
    maxRemovalAbsolute: numberOr(settings?.sync_max_removal_absolute, 50),
    maxRemovalPercent: numberOr(settings?.sync_max_removal_percent, 10),
    maxAdditionPercent: numberOr(settings?.sync_max_addition_percent, 50),
    notificationsSummaryEnabled: Boolean(settings?.notifications_summary_enabled),
    notificationsSummaryHour: numberOr(settings?.notifications_summary_hour, 8),
  };
}

function SettingsForm({ settings }: { settings: AppSettings | undefined }) {
  const toast = useToast();
  const updateSettings = useUpdateSettings();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: toFormValues(settings),
  });

  useEffect(() => {
    if (settings) reset(toFormValues(settings));
  }, [settings, reset]);

  const onSubmit = handleSubmit(async (values) => {
    try {
      await updateSettings.mutateAsync({
        app_timezone: values.timezone,
        sync_batch_size: values.syncBatchSize,
        sync_max_removal_absolute: values.maxRemovalAbsolute,
        sync_max_removal_percent: values.maxRemovalPercent,
        sync_max_addition_percent: values.maxAdditionPercent,
        notifications_summary_enabled: values.notificationsSummaryEnabled,
        notifications_summary_hour: values.notificationsSummaryHour,
      });
      toast.notify({ tone: "success", title: "Impostazioni salvate" });
    } catch {
      // L'errore è mostrato dall'ErrorState.
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          id="timezone"
          label="Fuso orario"
          required
          error={errors.timezone?.message}
          hint="Es. Europe/Rome."
        >
          <Input
            id="timezone"
            aria-invalid={Boolean(errors.timezone)}
            aria-describedby={errors.timezone ? "timezone-error" : "timezone-hint"}
            {...register("timezone")}
          />
        </Field>

        <Field
          id="syncBatchSize"
          label="Dimensione batch di sync"
          required
          error={errors.syncBatchSize?.message}
        >
          <Input
            id="syncBatchSize"
            type="number"
            inputMode="numeric"
            aria-invalid={Boolean(errors.syncBatchSize)}
            aria-describedby={errors.syncBatchSize ? "syncBatchSize-error" : undefined}
            {...register("syncBatchSize", { valueAsNumber: true })}
          />
        </Field>

        <Field
          id="maxRemovalAbsolute"
          label="Soglia assoluta di rimozione"
          required
          error={errors.maxRemovalAbsolute?.message}
          hint="Numero massimo di rimozioni senza approvazione."
        >
          <Input
            id="maxRemovalAbsolute"
            type="number"
            inputMode="numeric"
            aria-invalid={Boolean(errors.maxRemovalAbsolute)}
            aria-describedby={
              errors.maxRemovalAbsolute ? "maxRemovalAbsolute-error" : "maxRemovalAbsolute-hint"
            }
            {...register("maxRemovalAbsolute", { valueAsNumber: true })}
          />
        </Field>

        <Field
          id="maxRemovalPercent"
          label="Soglia percentuale di rimozione"
          required
          error={errors.maxRemovalPercent?.message}
        >
          <Input
            id="maxRemovalPercent"
            type="number"
            inputMode="decimal"
            step="0.01"
            aria-invalid={Boolean(errors.maxRemovalPercent)}
            aria-describedby={
              errors.maxRemovalPercent ? "maxRemovalPercent-error" : undefined
            }
            {...register("maxRemovalPercent", { valueAsNumber: true })}
          />
        </Field>

        <Field
          id="maxAdditionPercent"
          label="Soglia percentuale di aggiunta"
          required
          error={errors.maxAdditionPercent?.message}
        >
          <Input
            id="maxAdditionPercent"
            type="number"
            inputMode="decimal"
            step="0.01"
            aria-invalid={Boolean(errors.maxAdditionPercent)}
            aria-describedby={
              errors.maxAdditionPercent ? "maxAdditionPercent-error" : undefined
            }
            {...register("maxAdditionPercent", { valueAsNumber: true })}
          />
        </Field>

        <Field
          id="notificationsSummaryHour"
          label="Ora del riepilogo"
          error={errors.notificationsSummaryHour?.message}
          hint="0-23, nel fuso orario dell'app."
        >
          <Input
            id="notificationsSummaryHour"
            type="number"
            inputMode="numeric"
            min={0}
            max={23}
            aria-invalid={Boolean(errors.notificationsSummaryHour)}
            {...register("notificationsSummaryHour", { valueAsNumber: true })}
          />
        </Field>

        <div className="flex items-end pb-2">
          <Checkbox
            id="notificationsSummaryEnabled"
            label="Invia il riepilogo giornaliero delle sincronizzazioni"
            {...register("notificationsSummaryEnabled")}
          />
        </div>
      </div>

      {updateSettings.isError ? <ErrorState error={updateSettings.error} /> : null}
      {updateSettings.isSuccess ? (
        <InlineNotice tone="success">Impostazioni salvate.</InlineNotice>
      ) : null}

      <Button type="submit" busy={isSubmitting || updateSettings.isPending}>
        Salva impostazioni
      </Button>
    </form>
  );
}

/**
 * `POST /credentials/{kind}/verify` risponde in modo sincrono con
 * `CredentialVerifyOut`: l'esito va mostrato subito, non atteso via polling.
 */
function VerifyResult({ result }: { result: CredentialVerifyOut }) {
  const latency = result.latency_ms != null ? ` · ${result.latency_ms} ms` : "";
  const status = result.status_code != null ? ` (HTTP ${result.status_code})` : "";
  return (
    <InlineNotice tone={result.ok ? "success" : "warning"}>
      {result.ok ? "Verifica riuscita" : "Verifica fallita"}: {result.message}
      {status}
      {latency}
    </InlineNotice>
  );
}

function CredentialCard({
  config,
  credential,
}: {
  config: CredentialKindConfig;
  credential: Credential | undefined;
}) {
  const toast = useToast();
  const saveCredential = useSaveCredential(config.kind);
  const deleteCredential = useDeleteCredential(config.kind);
  const verifyCredential = useVerifyCredential(config.kind);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CredentialValues>({
    resolver: zodResolver(credentialSchema),
    defaultValues: { apiKey: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    try {
      await saveCredential.mutateAsync(values.apiKey);
      reset({ apiKey: "" });
      toast.notify({ tone: "success", title: `Chiave ${config.label} salvata` });
    } catch {
      // L'errore è mostrato dall'ErrorState.
    }
  });

  return (
    <Card>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-base font-semibold text-ink">{config.label}</h3>
          <p className="text-sm text-ink-muted">{config.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill
            label={credential ? credentialStatusLabels[credential.status] : "Non configurata"}
            tone={credential?.status === "CONFIGURED" ? "success" : "neutral"}
          />
          {credential?.masked_hint ? (
            <span className="font-mono text-xs text-ink-muted">{credential.masked_hint}</span>
          ) : null}
        </div>
      </div>

      {credential?.last_verified_at ? (
        <p className="mt-1 text-xs text-ink-muted">
          Ultima verifica: <Timestamp value={credential.last_verified_at} className="text-xs" />
        </p>
      ) : null}

      {!config.available ? (
        <p className="mt-3 text-sm text-ink-muted">
          Fonte non disponibile: la configurazione resta disabilitata finché non esiste un
          contratto di accesso ai dati.
        </p>
      ) : (
        <form onSubmit={onSubmit} noValidate className="mt-4 space-y-3">
          <Field
            id={`credential-${config.kind}`}
            label={`Nuova chiave ${config.label}`}
            error={errors.apiKey?.message}
            hint="La chiave viene inviata al server e non viene salvata nel browser."
          >
            <Input
              id={`credential-${config.kind}`}
              type="password"
              autoComplete="off"
              aria-invalid={Boolean(errors.apiKey)}
              aria-describedby={
                errors.apiKey
                  ? `credential-${config.kind}-error`
                  : `credential-${config.kind}-hint`
              }
              {...register("apiKey")}
            />
          </Field>

          {saveCredential.isError ? <ErrorState error={saveCredential.error} /> : null}
          {deleteCredential.isError ? <ErrorState error={deleteCredential.error} /> : null}
          {verifyCredential.isError ? <ErrorState error={verifyCredential.error} /> : null}
          {saveCredential.isSuccess ? (
            <InlineNotice tone="success">Chiave salvata cifrata sul server.</InlineNotice>
          ) : null}
          {verifyCredential.isSuccess ? <VerifyResult result={verifyCredential.data} /> : null}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" busy={isSubmitting || saveCredential.isPending}>
              Salva chiave
            </Button>
            <Button
              variant="secondary"
              onClick={() => verifyCredential.mutate()}
              busy={verifyCredential.isPending}
              disabled={!credential?.configured}
            >
              Verifica
            </Button>
            {confirmDelete ? (
              <>
                <Button
                  variant="danger"
                  onClick={() => {
                    deleteCredential.mutate(undefined, {
                      onSuccess: () =>
                        toast.notify({ tone: "info", title: `Chiave ${config.label} eliminata` }),
                    });
                    setConfirmDelete(false);
                  }}
                  busy={deleteCredential.isPending}
                >
                  Conferma eliminazione
                </Button>
                <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                  Annulla
                </Button>
              </>
            ) : (
              <Button
                variant="secondary"
                onClick={() => setConfirmDelete(true)}
                disabled={!credential?.configured}
              >
                Elimina
              </Button>
            )}
          </div>
        </form>
      )}
    </Card>
  );
}

function CredentialsPanel() {
  const credentials = useCredentials();

  return (
    <div className="space-y-6">
      <section aria-labelledby="credentials-heading">
        <h2 id="credentials-heading" className="mb-3 text-lg font-semibold text-ink">
          Credenziali delle fonti
        </h2>
        {credentials.isPending ? <TableSkeleton rows={2} /> : null}
        {credentials.isError ? (
          <ErrorState error={credentials.error} onRetry={() => void credentials.refetch()} />
        ) : null}
        {credentials.isSuccess && credentials.data.length === 0 ? (
          <EmptyState
            title="Nessuna credenziale"
            description="Configura le chiavi di TMDb e MDBList per abilitare acquisizione e sync."
          />
        ) : null}
        {credentials.isSuccess ? (
          <div className="space-y-4">
            {CREDENTIAL_KINDS.map((config) => (
              <CredentialCard
                key={config.kind}
                config={config}
                credential={credentials.data.find((item) => item.kind === config.kind)}
              />
            ))}
          </div>
        ) : null}
      </section>

      <ChangePasswordSection />
    </div>
  );
}

function ConnectorsPanel() {
  const toast = useToast();
  const sources = useSources();
  const settings = useSettings();
  const updateSettings = useUpdateSettings();
  const justwatchSource = (sources.data ?? []).find((source) => source.key === "justwatch");
  const healthcheck = useHealthcheckSource(justwatchSource?.id ?? "");
  const [defaultSource, setDefaultSource] = useState<DefaultSource>("justwatch");
  const [catalogScheduleEnabled, setCatalogScheduleEnabled] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    setDefaultSource(resolveDefaultSource(settings.data.default_source));
    setCatalogScheduleEnabled(settings.data.catalog_schedule_enabled === true);
  }, [settings.data]);

  const saveDefaultSource = (value: DefaultSource) => {
    setDefaultSource(value);
    updateSettings.mutate(
      { default_source: value },
      {
        onSuccess: () =>
          toast.notify({ tone: "success", title: "Fonte predefinita aggiornata" }),
      },
    );
  };

  const saveCatalogSchedule = (enabled: boolean) => {
    setCatalogScheduleEnabled(enabled);
    updateSettings.mutate(
      { catalog_schedule_enabled: enabled },
      {
        onSuccess: () =>
          toast.notify({
            tone: "success",
            title: enabled
              ? "Pianificazione catalogo attivata"
              : "Pianificazione catalogo disattivata",
          }),
      },
    );
  };

  return (
    <div className="space-y-6">
      <section aria-labelledby="connectors-heading">
        <h2 id="connectors-heading" className="mb-3 text-lg font-semibold text-ink">
          Connettori delle fonti
        </h2>
        <p className="mb-4 max-w-3xl text-sm text-ink-muted">
          Stato runtime, rate-limit, cache e mapping verificati delle fonti non TMDb.
          Le credenziali restano nella scheda Credenziali.
        </p>

        <Card className="mb-4" testId="default-source-settings">
          <h3 className="text-base font-semibold text-ink">Fonte predefinita</h3>
          <p className="text-sm text-ink-muted">
            Il builder propone questa fonte per le nuove collezioni.
          </p>
          {settings.isPending ? <TableSkeleton rows={1} /> : null}
          {settings.isError ? (
            <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
          ) : null}
          {settings.isSuccess ? (
            <div className="mt-3 space-y-4">
              <div className="flex flex-wrap gap-2">
                <ToggleChip
                  testId="default-source-justwatch"
                  pressed={defaultSource === "justwatch"}
                  onClick={() => saveDefaultSource("justwatch")}
                >
                  JustWatch
                </ToggleChip>
                <ToggleChip
                  testId="default-source-tmdb"
                  pressed={defaultSource === "tmdb"}
                  onClick={() => saveDefaultSource("tmdb")}
                >
                  TMDb
                </ToggleChip>
              </div>
              <Checkbox
                id="catalog-schedule-enabled"
                label="Pianifica acquisizioni catalogo scaglionate nelle 24 ore"
                checked={catalogScheduleEnabled}
                onChange={(event) => saveCatalogSchedule(event.target.checked)}
              />
              {updateSettings.isError ? <ErrorState error={updateSettings.error} /> : null}
            </div>
          ) : null}
        </Card>

        {sources.isPending ? <TableSkeleton rows={2} /> : null}
        {sources.isError ? (
          <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
        ) : null}
        {sources.isSuccess && !justwatchSource ? (
          <EmptyState
            title="Connettore JustWatch non disponibile"
            description="La fonte non è registrata nel backend."
          />
        ) : null}

        {justwatchSource ? (
          <Card className="mb-4" testId="justwatch-healthcheck">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-ink">Test connettività JustWatch</h3>
                <p className="text-sm text-ink-muted">
                  Verifica la raggiungibilità della fonte aggregatore. I mapping verificati
                  restano visibili nella card qui sotto.
                </p>
              </div>
              <Button
                variant="secondary"
                onClick={() => healthcheck.mutate()}
                busy={healthcheck.isPending}
                data-testid="justwatch-healthcheck-button"
              >
                Test connettività JustWatch
              </Button>
            </div>
            {healthcheck.isError ? <ErrorState error={healthcheck.error} /> : null}
            {healthcheck.isSuccess ? (
              <div className="mt-3">
                <InlineNotice tone={healthcheck.data.ok ? "success" : "warning"}>
                  {healthcheck.data.message}
                  {healthcheck.data.latency_ms != null
                    ? ` · ${healthcheck.data.latency_ms} ms`
                    : ""}
                </InlineNotice>
              </div>
            ) : null}
          </Card>
        ) : null}

        {justwatchSource ? <JustWatchConnectorCard source={justwatchSource} /> : null}
      </section>
    </div>
  );
}

function MaintenancePanel() {
  const settings = useSettings();

  return (
    <div className="space-y-6">
      <SystemStatusCard />
      <Card>
        <h2 className="mb-3 text-lg font-semibold text-ink">Parametri operativi</h2>
        {settings.isPending ? <TableSkeleton rows={3} /> : null}
        {settings.isError ? (
          <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
        ) : null}
        {settings.isSuccess ? (
          <>
            <StaleBanner updatedAt={settings.dataUpdatedAt} />
            <SettingsForm settings={settings.data} />
          </>
        ) : null}
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = searchParams.get("tab");
  const [tab, setTab] = useState<SettingsTab>(isSettingsTab(initial) ? initial : "credentials");

  const selectTab = (next: SettingsTab) => {
    setTab(next);
    setSearchParams({ tab: next }, { replace: true });
  };

  return (
    <>
      <PageHeader
        eyebrow="Configurazione"
        title="Impostazioni"
        description="Credenziali, notifiche, backup e portabilità. Nessun segreto viene mostrato dopo il salvataggio."
      />

      <div
        role="tablist"
        aria-label="Sezioni delle impostazioni"
        data-testid="settings-tabs"
        className="mb-6 flex flex-wrap gap-1 rounded-lg border border-line bg-surface p-1"
      >
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`settings-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`settings-panel-${item.id}`}
            onClick={() => selectTab(item.id)}
            className={cn(
              "inline-flex min-h-10 items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors",
              tab === item.id
                ? "bg-accent-soft text-accent"
                : "text-ink-muted hover:bg-surface-muted hover:text-ink",
            )}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`settings-panel-${tab}`}
        aria-labelledby={`settings-tab-${tab}`}
        tabIndex={0}
        className="focus:outline-none"
      >
        {tab === "credentials" ? <CredentialsPanel /> : null}
        {tab === "connectors" ? <ConnectorsPanel /> : null}
        {tab === "notifications" ? <NotificationsSection /> : null}
        {tab === "maintenance" ? <MaintenancePanel /> : null}
        {tab === "portability" ? <ConfigPortabilitySection /> : null}
      </div>
    </>
  );
}
