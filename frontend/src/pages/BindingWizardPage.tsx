import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  useCreateBinding,
  useCreatePreview,
  useCreateTarget,
} from "../api/mutations";
import { queryKeys } from "../api/query-keys";
import {
  useCollection,
  useCollections,
  usePreview,
  useProviders,
  useSources,
  useTargets,
} from "../api/queries";
import type { Collection } from "../api/types";
import { DateBasisBadge, OriginBadge } from "../components/ui/badges";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  Skeleton,
} from "../components/ui/feedback";
import {
  Button,
  Card,
  Checkbox,
  Field,
  Input,
  PageHeader,
  Select,
} from "../components/ui/primitives";
import { Stepper } from "../components/ui/stepper";
import { clearBindingDraft, loadBindingDraft, saveBindingDraft } from "../lib/binding-draft";
import { formatNumber } from "../lib/format";
import {
  BINDING_POLICY_VERSION,
  DEFAULT_BINDING_DRAFT,
  bindingDraftSchema,
  bindingStepFields,
  type BindingDraft,
} from "../lib/validation";

const STEPS = [
  "Provider e paese",
  "Fonte",
  "Collezione",
  "Film o serie",
  "Anteprima",
  "Lista MDBList",
  "Modo e soglie",
  "Conferma",
];

const MIRROR_WARNING =
  "MIRROR rimuoverà dalla lista gli elementi non presenti nella collezione, inclusi quelli aggiunti manualmente. L'operazione è tracciata e reversibile solo con un nuovo snapshot/sync.";

function clampStep(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(STEPS.length, Math.max(1, Math.trunc(value)));
}

