import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
  /** Etichetta usata nella card mobile; default: `header`. */
  cardLabel?: string;
  hideOnCard?: boolean;
}

export interface DataTableProps<T> {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyMessage?: string;
  /** Azioni mostrate in cima alla card mobile, prima dei campi. */
  cardActions?: (row: T) => ReactNode;
}

/**
 * Tabella accessibile su `md+`, elenco di definizioni su mobile: nessuno
 * scroll orizzontale a 320 px.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  emptyMessage = "Nessun elemento.",
  cardActions,
}: DataTableProps<T>) {
  if (rows.length === 0) {
    return <p className="py-6 text-center text-sm text-ink-muted">{emptyMessage}</p>;
  }

  const cardColumns = columns.filter((column) => !column.hideOnCard);

  return (
    <>
      <ul className="space-y-3 md:hidden">
        {rows.map((row) => (
          <li
            key={rowKey(row)}
            className="rounded-lg border border-line bg-surface-elevated p-4"
          >
            {cardActions ? (
              <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
                {cardActions(row)}
              </div>
            ) : null}
            <dl className="grid grid-cols-1 gap-2">
              {cardColumns.map((column) => (
                <div key={column.key} className="flex items-start justify-between gap-4">
                  <dt className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                    {column.cardLabel ?? column.header}
                  </dt>
                  <dd className="text-right text-sm text-ink">{column.render(row)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>

      <div className="hidden md:block">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-line">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(
                    "px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink-faint",
                    column.className,
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                className="border-b border-line/70 transition-colors last:border-0 hover:bg-surface-muted/60"
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn("px-3 py-3 align-top text-ink", column.className)}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
