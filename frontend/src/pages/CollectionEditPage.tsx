import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useCreateCollection,
  useUpdateCollection,
  type CollectionCreatePayload,
} from "../api/mutations";
import { useCollection, useCollections, useGenres, useProviders } from "../api/queries";
import type { Collection, MediaType } from "../api/types";
import { collectionProviderName } from "../lib/collections";
import { formatNumber } from "../lib/format";
import { ErrorState, InlineNotice, TableSkeleton } from "../components/ui/feedback";
import {
  Button,
  Card,
  Checkbox,
  Field,
  Input,
  PageHeader,
  Select,
  Textarea,
  ToggleChip,
} from "../components/ui/primitives";
import { IconArrowRight, IconFilter, IconLayers, IconSearch } from "../components/ui/icons";

type CollectionKindValue = "CATALOG" | "RECENTLY_ADDED" | "CUSTOM_FILTER";

const KIND_LABELS: Record<CollectionKindValue, string> = {
  CATALOG: "Catalogo / genere",
  RECENTLY_ADDED: "Appena rilevati",
  CUSTOM_FILTER: "Combinata multi-provider",
};

const MONETIZATION_OPTIONS = [
  { value: "FLATRATE", label: "Flatrate" },
  { value: "RENT", label: "Noleggio" },
  { value: "BUY", label: "Acquisto" },
  { value: "ADS", label: "Con pubblicità" },
  { value: "FREE", label: "Gratis" },
];

const SORT_OPTIONS = [
  { value: "vote_average.desc", label: "Voto medio decrescente" },
  { value: "vote_count.desc", label: "Numero voti decrescente" },
  { value: "release_date.desc", label: "Anno decrescente" },
  { value: "title.asc", label: "Titolo A-Z" },
  { value: "popularity.desc", label: "Popolarità decrescente" },
];

function isFullCatalog(collection: Collection): boolean {
  return collection.kind === "CATALOG" && !collection.filters?.with_genres;
}

