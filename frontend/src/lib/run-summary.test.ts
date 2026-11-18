import { describe, expect, it } from "vitest";
import { filterSamples, removalUsage } from "./run-summary";

describe("removalUsage", () => {
  it("usa zeri quando le soglie non sono nel summary", () => {
    const usage = removalUsage(undefined);
    expect(usage.observed).toBe(0);
    expect(usage.absoluteFill).toBe(0);
    expect(usage.percentFill).toBe(0);
    expect(usage.breached).toBe(false);
  });

  it("calcola il riempimento assoluto e percentuale", () => {
    const usage = removalUsage({
      observed_removals: 25,
      max_removal_absolute: 50,
      max_removal_percent: 10,
      remote_count: 1000,
    });
    expect(usage.absoluteFill).toBe(50);
    expect(usage.observedPercent).toBe(2.5);
    expect(usage.percentFill).toBe(25);
    expect(usage.overAbsolute).toBe(false);
    expect(usage.overPercent).toBe(false);
  });

  it("segnala il superamento delle soglie e limita la barra a 100", () => {
    const usage = removalUsage({
      observed_removals: 120,
      max_removal_absolute: 50,
      max_removal_percent: 5,
      remote_count: 1000,
    });
    expect(usage.absoluteFill).toBe(100);
    expect(usage.percentFill).toBe(100);
    expect(usage.overAbsolute).toBe(true);
    expect(usage.overPercent).toBe(true);
    expect(usage.breached).toBe(true);
  });
});

describe("filterSamples", () => {
  const samples = ["Dune (2021)", "Arrival (2016)", "Blade Runner 2049 (2017)"];

  it("filtra senza distinzione di maiuscole", () => {
    expect(filterSamples(samples, "dune")).toEqual(["Dune (2021)"]);
    expect(filterSamples(samples, "20")).toHaveLength(3);
  });

  it("restituisce tutto con una query vuota", () => {
    expect(filterSamples(samples, "  ")).toEqual(samples);
    expect(filterSamples(undefined, "x")).toEqual([]);
  });
});
