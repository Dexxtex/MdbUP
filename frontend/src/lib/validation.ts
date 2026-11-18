import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().trim().min(1, "Inserisci l'email.").email("Email non valida."),
  password: z.string().min(1, "Inserisci la password."),
});

export type LoginValues = z.infer<typeof loginSchema>;

export const bootstrapSchema = z
  .object({
    token: z.string().trim().min(1, "Inserisci il token di bootstrap."),
    email: z.string().trim().min(1, "Inserisci l'email.").email("Email non valida."),
    password: z
      .string()
      .min(12, "La password deve avere almeno 12 caratteri.")
      .max(200, "La password è troppo lunga."),
    confirmPassword: z.string().min(1, "Conferma la password."),
  })
  .superRefine((values, ctx) => {
    if (values.password !== values.confirmPassword) {
      ctx.addIssue({
        code: "custom",
        path: ["confirmPassword"],
        message: "Le password non coincidono.",
      });
    }
    if (values.password.toLowerCase() === values.email.toLowerCase()) {
      ctx.addIssue({
        code: "custom",
        path: ["password"],
        message: "La password non può coincidere con l'email.",
      });
    }
  });

export type BootstrapValues = z.infer<typeof bootstrapSchema>;

const MEDIA_TYPE_VALUES = ["MOVIE", "SHOW"] as const;
const SYNC_MODE_VALUES = ["MIRROR", "APPEND_ONLY"] as const;
const SCHEDULE_VALUES = ["MANUAL", "DAILY", "WEEKLY"] as const;
const SCHEDULE_POLICY_VALUES = [
  "AUTO_APPLY_IF_SAFE",
  "ALWAYS_APPROVE",
  "DRY_RUN_ONLY",
] as const;
const PREVIEW_STATE_VALUES = ["RUNNING", "READY", "BLOCKED", "FAILED"] as const;

const timeOfDay = z
  .string()
  .regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Orario non valido (HH:MM).");

const baseBindingDraftSchema = z.object({
  country: z.string().trim().length(2, "Usa il codice paese di 2 lettere (es. IT)."),
  providerId: z.string().min(1, "Seleziona un provider."),
  sourceId: z.string().min(1, "Seleziona una fonte."),
  collectionId: z.string().min(1, "Seleziona una collezione."),
  mediaType: z.enum(MEDIA_TYPE_VALUES),
  previewId: z.string().optional(),
  previewState: z.enum(PREVIEW_STATE_VALUES).optional(),
  acknowledgedRemovals: z.boolean(),
  targetMode: z.enum(["existing", "new"]),
  targetId: z.string().optional(),
  newListName: z.string().trim().max(80, "Massimo 80 caratteri.").optional(),
  private: z.boolean(),
  mode: z.enum(SYNC_MODE_VALUES),
  schedule: z.enum(SCHEDULE_VALUES),
  scheduleTime: timeOfDay,
  maxRemovalPct: z
    .number({ error: "Inserisci un numero." })
    .min(0, "La soglia non può essere negativa.")
    .max(50, "Massimo 50%."),
  maxRemovalAbs: z
    .number({ error: "Inserisci un numero." })
    .int("Usa un numero intero.")
    .min(0, "La soglia non può essere negativa.")
    .max(5000, "Massimo 5000 elementi."),
  preserveOrder: z.boolean(),
  reorderEnabled: z.boolean(),
  schedulePolicy: z.enum(SCHEDULE_POLICY_VALUES),
  requireReview: z.boolean(),
  policyAccepted: z.boolean(),
  justwatchCollection: z.boolean(),
  justwatchPolicyAccepted: z.boolean(),
  confirmName: z.string().min(1, "Digita il nome della collezione."),
});

function refineTarget(
  values: { targetMode: "existing" | "new"; targetId?: string; newListName?: string },
  ctx: z.RefinementCtx,
): void {
  if (values.targetMode === "existing" && !values.targetId) {
    ctx.addIssue({
      code: "custom",
      path: ["targetId"],
      message: "Seleziona una lista.",
    });
  }
  if (values.targetMode === "new") {
    const name = (values.newListName ?? "").trim();
    if (name.length < 3) {
      ctx.addIssue({
        code: "custom",
        path: ["newListName"],
        message: "Inserisci un nome di 3–80 caratteri.",
      });
    }
  }
}

function refineThresholds(
  values: { mode: "MIRROR" | "APPEND_ONLY"; maxRemovalPct: number; maxRemovalAbs: number },
  ctx: z.RefinementCtx,
): void {
  if (values.mode === "MIRROR" && values.maxRemovalPct === 0 && values.maxRemovalAbs === 0) {
    ctx.addIssue({
      code: "custom",
      path: ["maxRemovalAbs"],
      message: "Con MIRROR serve almeno una soglia di rimozione maggiore di zero.",
    });
  }
}

