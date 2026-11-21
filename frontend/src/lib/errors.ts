import { ApiError, isApiError } from "../api/client";
import type { ErrorCategory } from "../api/types";

export interface ErrorPresentation {
  title: string;
  message: string;
  category: ErrorCategory;
  requestId?: string;
  retryAfterS?: number;
  /** `true` quando l'utente può riprovare la stessa richiesta. */
  retryable: boolean;
}

function readNumber(
  details: Record<string, unknown> | undefined,
  key: string,
): number | null {
  const value = details?.[key];
  return typeof value === "number" ? value : null;
}


/**
 * Testi UI derivati dalla categoria: il messaggio grezzo del server non viene
 * mai mostrato (docs/phases/phase-01.md §6).
 */
export function describeApiError(error: unknown): ErrorPresentation {
  if (!isApiError(error)) {
    return {
      title: "Errore imprevisto",
      message: "Si è verificato un errore non gestito. Riprova.",
      category: "INTERNAL",
      retryable: true,
    };
  }

  const base = {
    category: error.category,
    requestId: error.requestId,
    retryAfterS: error.retryAfterS,
    retryable: error.retryable,
  };

  if (error.code === "ORDER_NOT_ENFORCED") {
    return {
      ...base,
      title: "Ordine non applicato",
      message:
        "Gli elementi sono corretti, ma MDBList non ha confermato l'ordine. Nessuna lista è stata ricreata.",
      retryable: false,
    };
  }

  if (error.code === "DRY_RUN_REQUIRED") {
    return {
      ...base,
      title: "Dry-run richiesto",
      message:
        "Serve un dry-run completato con successo prima di eseguire un run reale su questa lista.",
      retryable: false,
    };
  }

  if (error.code === "JUSTWATCH_POLICY_NOT_ACCEPTED") {
    return {
      ...base,
      title: "Policy JustWatch richiesta",
      message:
        "Accetta esplicitamente la policy JustWatch prima di creare il binding.",
      retryable: false,
    };
  }

  if (error.code === "PROVIDER_IN_USE") {
    return {
      ...base,
      title: "Provider in uso",
      message:
        "Il provider è collegato a una o più collezioni. Rimuovi prima quelle collezioni, poi elimina il provider.",
      retryable: false,
    };
  }

  if (error.code === "PROVIDER_ALREADY_EXISTS") {
    return {
      ...base,
      title: "Provider già esistente",
      message:
        "Esiste già un provider con questo slug. Apri la card del provider esistente o scegli uno slug diverso.",
      retryable: false,
    };
  }

  if (error.code === "MAPPING_ALREADY_EXISTS") {
    return {
      ...base,
      title: "ID già associato",
      message:
        "Questo ID esterno (TMDb o JustWatch) è già associato a un altro provider. Controlla l'ID digitato.",
      retryable: false,
    };
  }

  if (error.code === "SOURCE_NOT_AVAILABLE") {
    return {
      ...base,
      title: "Fonte non disponibile",
      message: error.message || "La fonte non è configurata: eseguire il seed.",
      retryable: false,
    };
  }

  /**
   * `429 AUTH_RATE_LIMITED` è un rate limit di autenticazione, non una sessione
   * scaduta: senza questo ramo la UI mostrerebbe "Sessione scaduta"
   * (docs/phases/phase-01.md §6: "429 mostra un countdown").
   */
  if (
    error.category === "AUTH" &&
    (error.status === 429 || error.code === "AUTH_RATE_LIMITED")
  ) {
    return {
      ...base,
      title: "Troppi tentativi",
      message:
        error.retryAfterS != null
          ? `Troppi tentativi di accesso. Riprova tra ${error.retryAfterS} secondi.`
          : "Troppi tentativi di accesso. Riprova più tardi.",
    };
  }

  switch (error.category) {
    case "AUTH":
      return {
        ...base,
        title: "Sessione scaduta",
        message: "Accedi di nuovo per continuare.",
      };
    case "VALIDATION":
      return {
        ...base,
        title: "Dati non validi",
        message: "Controlla i campi evidenziati.",
      };
    case "SOURCE":
      return {
        ...base,
        title: "Errore della fonte",
        message:
          "La fonte non ha risposto correttamente. Lo snapshot non è stato considerato valido.",
      };
    case "TARGET":
      return {
        ...base,
        title: "Errore MDBList",
        message:
          error.retryAfterS != null
            ? `MDBList ha rifiutato la richiesta. Riprova tra ${error.retryAfterS} s.`
            : "MDBList ha rifiutato la richiesta. Riprova più tardi.",
      };
    case "POLICY": {
      const observed = readNumber(error.details, "observed");
      const threshold = readNumber(error.details, "threshold");
      const detail =
        observed != null && threshold != null
          ? `La rimozione prevista (${observed}) supera la soglia (${threshold}).`
          : "L'operazione supera le soglie configurate.";
      return {
        ...base,
        title: "Operazione bloccata dalle soglie",
        message: `${detail} Serve una revisione manuale.`,
        retryable: false,
      };
    }
    case "CONFLICT":
      return {
        ...base,
        title: "Operazione già in corso",
        message:
          "Un'altra operazione è in corso su questa risorsa. Attendi e riprova.",
      };
    case "NETWORK":
      return {
        ...base,
        title: "Connessione assente",
        message: "Impossibile raggiungere il server. Verifica la rete.",
      };
    case "INTERNAL":
    default:
      return {
        ...base,
        title: "Errore interno",
        message: error.requestId
          ? `Errore imprevisto. Codice richiesta: ${error.requestId}.`
          : "Errore imprevisto. Riprova tra poco.",
      };
  }
}

/** Errori di campo da `details.fields` (422). */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!isApiError(error)) return {};
  const fields = error.details?.fields;
  if (typeof fields !== "object" || fields === null) return {};
  const result: Record<string, string> = {};
  for (const [field, value] of Object.entries(fields)) {
    if (typeof value === "string") result[field] = value;
  }
  return result;
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.isUnauthorized;
}

