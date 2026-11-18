import { describe, expect, it } from "vitest";
import {
  DEFAULT_BINDING_DRAFT,
  bindingDraftSchema,
  bindingStepFields,
  bootstrapSchema,
  settingsSchema,
  type BindingDraft,
} from "./validation";

function draft(overrides: Partial<BindingDraft> = {}): BindingDraft {
  return {
    ...DEFAULT_BINDING_DRAFT,
    providerId: "provider-1",
    sourceId: "source-1",
    collectionId: "collection-1",
    targetId: "target-1",
    previewId: "preview-1",
    previewState: "READY",
    policyAccepted: true,
    confirmName: "Netflix IT",
    ...overrides,
  };
}

function issuePaths(result: { success: boolean; error?: { issues: { path: (string | number)[] }[] } }) {
  return (result.error?.issues ?? []).map((issue) => issue.path.join("."));
}

describe("bindingDraftSchema", () => {
  it("accetta una bozza completa e valida", () => {
    const result = bindingDraftSchema.safeParse(draft());
    expect(result.success).toBe(true);
  });

  it("richiede una lista esistente quando targetMode è existing", () => {
    const result = bindingDraftSchema.safeParse(draft({ targetId: undefined }));
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("targetId");
  });

  it("richiede un nome di almeno 3 caratteri per una nuova lista", () => {
    const result = bindingDraftSchema.safeParse(
      draft({ targetMode: "new", targetId: undefined, newListName: "ab" }),
    );
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("newListName");
  });

  it("rifiuta MIRROR con entrambe le soglie a zero", () => {
    const result = bindingDraftSchema.safeParse(
      draft({ mode: "MIRROR", maxRemovalPct: 0, maxRemovalAbs: 0 }),
    );
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("maxRemovalAbs");
  });

  it("accetta APPEND_ONLY con soglie a zero", () => {
    const result = bindingDraftSchema.safeParse(
      draft({ mode: "APPEND_ONLY", maxRemovalPct: 0, maxRemovalAbs: 0 }),
    );
    expect(result.success).toBe(true);
  });

  it("richiede l'accettazione della policy", () => {
    const result = bindingDraftSchema.safeParse(draft({ policyAccepted: false }));
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("policyAccepted");
  });

  it("richiede la revisione manuale quando l'anteprima è bloccata", () => {
    const result = bindingDraftSchema.safeParse(
      draft({ previewState: "BLOCKED", requireReview: false }),
    );
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("requireReview");
  });

  it("rifiuta un orario non HH:MM", () => {
    const result = bindingDraftSchema.safeParse(draft({ scheduleTime: "25:00" }));
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("scheduleTime");
  });

  it("richiede l'accettazione della policy JustWatch quando la collezione è JustWatch", () => {
    const result = bindingDraftSchema.safeParse(
      draft({ justwatchCollection: true, justwatchPolicyAccepted: false }),
    );
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("justwatchPolicyAccepted");
  });

  it("accetta una bozza JustWatch con policy esplicita", () => {
    const result = bindingDraftSchema.safeParse(
      draft({ justwatchCollection: true, justwatchPolicyAccepted: true }),
    );
    expect(result.success).toBe(true);
  });

  it("espone i campi per tutti gli 8 step del wizard", () => {
    expect(Object.keys(bindingStepFields)).toHaveLength(8);
  });
});

describe("bootstrapSchema", () => {
  const valid = {
    token: "token",
    email: "admin@example.com",
    password: "password-lunga-12",
    confirmPassword: "password-lunga-12",
  };

  it("accetta dati validi", () => {
    expect(bootstrapSchema.safeParse(valid).success).toBe(true);
  });

  it("rifiuta password non coincidenti", () => {
    const result = bootstrapSchema.safeParse({ ...valid, confirmPassword: "diversa-password" });
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("confirmPassword");
  });

  it("rifiuta password uguale all'email", () => {
    const result = bootstrapSchema.safeParse({
      ...valid,
      email: "admin@example.com",
      password: "admin@example.com",
      confirmPassword: "admin@example.com",
    });
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("password");
  });

  it("rifiuta password più corte di 12 caratteri", () => {
    const result = bootstrapSchema.safeParse({
      ...valid,
      password: "corta",
      confirmPassword: "corta",
    });
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("password");
  });
});

describe("settingsSchema", () => {
  const valid = {
    timezone: "Europe/Rome",
    syncBatchSize: 100,
    maxRemovalAbsolute: 50,
    maxRemovalPercent: 10,
    maxAdditionPercent: 50,
    notificationsSummaryEnabled: true,
    notificationsSummaryHour: 8,
  };

  it("accetta valori validi", () => {
    expect(settingsSchema.safeParse(valid).success).toBe(true);
  });

  it("rifiuta una soglia percentuale oltre il 50%", () => {
    const result = settingsSchema.safeParse({ ...valid, maxRemovalPercent: 80 });
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("maxRemovalPercent");
  });

  it("rifiuta un batch non intero", () => {
    const result = settingsSchema.safeParse({ ...valid, syncBatchSize: 10.5 });
    expect(result.success).toBe(false);
    expect(issuePaths(result)).toContain("syncBatchSize");
  });
});
