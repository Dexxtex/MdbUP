import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAcquireCollection } from "../../hooks/mutations";
import type { Binding, Collection, MediaType, Provider } from "../../api/types";
import {
  buildProviderMatrix,
  filterProviderMatrix,
  sortProviderMatrix,
  type ProviderMatrixFilter,
  type ProviderMatrixRow,
  type ProviderMatrixSortKey,
  type SortDirection,
} from "../../lib/provider-matrix";
import { countryName } from "../../lib/countries";
import { formatNumber } from "../../lib/format";
import { EmptyState } from "../ui/feedback";
import { Button, Card, ToggleChip } from "../ui/primitives";
import { StatusPill } from "../ui/status-pill";
import { Timestamp } from "../ui/time";
import { IconActivity, IconLayers, IconRefresh } from "../ui/icons";

const FILTERS: readonly { value: ProviderMatrixFilter; label: string }[] = [
  { value: "all", label: "Tutti" },
  { value: "stale", label: "Snapshot mancanti/scaduti" },
  { value: "active-bindings", label: "Solo binding attivi" },
];

function SortHeader({
  label,
  sortKey,
  activeKey,
  direction,
  onSort,
}: {
  label: string;
  sortKey: ProviderMatrixSortKey;
  activeKey: ProviderMatrixSortKey;
  direction: SortDirection;
  onSort: (key: ProviderMatrixSortKey) => void;
}) {
  const active = sortKey === activeKey;
  return (
    <th scope="col" className="px-3 py-2 text-left">
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-ink-faint hover:text-ink"
      >
        {label}
        <span aria-hidden="true">{active ? (direction === "asc" ? "▲" : "▼") : "↕"}</span>
        <span className="sr-only">
          {active
            ? `Ordinato ${direction === "asc" ? "crescente" : "decrescente"}`
            : "Ordina"}
        </span>
      </button>
    </th>
  );
}

function Freshness({ value }: { value: string | null }) {
  if (!value) return <span className="text-xs text-ink-muted">Mai acquisito</span>;
  return <Timestamp value={value} className="text-xs" />;
}

function MapPill({ verified, label }: { verified: boolean; label: string }) {
  return (
    <StatusPill
      label={label}
      tone={verified ? "success" : "warning"}
    />
  );
}

function JustWatchCell({
  row,
  mediaType,
}: {
  row: ProviderMatrixRow;
  mediaType: MediaType;
}) {
  const state = mediaType === "MOVIE" ? row.justwatch.movie : row.justwatch.show;
  return (
    <div className="flex flex-col gap-1.5">
      <MapPill
        verified={state.mapped}
        label={state.mapped ? "Mapping verificato" : "Mapping da verificare"}
      />
      <p className="text-xs text-ink-muted">{formatNumber(state.collections)} collezioni</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Freshness value={state.lastSnapshotAt} />
        <StatusPill
          label={state.stale ? "Da aggiornare" : "Aggiornato"}
          tone={state.stale ? "warning" : "success"}
        />
      </div>
    </div>
  );
}

function TmdbCell({
  row,
  mediaType,
}: {
  row: ProviderMatrixRow;
  mediaType: MediaType;
}) {
  const state = mediaType === "MOVIE" ? row.tmdb.movie : row.tmdb.show;
  return (
    <div className="flex flex-col gap-1.5">
      <MapPill
        verified={state.mapped}
        label={state.mapped ? "Mapping verificato" : "Mapping da verificare"}
      />
      <p className="text-xs text-ink-muted">
        {formatNumber(state.collections)} collezioni
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Freshness value={state.lastSnapshotAt} />
        <StatusPill
          label={state.stale ? "Da aggiornare" : "Aggiornato"}
          tone={state.stale ? "warning" : "success"}
        />
      </div>
    </div>
  );
}

function AcquireAction({ collection }: { collection: Collection | undefined }) {
  const acquire = useAcquireCollection(collection?.id ?? "");
  return (
    <Button
      variant="secondary"
      size="sm"
      disabled={!collection}
      busy={acquire.isPending}
      onClick={() => acquire.mutate()}
      data-testid={collection ? `matrix-acquire-${collection.id}` : "matrix-acquire"}
    >
      <IconRefresh />
      Acquisisci ora
    </Button>
  );
}

function RowActions({
  row,
  collections,
  mediaType,
}: {
  row: ProviderMatrixRow;
  collections: readonly Collection[];
  mediaType: MediaType;
}) {
  const navigate = useNavigate();
  const provider = row.provider;
  const providerCollections = collections.filter(
    (collection) => collection.provider_id === provider.id,
  );
  const justwatchCollection =
    providerCollections.find(
      (collection) =>
        collection.source_key === "justwatch" &&
        collection.media_type === mediaType &&
        collection.kind === "CATALOG",
    ) ??
    providerCollections.find(
      (collection) =>
        collection.source_key === "justwatch" && collection.media_type === mediaType,
    );
  const tmdbCollection = providerCollections.find(
    (collection) =>
      collection.source_key === "tmdb" && collection.media_type === mediaType,
  );

  const openBuilder = (source: "justwatch" | "combined") => {
    const params = new URLSearchParams({
      source,
      provider: provider.id,
      media_type: mediaType,
      kind: source === "combined" ? "CUSTOM_FILTER" : "CATALOG",
    });
    if (source === "combined") {
      params.set("combine_mode", "UNION");
      if (justwatchCollection) {
        params.append("source_collection_ids", justwatchCollection.id);
      }
      if (tmdbCollection) {
        params.append("source_collection_ids", tmdbCollection.id);
      }
    }
    navigate(`/app/collections/new?${params.toString()}`);
  };

  return (
    <div className="flex flex-col gap-2">
      <AcquireAction collection={justwatchCollection} />
      <Button
        variant="secondary"
        size="sm"
        onClick={() => openBuilder("justwatch")}
        data-testid={`matrix-justwatch-${provider.slug}`}
      >
        <IconLayers />
        Crea collezione JustWatch
      </Button>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => openBuilder("combined")}
        data-testid={`matrix-combined-${provider.slug}`}
      >
        <IconLayers />
        Crea combinata
      </Button>
    </div>
  );
}

