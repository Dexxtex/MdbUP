import { DEFAULT_BINDING_DRAFT, type BindingDraft } from "./validation";

const DRAFT_KEY = "binding-draft:v1";
const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;

interface StoredDraft {
  savedAt: number;
  values: BindingDraft;
}

function storage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * La bozza del wizard vive solo in sessionStorage (mai localStorage) e non
 * contiene segreti: solo scelte di configurazione.
 */
export function loadBindingDraft(): BindingDraft | null {
  const store = storage();
  if (!store) return null;
  const raw = store.getItem(DRAFT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredDraft>;
    if (typeof parsed.savedAt !== "number") return null;
    if (Date.now() - parsed.savedAt > DRAFT_TTL_MS) {
      store.removeItem(DRAFT_KEY);
      return null;
    }
    const values = parsed.values;
    if (typeof values !== "object" || values === null) return null;
    return { ...DEFAULT_BINDING_DRAFT, ...values };
  } catch {
    store.removeItem(DRAFT_KEY);
    return null;
  }
}

export function saveBindingDraft(values: BindingDraft): void {
  const store = storage();
  if (!store) return;
  const payload: StoredDraft = { savedAt: Date.now(), values };
  try {
    store.setItem(DRAFT_KEY, JSON.stringify(payload));
  } catch {
    // Quota superata: la bozza è un aiuto, non un requisito.
  }
}

export function clearBindingDraft(): void {
  storage()?.removeItem(DRAFT_KEY);
}
