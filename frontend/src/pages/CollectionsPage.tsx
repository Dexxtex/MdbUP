import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useCountry } from "../app/country-context";
import { countryName } from "../lib/countries";
import { useCollections, useProviders } from "../hooks/queries";
import { useDeleteCollection } from "../hooks/mutations";
import type { Collection } from "../api/types";
import {
  CollectionSourceBadge,
  DateBasisBadge,
  OriginBadge,
  UpcomingBadge,
} from "../components/ui/badges";
import { DataTable, type Column } from "../components/ui/data-table";
import {
  EmptyState,
  ErrorState,
  StaleBanner,
  TableSkeleton,
} from "../components/ui/feedback";
import { Button, Card, Field, PageHeader, Select } from "../components/ui/primitives";
import { SnapshotStatusPill } from "../components/ui/status-pill";
import { Timestamp } from "../components/ui/time";
import {
  collectionKindLabel,
  collectionProviderName,
  collectionSourceLabel,
  collectionSourceTone,
  isUpcomingCollection,
} from "../lib/collections";
import { formatNumber } from "../lib/format";
import { IconLayers, IconTrash } from "../components/ui/icons";

function CollectionDeleteButton({
  collection,
  onDelete,
  deleting,
  className,
  testId,
}: {
  collection: Collection;
  onDelete: (collection: Collection) => void;
  deleting: boolean;
  className?: string;
  testId?: string;
}) {
  return (
    <Button
      variant="danger"
      size="sm"
      className={className}
      busy={deleting}
      title={`Elimina ${collection.name} e i suoi dati locali; le liste MDBList remote non vengono toccate.`}
      data-testid={testId ?? `collection-delete-${collection.slug}`}
      onClick={() => onDelete(collection)}
    >
      <IconTrash />
      Elimina
    </Button>
  );
}