export function ProviderMatrix({
  providers,
  collections,
  bindings,
  country,
}: {
  providers: readonly Provider[];
  collections: readonly Collection[];
  bindings: readonly Binding[];
  country: string;
}) {
  const [filter, setFilter] = useState<ProviderMatrixFilter>("all");
  const [sortKey, setSortKey] = useState<ProviderMatrixSortKey>("name");
  const [direction, setDirection] = useState<SortDirection>("asc");
  const [mediaType, setMediaType] = useState<MediaType>("MOVIE");

  const rows = useMemo(
    () => buildProviderMatrix(providers, collections, bindings),
    [providers, collections, bindings],
  );
  const visibleRows = useMemo(
    () => sortProviderMatrix(filterProviderMatrix(rows, filter), sortKey, direction),
    [rows, filter, sortKey, direction],
  );

  const onSort = (key: ProviderMatrixSortKey) => {
    if (key === sortKey) {
      setDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setDirection("asc");
  };

  return (
    <Card testId="provider-matrix">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">Stato per provider</h2>
          <p className="text-sm text-ink-muted">
            Per ogni provider: mapping JustWatch e TMDb, ultimo snapshot e binding attivi.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ToggleChip
            pressed={mediaType === "MOVIE"}
            onClick={() => setMediaType("MOVIE")}
            testId="matrix-media-MOVIE"
          >
            Film
          </ToggleChip>
          <ToggleChip
            pressed={mediaType === "SHOW"}
            onClick={() => setMediaType("SHOW")}
            testId="matrix-media-SHOW"
          >
            Serie
          </ToggleChip>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <ToggleChip
            key={option.value}
            pressed={filter === option.value}
            onClick={() => setFilter(option.value)}
            testId={`matrix-filter-${option.value}`}
          >
            {option.label}
          </ToggleChip>
        ))}
      </div>

      {visibleRows.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Nessun provider nella matrice"
            description="Nessun provider configurato o nessun provider corrisponde al filtro."
          />
        </div>
      ) : (
        <>
          <div className="mt-4 hidden overflow-x-auto md:block">
            <table className="w-full min-w-[64rem] border-collapse text-left text-sm">
              <caption className="sr-only">
                Stato dei provider — {countryName(country)}
              </caption>
              <thead>
                <tr className="border-b border-line">
                  <SortHeader
                    label="Servizio"
                    sortKey="name"
                    activeKey={sortKey}
                    direction={direction}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="JustWatch"
                    sortKey="justwatch"
                    activeKey={sortKey}
                    direction={direction}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="TMDb Film"
                    sortKey="tmdb-movie"
                    activeKey={sortKey}
                    direction={direction}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="TMDb Serie"
                    sortKey="tmdb-show"
                    activeKey={sortKey}
                    direction={direction}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Binding attivi"
                    sortKey="bindings"
                    activeKey={sortKey}
                    direction={direction}
                    onSort={onSort}
                  />
                  <th scope="col" className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                    Azioni
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr
                    key={row.provider.id}
                    data-testid={`matrix-row-${row.provider.slug}`}
                    className="border-b border-line/70 align-top last:border-0"
                  >
                    <td className="px-3 py-3">
                      <p className="font-medium text-ink">{row.provider.name}</p>
                      <p className="text-xs text-ink-muted">{row.provider.slug}</p>
                    </td>
                    <td className="px-3 py-3">
                      <JustWatchCell row={row} mediaType={mediaType} />
                    </td>
                    <td className="px-3 py-3">
                      <TmdbCell row={row} mediaType="MOVIE" />
                    </td>
                    <td className="px-3 py-3">
                      <TmdbCell row={row} mediaType="SHOW" />
                    </td>
                    <td className="px-3 py-3">
                      <span className="inline-flex items-center gap-1.5 text-sm tabular-nums text-ink">
                        <IconActivity />
                        {formatNumber(row.activeBindings)}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <RowActions
                        row={row}
                        collections={collections}
                        mediaType={mediaType}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="mt-4 space-y-3 md:hidden">
            {visibleRows.map((row) => (
              <li
                key={row.provider.id}
                className="rounded-lg border border-line bg-surface-elevated p-4"
              >
                <p className="text-base font-semibold text-ink">{row.provider.name}</p>
                <dl className="mt-2 space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-xs font-medium uppercase text-ink-faint">JustWatch</dt>
                    <dd className="text-right">
                      <JustWatchCell row={row} mediaType={mediaType} />
                    </dd>
                  </div>
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-xs font-medium uppercase text-ink-faint">TMDb Film</dt>
                    <dd className="text-right">
                      <TmdbCell row={row} mediaType="MOVIE" />
                    </dd>
                  </div>
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-xs font-medium uppercase text-ink-faint">TMDb Serie</dt>
                    <dd className="text-right">
                      <TmdbCell row={row} mediaType="SHOW" />
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-xs font-medium uppercase text-ink-faint">
                      Binding attivi
                    </dt>
                    <dd className="text-sm tabular-nums text-ink">{row.activeBindings}</dd>
                  </div>
                </dl>
                <div className="mt-3">
                  <RowActions row={row} collections={collections} mediaType={mediaType} />
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
