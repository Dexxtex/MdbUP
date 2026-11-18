import { useTheme } from "../../app/theme-provider";
import { cn } from "../../lib/cn";
import { IconMoon, IconSun } from "./icons";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const label = isDark ? "Passa al tema chiaro" : "Passa al tema scuro";

  return (
    <button
      type="button"
      data-testid="theme-toggle"
      aria-pressed={isDark}
      aria-label={label}
      title={label}
      onClick={toggleTheme}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-md border border-line bg-surface text-ink-muted transition-colors",
        "hover:border-line-strong hover:text-ink",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page",
        className,
      )}
    >
      {isDark ? <IconMoon /> : <IconSun />}
    </button>
  );
}