function BuilderSection({
  step,
  title,
  description,
  children,
}: {
  step: number;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <div className="mb-4 flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold tabular-nums text-accent">
          {step}
        </span>
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {description ? <p className="text-xs text-ink-muted">{description}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function PreviewRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line/70 py-2 last:border-0">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="text-right text-xs font-medium text-ink">{value}</dd>
    </div>
  );
}

export default function CollectionEditPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const isEdit = Boolean(collectionId);
  const collection = useCollection(collectionId);
  const providers = useProviders("IT");
  const create = useCreateCollection();
  const update = useUpdateCollection(collectionId ?? "");
  const navigate = useNavigate();

  const [providerId, setProviderId] = useState("");
  const [mediaType, setMediaType] = useState<MediaType>("MOVIE");
  const [kind, setKind] = useState<CollectionKindValue>("CATALOG");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [monetization, setMonetization] = useState("FLATRATE");
  const [genreIds, setGenreIds] = useState<number[]>([]);
  const [sourceCollectionId, setSourceCollectionId] = useState("");
  const [sourceCollectionIds, setSourceCollectionIds] = useState<string[]>([]);
  const [sharedSnapshotId, setSharedSnapshotId] = useState("");
  const [excludeGenreIds, setExcludeGenreIds] = useState<number[]>([]);
  const [minVoteAverage, setMinVoteAverage] = useState("");
  const [minVoteCount, setMinVoteCount] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [originalLanguage, setOriginalLanguage] = useState("");
  const [localSortBy, setLocalSortBy] = useState("vote_average.desc");
  const [windowDays, setWindowDays] = useState("14");
  const [isActive, setIsActive] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);
  const [genreQuery, setGenreQuery] = useState("");

  const genres = useGenres(mediaType);
  const collections = useCollections({
    providerId: kind === "CUSTOM_FILTER" ? "" : providerId,
    mediaType,
  });
  const fullCatalogs = useMemo(
    () => (collections.data ?? []).filter(isFullCatalog),
    [collections.data],
  );

  useEffect(() => {
    const data = collection.data;
    if (!data) return;
    setProviderId(data.provider_id);
    setMediaType(data.media_type);
    setKind(
      data.kind === "RECENTLY_ADDED"
        ? "RECENTLY_ADDED"
        : data.kind === "CUSTOM_FILTER"
          ? "CUSTOM_FILTER"
          : "CATALOG",
    );
    setName(data.name);
    setSlug(data.slug);
    setDescription(data.description ?? "");
    setMonetization(data.offer_types[0] ?? "FLATRATE");
    setGenreIds(
      String(data.filters?.with_genres ?? "")
        .split(",")
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value) && value > 0),
    );
    setSourceCollectionId(String(data.filters?.source_collection_id ?? ""));
    setSourceCollectionIds(
      Array.isArray(data.filters?.source_collection_ids)
        ? data.filters.source_collection_ids.map(String)
        : [],
    );
    setSharedSnapshotId(String(data.filters?.shared_snapshot_collection_id ?? ""));
    setExcludeGenreIds(
      String(data.filters?.exclude_genres ?? "")
        .split(",")
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value) && value > 0),
    );
    setMinVoteAverage(String(data.filters?.min_vote_average ?? ""));
    setMinVoteCount(String(data.filters?.min_vote_count ?? ""));
    setYearFrom(String(data.filters?.year_from ?? ""));
    setYearTo(String(data.filters?.year_to ?? ""));
    setOriginalLanguage(String(data.filters?.original_language ?? ""));
    setLocalSortBy(String(data.filters?.sort_by ?? "vote_average.desc"));
    setWindowDays(String(data.filters?.window_days ?? 14));
    setIsActive(data.is_active);
  }, [collection.data]);

  const verifiedProviders = useMemo(() => {
    return (providers.data ?? []).filter((provider) =>
      mediaType === "SHOW" ? provider.mapping_verified_tv : provider.mapping_verified_movie,
    );
  }, [providers.data, mediaType]);

  const providerOptions = verifiedProviders.length > 0 ? verifiedProviders : providers.data ?? [];

  const genreList = useMemo(() => genres.data?.items ?? [], [genres.data]);
  const genreName = useMemo(() => {
    const map = new Map<number, string>();
    for (const genre of genreList) map.set(genre.id, genre.name);
    return map;
  }, [genreList]);
  const visibleGenres = genreQuery.trim()
    ? genreList.filter((genre) =>
        genre.name.toLowerCase().includes(genreQuery.trim().toLowerCase()),
      )
    : genreList;

  const selectedProvider = providerOptions.find((provider) => provider.id === providerId);
  const selectedSources = (collections.data ?? []).filter((item) =>
    sourceCollectionIds.includes(item.id),
  );

  if (isEdit && collection.isPending) {
    return (
      <>
        <PageHeader title="Modifica collezione" />
        <TableSkeleton rows={4} />
      </>
    );
  }
  if (isEdit && collection.isError) {
    return (
      <>
        <PageHeader title="Modifica collezione" />
        <ErrorState error={collection.error} onRetry={() => void collection.refetch()} />
      </>
    );
  }

  const onSubmit = () => {
    setFormError(null);
    if (kind !== "CUSTOM_FILTER" && !providerId) {
      setFormError("Seleziona un provider.");
      return;
    }
    if (!name.trim()) {
      setFormError("Inserisci un nome.");
      return;
    }
    if (!isEdit && !slug.trim()) {
      setFormError("Inserisci uno slug.");
      return;
    }
    if (kind === "RECENTLY_ADDED" && !sourceCollectionId) {
      setFormError("Seleziona la collezione catalogo da usare come baseline.");
      return;
    }
    if (kind === "CUSTOM_FILTER" && sourceCollectionIds.length === 0) {
      setFormError("Seleziona almeno una collezione sorgente per la raccolta combinata.");
      return;
    }
    const days = Number(windowDays);
    if (kind === "RECENTLY_ADDED" && (!Number.isFinite(days) || days < 1 || days > 90)) {
      setFormError("La finestra deve essere tra 1 e 90 giorni.");
      return;
    }
    const base: CollectionCreatePayload = {
      ...(providerId ? { provider_id: providerId } : {}),
      media_type: mediaType,
      name: name.trim(),
      slug: slug.trim(),
      kind,
      genre_ids: genreIds,
      monetization_type: monetization,
      description: description.trim() || undefined,
      is_active: isActive,
      ...(kind === "RECENTLY_ADDED"
        ? { window_days: days, source_collection_id: sourceCollectionId }
        : {}),
      ...(kind === "CUSTOM_FILTER"
        ? {
            source_collection_ids: sourceCollectionIds,
            exclude_genre_ids: excludeGenreIds,
            min_vote_average: minVoteAverage ? Number(minVoteAverage) : undefined,
            min_vote_count: minVoteCount ? Number(minVoteCount) : undefined,
            year_from: yearFrom ? Number(yearFrom) : undefined,
            year_to: yearTo ? Number(yearTo) : undefined,
            original_language: originalLanguage.trim() || undefined,
            local_sort_by: localSortBy,
          }
        : {}),
      ...(kind === "CATALOG" && sharedSnapshotId
        ? { shared_snapshot_collection_id: sharedSnapshotId }
        : {}),
    };
    if (isEdit) {
      update.mutate(base, { onSuccess: () => navigate("/app/collections") });
    } else {
      create.mutate(base, { onSuccess: () => navigate("/app/collections") });
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Costruttore"
        title={isEdit ? "Modifica collezione" : "Nuova collezione"}
        description="Provider, tipo media, generi e filtri locali: l'anteprima a destra si aggiorna mentre scegli."
        actions={
          <Link
            to="/app/collections"
            className="inline-flex min-h-11 items-center rounded-md border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-muted"
          >
            Annulla
          </Link>
        }
      />

      {create.isError ? (
        <div className="mb-4">
          <ErrorState error={create.error} />
        </div>
      ) : null}
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

      <div
        data-testid="collection-builder"
        className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
      >
        <div className="space-y-4">
          <BuilderSection
            step={1}
            title="Provider e tipo di contenuto"
            description="Il provider determina il catalogo TMDb; film e serie restano separati."
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="collection-provider" label="Provider">
                <Select
                  id="collection-provider"
                  value={providerId}
                  disabled={isEdit || kind === "CUSTOM_FILTER"}
                  onChange={(event) => {
                    setProviderId(event.target.value);
                    setSourceCollectionId("");
                    setSourceCollectionIds([]);
                    setSharedSnapshotId("");
                  }}
                >
                  <option value="">Seleziona…</option>
                  {providerOptions.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field id="collection-kind" label="Costruzione">
                <Select
                  id="collection-kind"
                  value={kind}
                  disabled={isEdit}
                  onChange={(event) => setKind(event.target.value as CollectionKindValue)}
                >
                  <option value="CATALOG">Catalogo / genere</option>
                  <option value="RECENTLY_ADDED">Appena rilevati (storico)</option>
                  <option value="CUSTOM_FILTER">Combinata multi-provider</option>
                </Select>
              </Field>
            </div>

            <div className="mt-4">
              <p className="mb-2 text-xs font-medium text-ink-muted">Tipo media</p>
              <div className="flex flex-wrap gap-2">
                <ToggleChip
                  testId="media-type-MOVIE"
                  pressed={mediaType === "MOVIE"}
                  disabled={isEdit}
                  onClick={() => {
                    setMediaType("MOVIE");
                    setGenreIds([]);
                    setExcludeGenreIds([]);
                    setSourceCollectionId("");
                    setSourceCollectionIds([]);
                    setSharedSnapshotId("");
                  }}
                >
                  Film
                </ToggleChip>
                <ToggleChip
                  testId="media-type-SHOW"
                  pressed={mediaType === "SHOW"}
                  disabled={isEdit}
                  onClick={() => {
                    setMediaType("SHOW");
                    setGenreIds([]);
                    setExcludeGenreIds([]);
                    setSourceCollectionId("");
                    setSourceCollectionIds([]);
                    setSharedSnapshotId("");
                  }}
                >
                  Serie TV
                </ToggleChip>
              </div>
            </div>
          </BuilderSection>

          <BuilderSection
            step={2}
            title="Generi TMDb"
            description="Nessuna selezione = catalogo completo del provider."
          >
            <div className="relative mb-3">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
                <IconSearch />
              </span>
              <Input
                value={genreQuery}
                onChange={(event) => setGenreQuery(event.target.value)}
                placeholder="Cerca un genere…"
                aria-label="Cerca un genere TMDb"
                className="pl-9"
              />
            </div>
            {genres.isPending ? (
              <p className="text-xs text-ink-muted">Caricamento generi…</p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {visibleGenres.map((genre) => (
                <ToggleChip
                  key={genre.id}
                  testId={`genre-${genre.id}`}
                  pressed={genreIds.includes(genre.id)}
                  onClick={() =>
                    setGenreIds((current) =>
                      current.includes(genre.id)
                        ? current.filter((value) => value !== genre.id)
                        : [...current, genre.id],
                    )
                  }
                >
                  {genre.name}
                </ToggleChip>
              ))}
            </div>
            {genreIds.length > 0 ? (
              <p className="mt-3 text-xs text-ink-muted">
                {formatNumber(genreIds.length)} generi inclusi.
              </p>
            ) : null}

            {kind === "CUSTOM_FILTER" ? (
              <div className="mt-5 border-t border-line pt-4">
                <p className="mb-1 text-xs font-medium text-ink-muted">
                  Generi da escludere
                </p>
                <p className="mb-2 text-xs text-ink-faint">
                  Applicati dopo l&apos;unione degli snapshot delle collezioni sorgente.
                </p>
                <div className="flex flex-wrap gap-2">
                  {visibleGenres.map((genre) => (
                    <ToggleChip
                      key={`exclude-${genre.id}`}
                      testId={`exclude-genre-${genre.id}`}
                      pressed={excludeGenreIds.includes(genre.id)}
                      onClick={() =>
                        setExcludeGenreIds((current) =>
                          current.includes(genre.id)
                            ? current.filter((value) => value !== genre.id)
                            : [...current, genre.id],
                        )
                      }
                    >
                      {genre.name}
                    </ToggleChip>
                  ))}
                </div>
              </div>
            ) : null}
          </BuilderSection>

          <BuilderSection
            step={3}
            title="Filtri e finestra"
            description="Monetizzazione, filtri locali e finestra per le liste 'Appena rilevati'."
          >
            <p className="mb-2 text-xs font-medium text-ink-muted">Monetizzazione</p>
            <div className="flex flex-wrap gap-2">
              {MONETIZATION_OPTIONS.map((option) => (
                <ToggleChip
                  key={option.value}
                  pressed={monetization === option.value}
                  onClick={() => setMonetization(option.value)}
                >
                  {option.label}
                </ToggleChip>
              ))}
            </div>

            {kind === "CUSTOM_FILTER" ? (
              <div className="mt-5 space-y-4 border-t border-line pt-4">
                <div>
                  <p className="mb-1 text-xs font-medium text-ink-muted">
                    Collezioni sorgente (unione)
                  </p>
                  <p className="mb-2 text-xs text-ink-faint">
                    Unisce gli snapshot validi e applica i filtri in PostgreSQL. Nessuna
                    chiamata TMDb aggiuntiva.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {(collections.data ?? [])
                      .filter((item) => item.id !== collectionId)
                      .map((item) => (
                        <ToggleChip
                          key={item.id}
                          testId={`source-collection-${item.id}`}
                          pressed={sourceCollectionIds.includes(item.id)}
                          onClick={() =>
                            setSourceCollectionIds((current) =>
                              current.includes(item.id)
                                ? current.filter((value) => value !== item.id)
                                : [...current, item.id],
                            )
                          }
                        >
                          <IconLayers />
                          {item.name} ({collectionProviderName(item)})
                        </ToggleChip>
                      ))}
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <Field id="local-vote-average" label="Voto medio minimo">
                    <Input
                      id="local-vote-average"
                      type="number"
                      min={0}
                      max={10}
                      step="0.1"
                      value={minVoteAverage}
                      onChange={(event) => setMinVoteAverage(event.target.value)}
                    />
                  </Field>
                  <Field id="local-vote-count" label="Voti minimi">
                    <Input
                      id="local-vote-count"
                      type="number"
                      min={0}
                      value={minVoteCount}
                      onChange={(event) => setMinVoteCount(event.target.value)}
                    />
                  </Field>
                  <Field
                    id="local-language"
                    label="Lingua originale"
                    hint="Codice ISO, es. it o en."
                  >
                    <Input
                      id="local-language"
                      value={originalLanguage}
                      onChange={(event) => setOriginalLanguage(event.target.value)}
                    />
                  </Field>
                  <Field id="local-year-from" label="Anno da">
                    <Input
                      id="local-year-from"
                      type="number"
                      value={yearFrom}
                      onChange={(event) => setYearFrom(event.target.value)}
                    />
                  </Field>
                  <Field id="local-year-to" label="Anno a">
                    <Input
                      id="local-year-to"
                      type="number"
                      value={yearTo}
                      onChange={(event) => setYearTo(event.target.value)}
                    />
                  </Field>
                  <Field id="local-sort" label="Ordinamento locale">
                    <Select
                      id="local-sort"
                      value={localSortBy}
                      onChange={(event) => setLocalSortBy(event.target.value)}
                    >
                      {SORT_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
              </div>
            ) : null}

            {kind === "RECENTLY_ADDED" ? (
              <div className="mt-5 grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
                <Field
                  id="collection-source"
                  label="Collezione baseline"
                  hint="Catalogo completo dello stesso provider e tipo media."
                >
                  <Select
                    id="collection-source"
                    value={sourceCollectionId}
                    onChange={(event) => setSourceCollectionId(event.target.value)}
                  >
                    <option value="">Seleziona…</option>
                    {fullCatalogs.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  id="collection-window"
                  label="Finestra (giorni)"
                  hint="Titoli con first_seen_at successivo alla baseline."
                >
                  <Input
                    id="collection-window"
                    type="number"
                    min={1}
                    max={90}
                    value={windowDays}
                    onChange={(event) => setWindowDays(event.target.value)}
                  />
                </Field>
                <div className="flex flex-wrap gap-2 sm:col-span-2">
                  {[7, 14, 30, 60].map((days) => (
                    <ToggleChip
                      key={days}
                      pressed={windowDays === String(days)}
                      onClick={() => setWindowDays(String(days))}
                    >
                      {days} giorni
                    </ToggleChip>
                  ))}
                </div>
              </div>
            ) : null}

            {kind === "CATALOG" ? (
              <div className="mt-5 border-t border-line pt-4">
                <Field
                  id="collection-shared"
                  label="Snapshot condiviso (opzionale)"
                  hint="Riusa uno snapshot catalogo completo per evitare chiamate TMDb ridondanti."
                >
                  <Select
                    id="collection-shared"
                    value={sharedSnapshotId}
                    onChange={(event) => setSharedSnapshotId(event.target.value)}
                  >
                    <option value="">Nessuno (acquisisci da TMDb)</option>
                    {fullCatalogs.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            ) : null}
          </BuilderSection>

          <BuilderSection step={4} title="Identità della collezione">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="collection-name" label="Nome">
                <Input
                  id="collection-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field id="collection-slug" label="Slug" hint="Solo minuscole, numeri e trattini.">
                <Input
                  id="collection-slug"
                  value={slug}
                  disabled={isEdit}
                  onChange={(event) => setSlug(event.target.value)}
                />
              </Field>
            </div>
            <div className="mt-4">
              <Field id="collection-description" label="Descrizione (facoltativa)">
                <Textarea
                  id="collection-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={2}
                />
              </Field>
            </div>
            <div className="mt-4 border-t border-line pt-4">
              <Checkbox
                id="collection-active"
                label="Collezione attiva"
                checked={isActive}
                onChange={(event) => setIsActive(event.target.checked)}
              />
            </div>
          </BuilderSection>

          <div className="flex flex-wrap gap-2">
            <Button
              onClick={onSubmit}
              busy={create.isPending || update.isPending}
              data-testid="collection-submit"
            >
              {isEdit ? "Salva modifiche" : "Crea collezione"}
            </Button>
            <Button variant="secondary" onClick={() => navigate("/app/collections")}>
              Annulla
            </Button>
          </div>
        </div>

        <aside
          data-testid="collection-criteria-preview"
          aria-label="Anteprima criteri"
          className="lg:sticky lg:top-20 lg:self-start"
        >
          <Card className="p-4">
            <div className="flex items-center gap-2">
              <span className="text-accent">
                <IconFilter />
              </span>
              <h2 className="text-sm font-semibold text-ink">Anteprima criteri</h2>
            </div>
            <dl className="mt-3">
              <PreviewRow
                label="Provider"
                value={selectedProvider?.name ?? (providerId ? providerId.slice(0, 8) : "—")}
              />
              <PreviewRow label="Tipo" value={mediaType === "MOVIE" ? "Film" : "Serie TV"} />
              <PreviewRow label="Costruzione" value={KIND_LABELS[kind]} />
              <PreviewRow
                label="Monetizzazione"
                value={
                  MONETIZATION_OPTIONS.find((option) => option.value === monetization)
                    ?.label ?? monetization
                }
              />
              <PreviewRow
                label="Generi inclusi"
                value={
                  genreIds.length === 0
                    ? "Tutti"
                    : `${formatNumber(genreIds.length)}: ${genreIds
                        .map((id) => genreName.get(id) ?? id)
                        .join(", ")}`
                }
              />
              {kind === "CUSTOM_FILTER" ? (
                <>
                  <PreviewRow
                    label="Generi esclusi"
                    value={
                      excludeGenreIds.length === 0
                        ? "Nessuno"
                        : excludeGenreIds.map((id) => genreName.get(id) ?? id).join(", ")
                    }
                  />
                  <PreviewRow
                    label="Sorgenti"
                    value={
                      selectedSources.length === 0
                        ? "Nessuna"
                        : selectedSources.map((item) => item.name).join(" + ")
                    }
                  />
                  <PreviewRow
                    label="Voto / voti"
                    value={`${minVoteAverage || "—"} / ${minVoteCount || "—"}`}
                  />
                  <PreviewRow
                    label="Anni"
                    value={`${yearFrom || "—"} → ${yearTo || "—"}`}
                  />
                  <PreviewRow label="Lingua" value={originalLanguage || "Qualsiasi"} />
                  <PreviewRow
                    label="Ordinamento"
                    value={
                      SORT_OPTIONS.find((option) => option.value === localSortBy)?.label ??
                      localSortBy
                    }
                  />
                </>
              ) : null}
              {kind === "RECENTLY_ADDED" ? (
                <>
                  <PreviewRow
                    label="Baseline"
                    value={
                      fullCatalogs.find((item) => item.id === sourceCollectionId)?.name ??
                      "Da selezionare"
                    }
                  />
                  <PreviewRow label="Finestra" value={`${windowDays} giorni`} />
                </>
              ) : null}
              {kind === "CATALOG" ? (
                <PreviewRow
                  label="Snapshot condiviso"
                  value={
                    sharedSnapshotId
                      ? (fullCatalogs.find((item) => item.id === sharedSnapshotId)?.name ??
                        sharedSnapshotId.slice(0, 8))
                      : "Nessuno"
                  }
                />
              ) : null}
              <PreviewRow label="Stato" value={isActive ? "Attiva" : "Disattivata"} />
            </dl>

            <div className="mt-4 rounded-md border border-line bg-surface-muted p-3 text-xs text-ink-muted">
              <p className="flex items-center gap-1 font-medium text-ink">
                Pipeline
                <IconArrowRight />
              </p>
              <p className="mt-1">
                Snapshot TMDb → filtri locali → lista MDBList. I filtri locali non generano
                chiamate aggiuntive.
              </p>
            </div>

            <Button
              className="mt-4 w-full"
              onClick={onSubmit}
              busy={create.isPending || update.isPending}
              data-testid="collection-submit-preview"
            >
              {isEdit ? "Salva modifiche" : "Crea collezione"}
            </Button>
          </Card>
        </aside>
      </div>
    </>
  );
}
