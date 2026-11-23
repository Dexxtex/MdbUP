import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryState {
  hasError: boolean;
}

/** Fallback senza stack trace né dettagli interni (specifica fase 1 §8). */
export class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Errore non gestito nella UI", error.name, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center p-6">
          <h1 className="text-xl font-semibold text-ink">Si è verificato un errore</h1>
          <p className="mt-2 text-sm text-ink-muted">
            La pagina non può essere mostrata. Ricarica per riprovare.
          </p>
          <button
            type="button"
            className="mt-4 min-h-11 w-fit rounded-md bg-accent px-4 text-sm font-medium text-accent-contrast hover:bg-accent-strong"
            onClick={() => window.location.reload()}
          >
            Ricarica
          </button>
        </main>
      );
    }
    return this.props.children;
  }
}
