import { useEffect, useId, useMemo, useRef, useState } from "react";

import { cn } from "../../lib/cn";
import { useTvdbCompanies } from "../../hooks/queries";
import { Input } from "../ui/primitives";

/** Attesa prima di interrogare TheTVDB mentre si scrive (l'API vuole ≥2 lettere). */
const DEBOUNCE_MS = 300;
const MIN_QUERY = 2;

export interface TvdbCompanySelectProps {
  id: string;
  /** `company_id` selezionato (stringa vuota = nessuno). */
  value: string;
  onChange: (companyId: string) => void;
  placeholder?: string;
}

/**
 * Campo "ID azienda su TheTVDB": menù a tendina con ricerca sul catalogo
 * company della fonte. TheTVDB cerca solo da 2 caratteri in su e non dichiara
 * disponibilità per paese: le voci sono identificativi, non prove di offerta.
 */
export function TvdbCompanySelect({
  id,
  value,
  onChange,
  placeholder = "Cerca per nome, es. Netflix",
}: TvdbCompanySelectProps) {
  const listboxId = `${useId()}-listbox`;
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [label, setLabel] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const search = useTvdbCompanies(debounced);
  const results = useMemo(() => search.data?.items ?? [], [search.data]);
  const canSearch = debounced.length >= MIN_QUERY;

  useEffect(() => {
    setActive(0);
  }, [results.length, debounced]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function choose(companyId: string, companyLabel: string) {
    onChange(companyId);
    setLabel(companyLabel);
    setQuery("");
    setOpen(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => (current + delta + results.length) % results.length);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const company = results[active];
      if (company) choose(company.company_id, company.name);
      return;
    }
    if (event.key === "Escape") setOpen(false);
  }

  const display = open ? query : value;
  const showMenu = open && canSearch && results.length > 0;
  const activeCompany = results[active];

  return (
    <div ref={rootRef} className="relative">
      <Input
        id={id}
        role="combobox"
        autoComplete="off"
        aria-expanded={showMenu}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={
          showMenu && activeCompany ? `${id}-option-${activeCompany.company_id}` : undefined
        }
        value={display}
        placeholder={placeholder}
        onFocus={() => {
          setOpen(true);
          setQuery(label || "");
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => window.setTimeout(() => setOpen(false), 0)}
      />
      {open && canSearch ? (
        <div className="absolute z-20 mt-1 w-full rounded-md border border-line bg-surface-elevated py-1 shadow-lg">
          {search.isFetching ? (
            <p className="px-3 py-2 text-sm text-ink-muted">Cerco su TheTVDB…</p>
          ) : search.isError ? (
            <p className="px-3 py-2 text-sm text-ink-muted">
              Ricerca non disponibile: controlla la credenziale TheTVDB.
            </p>
          ) : results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-ink-muted">
              Nessuna company trovata per “{debounced}”.
            </p>
          ) : (
            <ul id={listboxId} role="listbox" aria-label="Company TheTVDB" className="max-h-64 overflow-y-auto">
              {results.map((company, index) => (
                <li
                  key={company.company_id}
                  id={`${id}-option-${company.company_id}`}
                  role="option"
                  aria-selected={index === active}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    choose(company.company_id, company.name);
                  }}
                  onMouseEnter={() => setActive(index)}
                  className={cn(
                    "cursor-pointer px-3 py-2 text-sm",
                    index === active ? "bg-surface-muted text-ink" : "text-ink",
                  )}
                >
                  {company.name}
                  <span className="ml-2 text-xs text-ink-faint">{company.company_id}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
      {!open && label ? (
        <p className="mt-1 text-xs text-ink-muted">Selezionato: {label}</p>
      ) : null}
      {!canSearch && query.trim().length === 1 ? (
        <p className="mt-1 text-xs text-ink-muted">Scrivi almeno {MIN_QUERY} lettere per cercare.</p>
      ) : null}
    </div>
  );
}
