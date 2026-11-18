import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  useCreateCollection,
  useUpdateCollection,
} from "../api/mutations";
import {
  useCollection,
  useCollections,
  useGenres,
  useProviders,
  useSettings,
  useSources,
} from "../api/queries";
import type {
  BuilderSource,
  Collection,
  CollectionKind,
  CombineMode,
  MediaType,
  OfferType,
} from "../api/types";
import { CollectionSourceBadge } from "../components/ui/badges";
import { SnapshotStatusPill } from "../components/ui/status-pill";
import { collectionProviderName } from "../lib/collections";
import {
  buildCollectionPayload,
  builderProvenanceLabel,
  resolveDefaultSource,
} from "../lib/collection-builder";
import {
  JUSTWATCH_KINDS,
  isJustWatchSource,
  isVerifiedJustWatchProvider,
  justWatchBindingNotice,
} from "../lib/justwatch";
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

const KIND_LABELS: Record<CollectionKind, string> = {
  CATALOG: "Catalogo / genere",
  RECENTLY_ADDED: "Appena rilevati",
  CUSTOM_FILTER: "Combinata multi-provider",
  CHART: "Classifica",
  UPCOMING: "In arrivo",
};

const JUSTWATCH_KIND_LABELS: Record<CollectionKind, string> = {
  CATALOG: "Catalogo",
  RECENTLY_ADDED: "Novità",
  CUSTOM_FILTER: "Combinata multi-provider",
  CHART: "Classifica",
  UPCOMING: "In arrivo",
};

const MONETIZATION_OPTIONS = [
  { value: "FLATRATE", label: "Flatrate" },
  { value: "RENT", label: "Noleggio" },
  { value: "BUY", label: "Acquisto" },
  { value: "ADS", label: "Con pubblicità" },
  { value: "FREE", label: "Gratis" },
];

const SOURCE_OPTIONS: readonly {
  value: BuilderSource;
  label: string;
  description: string;
}[] = [
  {
    value: "justwatch",
    label: "JustWatch",
    description: "Aggregatore: catalogo, novità, in arrivo e classifiche.",
  },
  {
    value: "tmdb",
    label: "TMDb",
    description: "Catalogo ufficiale TMDb con filtri locali.",
  },
  {
    value: "combined",
    label: "Combinata locale",
    description: "Unione o intersezione di snapshot JustWatch e TMDb.",
  },
];

const COMBINE_MODE_OPTIONS: readonly { value: CombineMode; label: string }[] = [
  { value: "UNION", label: "Unione" },
  { value: "INTERSECTION", label: "Intersezione" },
];

const COLLECTION_KINDS: readonly CollectionKind[] = [
  "CATALOG",
  "RECENTLY_ADDED",
  "CUSTOM_FILTER",
  "CHART",
  "UPCOMING",
];

