import { describe, expect, it } from "vitest";
import type { CatalogChangeItem } from "../api/types";
import {
  catalogChangeDirectionLabel,
  catalogChangeDirectionSign,
  catalogChangeDirectionTone,
  catalogChangeSourceLabel,
  catalogChangeWindowLabel,
  catalogChangesQuery,
  episodeEventLabel,
  episodeEventTone,
} from "./catalog-changes";

function change(overrides: Partial<CatalogChangeItem> = {}): CatalogChangeItem {
  return {
    id: "change-1",
    media_id: "media-1",
    title: "Dune: Parte due",
    year: 2024,
    media_type: "MOVIE",
    provider_id: "provider-1",
    provider_slug: "netflix",
    provider_name: "Netflix",
    source_key: "justwatch",
    source_label: "Fonte: JustWatch (Aggregatore)",
    direction: "ADDED",
    detected_at: "2026-01-03T04:02:00Z",
    detected_at_rome: "03/01/2026, 05:02",
    collection_id: "collection-1",
    collection_name: "Netflix film",
    collection_slug: "netflix-film",
    previous_snapshot_id: "snapshot-1",
    current_snapshot_id: "snapshot-2",
    season_number: null,
    episode_number: null,
    episode_event_type: null,
    ...overrides,
  };
}

describe("catalogChangesQuery", () => {
  it("invia sempre periodo e paginazione, omettendo i filtri vuoti", () => {
    const query = new URLSearchParams(
      catalogChangesQuery({
        window: "24h",
        providerId: "",
        mediaType: "",
        sourceKey: "",
        direction: "",
        search: "   ",
      }),
    );
    expect(query.get("window")).toBe("24h");
    expect(query.get("page")).toBe("1");
    expect(query.get("page_size")).toBe("50");
    expect(query.has("provider_id")).toBe(false);
    expect(query.has("search")).toBe(false);
  });

  it("codifica provider, tipo media, fonte, direzione e ricerca", () => {
    const query = new URLSearchParams(
      catalogChangesQuery({
        window: "7d",
        providerId: "provider-1",
        mediaType: "SHOW",
        sourceKey: "tmdb",
        direction: "REMOVED",
        search: "  Severance  ",
        page: 3,
        pageSize: 25,
      }),
    );
    expect(query.get("window")).toBe("7d");
    expect(query.get("provider_id")).toBe("provider-1");
    expect(query.get("media_type")).toBe("SHOW");
    expect(query.get("source_key")).toBe("tmdb");
    expect(query.get("direction")).toBe("REMOVED");
    expect(query.get("search")).toBe("Severance");
    expect(query.get("page")).toBe("3");
    expect(query.get("page_size")).toBe("25");
  });
});

describe("etichette cambi catalogo", () => {
  it("traduce periodo e direzione", () => {
    expect(catalogChangeWindowLabel("24h")).toBe("Oggi");
    expect(catalogChangeWindowLabel("7d")).toBe("7g");
    expect(catalogChangeDirectionLabel("ADDED")).toBe("Entrato");
    expect(catalogChangeDirectionLabel("REMOVED")).toBe("Uscito");
  });

  it("usa verde per gli entrati e rosso per gli usciti", () => {
    expect(catalogChangeDirectionTone("ADDED")).toBe("success");
    expect(catalogChangeDirectionTone("REMOVED")).toBe("danger");
    expect(catalogChangeDirectionSign("ADDED")).toBe("+");
    expect(catalogChangeDirectionSign("REMOVED")).toBe("−");
  });

  it("mostra il source_label esatto del backend", () => {
    expect(catalogChangeSourceLabel(change())).toBe(
      "Fonte: JustWatch (Aggregatore)",
    );
    expect(
      catalogChangeSourceLabel(
        change({ source_key: "tmdb", source_label: "" }),
      ),
    ).toBe("TMDb");
  });
});

describe("eventi stagione/episodio", () => {
  it("etichetta Nuova stagione e Nuovo episodio", () => {
    expect(episodeEventLabel("SEASON_ADDED")).toBe("Nuova stagione");
    expect(episodeEventLabel("EPISODE_ADDED")).toBe("Nuovo episodio");
    expect(episodeEventLabel("SEASON_REMOVED")).toBe("Stagione rimossa");
  });

  it("distingue aggiunte e rimozioni con toni semantici", () => {
    expect(episodeEventTone("SEASON_ADDED")).toBe("success");
    expect(episodeEventTone("EPISODE_REMOVED")).toBe("danger");
  });
});
