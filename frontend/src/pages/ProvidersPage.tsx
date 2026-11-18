import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useCollections, useProviders, useSources } from "../api/queries";
import type { Collection, Provider } from "../api/types";
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
  ToggleChip,
} from "../components/ui/primitives";
import { StatusPill } from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import { formatNumber } from "../lib/format";
import { IconBuilding, IconGrid, IconLayers, IconSearch } from "../components/ui/icons";
import { JustWatchConnectorCard } from "../components/justwatch/connector-card";

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
  if (!provider.justwatch_verified) {
    return (
      <div className="flex flex-col gap-1 text-xs">
        <StatusPill label="JustWatch non verificato" tone="neutral" />
        <span className="text-ink-muted">
          ID: <span className="font-mono text-ink">{provider.justwatch_provider_id ?? "—"}</span>
        </span>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1 text-xs">
      <StatusPill label="JustWatch verificato" tone="success" />
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

export default function ProvidersPage() {
  const [country, setCountry] = useState("IT");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"cards" | "table">("cards");
  const providers = useProviders(country);
  const sources = useSources();
  const collections = useCollections({});
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
        }
      />

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