function isCollectionKind(value: string | null): value is CollectionKind {
  return value != null && COLLECTION_KINDS.includes(value as CollectionKind);
}

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
  const [searchParams] = useSearchParams();
  const querySource = searchParams.get("source") ?? searchParams.get("source_key");
  const initialSource: BuilderSource =
    querySource === "tmdb" || querySource === "justwatch" || querySource === "combined"
      ? querySource
      : "justwatch";
  const kindParam = searchParams.get("kind");
  const initialKind: CollectionKind = isCollectionKind(kindParam)
    ? kindParam
    : initialSource === "combined"
      ? "CUSTOM_FILTER"
      : "CATALOG";
  const initialMedia: MediaType =
    searchParams.get("media_type") === "SHOW" ? "SHOW" : "MOVIE";
  const collection = useCollection(collectionId);
  const providers = useProviders("IT");
  const sources = useSources();
  const settings = useSettings();
  const create = useCreateCollection();
  const update = useUpdateCollection(collectionId ?? "");
  const navigate = useNavigate();

  const [sourceKey, setSourceKey] = useState<BuilderSource>(initialSource);
  const [sourceTouched, setSourceTouched] = useState(Boolean(querySource));
  const [providerId, setProviderId] = useState(searchParams.get("provider") ?? "");
  const [mediaType, setMediaType] = useState<MediaType>(initialMedia);
  const [kind, setKind] = useState<CollectionKind>(initialKind);
  const [combineMode, setCombineMode] = useState<CombineMode>(
    searchParams.get("combine_mode") === "INTERSECTION" ? "INTERSECTION" : "UNION",
  );
  const [justWatchOfferMode, setJustWatchOfferMode] = useState<"FLATRATE" | "ALL">(
    "FLATRATE",
  );
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [monetization, setMonetization] = useState<OfferType>("FLATRATE");
  const [genreIds, setGenreIds] = useState<number[]>([]);
  const [sourceCollectionId, setSourceCollectionId] = useState("");
  const [sourceCollectionIds, setSourceCollectionIds] = useState<string[]>(
    searchParams.getAll("source_collection_ids"),
  );
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

  const defaultSource = resolveDefaultSource(settings.data?.default_source);
  const isCombined = sourceKey === "combined";

  useEffect(() => {
    if (isEdit || sourceTouched || !settings.isSuccess) return;
    setSourceKey(defaultSource);
  }, [defaultSource, isEdit, sourceTouched, settings.isSuccess]);

  const genres = useGenres(mediaType);
  const collections = useCollections({
    providerId: kind === "CUSTOM_FILTER" || isCombined ? "" : providerId,
    mediaType,
  });
  const fullCatalogs = useMemo(
    () => (collections.data ?? []).filter(isFullCatalog),
    [collections.data],
  );

  useEffect(() => {
    const data = collection.data;
    if (!data) return;
    setSourceKey(
      data.source_key === "justwatch"
        ? "justwatch"
        : data.source_key === "combined"
          ? "combined"
          : "tmdb",
    );
    setSourceTouched(true);
    setProviderId(data.provider_id);
    setMediaType(data.media_type);
    setKind(data.kind);
    setName(data.name);
    setSlug(data.slug);
    setDescription(data.description ?? "");
    setMonetization((data.offer_types[0] as OfferType | undefined) ?? "FLATRATE");
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
    setCombineMode(
      data.filters?.combine_mode === "INTERSECTION" ? "INTERSECTION" : "UNION",
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

  const verifiedJustWatchProviders = useMemo(
    () =>
      (providers.data ?? []).filter((provider) =>
        isVerifiedJustWatchProvider(provider, mediaType),
      ),
    [providers.data, mediaType],
  );

  const providerOptions = isCombined
    ? (providers.data ?? [])
    : sourceKey === "justwatch"
      ? verifiedJustWatchProviders
      : verifiedProviders.length > 0
        ? verifiedProviders
        : (providers.data ?? []);

  const justwatchSource = (sources.data ?? []).find((source) => source.key === "justwatch");
  const verifiedJustWatchMappings = justwatchSource?.justwatch?.mappings.length ?? 0;
  const isJustWatch = isJustWatchSource(sourceKey);

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
  const offerOptions = useMemo(() => {
    if (!isJustWatch) return MONETIZATION_OPTIONS;
    const supported = (selectedProvider?.justwatch_monetization_types ?? []).map((value) =>
      value.toUpperCase(),
    );
    if (supported.length === 0) {
      return MONETIZATION_OPTIONS.filter((option) => option.value === "FLATRATE");
    }
    return MONETIZATION_OPTIONS.filter((option) => supported.includes(option.value));
  }, [isJustWatch, selectedProvider]);
  const selectedSources = (collections.data ?? []).filter((item) =>
    sourceCollectionIds.includes(item.id),
  );
  const sourceCollectionOptions = (collections.data ?? []).filter(
    (item) => item.id !== collectionId,
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
    if (!isCombined && kind !== "CUSTOM_FILTER" && !providerId) {
      setFormError("Seleziona un provider.");
      return;
    }
    if (isCombined) {
      const selected = (collections.data ?? []).filter((item) =>
        sourceCollectionIds.includes(item.id),
      );
      const hasJustWatch = selected.some((item) =>
        isJustWatchSource(item.source_key),
      );
      const hasTmdb = selected.some((item) => item.source_key === "tmdb");
      if (sourceCollectionIds.length < 2 || !hasJustWatch || !hasTmdb) {
        setFormError(
          "Seleziona almeno una collezione JustWatch e una TMDb per la combinata locale.",
        );
        return;
      }
    }
    if (sourceKey === "justwatch" && !providerOptions.some((item) => item.id === providerId)) {
      setFormError("Seleziona un provider con mapping JustWatch verificato.");
      return;
    }
    if (sourceKey === "justwatch" && !JUSTWATCH_KINDS.includes(kind)) {
      setFormError("JustWatch supporta Catalogo, Novità, In arrivo e Classifica.");
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
    if (sourceKey === "tmdb" && kind === "RECENTLY_ADDED" && !sourceCollectionId) {
      setFormError("Seleziona la collezione catalogo da usare come baseline.");
      return;
    }
    if (sourceKey === "tmdb" && kind === "CUSTOM_FILTER" && sourceCollectionIds.length === 0) {
      setFormError("Seleziona almeno una collezione sorgente per la raccolta combinata.");
      return;
    }
    const days = Number(windowDays);
    if (
      sourceKey === "tmdb" &&
      kind === "RECENTLY_ADDED" &&
      (!Number.isFinite(days) || days < 1 || days > 90)
    ) {
      setFormError("La finestra deve essere tra 1 e 90 giorni.");
      return;
    }
    if (sourceKey === "justwatch" && yearFrom && yearTo && Number(yearFrom) > Number(yearTo)) {
      setFormError("L'anno iniziale non può superare quello finale.");
      return;
    }
    const base = buildCollectionPayload({
      sourceKey,
      combineMode,
      justWatchOfferMode,
      providerId,
      mediaType,
      kind,
      name,
      slug,
      description,
      offerType: monetization,
      genreIds,
      sourceCollectionId,
      sourceCollectionIds,
      sharedSnapshotId,
      excludeGenreIds,
      minVoteAverage,
      minVoteCount,
      yearFrom,
      yearTo,
      originalLanguage,
      localSortBy,
      windowDays,
      isActive,
    });
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
            description={
              isCombined
                ? "La combinata locale fonde o interseca gli snapshot JustWatch e TMDb già acquisiti."
                : isJustWatch
                  ? "JustWatch usa un mapping provider verificato; film e serie restano separati."
                  : "Il provider determina il catalogo TMDb; film e serie restano separati."
            }
          >
            <div className="mb-4">
              <p className="mb-2 text-xs font-medium text-ink-muted">Fonte</p>
              <div
                role="radiogroup"
                aria-label="Fonte della collezione"
                className="grid gap-2 sm:grid-cols-3"
              >
                {SOURCE_OPTIONS.map((option) => {
                  const selected = sourceKey === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      disabled={isEdit}
                      data-testid={`builder-source-${option.value}`}
                      onClick={() => {
                        setSourceTouched(true);
                        setSourceKey(option.value);
                        setProviderId("");
                        setKind(option.value === "combined" ? "CUSTOM_FILTER" : "CATALOG");
                        setGenreIds([]);
                        setExcludeGenreIds([]);
                        setSourceCollectionId("");
                        setSourceCollectionIds([]);
                        setSharedSnapshotId("");
                        setMonetization("FLATRATE");
                        setJustWatchOfferMode("FLATRATE");
                      }}
                      className={`flex min-h-20 flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                        selected
                          ? "border-accent bg-accent-soft"
                          : "border-line bg-surface hover:border-line-strong"
                      }`}
                    >
                      <span className="flex w-full items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-ink">{option.label}</span>
                        {defaultSource === option.value ? (
                          <span className="rounded-full border border-accent/40 bg-surface px-2 py-0.5 text-[0.65rem] font-semibold text-accent">
                            Predefinito
                          </span>
                        ) : null}
                      </span>
                      <span className="text-xs text-ink-muted">{option.description}</span>
                    </button>
                  );
                })}
              </div>
              {isEdit ? (
                <p className="mt-1 text-xs text-ink-muted">
                  La fonte di una collezione esistente non è modificabile.
                </p>
              ) : null}
            </div>

            {isJustWatch ? (
              <div className="mb-4">
                <InlineNotice tone="info">
                  JustWatch è un aggregatore: niente date di aggiunta, niente Sync MDBList
                  automatica. {justWatchBindingNotice()}
                </InlineNotice>
              </div>
            ) : null}
            {isCombined ? (
              <div className="mb-4">
                <InlineNotice tone="info">
                  La combinata locale usa solo snapshot già acquisiti: nessuna chiamata
                  aggiuntiva a JustWatch o TMDb.
                </InlineNotice>
              </div>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                id="collection-provider"
                label="Provider"
                hint={
                  isCombined
                    ? "Facoltativo: il provider principale può essere derivato dalle sorgenti."
                    : isJustWatch
                      ? providerOptions.length === 0
                        ? "Nessun provider con mapping JustWatch verificato."
                        : `${formatNumber(verifiedJustWatchMappings)} mapping JustWatch verificati in IT.`
                      : undefined
                }
              >
                <Select
                  id="collection-provider"
                  value={providerId}
                  disabled={isEdit || (!isJustWatch && !isCombined && kind === "CUSTOM_FILTER")}
                  onChange={(event) => {
                    setProviderId(event.target.value);
                    setSourceCollectionId("");
                    setSourceCollectionIds([]);
                    setSharedSnapshotId("");
                    setMonetization("FLATRATE");
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
                  onChange={(event) => setKind(event.target.value as CollectionKind)}
                >
                  {isCombined ? (
                    <option value="CUSTOM_FILTER">Combinata locale (JustWatch + TMDb)</option>
                  ) : isJustWatch ? (
                    <>
                      <option value="CATALOG">Catalogo</option>
                      <option value="RECENTLY_ADDED">Novità</option>
                      <option value="UPCOMING">In arrivo</option>
                      <option value="CHART">Classifica</option>
                    </>
                  ) : (
                    <>
                      <option value="CATALOG">Catalogo / genere</option>
                      <option value="RECENTLY_ADDED">Appena rilevati (storico)</option>
                      <option value="CUSTOM_FILTER">Combinata multi-provider</option>
                    </>
                  )}
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

          {sourceKey === "tmdb" ? (
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

          ) : null}

          <BuilderSection
            step={3}
            title="Filtri e finestra"
            description={
              isCombined
                ? "Scegli le collezioni sorgente e come combinare i loro snapshot."
                : isJustWatch
                  ? "Tipo di offerta e anni; niente filtri TMDb o locali."
                  : "Monetizzazione, filtri locali e finestra per le liste 'Appena rilevati'."
            }
          >
            {isJustWatch ? (
              <>
                <p className="mb-2 text-xs font-medium text-ink-muted">
                  Tipo di offerta (default Flatrate)
                </p>
                <div className="flex flex-wrap gap-2">
                  <ToggleChip
                    testId="justwatch-offer-flatrate"
                    pressed={justWatchOfferMode === "FLATRATE"}
                    onClick={() => setJustWatchOfferMode("FLATRATE")}
                  >
                    Flatrate
                  </ToggleChip>
                  <ToggleChip
                    testId="justwatch-offer-all"
                    pressed={justWatchOfferMode === "ALL"}
                    onClick={() => setJustWatchOfferMode("ALL")}
                  >
                    Tutte le offerte
                  </ToggleChip>
                </div>
              </>
            ) : null}
            {sourceKey === "tmdb" ? (
              <>
                <p className="mb-2 text-xs font-medium text-ink-muted">Monetizzazione</p>
                <div className="flex flex-wrap gap-2">
                  {offerOptions.map((option) => (
                    <ToggleChip
                      key={option.value}
                      testId={`offer-${option.value}`}
                      pressed={monetization === option.value}
                      onClick={() => setMonetization(option.value as OfferType)}
                    >
                      {option.label}
                    </ToggleChip>
                  ))}
                </div>
              </>
            ) : null}

            {isJustWatch ? (
              <div className="mt-5 grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
                <Field id="justwatch-year-from" label="Anno da" hint="Facoltativo.">
                  <Input
                    id="justwatch-year-from"
                    type="number"
                    min={1900}
                    max={2100}
                    value={yearFrom}
                    onChange={(event) => setYearFrom(event.target.value)}
                  />
                </Field>
                <Field id="justwatch-year-to" label="Anno a" hint="Facoltativo.">
                  <Input
                    id="justwatch-year-to"
                    type="number"
                    min={1900}
                    max={2100}
                    value={yearTo}
                    onChange={(event) => setYearTo(event.target.value)}
                  />
                </Field>
              </div>
            ) : null}

            {isCombined ? (
              <div className="mt-5 space-y-4 border-t border-line pt-4">
                <div>
                  <p className="mb-1 text-xs font-medium text-ink-muted">Modalità</p>
                  <div className="flex flex-wrap gap-2">
                    {COMBINE_MODE_OPTIONS.map((option) => (
                      <ToggleChip
                        key={option.value}
                        testId={`combine-mode-${option.value}`}
                        pressed={combineMode === option.value}
                        onClick={() => setCombineMode(option.value)}
                      >
                        {option.label}
                      </ToggleChip>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-ink-muted">
                    Collezioni sorgente (JustWatch + TMDb)
                  </p>
                  <p className="mb-2 text-xs text-ink-faint">
                    Servono almeno una collezione JustWatch e una TMDb. Lo stato mostra
                    l&apos;ultimo snapshot valido disponibile.
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {sourceCollectionOptions.map((item) => {
                      const snapshot = item.last_valid_snapshot ?? item.latest_snapshot;
                      return (
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
                          className="justify-between"
                        >
                          <span className="flex items-center gap-1.5">
                            <IconLayers />
                            {item.name} ({collectionProviderName(item)})
                          </span>
                          {snapshot ? (
                            <SnapshotStatusPill status={snapshot.status} />
                          ) : (
                            <span className="text-ink-faint">Nessuno snapshot</span>
                          )}
                        </ToggleChip>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : null}

            {sourceKey === "tmdb" && kind === "CUSTOM_FILTER" ? (
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

            {sourceKey === "tmdb" && kind === "RECENTLY_ADDED" ? (
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

            {sourceKey === "tmdb" && kind === "CATALOG" ? (
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
            <div className="mt-3 rounded-md border border-line bg-surface-muted p-3">
              <p className="mb-1 text-xs font-medium text-ink-muted">
                Badge di provenienza (anteprima)
              </p>
              <CollectionSourceBadge
                label={builderProvenanceLabel(sourceKey, kind)}
                tone={isCombined ? "info" : isJustWatch ? "warning" : "info"}
              />
            </div>
            <dl className="mt-3">
              <PreviewRow
                label="Fonte"
                value={isCombined ? "Combinata locale" : isJustWatch ? "JustWatch" : "TMDb"}
              />
              <PreviewRow
                label="Provider"
                value={selectedProvider?.name ?? (providerId ? providerId.slice(0, 8) : "—")}
              />
              <PreviewRow label="Tipo" value={mediaType === "MOVIE" ? "Film" : "Serie TV"} />
              <PreviewRow
                label="Costruzione"
                value={
                  isCombined
                    ? "Combinata locale (JustWatch + TMDb)"
                    : (isJustWatch ? JUSTWATCH_KIND_LABELS : KIND_LABELS)[kind]
                }
              />
              {isJustWatch ? (
                <PreviewRow
                  label="Offerta"
                  value={justWatchOfferMode === "ALL" ? "Tutte le offerte" : "Flatrate"}
                />
              ) : null}
              {sourceKey === "tmdb" ? (
                <PreviewRow
                  label="Monetizzazione"
                  value={
                    MONETIZATION_OPTIONS.find((option) => option.value === monetization)
                      ?.label ?? monetization
                  }
                />
              ) : null}
              {isJustWatch ? (
                <PreviewRow label="Anni" value={`${yearFrom || "—"} → ${yearTo || "—"}`} />
              ) : sourceKey === "tmdb" ? (
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
              ) : null}
              {isCombined ? (
                <>
                  <PreviewRow
                    label="Modalità"
                    value={
                      COMBINE_MODE_OPTIONS.find((option) => option.value === combineMode)
                        ?.label ?? combineMode
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
                  {selectedSources.map((item) => {
                    const snapshot = item.last_valid_snapshot ?? item.latest_snapshot;
                    return (
                      <PreviewRow
                        key={item.id}
                        label={item.name}
                        value={
                          snapshot ? (
                            <SnapshotStatusPill status={snapshot.status} />
                          ) : (
                            <span className="text-ink-faint">Nessuno snapshot</span>
                          )
                        }
                      />
                    );
                  })}
                </>
              ) : null}
              {sourceKey === "tmdb" && kind === "CUSTOM_FILTER" ? (
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
              {sourceKey === "tmdb" && kind === "RECENTLY_ADDED" ? (
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
              {sourceKey === "tmdb" && kind === "CATALOG" ? (
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
              {isCombined ? (
                <p className="mt-1">
                  Snapshot JustWatch + TMDb → {combineMode === "UNION" ? "unione" : "intersezione"}
                  → lista MDBList. Nessuna chiamata alle fonti.
                </p>
              ) : isJustWatch ? (
                <p className="mt-1">
                  Snapshot JustWatch → preview source-only. Sync MDBList disabilitata di
                  default: dry-run obbligatorio prima del primo run reale.
                </p>
              ) : (
                <p className="mt-1">
                  Snapshot TMDb → filtri locali → lista MDBList. I filtri locali non
                  generano chiamate aggiuntive.
                </p>
              )}
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
