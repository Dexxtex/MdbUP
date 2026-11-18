// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearBindingDraft, loadBindingDraft, saveBindingDraft } from "./binding-draft";
import { DEFAULT_BINDING_DRAFT } from "./validation";

describe("binding draft", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("restituisce null senza bozza", () => {
    expect(loadBindingDraft()).toBeNull();
  });

  it("salva, carica e cancella la bozza", () => {
    saveBindingDraft({ ...DEFAULT_BINDING_DRAFT, collectionId: "c1" });
    const loaded = loadBindingDraft();
    expect(loaded?.collectionId).toBe("c1");
    clearBindingDraft();
    expect(loadBindingDraft()).toBeNull();
  });

  it("scarta JSON corrotto e bozze scadute", () => {
    window.sessionStorage.setItem("binding-draft:v1", "not-json");
    expect(loadBindingDraft()).toBeNull();
    window.sessionStorage.setItem(
      "binding-draft:v1",
      JSON.stringify({ savedAt: Date.now() - 25 * 60 * 60 * 1000, values: DEFAULT_BINDING_DRAFT }),
    );
    expect(loadBindingDraft()).toBeNull();
  });

  it("tollera uno storage che lancia", () => {
    const original = window.sessionStorage.getItem;
    const spy = vi.spyOn(window.sessionStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadBindingDraft()).toBeNull();
    spy.mockRestore();
    expect(original).toBeDefined();
  });

  it("scarta valori non oggetto", () => {
    window.sessionStorage.setItem(
      "binding-draft:v1",
      JSON.stringify({ savedAt: Date.now(), values: null }),
    );
    expect(loadBindingDraft()).toBeNull();
  });
});
