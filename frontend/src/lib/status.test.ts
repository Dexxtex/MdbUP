import { describe, expect, it } from "vitest";
import {
  RUN_STATUS_TONES,
  SNAPSHOT_QUALITY_TONES,
  SNAPSHOT_STATUS_TONES,
  originPresentation,
  sourceLabel,
} from "./status";

describe("mappatura stato run", () => {
  it("usa toni semantici coerenti", () => {
    expect(RUN_STATUS_TONES.SUCCEEDED).toBe("success");
    expect(RUN_STATUS_TONES.AWAITING_APPROVAL).toBe("warning");
    expect(RUN_STATUS_TONES.FAILED).toBe("danger");
    expect(RUN_STATUS_TONES.PARTIAL).toBe("warning");
    expect(RUN_STATUS_TONES.PENDING).toBe("neutral");
  });
});

describe("mappatura snapshot", () => {
  it("distingue stato e qualità", () => {
    expect(SNAPSHOT_STATUS_TONES.COMPLETE).toBe("success");
    expect(SNAPSHOT_STATUS_TONES.INCOMPLETE).toBe("warning");
    expect(SNAPSHOT_STATUS_TONES.RUNNING).toBe("info");
    expect(SNAPSHOT_QUALITY_TONES.WARNINGS).toBe("warning");
    expect(SNAPSHOT_QUALITY_TONES.ANOMALY).toBe("danger");
  });
});

describe("origine delle collezioni", () => {
  it("etichetta le categorie ufficiali", () => {
    expect(originPresentation("OFFICIAL").label).toBe("Ufficiale");
  });

  it("attribuisce l'aggregatore alla fonte reale", () => {
    expect(originPresentation("AGGREGATOR", "tmdb").label).toBe("Aggregatore TMDb");
    expect(originPresentation("AGGREGATOR", "justwatch").label).toBe(
      "Aggregatore JustWatch",
    );
    expect(originPresentation("AGGREGATOR", null).label).toBe("Aggregatore");
  });

  it("distingue filtro locale e multi-provider", () => {
    expect(originPresentation("CUSTOM").label).toBe("Filtro locale");
    expect(originPresentation("CUSTOM", null, true).label).toBe("Multi-provider");
  });

  it("normalizza le chiavi fonte note", () => {
    expect(sourceLabel("TMDb")).toBe("TMDb");
    expect(sourceLabel("justwatch")).toBe("JustWatch");
    expect(sourceLabel("altro")).toBe("altro");
    expect(sourceLabel(null)).toBeNull();
  });
});
