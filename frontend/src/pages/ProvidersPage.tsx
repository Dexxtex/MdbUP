import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useBindings, useCollections, useProviderCatalog, useProviders } from "../hooks/queries";
import {
  useCreateProvider,
  useDeleteCollection,
  useDeleteProvider,
} from "../hooks/mutations";
import type {
  Collection,
  Provider,
  ProviderCandidate,
  ProviderCreatePayload,
  OfferType,
} from "../api/types";
import { CountrySelect } from "../components/ui/country-select";
import { DataTable, type Column } from "../components/ui/data-table";
import {
  EmptyState,
  ErrorState,
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
import { DEFAULT_COUNTRY } from "../lib/countries";
import { formatNumber } from "../lib/format";
import { hasJustWatchMapping } from "../lib/justwatch";
import { IconBuilding, IconGrid, IconLayers, IconTrash } from "../components/ui/icons";
import { ProviderMatrix } from "../components/providers/provider-matrix";
import { ProviderSuggest } from "../components/providers/provider-suggest";

/** Provider italiani noti: le chip compaiono solo se il backend li espone. */
const KNOWN_PROVIDERS = [
  "Netflix",
  "Prime Video",
  "Disney+",
  "Apple TV+",
  "NOW",
  "Mediaset Infinity",
  "RaiPlay",
];

const PROVIDER_KINDS: {
  value: ProviderCreatePayload["kind"];
  label: string;
  description: string;
}[] = [
  {
    value: "SVOD",
    label: "SVOD — Abbonamento",
    description: "Accesso incluso in un abbonamento mensile o annuale.",
  },
  {
    value: "TVOD",
    label: "TVOD — Noleggio/acquisto singolo",
    description: "Paghi solo il titolo che noleggi o acquisti.",
  },
  {
    value: "AVOD",
    label: "AVOD — Gratuito con pubblicità",
    description: "Catalogo gratuito finanziato dalla pubblicità.",
  },
  {
    value: "TVE",
    label: "TVE — TV Everywhere",
    description: "Accesso tramite l’abbonamento TV o pay-TV.",
  },
  {
    value: "STORE",
    label: "STORE — Negozio digitale",
    description: "Negozio di film e serie in acquisto.",
  },
  {
    value: "CINEMA",
    label: "CINEMA — Sala/catena",
    description: "Programmazione cinematografica, non streaming.",
  },
  {
    value: "CHANNEL",
    label: "CHANNEL — Canale/add-on",
    description: "Canale lineare o canale aggiuntivo di una piattaforma.",
  },
];

const OFFER_OPTIONS: { value: OfferType; label: string; description: string }[] = [
  { value: "FLATRATE", label: "FLATRATE", description: "Incluso nell’abbonamento." },
  { value: "RENT", label: "RENT", description: "Noleggio del singolo titolo." },
  { value: "BUY", label: "BUY", description: "Acquisto definitivo del titolo." },
  { value: "ADS", label: "ADS", description: "Visione gratuita con pubblicità." },
  { value: "FREE", label: "FREE", description: "Gratuito senza acquisto." },
];

const PROVIDER_SOURCE_ORDER = ["tmdb", "justwatch", "tvdb"] as const;

const STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;

interface SnapshotFreshness {
  lastValidAt: string | null;
  collections: number;
  stale: boolean;
}

function freshnessByProvider(collections: readonly Collection[]): Map<string, SnapshotFreshness> {
  const result = new Map<string, SnapshotFreshness>();
  for (const collection of collections) {
    const current = result.get(collection.provider_id) ?? {
      lastValidAt: null,
      collections: 0,
      stale: false,
    };
    current.collections += 1;
    const finishedAt = collection.last_valid_snapshot?.finished_at ?? null;
    if (finishedAt && (!current.lastValidAt || finishedAt > current.lastValidAt)) {
      current.lastValidAt = finishedAt;
    }
    result.set(collection.provider_id, current);
  }
  for (const value of result.values()) {
    value.stale =
      !value.lastValidAt || Date.now() - new Date(value.lastValidAt).getTime() > STALE_AFTER_MS;
  }
  return result;
}

function MappingCell({
  movieId,
  showId,
}: {
  movieId: string | null | undefined;
  showId: string | null | undefined;
}) {
  return (
    <div className="flex flex-col gap-1 text-xs">
      <span className="text-ink-muted">
        Film:{" "}
        <span className="font-mono text-ink">{movieId ?? "—"}</span>
      </span>
      <span className="text-ink-muted">
        Serie:{" "}
        <span className="font-mono text-ink">{showId ?? "—"}</span>
      </span>
    </div>
  );
}

function JustWatchMappingCell({ provider }: { provider: Provider }) {
  const mapped = hasJustWatchMapping(provider);
  const verified = provider.justwatch_verified === true && mapped;
  const label = verified
    ? "JustWatch verificato"
    : mapped
      ? "JustWatch da verificare"
      : "JustWatch non verificato";
  return (
    <div className="flex flex-col gap-1 text-xs">
      <StatusPill label={label} tone={verified ? "success" : "neutral"} />
      <span className="text-ink-muted">
        ID: <span className="font-mono text-ink">{provider.justwatch_provider_id ?? "—"}</span>
      </span>
      <span className="text-ink-muted">
        Offerte:{" "}
        <span className="text-ink">
          {provider.justwatch_monetization_types.length > 0
            ? provider.justwatch_monetization_types.join(", ")
            : "—"}
        </span>
      </span>
    </div>
  );
}

function ProviderCard({
  provider,
  freshness,
  collections,
  onDelete,
  onDeleteCollection,
  deleting,
  deletingCollectionId,
}: {
  provider: Provider;
  freshness: SnapshotFreshness | undefined;
  collections: readonly Collection[];
  onDelete: (provider: Provider) => void;
  onDeleteCollection: (collection: Collection) => void;
  deleting: boolean;
  deletingCollectionId: string | null;
}) {
  const linkedCollections = Math.max(
    provider.collections_count,
    collections.length,
    freshness?.collections ?? 0,
  );
  return (
    <article
      data-testid={`provider-card-${provider.slug}`}
      className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-4 shadow-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-ink">{provider.name}</h3>
          <p className="text-xs text-ink-muted">
            {provider.kind} · {provider.country_code}
          </p>
        </div>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-ink-muted">
          <IconBuilding />
        </span>
      </div>

      <div className="space-y-2">
        <div>
          <p className="mb-1 text-xs font-medium text-ink-muted">Mapping TMDb</p>
          <div className="flex flex-wrap gap-1.5">
            <StatusPill
              label={`Film TMDb ${provider.mapping_verified_movie ? "verificato" : "da verificare"}`}
              tone={provider.mapping_verified_movie ? "success" : "warning"}
            />
            <StatusPill
              label={`Serie TMDb ${provider.mapping_verified_tv ? "verificato" : "da verificare"}`}
              tone={provider.mapping_verified_tv ? "success" : "warning"}
            />
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium text-ink-muted">Mapping JustWatch</p>
          <JustWatchMappingCell provider={provider} />
        </div>
        {provider.tvdb_company_id ? (
          <div>
            <p className="mb-1 text-xs font-medium text-ink-muted">Company TheTVDB</p>
            <StatusPill
              label={`${provider.tvdb_company_id} · metadati, non disponibilità IT`}
              tone="neutral"
            />
          </div>
        ) : null}
      </div>

      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-xs text-ink-faint">Collezioni film</dt>
          <dd className="font-semibold tabular-nums text-ink">
            {formatNumber(provider.movie_collections)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-faint">Collezioni serie</dt>
          <dd className="font-semibold tabular-nums text-ink">
            {formatNumber(provider.show_collections)}
          </dd>
        </div>
      </dl>

      <div className="mt-auto space-y-1 border-t border-line pt-3">
        <p className="text-xs text-ink-faint">Ultimo snapshot valido</p>
        {freshness?.lastValidAt ? (
          <div className="flex flex-wrap items-center gap-2">
            <Timestamp value={freshness.lastValidAt} className="text-xs" />
            <StatusPill
              label={freshness.stale ? "Da aggiornare" : "Aggiornato"}
              tone={freshness.stale ? "warning" : "success"}
            />
          </div>
        ) : (
          <p className="text-xs text-ink-muted">Mai acquisito</p>
        )}
        <div className="mt-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-ink-muted">
              Collezioni locali ({formatNumber(collections.length)})
            </p>
            <Link
              to={`/app/collections?provider=${provider.id}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-accent underline"
            >
              <IconLayers />
              Apri elenco
            </Link>
          </div>
          {collections.length > 0 ? (
            <ul className="mt-1 max-h-44 space-y-1.5 overflow-y-auto pr-1">
              {collections.map((collection) => (
                <li
                  key={collection.id}
                  className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface-muted px-2 py-1.5"
                >
                  <div className="min-w-0">
                    <Link
                      to={`/app/collections/${collection.id}`}
                      className="block truncate text-xs font-medium text-ink underline"
                    >
                      {collection.name}
                    </Link>
                    <span className="text-[11px] text-ink-faint">
                      {collection.media_type === "MOVIE" ? "Film" : "Serie"}
                    </span>
                  </div>
                  <Button
                    variant="danger"
                    size="sm"
                    busy={deletingCollectionId === collection.id}
                    title={`Elimina ${collection.name} e i suoi dati locali; le liste MDBList remote non vengono toccate.`}
                    data-testid={`provider-collection-delete-${collection.slug}`}
                    onClick={() => onDeleteCollection(collection)}
                  >
                    <IconTrash />
                    Elimina
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-xs text-ink-muted">Nessuna collezione locale.</p>
          )}
        </div>
        <Button
          variant="danger"
          size="sm"
          className="mt-2 w-full"
          busy={deleting}
          title={
            linkedCollections > 0
              ? `Elimina ${provider.name} e le ${formatNumber(
                  linkedCollections,
                )} collezioni locali collegate.`
              : `Elimina ${provider.name}`
          }
          data-testid={`provider-delete-${provider.slug}`}
          onClick={() => onDelete(provider)}
        >
          <IconTrash />
          Elimina
        </Button>
      </div>
    </article>
  );
}

function providerColumns(
  freshness: Map<string, SnapshotFreshness>,
  onDelete: (provider: Provider) => void,
  deletingId: string | null,
): Column<Provider>[] {
  return [
    { key: "name", header: "Provider", render: (provider) => provider.name },
    { key: "kind", header: "Tipo", render: (provider) => provider.kind },
    { key: "country", header: "Paese", render: (provider) => provider.country_code },
    {
      key: "mapping",
      header: "Mapping TMDb",
      render: (provider) => (
        <MappingCell
          movieId={provider.tmdb_provider_id_movie}
          showId={provider.tmdb_provider_id_tv}
        />
      ),
    },
    {
      key: "justwatch",
      header: "Mapping JustWatch",
      render: (provider) => <JustWatchMappingCell provider={provider} />,
    },
    {
      key: "collections",
      header: "Copertura",
      render: (provider) =>
        `${formatNumber(provider.movie_collections)} film · ${formatNumber(
          provider.show_collections,
        )} serie`,
    },
    {
      key: "freshness",
      header: "Ultimo snapshot",
      render: (provider) => {
        const info = freshness.get(provider.id);
        if (!info?.lastValidAt) return <span className="text-xs text-ink-muted">Mai</span>;
        return (
          <div className="flex flex-col gap-1">
            <Timestamp value={info.lastValidAt} className="text-xs" />
            <StatusPill
              label={info.stale ? "Da aggiornare" : "Aggiornato"}
              tone={info.stale ? "warning" : "success"}
            />
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "Azioni",
      render: (provider) => {
        const linkedCollections = Math.max(
          provider.collections_count,
          freshness.get(provider.id)?.collections ?? 0,
        );
        return (
          <Button
            variant="danger"
            size="sm"
            busy={deletingId === provider.id}
            title={
              linkedCollections > 0
                ? `Elimina ${provider.name} e le ${formatNumber(
                    linkedCollections,
                  )} collezioni locali collegate.`
                : `Elimina ${provider.name}`
            }
            data-testid={`provider-delete-${provider.slug}`}
            onClick={() => onDelete(provider)}
          >
            <IconTrash />
            Elimina
          </Button>
        );
      },
    },
  ];
}

function CreateProviderCard({ onClose }: { onClose: () => void }) {
  const createProvider = useCreateProvider();
  const [payload, setPayload] = useState<
    Omit<ProviderCreatePayload, "justwatch_monetization_types">
  >({
    slug: "",
    name: "",
    kind: "SVOD",
    tmdb_movie_id: "",
    tmdb_tv_id: "",
    justwatch_short_name: "",
    justwatch_technical_name: "",
    tvdb_company_id: "",
  });
  const [offers, setOffers] = useState<OfferType[]>(["FLATRATE"]);
  const catalog = useProviderCatalog("IT");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState("");

  const candidates = useMemo(() => {
    const needle = catalogQuery.trim().toLocaleLowerCase("it");
    return (catalog.data?.items ?? []).filter((candidate) =>
      candidate.name.toLocaleLowerCase("it").includes(needle),
    );
  }, [catalog.data, catalogQuery]);

  const groupedCandidates = useMemo(
    () =>
      PROVIDER_SOURCE_ORDER.map((source) => ({
        source,
        items: candidates.filter((candidate) => candidate.source_key === source),
      })).filter((group) => group.items.length > 0),
    [candidates],
  );

  const chooseCandidate = (key: string) => {
    setSelectedCandidate(key);
    const candidate = (catalog.data?.items ?? []).find((item) => item.key === key);
    if (candidate) applyCandidate(candidate);
  };

  const applyCandidate = (candidate: ProviderCandidate) => {
    setPayload({
      slug: candidate.suggested_slug,
      name: candidate.name,
      kind: payload.kind,
      tmdb_movie_id: candidate.tmdb_movie_id ?? "",
      tmdb_tv_id: candidate.tmdb_tv_id ?? "",
      justwatch_short_name: candidate.justwatch_short_name ?? "",
      justwatch_technical_name: candidate.justwatch_technical_name ?? "",
      tvdb_company_id: candidate.tvdb_company_id ?? "",
    });
    const candidateOffers = candidate.justwatch_monetization_types.filter(
      (value): value is OfferType => OFFER_OPTIONS.some((option) => option.value === value),
    );
    setOffers(candidateOffers.length > 0 ? candidateOffers : ["FLATRATE"]);
  };

  const sourceLabel = (source: string) =>
    source === "tmdb" ? "TMDb" : source === "justwatch" ? "JustWatch" : "TVDB";

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await createProvider.mutateAsync({
      ...payload,
      slug: payload.slug.trim(),
      name: payload.name.trim(),
      tmdb_movie_id: payload.tmdb_movie_id?.trim() || undefined,
      tmdb_tv_id: payload.tmdb_tv_id?.trim() || undefined,
      justwatch_short_name: payload.justwatch_short_name?.trim() || undefined,
      justwatch_technical_name: payload.justwatch_technical_name?.trim() || undefined,
      justwatch_monetization_types: offers.length > 0 ? offers : ["FLATRATE"],
      tvdb_company_id: payload.tvdb_company_id?.trim() || undefined,
    });
    onClose();
  };

  return (
    <Card className="mb-6" testId="provider-create-card">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ink">Nuovo provider</h2>
        <p className="text-sm text-ink-muted">
          Inserisci il servizio che vuoi monitorare. I mapping sono facoltativi, ma senza
          almeno un ID TMDb o JustWatch non potrai creare collezioni per questo provider.
          Gli ID che digiti qui restano manuali: la card li mostrerà come “da verificare”.
        </p>
      </div>
      <div className="mb-4 rounded-lg border border-line bg-surface-muted p-3">
        <Field
          id="provider-catalog-search"
          label="Cerca nei provider disponibili"
          hint="Le fonti sono separate: TMDb e JustWatch. TheTVDB non espone un elenco streaming: usa il Company ID manuale."
        >
          <Input
            id="provider-catalog-search"
            value={catalogQuery}
            onChange={(event) => setCatalogQuery(event.target.value)}
            placeholder="Es. Netflix, Disney, Rai…"
          />
        </Field>
        <Field id="provider-catalog-select" label="Provider disponibili">
          <Select
            id="provider-catalog-select"
            value={selectedCandidate}
            onChange={(event) => chooseCandidate(event.target.value)}
            disabled={catalog.isLoading || candidates.length === 0}
          >
            <option value="">
              {catalog.isLoading
                ? "Caricamento provider…"
                : candidates.length === 0
                  ? "Nessun provider trovato"
                  : `${candidates.length} provider disponibili`}
            </option>
            {groupedCandidates.map((group) => (
              <optgroup key={group.source} label={sourceLabel(group.source)}>
                {group.items.map((candidate) => (
                  <option key={candidate.key} value={candidate.key}>
                    {candidate.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        </Field>
        {catalog.data ? (
          <p className="mt-2 text-xs text-ink-muted">
            {catalog.data.sources
              .map(
                (source) =>
                  `${sourceLabel(source.source_key)}: ${
                    source.status === "OK"
                      ? "OK"
                      : source.status === "MISSING_CREDENTIAL"
                        ? "credenziale mancante"
                        : source.status === "MANUAL_ONLY"
                          ? "solo Company ID manuale"
                          : "errore"
                  }`,
              )
              .join(" · ")}
          </p>
        ) : null}
        {catalog.data?.sources.some(
          (source) => source.source_key === "tvdb" && source.status === "MISSING_CREDENTIAL",
        ) ? (
          <p className="mt-2 text-xs text-ink-muted">
            TheTVDB è opzionale: per cercare le sue company aggiungi la API key in{" "}
            <Link className="text-accent underline" to="/app/settings">
              Impostazioni → Credenziali
            </Link>
            . TVDB fornisce company ID e metadati, non la disponibilità per paese.
          </p>
        ) : null}
        {catalog.data?.sources.some(
          (source) => source.source_key === "tvdb" && source.status === "MANUAL_ONLY",
        ) ? (
          <p className="mt-2 text-xs text-ink-muted">
            TheTVDB non espone un elenco di provider streaming: inserisci il Company ID
            nel campo dedicato, oppure cerca il nome sul sito TheTVDB.
          </p>
        ) : null}
        {catalog.isError ? <ErrorState error={catalog.error} /> : null}
      </div>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
        <h3 className="text-sm font-semibold text-ink sm:col-span-2">Identità del provider</h3>
        <Field
          id="provider-slug"
          label="Slug"
          hint="Identificativo univoco per URL e collezioni: minuscole, numeri e trattini."
        >
          <Input
            id="provider-slug"
            value={payload.slug}
            onChange={(event) => setPayload({ ...payload, slug: event.target.value })}
            placeholder="mio-provider"
            required
          />
        </Field>
        <Field id="provider-name" label="Nome visualizzato" hint="Come comparirà nella dashboard e nelle collezioni.">
          <Input
            id="provider-name"
            value={payload.name}
            onChange={(event) => setPayload({ ...payload, name: event.target.value })}
            placeholder="Mio Provider"
            required
          />
        </Field>
        <Field
          id="provider-kind"
          label="Modello commerciale"
          hint={
            PROVIDER_KINDS.find((item) => item.value === payload.kind)?.description ??
            "Classificazione del servizio."
          }
        >
          <Select
            id="provider-kind"
            value={payload.kind}
            onChange={(event) =>
              setPayload({
                ...payload,
                kind: event.target.value as ProviderCreatePayload["kind"],
              })
            }
          >
            {PROVIDER_KINDS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
        </Field>
        <h3 className="text-sm font-semibold text-ink sm:col-span-2">Mapping TMDb</h3>
        <Field
          id="provider-tmdb-movie"
          label="ID TMDb film"
          hint="ID numerico del provider TMDb per i film. Compilato dal catalogo; facoltativo."
        >
          <Input
            id="provider-tmdb-movie"
            value={payload.tmdb_movie_id ?? ""}
            onChange={(event) => setPayload({ ...payload, tmdb_movie_id: event.target.value })}
          />
        </Field>
        <Field
          id="provider-tmdb-tv"
          label="ID TMDb serie"
          hint="ID numerico del provider TMDb per le serie. Può essere assente per alcuni servizi."
        >
          <Input
            id="provider-tmdb-tv"
            value={payload.tmdb_tv_id ?? ""}
            onChange={(event) => setPayload({ ...payload, tmdb_tv_id: event.target.value })}
          />
        </Field>
        <h3 className="text-sm font-semibold text-ink sm:col-span-2">Mapping JustWatch</h3>
        <Field
          id="provider-justwatch-short"
          label="Codice breve JustWatch"
          hint="shortName del package, es. nfx o prv. È l’identificativo usato nelle collezioni."
        >
          <Input
            id="provider-justwatch-short"
            value={payload.justwatch_short_name ?? ""}
            onChange={(event) =>
              setPayload({ ...payload, justwatch_short_name: event.target.value })
            }
          />
        </Field>
        <Field
          id="provider-justwatch-technical"
          label="Nome tecnico JustWatch"
          hint="technicalName del package, es. netflix. Non è l’ID e serve alla verifica live."
        >
          <Input
            id="provider-justwatch-technical"
            value={payload.justwatch_technical_name ?? ""}
            onChange={(event) =>
              setPayload({ ...payload, justwatch_technical_name: event.target.value })
            }
          />
        </Field>
        <Field
          id="provider-justwatch-offers"
          label="Offerte JustWatch"
          hint="Seleziona tutte le modalità che il package espone per questo servizio."
        >
          <div className="flex flex-wrap gap-2" data-testid="provider-offers">
            {OFFER_OPTIONS.map((option) => (
              <ToggleChip
                key={option.value}
                pressed={offers.includes(option.value)}
                title={option.description}
                testId={`provider-offer-${option.value}`}
                onClick={() =>
                  setOffers((current) =>
                    current.includes(option.value)
                      ? current.filter((value) => value !== option.value)
                      : [...current, option.value],
                  )
                }
              >
                {option.label}
              </ToggleChip>
            ))}
          </div>
          <details className="mt-2 text-xs text-ink-muted">
            <summary className="cursor-pointer font-medium text-ink">
              Cosa significano queste offerte?
            </summary>
            <ul className="mt-2 space-y-1">
              {OFFER_OPTIONS.map((option) => (
                <li key={option.value}>
                  <strong className="text-ink">{option.label}</strong>: {option.description}
                </li>
              ))}
            </ul>
          </details>
        </Field>
        <h3 className="text-sm font-semibold text-ink sm:col-span-2">TheTVDB (metadati)</h3>
        <Field
          id="provider-tvdb-company"
          label="Company ID TheTVDB"
          hint="ID numerico della company TVDB. Metadati: non implica disponibilità nel paese selezionato."
        >
          <Input
            id="provider-tvdb-company"
            value={payload.tvdb_company_id ?? ""}
            onChange={(event) => setPayload({ ...payload, tvdb_company_id: event.target.value })}
          />
        </Field>
        <div className="flex items-end gap-2 sm:col-span-2">
          <Button type="submit" busy={createProvider.isPending}>
            Crea provider
          </Button>
          <p className="text-xs text-ink-muted">
            Gli ID sono configurazione manuale e restano “da verificare”: controllali sulla
            fonte prima di creare collezioni.
          </p>
        </div>
      </form>
      {createProvider.isError ? (
        <div className="mt-3">
          <ErrorState error={createProvider.error} />
        </div>
      ) : null}
    </Card>
  );
}

export default function ProvidersPage() {
  const [country, setCountry] = useState(DEFAULT_COUNTRY);
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"cards" | "table">("cards");
  const [showCreate, setShowCreate] = useState(false);
  const providers = useProviders(country);
  const collections = useCollections({});
  const bindings = useBindings();
  const deleteProvider = useDeleteProvider();
  const deleteCollection = useDeleteCollection();
  const freshness = useMemo(
    () => freshnessByProvider(collections.data ?? []),
    [collections.data],
  );
  const collectionsByProvider = useMemo(() => {
    const grouped = new Map<string, Collection[]>();
    for (const collection of collections.data ?? []) {
      const list = grouped.get(collection.provider_id) ?? [];
      list.push(collection);
      grouped.set(collection.provider_id, list);
    }
    return grouped;
  }, [collections.data]);

  const handleDelete = (provider: Provider) => {
    const loadedCollections = (collections.data ?? []).filter(
      (collection) => collection.provider_id === provider.id,
    ).length;
    const linkedCount = Math.max(provider.collections_count, loadedCollections);
    const linked =
      linkedCount > 0
        ? ` Verranno rimosse anche ${formatNumber(
            linkedCount,
          )} collezioni locali collegate con la loro cronologia. Le liste MDBList remote non vengono toccate.`
        : " Nessuna collezione locale è collegata.";
    const confirmed = window.confirm(
      `Eliminare il provider “${provider.name}”?${linked}`,
    );
    if (!confirmed) return;
    deleteProvider.mutate(provider.id);
  };

  const handleDeleteCollection = (collection: Collection) => {
    const confirmed = window.confirm(
      `Eliminare la collezione “${collection.name}”? Verranno rimossi gli snapshot locali, l'eventuale binding e la cronologia delle run. Le liste MDBList remote non vengono toccate.`,
    );
    if (!confirmed) return;
    deleteCollection.mutate(collection.id);
  };

  const allProviders = providers.data ?? [];
  const knownChips = KNOWN_PROVIDERS.filter((name) =>
    allProviders.some((provider) =>
      provider.name.toLowerCase().includes(name.toLowerCase()),
    ),
  );
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? allProviders.filter(
        (provider) =>
          provider.name.toLowerCase().includes(needle) ||
          provider.slug.toLowerCase().includes(needle) ||
          provider.kind.toLowerCase().includes(needle),
      )
    : allProviders;

  return (
    <>
      <PageHeader
        eyebrow="Fonti"
        title="Provider"
        description="Provider canonici con mapping TMDb, copertura film/serie e freschezza degli snapshot."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => setShowCreate((current) => !current)}
              data-testid="provider-create-toggle"
            >
              {showCreate ? "Chiudi" : "Aggiungi provider"}
            </Button>
            <div className="flex gap-1 rounded-md border border-line bg-surface p-1">
            <ToggleChip
              pressed={view === "cards"}
              onClick={() => setView("cards")}
              className="border-0"
            >
              <IconGrid />
              Card
            </ToggleChip>
            <ToggleChip
              pressed={view === "table"}
              onClick={() => setView("table")}
              className="border-0"
            >
              <IconLayers />
              Tabella
            </ToggleChip>
            </div>
          </div>
        }
      />

      {showCreate ? <CreateProviderCard onClose={() => setShowCreate(false)} /> : null}

      <Card className="mb-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
          <Field
            id="country"
            label="Paese"
            hint="Cerca per nome o codice ISO 3166-1 (es. Italia o IT)."
          >
            <CountrySelect id="country" value={country} onChange={setCountry} />
          </Field>
          <Field
            id="provider-search"
            label="Cerca provider"
            hint={
              allProviders.length > 0
                ? "Scrivi per filtrare o scegli dall'elenco dei provider presenti."
                : undefined
            }
          >
            <ProviderSuggest
              id="provider-search"
              value={query}
              onChange={setQuery}
              providers={allProviders}
            />
          </Field>
        </div>

        {knownChips.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <ToggleChip pressed={query === ""} onClick={() => setQuery("")}>
              Tutti
            </ToggleChip>
            {knownChips.map((name) => (
              <ToggleChip
                key={name}
                pressed={query === name}
                onClick={() => setQuery(query === name ? "" : name)}
              >
                {name}
              </ToggleChip>
            ))}
          </div>
        ) : null}
      </Card>

      {providers.isPending ? <TableSkeleton /> : null}

      {providers.isSuccess ? (
        <div className="mb-6">
          <ProviderMatrix
            country={country}
            providers={providers.data}
            collections={collections.data ?? []}
            bindings={bindings.data ?? []}
          />
        </div>
      ) : null}

      {providers.isError ? (
        <ErrorState error={providers.error} onRetry={() => void providers.refetch()} />
      ) : null}
      {deleteProvider.isError ? (
        <div className="mb-4">
          <ErrorState error={deleteProvider.error} />
        </div>
      ) : null}
      {deleteCollection.isError ? (
        <div className="mb-4">
          <ErrorState error={deleteCollection.error} />
        </div>
      ) : null}

      {providers.isSuccess ? (
        <>
          <StaleBanner updatedAt={providers.dataUpdatedAt} />
          {filtered.length === 0 ? (
            <EmptyState
              title="Nessun provider disponibile"
              description={
                needle
                  ? `Nessun provider corrisponde a “${query}” per il paese ${country}.`
                  : `Nessun provider canonico per il paese ${country}.`
              }
              action={
                needle ? (
                  <Button variant="secondary" onClick={() => setQuery("")}>
                    Azzera la ricerca
                  </Button>
                ) : undefined
              }
            />
          ) : view === "cards" ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((provider) => (
                <ProviderCard
                  key={provider.id}
                  provider={provider}
                  freshness={freshness.get(provider.id)}
                  collections={collectionsByProvider.get(provider.id) ?? []}
                  onDelete={handleDelete}
                  onDeleteCollection={handleDeleteCollection}
                  deleting={deleteProvider.isPending && deleteProvider.variables === provider.id}
                  deletingCollectionId={
                    deleteCollection.isPending
                      ? (deleteCollection.variables ?? null)
                      : null
                  }
                />
              ))}
            </div>
          ) : (
            <Card>
              <DataTable
                caption={`Provider per il paese ${country}`}
                columns={providerColumns(
                  freshness,
                  handleDelete,
                  deleteProvider.isPending ? (deleteProvider.variables ?? null) : null,
                )}
                rows={filtered}
                rowKey={(provider) => provider.id}
              />
            </Card>
          )}
        </>
      ) : null}
    </>
  );
}
