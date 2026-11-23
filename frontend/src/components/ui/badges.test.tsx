import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CatalogChangeDirectionBadge, EpisodeEventBadge } from "./badges";

describe("CatalogChangeDirectionBadge", () => {
  it("mostra + Entrato in verde", () => {
    const html = renderToStaticMarkup(
      <CatalogChangeDirectionBadge direction="ADDED" />,
    );
    expect(html).toContain("Entrato");
    expect(html).toContain('data-direction="ADDED"');
    expect(html).toContain("text-success");
  });

  it("mostra - Uscito in rosso", () => {
    const html = renderToStaticMarkup(
      <CatalogChangeDirectionBadge direction="REMOVED" />,
    );
    expect(html).toContain("Uscito");
    expect(html).toContain('data-direction="REMOVED"');
    expect(html).toContain("text-danger");
  });
});

describe("EpisodeEventBadge", () => {
  it("etichetta una nuova stagione", () => {
    const html = renderToStaticMarkup(
      <EpisodeEventBadge eventType="SEASON_ADDED" />,
    );
    expect(html).toContain("Nuova stagione");
    expect(html).toContain('data-event-type="SEASON_ADDED"');
  });

  it("etichetta un nuovo episodio", () => {
    const html = renderToStaticMarkup(
      <EpisodeEventBadge eventType="EPISODE_ADDED" />,
    );
    expect(html).toContain("Nuovo episodio");
  });
});
