import { cn } from "../../lib/cn";

export interface StepperProps {
  steps: string[];
  current: number;
}

export function Stepper({ steps, current }: StepperProps) {
  return (
    <nav aria-label="Passaggi" className="mb-6">
      <ol className="flex flex-wrap gap-2">
        {steps.map((label, index) => {
          const stepNumber = index + 1;
          const isCurrent = stepNumber === current;
          const isDone = stepNumber < current;
          return (
            <li
              key={label}
              aria-current={isCurrent ? "step" : undefined}
              className={cn(
                "flex min-h-9 items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
                isCurrent && "border-accent bg-accent-soft text-accent",
                isDone && "border-success/40 bg-success-soft text-success",
                !isCurrent && !isDone && "border-line bg-surface text-ink-muted",
              )}
            >
              <span aria-hidden="true" className="font-semibold tabular-nums">
                {stepNumber}
              </span>
              <span>{label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