function collectionColumns(
  onDelete: (collection: Collection) => void,
  deletingId: string | null,
): Column<Collection>[] {
  return [
    {
      key: "name",
      header: "Collezione",
      render: (collection) => (
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Link
              to={`/app/collections/${collection.id}`}
              className="font-medium text-accent underline"
            >
              {collection.name}
            </Link>
            <CollectionSourceBadge
              label={collectionSourceLabel(collection)}
              tone={collectionSourceTone(collection)}
            />
            {isUpcomingCollection(collection) ? <UpcomingBadge /> : null}
          </div>
          <span className="text-xs text-ink-muted">{collectionKindLabel(collection.kind)}</span>
          {collection.is_local_filter ? (
            <span className="w-fit rounded-full border border-warning/40 bg-warning-soft px-2 py-0.5 text-xs text-warning">
              {collection.is_multi_provider ? "Multi-provider (locale)" : "Filtro locale"}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "provider",
      header: "Provider",
      render: (collection) =>
        collection.is_multi_provider
          ? `${collection.provider_names?.join(" + ") || "Multi-provider"}`
          : collectionProviderName(collection),
    },
    {
      key: "media",
      header: "Tipo",
      render: (collection) => (collection.media_type === "MOVIE" ? "Film" : "Serie"),
    },
    {
      key: "origin",
      header: "Origine",
      render: (collection) => (
        <OriginBadge
          origin={collection.origin}
          source={collection.source_key}
          multiProvider={collection.is_multi_provider}
        />
      ),
    },
    {
      key: "date_basis",
      header: "Base della data",
      render: (collection) => (
        <DateBasisBadge dateBasis={collection.date_basis} source={collection.source_key} />
      ),
    },
    {
      key: "snapshot",
      header: "Ultimo snapshot valido",
      render: (collection) =>
        collection.last_valid_snapshot ? (
          <div className="flex flex-col gap-1">
            <SnapshotStatusPill status={collection.last_valid_snapshot.status} />
            <Timestamp value={collection.last_valid_snapshot.finished_at} className="text-xs" />
            <span className="text-xs tabular-nums text-ink-faint">
              {formatNumber(collection.last_valid_snapshot.items_count)} elementi
            </span>
          </div>
        ) : (
          <span className="text-xs text-ink-muted">Nessuno</span>
        ),
    },
    {
      key: "active",
      header: "Stato",
      render: (collection) => (
        <span className={collection.is_active ? "text-success" : "text-ink-faint"}>
          {collection.is_active ? "Attiva" : "Disattivata"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Azioni",
      render: (collection) => (
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <Link
            to={`/app/collections/${collection.id}`}
            className="font-medium text-accent underline"
          >
            Apri
          </Link>
          <Link
            to={`/app/collections/${collection.id}/edit`}
            className="font-medium text-ink-muted underline hover:text-ink"
          >
            Modifica
          </Link>
          <CollectionDeleteButton
            collection={collection}
            onDelete={onDelete}
            deleting={deletingId === collection.id}
            className="hidden md:inline-flex"
          />
        </div>
      ),
    },
  ];
}

const FILTER_KEYS = ["provider", "media", "origin", "kind", "active"] as const;

export default function CollectionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [providerId, setProviderId] = useState(() => searchParams.get("provider") ?? "");
  const [mediaType, setMediaType] = useState(() => searchParams.get("media") ?? "");
  const [origin, setOrigin] = useState(() => searchParams.get("origin") ?? "");
  const [kind, setKind] = useState(() => searchParams.get("kind") ?? "");
  const [isActive, setIsActive] = useState(() => searchParams.get("active") ?? "");
  const navigate = useNavigate();

  const { country } = useCountry();
  const providers = useProviders(country);
  const collections = useCollections({ providerId, mediaType, origin, kind, isActive });
  const deleteCollection = useDeleteCollection();

  const activeFilterCount = [providerId, mediaType, origin, kind, isActive].filter(
    Boolean,
  ).length;

  // I filtri vivono anche nell'URL: così il link "Apri elenco" del provider,
  // un refresh o un link condiviso mostrano la stessa vista.
  const filtersQuery = useMemo(() => {
    const next = new URLSearchParams();
    if (providerId) next.set("provider", providerId);
    if (mediaType) next.set("media", mediaType);
    if (origin) next.set("origin", origin);
    if (kind) next.set("kind", kind);
    if (isActive) next.set("active", isActive);
    return next.toString();
  }, [providerId, mediaType, origin, kind, isActive]);

  const resetFilters = () => {
    setProviderId("");
    setMediaType("");
    setOrigin("");
    setKind("");
    setIsActive("");
  };

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    for (const key of FILTER_KEYS) {
      next.delete(key);
    }
    for (const [key, value] of new URLSearchParams(filtersQuery)) {
      next.set(key, value);
    }
    const nextQuery = next.toString();
    if (nextQuery === searchParams.toString()) return;
    setSearchParams(next, { replace: true });
  }, [filtersQuery, searchParams, setSearchParams]);

  const currentProvider = (providers.data ?? []).find((item) => item.id === providerId);

  // Un link che porta un provider di un altro paese: il filtro non avrebbe
  // un'opzione visibile, quindi si azzera appena la lista è disponibile.
  useEffect(() => {
    if (providerId && providers.isSuccess && currentProvider === undefined) {
      setProviderId("");
    }
  }, [providerId, providers.isSuccess, currentProvider]);

  const handleDelete = (collection: Collection) => {
    const confirmed = window.confirm(
      `Eliminare la collezione “${collection.name}”? Verranno rimossi gli snapshot locali, l'eventuale binding e la cronologia delle run. Le liste MDBList remote non vengono toccate.`,
    );
    if (!confirmed) return;
    deleteCollection.mutate(collection.id);
  };

  return (
    <>
      <PageHeader
        eyebrow="Catalogo"
        title="Collezioni"
        description="Raccolte disponibili per provider, con origine, base della data e freschezza dello snapshot."
        actions={
          <Button onClick={() => navigate("/app/collections/new")}>Nuova collezione</Button>
        }
      />

      {currentProvider ? (
        <div
          data-testid="collections-context"
          className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-surface-muted px-3 py-2 text-sm"
        >
          <span className="text-ink">
            Collezioni di <strong>{currentProvider.name}</strong>
            {activeFilterCount > 1 ? (
              <span className="text-ink-muted"> · altri filtri attivi</span>
            ) : null}
          </span>
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Tutte le collezioni
          </Button>
        </div>
      ) : null}

      <Card className="mb-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field id="filter-provider" label={`Provider — ${countryName(country)}`}>
            <Select
              id="filter-provider"
              value={providerId}
              onChange={(event) => setProviderId(event.target.value)}
            >
              <option value="">Tutti</option>
              {(providers.data ?? []).map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field id="filter-media" label="Tipo">
            <Select
              id="filter-media"
              value={mediaType}
              onChange={(event) => setMediaType(event.target.value)}
            >
              <option value="">Tutti</option>
              <option value="MOVIE">Film</option>
              <option value="SHOW">Serie</option>
            </Select>
          </Field>

          <Field id="filter-origin" label="Origine">
            <Select
              id="filter-origin"
              value={origin}
              onChange={(event) => setOrigin(event.target.value)}
            >
              <option value="">Tutte</option>
              <option value="OFFICIAL">Ufficiale</option>
              <option value="AGGREGATOR">Aggregatore</option>
              <option value="CUSTOM">Filtro locale</option>
            </Select>
          </Field>

          <Field id="filter-kind" label="Costruzione">
            <Select
              id="filter-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              <option value="">Tutte</option>
              <option value="CATALOG">Catalogo</option>
              <option value="RECENTLY_ADDED">Appena rilevati</option>
              <option value="CHART">Classifica</option>
              <option value="UPCOMING">In arrivo</option>
              <option value="CUSTOM_FILTER">Combinata locale</option>
            </Select>
          </Field>

          <Field id="filter-active" label="Stato">
            <Select
              id="filter-active"
              value={isActive}
              onChange={(event) => setIsActive(event.target.value)}
            >
              <option value="">Tutti</option>
              <option value="true">Attive</option>
              <option value="false">Disattivate</option>
            </Select>
          </Field>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
          <span>
            {collections.isSuccess
              ? `${formatNumber(collections.data.length)} collezioni`
              : "Caricamento…"}
            {activeFilterCount > 0 ? ` · ${activeFilterCount} filtri attivi` : ""}
          </span>
          {activeFilterCount > 0 ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={resetFilters}
            >
              Azzera filtri
            </Button>
          ) : null}
        </div>
      </Card>

      {collections.isPending ? <TableSkeleton /> : null}

      {collections.isError ? (
        <ErrorState error={collections.error} onRetry={() => void collections.refetch()} />
      ) : null}
      {deleteCollection.isError ? (
        <div className="mb-4">
          <ErrorState error={deleteCollection.error} />
        </div>
      ) : null}

      {collections.isSuccess ? (
        <>
          <StaleBanner updatedAt={collections.dataUpdatedAt} />
          {collections.data.length === 0 ? (
            <EmptyState
              icon={<IconLayers />}
              title="Nessuna collezione"
              description="Modifica i filtri o crea una collezione con il costruttore guidato."
              action={
                <Button onClick={() => navigate("/app/collections/new")}>
                  Crea una collezione
                </Button>
              }
            />
          ) : (
            <Card>
              <DataTable
                caption="Elenco delle collezioni"
                columns={collectionColumns(
                  handleDelete,
                  deleteCollection.isPending
                    ? (deleteCollection.variables ?? null)
                    : null,
                )}
                cardActions={(collection) => (
                  <CollectionDeleteButton
                    collection={collection}
                    onDelete={handleDelete}
                    deleting={
                      deleteCollection.isPending &&
                      deleteCollection.variables === collection.id
                    }
                    testId={`collection-delete-card-${collection.slug}`}
                  />
                )}
                rows={collections.data}
                rowKey={(collection) => collection.id}
              />
            </Card>
          )}
        </>
      ) : null}
    </>
  );
}
