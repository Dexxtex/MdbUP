import { useEffect, useId, useMemo, useRef, useState } from "react";

import { cn } from "../../lib/cn";
import { IconSearch } from "../ui/icons";
import { Input } from "../ui/primitives";

/** Ciò che serve al menu: nome mostrato, slug e tipo per la ricerca. */
export interface SuggestProvider {
  name: string;
  slug: string;
  kind?: string;
}

export interface ProviderSuggestProps {
  id: string;
  value: string;
  onChange: (text: string) => void;
  providers: readonly SuggestProvider[];
  placeholder?: string;
}

/**
 * Campo "Cerca provider" con menu a tendina dei provider presenti.
 *
 * Se non ci sono provider il menu non esiste affatto (nessuna listbox vuota,
 * nessun messaggio): l'input resta un normale campo di ricerca. Lo stesso
 * predicato del filtro di pagina (nome, slug, tipo) governa le voci proposte.
 */
export function ProviderSuggest({
  id,
  value,
  onChange,
  providers,
  placeholder = "Netflix, Prime Video, Disney+…",
}: ProviderSuggestProps) {
  const listboxId = `${useId()}-listbox`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const hasProviders = providers.length > 0;

  const visible = useMemo(() => {
    const needle = value.trim().toLowerCase();
    if (!needle) return providers;
    return providers.filter(
      (provider) =>
        provider.name.toLowerCase().includes(needle) ||
        provider.slug.toLowerCase().includes(needle) ||
        (provider.kind ?? "").toLowerCase().includes(needle),
    );
  }, [providers, value]);

  useEffect(() => {
    setActive(0);
  }, [value, providers.length]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function choose(name: string) {
    onChange(name);
    setOpen(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!hasProviders || visible.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => (current + delta + visible.length) % visible.length);
      return;
    }
    if (event.key === "Enter" && open) {
      event.preventDefault();
      const option = visible[active];
      if (option) choose(option.name);
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
        <IconSearch />
      </span>
      <Input
        id={id}
        role="combobox"
        autoComplete="off"
        aria-expanded={open && visible.length > 0}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={open && visible[active] ? `${id}-option-${visible[active].slug}` : undefined}
        value={value}
        placeholder={placeholder}
        className="pl-9"
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => window.setTimeout(() => setOpen(false), 0)}
      />
      {/* Nessun provider presente → nessun menu da mostrare. */}
      {open && visible.length > 0 ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Provider presenti"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-line bg-surface-elevated py-1 shadow-lg"
        >
          {visible.map((provider, index) => (
            <li
              key={provider.slug}
              id={`${id}-option-${provider.slug}`}
              role="option"
              aria-selected={index === active}
              onMouseDown={(event) => {
                event.preventDefault();
                choose(provider.name);
              }}
              onMouseEnter={() => setActive(index)}
              className={cn(
                "cursor-pointer px-3 py-2 text-sm",
                index === active ? "bg-surface-muted text-ink" : "text-ink",
              )}
            >
              {provider.name}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
