import type { Source } from "../../api/types";
import { formatNumber } from "../../lib/format";
import {
  justWatchCapabilityList,
  justWatchCacheTtlLabel,
  justWatchThrottleLabel,
} from "../../lib/justwatch";
import { Card } from "../ui/primitives";
import { SourceStatusPill, StatusPill } from "../ui/status-pill";
import { IconActivity, IconLink, IconServer } from "../ui/icons";

const TOS_NOTICE =
  "Rispetta i termini d'uso di JustWatch: una richiesta al secondo, cache locale e sole letture (GET). " +
  "Nessun accesso partner: i dati provengono dal catalogo pubblico dell'aggregatore.";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-surface-elevated px-3 py-2">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}

/**
 * Card unica per pagina Provider e tab Connettori: `GET /api/sources` espone
 * throttle, cache, usage e mapping verificati nel blocco `justwatch`.
 */
export function JustWatchConnectorCard({
  source,
  testId = "justwatch-connector",
}: {
  source: Source | undefined;
  testId?: string;
}) {
  if (!source) return null;
  const info = source.justwatch;
  const capabilities = justWatchCapabilityList(info?.supported_kinds);
  const mappings = info?.mappings ?? [];

  return (
    <Card testId={testId}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">
            Connettore
          </p>
          <h2 className="text-lg font-semibold text-ink">{source.name}</h2>
          <p className="text-sm text-ink-muted">
            Aggregatore pubblico per catalogo, novità, in arrivo e classifiche. Le date di
            aggiunta non sono dichiarate dalla fonte.
          </p>
        </div>
        <SourceStatusPill status={source.status} />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <StatusPill label="Aggregatore" tone="warning" />
        <StatusPill label="Date non disponibili" tone="neutral" />
        {source.connector_available ? (
          <StatusPill label="Connettore disponibile" tone="success" />
        ) : (
          <StatusPill label="Connettore non disponibile" tone="neutral" />
        )}
      </div>

      {!info ? (
        <p className="mt-4 text-sm text-ink-muted">
          Dati runtime non disponibili per questa fonte.
        </p>
      ) : (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <Metric label="Throttle" value={justWatchThrottleLabel(info.throttle_ms)} />
            <Metric label="Cache TTL" value={justWatchCacheTtlLabel(info.cache_ttl_seconds)} />
            <Metric label="Cache hit" value={formatNumber(info.cache_hits)} />
            <Metric label="Cache miss" value={formatNumber(info.cache_misses)} />
            <Metric label="Richieste ora" value={formatNumber(info.requests_hour)} />
            <Metric label="Richieste oggi" value={formatNumber(info.requests_today)} />
            <Metric
              label="Voci cache"
              value={formatNumber(info.cache_max_entries ?? undefined)}
            />
            <Metric label="Mapping IT" value={formatNumber(mappings.length)} />
          </dl>

          <div className="mt-4">
            <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
              <IconServer />
              Capacità della fonte
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {capabilities.map((capability) => (
                <StatusPill
                  key={capability.key}
                  label={capability.label}
                  tone={capability.enabled ? "success" : "neutral"}
                  code={capability.key}
                />
              ))}
              {info.supported_offer_types.length > 0 ? (
                <StatusPill
                  label={`Offerte: ${info.supported_offer_types.join(", ")}`}
                  tone="info"
                />
              ) : null}
            </div>
          </div>

          <div className="mt-4">
            <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
              <IconLink />
              Mapping JustWatch verificati (IT)
            </h3>
            {mappings.length === 0 ? (
              <p className="text-sm text-ink-muted">
                Nessun mapping verificato: esegui la verifica provider dalla fonte.
              </p>
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2">
                {mappings.map((mapping) => (
                  <li
                    key={mapping.provider_slug}
                    className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm"
                  >
                    <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                      {mapping.provider_name}
                      <span className="font-mono text-xs text-ink-faint">
                        {mapping.provider_slug}
                      </span>
                    </p>
                    <p className="mt-0.5 text-xs text-ink-muted">
                      ID {mapping.external_id ?? "—"}
                      {mapping.technical_name ? ` · ${mapping.technical_name}` : ""}
                      {mapping.clear_name && mapping.clear_name !== mapping.provider_name
                        ? ` · ${mapping.clear_name}`
                        : ""}
                    </p>
                    <p className="mt-0.5 text-xs text-ink-muted">
                      {mapping.monetization_types.length > 0
                        ? mapping.monetization_types.join(", ")
                        : "Offerte non dichiarate"}
                      {" · "}
                      {formatNumber(mapping.collections_count)} collezioni
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      <div className="mt-4 rounded-md border border-warning/40 bg-warning-soft p-3 text-xs text-ink">
        <p className="flex items-center gap-1.5 font-semibold text-warning">
          <IconActivity />
          ToS e rate-limit
        </p>
        <p className="mt-1">{TOS_NOTICE}</p>
      </div>
    </Card>
  );
}