export default function BindingWizardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const step = clampStep(Number(searchParams.get("step") ?? "1"));
  const initialDraft = useMemo(() => loadBindingDraft() ?? DEFAULT_BINDING_DRAFT, []);

  const {
    register,
    watch,
    setValue,
    getValues,
    setError,
    clearErrors,
    trigger,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<BindingDraft>({
    resolver: zodResolver(bindingDraftSchema),
    defaultValues: initialDraft,
    mode: "onTouched",
  });

  const values = watch();
  const [stepMessage, setStepMessage] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<unknown>(null);

  const providers = useProviders(values.country || "IT");
  const sources = useSources();
  const collections = useCollections({
    providerId: values.providerId,
    mediaType: values.mediaType,
  });
  const selectedCollectionQuery = useCollection(values.collectionId || undefined);
  const targets = useTargets(values.mediaType);
  const preview = usePreview(values.previewId);

  const createPreview = useCreatePreview();
  const createTarget = useCreateTarget();
  const createBinding = useCreateBinding();

  const selectedCollection: Collection | undefined =
    selectedCollectionQuery.data ??
    collections.data?.find((collection) => collection.id === values.collectionId);

  const availableProviders = providers.data ?? [];
  const catalogSources = (sources.data ?? []).filter(
    (source) =>
      source.capabilities.catalog === true &&
      (source.status === "OK" || source.status === "DEGRADED"),
  );
  const mediaTargets = (targets.data ?? []).filter(
    (target) => target.mediatype === values.mediaType,
  );

  const previewCounts = preview.data?.counts;
  const toRemove = previewCounts?.to_remove ?? 0;
  const previewReady =
    values.previewState === "READY" ||
    (values.previewState === "BLOCKED" && values.requireReview);

  useEffect(() => {
    const subscription = watch((draft) => {
      saveBindingDraft(draft as BindingDraft);
    });
    return () => subscription.unsubscribe();
  }, [watch]);

  useEffect(() => {
    if (preview.data && preview.data.state !== getValues("previewState")) {
      setValue("previewState", preview.data.state);
    }
  }, [preview.data, getValues, setValue]);

  const initialStepChecked = useRef(false);
  useEffect(() => {
    if (initialStepChecked.current) return;
    initialStepChecked.current = true;
    void (async () => {
      for (let candidate = 1; candidate < step; candidate += 1) {
        const valid = await trigger(bindingStepFields[candidate]);
        if (!valid) {
          setSearchParams({ step: String(candidate) }, { replace: true });
          return;
        }
      }
    })();
  }, [step, trigger, setSearchParams]);

  const goToStep = (next: number) => {
    setStepMessage(null);
    setSearchParams({ step: String(clampStep(next)) });
  };

  const goBack = () => {
    if (step === 1) {
      navigate("/app/bindings");
      return;
    }
    goToStep(step - 1);
  };

  const onComputePreview = async () => {
    setStepMessage(null);
    const valid = await trigger(["collectionId"]);
    if (!valid) return;
    try {
      const result = await createPreview.mutateAsync({
        collection_id: values.collectionId,
        target_id: values.targetId || undefined,
        mode: values.mode,
        thresholds: {
          max_removal_pct: values.maxRemovalPct,
          max_removal_abs: values.maxRemovalAbs,
        },
      });
      setValue("previewId", result.preview_id);
      setValue("previewState", "RUNNING");
    } catch {
      // L'errore è mostrato dall'ErrorState accanto alla preview.
    }
  };

  const onSubmit = handleSubmit(async (draft) => {
    setSubmitError(null);
    const collectionName = selectedCollection?.name;
    // Senza il nome della collezione la conferma digitata non è verificabile:
    // bloccare il submit invece di saltare il controllo dello step 8.
    if (!collectionName) {
      setStepMessage(
        "La collezione selezionata non è disponibile: torna allo step 3 e selezionala di nuovo.",
      );
      return;
    }
    if (draft.confirmName.trim() !== collectionName) {
      setError("confirmName", {
        type: "manual",
        message: "Il nome digitato non coincide con quello della collezione.",
      });
      return;
    }
    try {
      let targetId = draft.targetId;
      if (draft.targetMode === "new") {
        const target = await createTarget.mutateAsync({
          name: draft.newListName?.trim() ?? "",
          private: draft.private,
          media_type: draft.mediaType,
        });
        targetId = target.id;
      }
      if (!targetId) {
        setError("targetId", { type: "manual", message: "Seleziona o crea una lista." });
        return;
      }
      await createBinding.mutateAsync({
        collection_id: draft.collectionId,
        target_id: targetId,
        mode: draft.mode,
        schedule: draft.schedule,
        schedule_time: draft.scheduleTime,
        thresholds: {
          max_removal_pct: draft.maxRemovalPct,
          max_removal_abs: draft.maxRemovalAbs,
        },
        preserve_order: draft.preserveOrder,
        reorder_enabled: draft.reorderEnabled,
        schedule_policy: draft.schedulePolicy,
        require_review: draft.requireReview,
        enabled: true,
        policy_version: BINDING_POLICY_VERSION,
      });
      clearBindingDraft();
      await queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
      navigate("/app/bindings");
    } catch (error) {
      setSubmitError(error);
    }
  });

  const goNext = async () => {
    setStepMessage(null);
    const valid = await trigger(bindingStepFields[step], { shouldFocus: true });
    if (!valid) return;

    if (step === 3 && selectedCollection && selectedCollection.media_type !== values.mediaType) {
      setValue("mediaType", selectedCollection.media_type);
    }

    if (step === 5) {
      if (!previewReady) {
        setStepMessage(
          "Calcola un'anteprima valida (READY) prima di procedere; se è BLOCKED serve la revisione manuale.",
        );
        return;
      }
      if (toRemove > 0 && !values.acknowledgedRemovals) {
        setStepMessage("Conferma di aver letto l'elenco delle rimozioni previste.");
        return;
      }
    }

    if (step === STEPS.length) {
      await onSubmit();
      return;
    }
    goToStep(step + 1);
  };

  const onProviderChange = (providerId: string) => {
    setValue("providerId", providerId, { shouldValidate: true });
    setValue("collectionId", "");
    setValue("previewId", undefined);
    setValue("previewState", undefined);
    setValue("targetId", undefined);
    clearErrors(["collectionId", "targetId"]);
  };

  const onCollectionChange = (collectionId: string) => {
    setValue("collectionId", collectionId, { shouldValidate: true });
    setValue("previewId", undefined);
    setValue("previewState", undefined);
    setValue("targetId", undefined);
    const collection = collections.data?.find((item) => item.id === collectionId);
    if (collection) setValue("mediaType", collection.media_type);
  };

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <div className="space-y-4">
            <Field
              id="country"
              label="Paese"
              required
              error={errors.country?.message}
              hint="Codice ISO a 2 lettere, es. IT."
            >
              <Input
                id="country"
                maxLength={2}
                aria-invalid={Boolean(errors.country)}
                aria-describedby={errors.country ? "country-error" : "country-hint"}
                {...register("country", {
                  onChange: (event) => {
                    setValue("country", event.target.value.toUpperCase());
                  },
                })}
              />
            </Field>

            <Field
              id="providerId"
              label="Provider"
              required
              error={errors.providerId?.message}
            >
              <Select
                id="providerId"
                value={values.providerId}
                aria-invalid={Boolean(errors.providerId)}
                aria-describedby={errors.providerId ? "providerId-error" : undefined}
                onChange={(event) => onProviderChange(event.target.value)}
              >
                <option value="">Seleziona un provider…</option>
                {availableProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </Select>
            </Field>

            {providers.isPending ? <Skeleton className="h-10 w-full" /> : null}
            {providers.isError ? (
              <ErrorState error={providers.error} onRetry={() => void providers.refetch()} />
            ) : null}
            {providers.isSuccess && availableProviders.length === 0 ? (
              <InlineNotice tone="warning">
                Nessun provider disponibile per {values.country}. Acquisisci prima i
                provider dalla fonte.
              </InlineNotice>
            ) : null}
          </div>
        );

      case 2:
        return (
          <div className="space-y-4">
            <Field
              id="sourceId"
              label="Fonte"
              required
              error={errors.sourceId?.message}
              hint="Solo fonti con capacità catalogo e stato OK o DEGRADED."
            >
              <Select
                id="sourceId"
                aria-invalid={Boolean(errors.sourceId)}
                aria-describedby={errors.sourceId ? "sourceId-error" : "sourceId-hint"}
                {...register("sourceId")}
              >
                <option value="">Seleziona una fonte…</option>
                {catalogSources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.name} ({source.status})
                  </option>
                ))}
              </Select>
            </Field>

            {sources.isPending ? <Skeleton className="h-10 w-full" /> : null}
            {sources.isError ? (
              <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
            ) : null}
            {sources.isSuccess && catalogSources.length === 0 ? (
              <InlineNotice tone="warning">
                Nessuna fonte con capacità catalogo disponibile: configura le credenziali
                nelle impostazioni.
              </InlineNotice>
            ) : null}
          </div>
        );

      case 3:
        return (
          <div className="space-y-4">
            <Field
              id="collectionId"
              label="Collezione"
              required
              error={errors.collectionId?.message}
            >
              <Select
                id="collectionId"
                value={values.collectionId}
                aria-invalid={Boolean(errors.collectionId)}
                aria-describedby={errors.collectionId ? "collectionId-error" : undefined}
                onChange={(event) => onCollectionChange(event.target.value)}
              >
                <option value="">Seleziona una collezione…</option>
                {(collections.data ?? []).map((collection) => (
                  <option key={collection.id} value={collection.id}>
                    {collection.name} · {collection.media_type === "MOVIE" ? "Film" : "Serie"}
                  </option>
                ))}
              </Select>
            </Field>

            {collections.isPending ? <Skeleton className="h-10 w-full" /> : null}
            {collections.isError ? (
              <ErrorState
                error={collections.error}
                onRetry={() => void collections.refetch()}
              />
            ) : null}
            {collections.isSuccess && collections.data.length === 0 ? (
              <EmptyState
                title="Nessuna collezione"
                description="Scegli un altro provider o acquisisci le collezioni dalla fonte."
              />
            ) : null}

            {selectedCollection ? (
              <div className="rounded-md border border-line bg-surface-muted p-3">
                <p className="text-sm font-medium text-ink">
                  {selectedCollection.name}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <OriginBadge
                    origin={selectedCollection.origin}
                    source={selectedCollection.source_key}
                  />
                  <DateBasisBadge
                    dateBasis={selectedCollection.date_basis}
                    source={selectedCollection.source_key}
                  />
                </div>
                <p className="mt-2 text-xs text-ink-muted">
                  Ultimo snapshot valido:{" "}
                  {selectedCollectionQuery.data?.latest_snapshot?.is_valid
                    ? `sì (${formatNumber(selectedCollectionQuery.data.latest_snapshot.items_count)} elementi)`
                    : "non disponibile"}
                </p>
              </div>
            ) : null}
          </div>
        );

      case 4:
        return (
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-ink">Tipo di contenuto</legend>
            <label className="flex items-start gap-3">
              <input
                type="radio"
                value="MOVIE"
                className="mt-1 h-5 w-5"
                {...register("mediaType")}
              />
              <span className="text-sm text-ink">
                Film
                <span className="block text-xs text-ink-muted">
                  Film e serie restano separati in target, binding e run.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-3">
              <input
                type="radio"
                value="SHOW"
                className="mt-1 h-5 w-5"
                {...register("mediaType")}
              />
              <span className="text-sm text-ink">
                Serie
                <span className="block text-xs text-ink-muted">
                  TMDb `tv` diventa SHOW: un solo spelling per concetto.
                </span>
              </span>
            </label>
            {selectedCollection && selectedCollection.media_type !== values.mediaType ? (
              <InlineNotice tone="warning">
                La collezione selezionata è di tipo {selectedCollection.media_type}: il tipo
                verrà allineato prima di procedere.
              </InlineNotice>
            ) : null}
          </fieldset>
        );

      case 5:
        return (
          <div className="space-y-4">
            <p className="text-sm text-ink-muted">
              L&apos;anteprima calcola il piano senza scrivere nulla sulla lista remota.
            </p>
            <Button onClick={() => void onComputePreview()} busy={createPreview.isPending}>
              {values.previewId ? "Ricalcola anteprima" : "Calcola anteprima"}
            </Button>

            {createPreview.isError ? <ErrorState error={createPreview.error} /> : null}
            {preview.isError ? (
              <ErrorState error={preview.error} onRetry={() => void preview.refetch()} />
            ) : null}

            {values.previewId && preview.isPending ? (
              <div className="space-y-2" aria-busy="true">
                <span className="sr-only">Calcolo dell&apos;anteprima in corso…</span>
                <Skeleton className="h-16 w-full" />
              </div>
            ) : null}

            {preview.data ? (
              <div className="rounded-md border border-line bg-surface p-4">
                <p className="text-sm font-medium text-ink">
                  Stato anteprima: {preview.data.state}
                </p>
                <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">Da aggiungere</dt>
                    <dd className="text-lg font-semibold text-ink">
                      +{formatNumber(previewCounts?.to_add ?? 0)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">Da rimuovere</dt>
                    <dd className="text-lg font-semibold text-ink">
                      −{formatNumber(toRemove)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">Invariati</dt>
                    <dd className="text-lg font-semibold text-ink">
                      {formatNumber(previewCounts?.unchanged ?? 0)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">Non risolti</dt>
                    <dd className="text-lg font-semibold text-ink">
                      {formatNumber(previewCounts?.unresolved ?? 0)}
                    </dd>
                  </div>
                </dl>

                {preview.data.blocked ? (
                  <div className="mt-3">
                    <InlineNotice tone="warning">
                      Anteprima bloccata: {preview.data.blocked.reason}
                      {preview.data.blocked.observed != null &&
                      preview.data.blocked.threshold != null
                        ? ` (osservato ${preview.data.blocked.observed}, soglia ${preview.data.blocked.threshold})`
                        : ""}
                      . Per procedere attiva la revisione manuale.
                    </InlineNotice>
                  </div>
                ) : null}

                {toRemove > 0 ? (
                  <div className="mt-3">
                    <Checkbox
                      id="acknowledgedRemovals"
                      label={`Ho letto le ${toRemove} rimozioni previste. ${MIRROR_WARNING}`}
                      aria-invalid={Boolean(errors.acknowledgedRemovals)}
                      {...register("acknowledgedRemovals")}
                    />
                  </div>
                ) : null}
              </div>
            ) : null}

            {stepMessage ? <InlineNotice tone="warning">{stepMessage}</InlineNotice> : null}
          </div>
        );

      case 6:
        return (
          <div className="space-y-4">
            <fieldset className="space-y-3">
              <legend className="text-sm font-medium text-ink">Lista di destinazione</legend>
              <label className="flex items-start gap-3">
                <input
                  type="radio"
                  value="existing"
                  className="mt-1 h-5 w-5"
                  {...register("targetMode")}
                />
                <span className="text-sm text-ink">Usa una lista esistente</span>
              </label>
              <label className="flex items-start gap-3">
                <input
                  type="radio"
                  value="new"
                  className="mt-1 h-5 w-5"
                  {...register("targetMode")}
                />
                <span className="text-sm text-ink">Crea una nuova lista</span>
              </label>
            </fieldset>

            {values.targetMode === "existing" ? (
              <Field
                id="targetId"
                label="Lista MDBList"
                required
                error={errors.targetId?.message}
              >
                <Select
                  id="targetId"
                  aria-invalid={Boolean(errors.targetId)}
                  aria-describedby={errors.targetId ? "targetId-error" : undefined}
                  {...register("targetId")}
                >
                  <option value="">Seleziona una lista…</option>
                  {mediaTargets.map((target) => (
                    <option key={target.id} value={target.id}>
                      {target.name}
                      {target.item_count != null ? ` (${target.item_count} elementi)` : ""}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : (
              <Field
                id="newListName"
                label="Nome della nuova lista"
                required
                error={errors.newListName?.message}
                hint="Da 3 a 80 caratteri."
              >
                <Input
                  id="newListName"
                  aria-invalid={Boolean(errors.newListName)}
                  aria-describedby={
                    errors.newListName ? "newListName-error" : "newListName-hint"
                  }
                  {...register("newListName")}
                />
              </Field>
            )}

            {values.targetMode === "new" ? (
              <Checkbox
                id="private"
                label="Lista privata"
                {...register("private")}
              />
            ) : null}

            {targets.isPending ? <Skeleton className="h-10 w-full" /> : null}
            {targets.isError ? (
              <ErrorState error={targets.error} onRetry={() => void targets.refetch()} />
            ) : null}
            {targets.isSuccess && values.targetMode === "existing" && mediaTargets.length === 0 ? (
              <InlineNotice tone="warning">
                Nessuna lista MDBList disponibile per questo tipo: creane una nuova.
              </InlineNotice>
            ) : null}

            <Button variant="secondary" onClick={() => void onComputePreview()} busy={createPreview.isPending}>
              Ricalcola anteprima con questa lista
            </Button>
          </div>
        );

      case 7:
        return (
          <div className="space-y-4">
            <fieldset className="space-y-3">
              <legend className="text-sm font-medium text-ink">Modo di sincronizzazione</legend>
              <label className="flex items-start gap-3">
                <input
                  type="radio"
                  value="MIRROR"
                  className="mt-1 h-5 w-5"
                  {...register("mode")}
                />
                <span className="text-sm text-ink">
                  MIRROR — rispecchia la collezione
                  <span className="block text-xs text-ink-muted">{MIRROR_WARNING}</span>
                </span>
              </label>
              <label className="flex items-start gap-3">
                <input
                  type="radio"
                  value="APPEND_ONLY"
                  className="mt-1 h-5 w-5"
                  {...register("mode")}
                />
                <span className="text-sm text-ink">
                  APPEND_ONLY — solo aggiunte
                  <span className="block text-xs text-ink-muted">
                    Nessuna rimozione dalla lista remota.
                  </span>
                </span>
              </label>
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="schedule" label="Frequenza" required error={errors.schedule?.message}>
                <Select id="schedule" {...register("schedule")}>
                  <option value="MANUAL">Manuale</option>
                  <option value="DAILY">Giornaliera</option>
                  <option value="WEEKLY">Settimanale</option>
                </Select>
              </Field>

              <Field
                id="scheduleTime"
                label="Orario"
                required
                error={errors.scheduleTime?.message}
                hint="Formato HH:MM."
              >
                <Input
                  id="scheduleTime"
                  type="time"
                  aria-invalid={Boolean(errors.scheduleTime)}
                  aria-describedby={
                    errors.scheduleTime ? "scheduleTime-error" : "scheduleTime-hint"
                  }
                  {...register("scheduleTime")}
                />
              </Field>

              <Field
                id="maxRemovalPct"
                label="Rimozioni massime (%)"
                required
                error={errors.maxRemovalPct?.message}
              >
                <Input
                  id="maxRemovalPct"
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  aria-invalid={Boolean(errors.maxRemovalPct)}
                  aria-describedby={errors.maxRemovalPct ? "maxRemovalPct-error" : undefined}
                  {...register("maxRemovalPct", { valueAsNumber: true })}
                />
              </Field>

              <Field
                id="maxRemovalAbs"
                label="Rimozioni massime (elementi)"
                required
                error={errors.maxRemovalAbs?.message}
              >
                <Input
                  id="maxRemovalAbs"
                  type="number"
                  inputMode="numeric"
                  aria-invalid={Boolean(errors.maxRemovalAbs)}
                  aria-describedby={errors.maxRemovalAbs ? "maxRemovalAbs-error" : undefined}
                  {...register("maxRemovalAbs", { valueAsNumber: true })}
                />
              </Field>
            </div>

            <Field
              id="schedulePolicy"
              label="Policy di applicazione"
              required
              error={errors.schedulePolicy?.message}
            >
              <Select id="schedulePolicy" {...register("schedulePolicy")}>
                <option value="AUTO_APPLY_IF_SAFE">Applica se sicuro</option>
                <option value="ALWAYS_APPROVE">Richiedi sempre approvazione</option>
                <option value="DRY_RUN_ONLY">Solo dry-run</option>
              </Select>
            </Field>

            <div className="space-y-3">
              <Checkbox
                id="preserveOrder"
                label="Preserva l'ordine (best-effort; max 1.000 elementi per blocco)"
                {...register("preserveOrder")}
              />
              <Checkbox
                id="reorderEnabled"
                label="Abilita il riordino della lista remota"
                {...register("reorderEnabled")}
              />
              <Checkbox
                id="requireReview"
                label="Richiedi revisione manuale oltre soglia"
                {...register("requireReview")}
              />
            </div>
            {errors.requireReview?.message ? (
              <p role="alert" className="text-sm font-medium text-danger">
                {errors.requireReview.message}
              </p>
            ) : null}

            {previewCounts ? (
              <InlineNotice>
                Anteprima: +{formatNumber(previewCounts.to_add ?? 0)} / −
                {formatNumber(previewCounts.to_remove ?? 0)} / =
                {formatNumber(previewCounts.unchanged)} / !
                {formatNumber(previewCounts.unresolved)} non risolti.
              </InlineNotice>
            ) : null}
          </div>
        );

      case 8:
        return (
          <div className="space-y-4">
            <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Collezione</dt>
                <dd className="text-sm text-ink">
                  {selectedCollection?.name ?? values.collectionId}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Lista</dt>
                <dd className="text-sm text-ink">
                  {values.targetMode === "new"
                    ? values.newListName
                    : (mediaTargets.find((target) => target.id === values.targetId)?.name ??
                      values.targetId)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Modo</dt>
                <dd className="text-sm text-ink">{values.mode}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Frequenza</dt>
                <dd className="text-sm text-ink">
                  {values.schedule} {values.schedule === "MANUAL" ? "" : values.scheduleTime}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Soglie</dt>
                <dd className="text-sm text-ink">
                  {values.maxRemovalPct}% · {values.maxRemovalAbs} elementi
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Ordine</dt>
                <dd className="text-sm text-ink">
                  {values.preserveOrder ? "preservato (best-effort)" : "non preservato"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Anteprima</dt>
                <dd className="text-sm text-ink">
                  +{formatNumber(previewCounts?.to_add ?? 0)} / −
                  {formatNumber(previewCounts?.to_remove ?? 0)} / =
                  {formatNumber(previewCounts?.unchanged ?? 0)} / !
                  {formatNumber(previewCounts?.unresolved ?? 0)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Policy</dt>
                <dd className="text-sm text-ink">{values.schedulePolicy}</dd>
              </div>
            </dl>

            <Field
              id="confirmName"
              label={`Digita il nome della collezione per confermare`}
              required
              error={errors.confirmName?.message}
              hint={selectedCollection?.name}
            >
              <Input
                id="confirmName"
                aria-invalid={Boolean(errors.confirmName)}
                aria-describedby={errors.confirmName ? "confirmName-error" : "confirmName-hint"}
                {...register("confirmName")}
              />
            </Field>

            <Checkbox
              id="policyAccepted"
              label="Accetto la policy di sincronizzazione: le modifiche sono tracciate e reversibili solo con un nuovo snapshot/sync."
              aria-invalid={Boolean(errors.policyAccepted)}
              {...register("policyAccepted")}
            />
            {errors.policyAccepted?.message ? (
              <p role="alert" className="text-sm font-medium text-danger">
                {errors.policyAccepted.message}
              </p>
            ) : null}

            {submitError ? <ErrorState error={submitError} /> : null}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <>
      <PageHeader
        title="Nuovo binding"
        description="Otto passaggi: provider, fonte, collezione, tipo, anteprima, lista, modo e conferma."
        actions={
          <Button
            variant="ghost"
            onClick={() => {
              clearBindingDraft();
              navigate("/app/bindings");
            }}
          >
            Annulla
          </Button>
        }
      />

      <Stepper steps={STEPS} current={step} />

      <Card>
        <h2 className="mb-4 text-lg font-semibold text-ink">
          {step}. {STEPS[step - 1]}
        </h2>
        {renderStep()}
      </Card>

      {stepMessage && step !== 5 ? (
        <div className="mt-4">
          <InlineNotice tone="warning">{stepMessage}</InlineNotice>
        </div>
      ) : null}

      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        <Button variant="secondary" onClick={goBack}>
          Indietro
        </Button>
        <Button
          onClick={() => void goNext()}
          busy={isSubmitting || createBinding.isPending || createTarget.isPending}
        >
          {step === STEPS.length ? "Crea binding" : "Avanti"}
        </Button>
      </div>

      <p className="mt-6 text-sm text-ink-muted">
        <Link to="/app/bindings" className="font-medium text-accent underline">
          Torna ai binding
        </Link>
      </p>
    </>
  );
}