export const bindingDraftSchema = baseBindingDraftSchema.superRefine((values, ctx) => {
  refineTarget(values, ctx);
  refineThresholds(values, ctx);

  if (values.previewState === "BLOCKED" && !values.requireReview) {
    ctx.addIssue({
      code: "custom",
      path: ["requireReview"],
      message: "Con anteprima bloccata serve la revisione manuale.",
    });
  }
  if (!values.policyAccepted) {
    ctx.addIssue({
      code: "custom",
      path: ["policyAccepted"],
      message: "Devi accettare la policy di sincronizzazione.",
    });
  }
  if (values.justwatchCollection && !values.justwatchPolicyAccepted) {
    ctx.addIssue({
      code: "custom",
      path: ["justwatchPolicyAccepted"],
      message:
        "Accetta esplicitamente la policy JustWatch: il binding nasce disabilitato e richiede un dry-run.",
    });
  }
});

export type BindingDraft = z.infer<typeof bindingDraftSchema>;

export const DEFAULT_BINDING_DRAFT: BindingDraft = {
  country: "IT",
  providerId: "",
  sourceId: "",
  collectionId: "",
  mediaType: "MOVIE",
  acknowledgedRemovals: false,
  targetMode: "existing",
  private: false,
  mode: "MIRROR",
  schedule: "MANUAL",
  scheduleTime: "03:00",
  maxRemovalPct: 10,
  maxRemovalAbs: 50,
  preserveOrder: false,
  reorderEnabled: false,
  schedulePolicy: "ALWAYS_APPROVE",
  requireReview: true,
  policyAccepted: false,
  justwatchCollection: false,
  justwatchPolicyAccepted: false,
  confirmName: "",
};

/** Campi validati da ciascuno step del wizard (1-based). */
export const bindingStepFields: Record<number, (keyof BindingDraft)[]> = {
  1: ["country", "providerId"],
  2: ["sourceId"],
  3: ["collectionId", "mediaType"],
  4: ["mediaType"],
  5: ["previewId", "acknowledgedRemovals"],
  6: ["targetMode", "targetId", "newListName", "private"],
  7: [
    "mode",
    "schedule",
    "scheduleTime",
    "maxRemovalPct",
    "maxRemovalAbs",
    "preserveOrder",
    "reorderEnabled",
    "schedulePolicy",
    "requireReview",
  ],
  8: ["policyAccepted", "justwatchPolicyAccepted", "confirmName"],
};

export const BINDING_POLICY_VERSION = "planning-v1";

export const settingsSchema = z.object({
  timezone: z.string().trim().min(1, "Indica un fuso orario."),
  syncBatchSize: z
    .number({ error: "Inserisci un numero." })
    .int("Usa un numero intero.")
    .min(1, "Minimo 1.")
    .max(1000, "Massimo 1000."),
  maxRemovalAbsolute: z
    .number({ error: "Inserisci un numero." })
    .int("Usa un numero intero.")
    .min(0, "La soglia non può essere negativa.")
    .max(5000, "Massimo 5000."),
  maxRemovalPercent: z
    .number({ error: "Inserisci un numero." })
    .min(0, "La soglia non può essere negativa.")
    .max(50, "Massimo 50%."),
  maxAdditionPercent: z
    .number({ error: "Inserisci un numero." })
    .min(0, "La soglia non può essere negativa.")
    .max(100, "Massimo 100%."),
  notificationsSummaryEnabled: z.boolean(),
  notificationsSummaryHour: z
    .number({ error: "Inserisci un'ora." })
    .int("Usa un numero intero.")
    .min(0, "Minimo 0.")
    .max(23, "Massimo 23."),
});

export type SettingsValues = z.infer<typeof settingsSchema>;

export const credentialSchema = z.object({
  apiKey: z
    .string()
    .trim()
    .min(8, "La chiave sembra troppo corta.")
    .max(500, "La chiave è troppo lunga."),
});

export type CredentialValues = z.infer<typeof credentialSchema>;

export const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, "Inserisci la password attuale."),
    newPassword: z
      .string()
      .min(12, "La nuova password deve avere almeno 12 caratteri.")
      .max(128, "La password è troppo lunga."),
    confirmPassword: z.string().min(1, "Conferma la nuova password."),
  })
  .superRefine((values, ctx) => {
    if (values.newPassword !== values.confirmPassword) {
      ctx.addIssue({
        code: "custom",
        path: ["confirmPassword"],
        message: "Le password non coincidono.",
      });
    }
  });

export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
