import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-4 py-16 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">404</p>
      <h1 className="mt-2 text-2xl font-semibold text-ink">Pagina non trovata</h1>
      <p className="mt-2 text-sm text-ink-muted">
        La pagina richiesta non esiste o è stata spostata.
      </p>
      <Link
        to="/app"
        className="mt-6 inline-flex min-h-11 items-center rounded-md bg-accent px-4 text-sm font-medium text-accent-contrast hover:bg-accent-strong"
      >
        Torna alla dashboard
      </Link>
    </main>
  );
}
