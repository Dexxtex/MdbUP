import { useEffect, useId, useMemo, useRef, useState } from "react";

import { COUNTRIES, countryLabel, type Country } from "../../lib/countries";
import { Input } from "./primitives";
import { cn } from "../../lib/cn";

/**
 * Combobox per il paese: 249 voci sono troppe per un `<select>` navigabile,
 * quindi il campo è un input con filtro e una listbox. Pattern ARIA 1.2
 * (`role="combobox"` + `aria-activedescendant`), nessuna dipendenza esterna.
 */
export interface CountrySelectProps {
  id: string;
  value: string;
  onChange: (code: string) => void;
  countries?: readonly Country[];
  className?: string;
}

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function CountrySelect({
  id,
  value,
  onChange,
  countries = COUNTRIES,
  className,
}: CountrySelectProps) {
  const listboxId = `${useId()}-listbox`;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const filtered = useMemo(() => {
    const needle = normalize(query);
    if (!needle) return countries;
    return countries.filter(
      (country) =>
        normalize(country.name).includes(needle) ||
        country.code.toLowerCase().startsWith(needle),
    );
  }, [countries, query]);

  // Nessun "pin" del paese selezionato: mentre si filtra l'elenco deve essere
  // esattamente ciò che la query seleziona. Il valore corrente resta leggibile
  // nell'input quando la listbox è chiusa.
  useEffect(() => {
    setActive((current) => Math.min(current, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function close() {
    setOpen(false);
    setQuery("");
  }

  function select(code: string) {
    onChange(code);
    close();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => {
        if (filtered.length === 0) return 0;
        return (current + delta + filtered.length) % filtered.length;
      });
      return;
    }
    if (event.key === "Enter") {
      if (!open) {
        setOpen(true);
        return;
      }
      event.preventDefault();
      const option = filtered[active];
      if (option) select(option.code);
      return;
    }
    if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        close();
      }
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      if (!open) return;
      event.preventDefault();
      setActive(event.key === "Home" ? 0 : Math.max(0, filtered.length - 1));
    }
  }

  const activeOption = filtered[active];

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <Input
        id={id}
        role="combobox"
        autoComplete="off"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={open && activeOption ? `${id}-option-${activeOption.code}` : undefined}
        value={open ? query : countryLabel(value)}
        placeholder="Cerca per nome o codice ISO, es. Italia o IT"
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActive(0);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          // Chiude solo se il focus non va su un'opzione (mousedown la mantiene).
          window.setTimeout(() => setOpen(false), 0);
        }}
        className={cn(open && "border-accent")}
      />
      {open ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Paesi disponibili"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-line bg-surface-elevated py-1 shadow-lg"
        >
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-sm text-ink-muted" role="presentation">
              Nessun paese corrisponde alla ricerca.
            </li>
          ) : (
            filtered.map((country, index) => (
              <li
                key={country.code}
                id={`${id}-option-${country.code}`}
                role="option"
                aria-selected={country.code === value}
                onMouseDown={(event) => {
                  event.preventDefault();
                  select(country.code);
                }}
                onMouseEnter={() => setActive(index)}
                className={cn(
                  "cursor-pointer px-3 py-2 text-sm",
                  index === active ? "bg-surface-muted text-ink" : "text-ink",
                  country.code === value && "font-semibold text-accent",
                )}
              >
                {country.code} — {country.name}
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
