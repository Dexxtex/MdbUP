import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useCollections, useProviders } from "../hooks/queries";
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
import { IconLayers } from "../components/ui/icons";

const columns: Column<Collection>[] = [
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
      <div className="flex flex-wrap gap-3 text-xs">
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
      </div>
    ),
  },
];

export default function CollectionsPage() {
  const [searchParams] = useSearchParams();
  const [providerId, setProviderId] = useState(() => searchParams.get("provider") ?? "");
  const [mediaType, setMediaType] = useState("");
  const [origin, setOrigin] = useState("");
  const [kind, setKind] = useState("");
  const [isActive, setIsActive] = useState("");
  const navigate = useNavigate();

  const providers = useProviders("IT");
  const collections = useCollections({ providerId, mediaType, origin, kind, isActive });

  const activeFilterCount = [providerId, mediaType, origin, kind, isActive].filter(
    Boolean,
  ).length;

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

      <Card className="mb-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field id="filter-provider" label="Provider">
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
              onClick={() => {
                setProviderId("");
                setMediaType("");
                setOrigin("");
                setKind("");
                setIsActive("");
              }}
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
                columns={columns}
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
