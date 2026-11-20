import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useBindings, useCollections, useProviderCatalog, useProviders, useSources } from "../hooks/queries";
import { useCreateProvider } from "../hooks/mutations";
import type {
  Collection,
  Provider,
  ProviderCandidate,
  ProviderCreatePayload,
} from "../api/types";
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
import { formatNumber } from "../lib/format";
import { hasJustWatchMapping } from "../lib/justwatch";
import { IconBuilding, IconGrid, IconLayers, IconSearch } from "../components/ui/icons";
import { JustWatchConnectorCard } from "../components/justwatch/connector-card";
import { ProviderMatrix } from "../components/providers/provider-matrix";

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
}: {
  provider: Provider;
  freshness: SnapshotFreshness | undefined;
}) {
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
        <Link
          to={`/app/collections?provider=${provider.id}`}
          className="inline-flex items-center gap-1 text-xs font-medium text-accent underline"
        >
          <IconLayers />
          {formatNumber(freshness?.collections ?? 0)} collezioni
        </Link>
      </div>
    </article>
  );
}

function providerColumns(
  freshness: Map<string, SnapshotFreshness>,
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
  // Raw text: splitting per keystroke would eat commas before the operator
  // finishes typing the next offer.
  const [offersText, setOffersText] = useState("FLATRATE");
  const catalog = useProviderCatalog("IT");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState("");

  const candidates = useMemo(() => {
    const needle = catalogQuery.trim().toLocaleLowerCase("it");
    return (catalog.data?.items ?? []).filter((candidate) =>
      candidate.name.toLocaleLowerCase("it").includes(needle),
    );
  }, [catalog.data, catalogQuery]);

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
    setOffersText(
      candidate.justwatch_monetization_types.length > 0
        ? candidate.justwatch_monetization_types.join(", ")
        : "FLATRATE",
    );
  };

  const sourceLabel = (source: string) =>
    source === "tmdb" ? "TMDb" : source === "justwatch" ? "JustWatch" : "TVDB";

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const offers = offersText
      .split(",")
      .map((value) => value.trim().toUpperCase())
      .filter(Boolean);
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
          hint="TMDb, JustWatch e TheTVDB. La selezione compila gli ID; puoi sempre modificarli."
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
            {candidates.map((candidate) => (
              <option key={candidate.key} value={candidate.key}>
                {candidate.name} — {candidate.sources.map(sourceLabel).join(" / ")}
              </option>
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
                        : "errore"
                  }`,
              )
              .join(" · ")}
          </p>
        ) : null}
        {catalog.isError ? <ErrorState error={catalog.error} /> : null}
      </div>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
        <Field id="provider-slug" label="Slug" hint="Solo minuscole, numeri e trattini.">
          <Input
            id="provider-slug"
            value={payload.slug}
            onChange={(event) => setPayload({ ...payload, slug: event.target.value })}
            placeholder="mio-provider"
            required
          />
        </Field>
        <Field id="provider-name" label="Nome">
          <Input
            id="provider-name"
            value={payload.name}
            onChange={(event) => setPayload({ ...payload, name: event.target.value })}
            placeholder="Mio Provider"
            required
          />
        </Field>
        <Field id="provider-kind" label="Tipo">
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
            {["SVOD", "TVOD", "AVOD", "TVE", "STORE", "CINEMA", "CHANNEL"].map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="provider-tmdb-movie" label="ID TMDb film" hint="Facoltativo.">
          <Input
            id="provider-tmdb-movie"
            value={payload.tmdb_movie_id ?? ""}
            onChange={(event) => setPayload({ ...payload, tmdb_movie_id: event.target.value })}
          />
        </Field>
        <Field id="provider-tmdb-tv" label="ID TMDb serie" hint="Facoltativo.">
          <Input
            id="provider-tmdb-tv"
            value={payload.tmdb_tv_id ?? ""}
            onChange={(event) => setPayload({ ...payload, tmdb_tv_id: event.target.value })}
          />
        </Field>
        <Field id="provider-justwatch-short" label="Codice JustWatch" hint="Es. nfx, prv.">
          <Input
            id="provider-justwatch-short"
            value={payload.justwatch_short_name ?? ""}
            onChange={(event) =>
              setPayload({ ...payload, justwatch_short_name: event.target.value })
            }
          />
        </Field>
        <Field id="provider-justwatch-technical" label="Technical name JustWatch" hint="Es. netflix.">
          <Input
            id="provider-justwatch-technical"
            value={payload.justwatch_technical_name ?? ""}
            onChange={(event) =>
              setPayload({ ...payload, justwatch_technical_name: event.target.value })
            }
          />
        </Field>
        <Field id="provider-tvdb-company" label="Company ID TVDB" hint="Facoltativo; non implica disponibilità in Italia.">
          <Input
            id="provider-tvdb-company"
            value={payload.tvdb_company_id ?? ""}
            onChange={(event) => setPayload({ ...payload, tvdb_company_id: event.target.value })}
          />
        </Field>
        <Field id="provider-justwatch-offers" label="Offerte JustWatch" hint="Separate da virgola.">
          <Input
            id="provider-justwatch-offers"
            value={offersText}
            onChange={(event) => setOffersText(event.target.value)}
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
  const [country, setCountry] = useState("IT");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"cards" | "table">("cards");
  const [showCreate, setShowCreate] = useState(false);
  const providers = useProviders(country);
  const sources = useSources();
  const collections = useCollections({});
  const bindings = useBindings();
  const justwatchSource = (sources.data ?? []).find((source) => source.key === "justwatch");
  const freshness = useMemo(
    () => freshnessByProvider(collections.data ?? []),
    [collections.data],
  );

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
          <Field id="country" label="Paese" hint="Codice ISO a 2 lettere, es. IT.">
            <Input
              id="country"
              value={country}
              maxLength={2}
              onChange={(event) => setCountry(event.target.value.toUpperCase())}
            />
          </Field>
          <Field id="provider-search" label="Cerca provider">
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
                <IconSearch />
              </span>
              <Input
                id="provider-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Netflix, Prime Video, Disney+…"
                className="pl-9"
              />
            </div>
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

      {justwatchSource ? (
        <div className="mb-6">
          <JustWatchConnectorCard source={justwatchSource} />
        </div>
      ) : null}

      {providers.isPending ? <TableSkeleton /> : null}

      {providers.isSuccess ? (
        <div className="mb-6">
          <ProviderMatrix
            providers={providers.data}
            collections={collections.data ?? []}
            bindings={bindings.data ?? []}
          />
        </div>
      ) : null}

      {providers.isError ? (
        <ErrorState error={providers.error} onRetry={() => void providers.refetch()} />
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
                />
              ))}
            </div>
          ) : (
            <Card>
              <DataTable
                caption={`Provider per il paese ${country}`}
                columns={providerColumns(freshness)}
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
