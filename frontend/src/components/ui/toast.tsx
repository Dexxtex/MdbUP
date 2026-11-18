import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cn } from "../../lib/cn";
import { IconAlert, IconCheck, IconDot, IconX } from "./icons";

export type ToastTone = "success" | "error" | "info";

export interface ToastInput {
  title: string;
  description?: string;
  tone?: ToastTone;
}

interface ToastEntry extends Required<Pick<ToastInput, "title" | "tone">> {
  id: number;
  description?: string;
}

interface ToastContextValue {
  notify: (toast: ToastInput) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_TIMEOUT_MS = 5_000;

const toneStyles: Record<ToastTone, string> = {
  success: "border-success/40 bg-surface-elevated text-ink",
  error: "border-danger/50 bg-surface-elevated text-ink",
  info: "border-accent/40 bg-surface-elevated text-ink",
};

const toneIcons: Record<ToastTone, typeof IconDot> = {
  success: IconCheck,
  error: IconAlert,
  info: IconDot,
};

const toneIconStyles: Record<ToastTone, string> = {
  success: "text-success",
  error: "text-danger",
  info: "text-accent",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    ({ title, description, tone = "info" }: ToastInput) => {
      const id = nextId.current;
      nextId.current += 1;
      setToasts((current) => [...current.slice(-3), { id, title, description, tone }]);
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), TOAST_TIMEOUT_MS),
      );
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending.values()) clearTimeout(timer);
      pending.clear();
    };
  }, []);

  const value = useMemo(() => ({ notify, dismiss }), [notify, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end"
      >
        {toasts.map((toast) => {
          const Icon = toneIcons[toast.tone];
          return (
            <div
              key={toast.id}
              role="status"
              data-testid="toast"
              className={cn(
                "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border px-4 py-3 shadow-pop animate-toast-in",
                toneStyles[toast.tone],
              )}
            >
              <span className={cn("mt-0.5", toneIconStyles[toast.tone])}>
                <Icon />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{toast.title}</p>
                {toast.description ? (
                  <p className="mt-0.5 text-xs text-ink-muted">{toast.description}</p>
                ) : null}
              </div>
              <button
                type="button"
                aria-label="Chiudi notifica"
                className="rounded p-1 text-ink-faint hover:bg-surface-muted hover:text-ink"
                onClick={() => dismiss(toast.id)}
              >
                <IconX />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast deve essere usato dentro ToastProvider");
  }
  return context;
}
