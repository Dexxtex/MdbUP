import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "../hooks/queries";
import { ErrorState, TableSkeleton } from "../components/ui/feedback";
import { isUnauthorized } from "../lib/errors";

export function RequireSession({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();

  if (session.isPending) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <TableSkeleton rows={3} />
      </div>
    );
  }

  if (session.isError) {
    if (isUnauthorized(session.error)) {
      const next = encodeURIComponent(`${location.pathname}${location.search}`);
      return <Navigate to={`/login?next=${next}`} replace />;
    }
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorState error={session.error} onRetry={() => void session.refetch()} />
      </div>
    );
  }

  return <>{children}</>;
}
