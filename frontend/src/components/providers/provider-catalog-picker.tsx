import { useEffect, useId, useMemo, useRef, useState } from "react";

import { cn } from "../../lib/cn";
import { Input } from "../ui/primitives";

export interface CatalogOption {
  key: string;
  name: string;
}

export interface CatalogGroup<T extends CatalogOption> {
  source: string;
  label: string;
  items: readonly T[];
}

export interface ProviderCatalogPickerProps<T extends CatalogOption> {
  id: string;
  value: string;
  onChange: (text: string) => void;
  groups: readonly CatalogGroup<T>[];
  onSelect: (item: T) => void;
  placeholder?: string;
}

/**
 * Ricerca e scelta del provider da catalogo in un unico controllo: si scrive
 * per filtrare, si apre il menu e si sceglie la voce (raggruppata per fonte).
 *
 * Se non c'è nessun candidato il menu non viene renderizzato: nessuna listbox
 * vuota e nessun messaggio; lo stato delle fonti resta nelle righe sotto.
 */
export function ProviderCatalogPicker<T extends CatalogOption>({
  id,
  value,
  onChange,
  groups,
  onSelect,
  placeholder = "Es. Netflix, Disney, Rai…",
}: ProviderCatalogPickerProps<T>) {
  const listboxId = `${useId()}-listbox`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const flat = useMemo(() => groups.flatMap((group) => group.items), [groups]);

  useEffect(() => {
    setActive(0);
  }, [value, flat.length]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function choose(item: T) {
    onSelect(item);
    setOpen(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (flat.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => (current + delta + flat.length) % flat.length);
      return;
    }
    if (event.key === "Enter" && open) {
      event.preventDefault();
      const option = flat[active];
      if (option) choose(option);
      return;
    }
    if (event.key === "Escape") setOpen(false);
  }

  const activeItem = flat[active];

  return (
    <div ref={rootRef} className="relative">
      <Input
        id={id}
        role="combobox"
        autoComplete="off"
        aria-expanded={open && flat.length > 0}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={open && activeItem ? `${id}-option-${activeItem.key}` : undefined}
        value={value}
        placeholder={placeholder}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => window.setTimeout(() => setOpen(false), 0)}
      />
      {open && flat.length > 0 ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Provider disponibili"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-line bg-surface-elevated py-1 shadow-lg"
        >
          {groups.map((group) => (
            <li key={group.source} role="group" aria-label={group.label} className="py-1">
              <p className="px-3 py-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                {group.label}
              </p>
              <ul role="none">
                {group.items.map((item) => {
                  const index = flat.indexOf(item);
                  return (
                    <li
                      key={item.key}
                      id={`${id}-option-${item.key}`}
                      role="option"
                      aria-selected={index === active}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        choose(item);
                      }}
                      onMouseEnter={() => setActive(index)}
                      className={cn(
                        "cursor-pointer px-3 py-2 text-sm",
                        index === active ? "bg-surface-muted text-ink" : "text-ink",
                      )}
                    >
                      {item.name}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
