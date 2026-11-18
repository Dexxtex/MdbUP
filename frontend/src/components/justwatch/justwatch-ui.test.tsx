import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Source } from "../../api/types";
import { CollectionSourceBadge, OriginBadge, UpcomingBadge } from "../ui/badges";
import { JustWatchConnectorCard } from "./connector-card";

const SOURCE: Source = {
  id: "source-jw",
  key: "justwatch",
  name: "JustWatch",
  type: "API",
  status: "OK",
  base_url: null,
  status_message: null,
  is_official: false,
  origin_default: "AGGREGATOR",
  requires_contract: false,
  capabilities: { catalog: true, upcoming: true, charts: true },
  credential_configured: false,
  connector_available: true,
  last_healthcheck_at: null,
  last_success_at: null,
  justwatch: {
    throttle_ms: 1000,
    cache_ttl_seconds: 3600,
    cache_max_entries: 1000,
    cache_hits: 12,
    cache_misses: 3,
    requests_hour: 4,
    requests_today: 30,
    mappings: [
      {
        provider_slug: "netflix",
        provider_name: "Netflix",
        external_id: "8",
        technical_name: "netflix",
        clear_name: "Netflix",
        monetization_types: ["FLATRATE"],
        collections_count: 2,
      },
    ],
    supported_kinds: ["CATALOG", "RECENTLY_ADDED", "UPCOMING", "CHART"],
    supported_offer_types: ["FLATRATE"],
  },
};

describe("badge JustWatch", () => {
  it("mostra l'etichetta source_label della classifica", () => {
    const html = renderToStaticMarkup(
      <CollectionSourceBadge label="Classifica JustWatch" tone="warning" />,
    );
    expect(html).toContain("Classifica JustWatch");
    expect(html).toContain('data-source-label="Classifica JustWatch"');
  });

  it("mostra il badge In arrivo per le collezioni UPCOMING", () => {
    const html = renderToStaticMarkup(<UpcomingBadge />);
    expect(html).toContain("In arrivo");
    expect(html).toContain('data-kind="UPCOMING"');
  });

  it("attribuisce l'aggregatore a JustWatch", () => {
    const html = renderToStaticMarkup(
      <OriginBadge origin="AGGREGATOR" source="justwatch" />,
    );
    expect(html).toContain("Aggregatore JustWatch");
  });
});

describe("JustWatchConnectorCard", () => {
  it("mostra throttle, usage, mapping e capacità della fonte", () => {
    const html = renderToStaticMarkup(<JustWatchConnectorCard source={SOURCE} />);
    expect(html).toContain("1 req/s");
    expect(html).toContain("Cache hit");
    expect(html).toContain("Netflix");
    expect(html).toContain("Classifiche");
    expect(html).toContain("ToS e rate-limit");
  });
});
