import {
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type RefObject,
  type SVGProps,
} from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useLogout } from "../hooks/mutations";
import { useRuns, useSession } from "../hooks/queries";
import { Button } from "../components/ui/primitives";
import { HealthCluster } from "../components/ui/health-cluster";
import { ThemeToggle } from "../components/ui/theme-toggle";
import {
  IconActivity,
  IconBuilding,
  IconChevronLeft,
  IconChevronRight,
  IconGrid,
  IconHelp,
  IconLayers,
  IconLink,
  IconLogout,
  IconMenu,
  IconRefresh,
  IconSettings,
  IconShield,
  IconX,
} from "../components/ui/icons";
import { useCountry } from "./country-context";
import { cn } from "../lib/cn";
import { withCountry } from "../lib/country-url";

const SIDEBAR_STORAGE_KEY = "mdbup-sidebar-collapsed";

interface NavItem {
  to: string;
  label: string;
  end: boolean;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  testId: string;
}

const navigation: NavItem[] = [
  { to: "/app", label: "Dashboard", end: true, icon: IconGrid, testId: "nav-dashboard" },
  {
    to: "/app/catalog-changes",
    label: "Cambi Catalogo",
    end: false,
    icon: IconRefresh,
    testId: "nav-catalog-changes",
  },
  {
    to: "/app/providers",
    label: "Provider",
    end: false,
    icon: IconBuilding,
    testId: "nav-providers",
  },
  {
    to: "/app/collections",
    label: "Collezioni",
    end: false,
    icon: IconLayers,
    testId: "nav-collections",
  },
  { to: "/app/bindings", label: "Binding", end: false, icon: IconLink, testId: "nav-bindings" },
  { to: "/app/runs", label: "Run", end: false, icon: IconActivity, testId: "nav-runs" },
  {
    to: "/app/settings",
    label: "Impostazioni",
    end: false,
    icon: IconSettings,
    testId: "nav-settings",
  },
  {
    to: "/app/help",
    label: "Guida",
    end: false,
    icon: IconHelp,
    testId: "nav-help",
  },
];

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function storeCollapsed(value: boolean): void {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(value));
  } catch {
    // Preferenza non persistita: la sidebar resta usabile.
  }
}

function currentSection(pathname: string): string {
  const match = navigation.find(
    (item) => item.to !== "/app" && pathname.startsWith(item.to),
  );
  return match?.label ?? "Dashboard";
}

function NavItems({
  collapsed,
  onNavigate,
  firstLinkRef,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  firstLinkRef?: RefObject<HTMLAnchorElement>;
}) {
  const { country } = useCountry();
  return (
    <ul className="space-y-1">
      {navigation.map((item, index) => {
        const Icon = item.icon;
        return (
          <li key={item.to}>
            <NavLink
              to={withCountry(item.to, country)}
              end={item.end}
              onClick={onNavigate}
              ref={index === 0 ? firstLinkRef : undefined}
              data-testid={item.testId}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                cn(
                  "flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  collapsed && "justify-center px-0",
                  isActive
                    ? "bg-accent-soft text-accent"
                    : "text-ink-muted hover:bg-surface-muted hover:text-ink",
                )
              }
            >
              <Icon className="shrink-0" />
              <span className={cn(collapsed && "sr-only")}>{item.label}</span>
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const approvals = useRuns({ status: "AWAITING_APPROVAL" });
  const logout = useLogout();
  const mainRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const firstDrawerLinkRef = useRef<HTMLAnchorElement>(null);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    // Focus the main region for screen readers, but do not let the browser
    // scroll the focused element under the sticky header; reset to the top.
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    mainRef.current?.focus({ preventScroll: true });
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (mobileOpen) firstDrawerLinkRef.current?.focus();
  }, [mobileOpen]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    storeCollapsed(next);
  };

  const onLogout = async () => {
    try {
      await logout.mutateAsync();
    } finally {
      navigate("/login", { replace: true });
    }
  };

  const pendingApprovals = approvals.data?.total ?? 0;
  const section = currentSection(location.pathname);

  return (
    <div className="min-h-screen bg-page">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-accent focus:shadow-pop"
      >
        Vai al contenuto
      </a>

      <div className="flex min-h-screen">
        <aside
          className={cn(
            "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-surface lg:flex",
            collapsed ? "w-[4.75rem]" : "w-64",
          )}
        >
          <div
            className={cn(
              "flex h-16 items-center gap-2 border-b border-line px-4",
              collapsed && "justify-center px-0",
            )}
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-contrast">
              <IconShield />
            </span>
            <span className={cn("text-base font-semibold tracking-tight", collapsed && "sr-only")}>
              MdbUP
            </span>
          </div>

          <nav
            aria-label="Navigazione principale"
            data-testid="app-nav"
            className="flex-1 overflow-y-auto p-3"
          >
            <NavItems collapsed={collapsed} />
          </nav>

          <div className="border-t border-line p-3">
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-pressed={collapsed}
              aria-label={collapsed ? "Espandi la barra laterale" : "Comprimi la barra laterale"}
              title={collapsed ? "Espandi" : "Comprimi"}
              className={cn(
                "flex min-h-9 w-full items-center gap-2 rounded-md px-3 text-xs font-medium text-ink-muted hover:bg-surface-muted hover:text-ink",
                collapsed && "justify-center px-0",
              )}
            >
              {collapsed ? <IconChevronRight /> : <IconChevronLeft />}
              <span className={cn(collapsed && "sr-only")}>Comprimi</span>
            </button>
          </div>
        </aside>

        {mobileOpen ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button
              type="button"
              aria-label="Chiudi il menu"
              className="absolute inset-0 bg-black/60"
              onClick={() => setMobileOpen(false)}
            />
            <aside
              id="app-nav-drawer"
              aria-label="Navigazione principale"
              className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-line bg-surface shadow-pop"
            >
              <div className="flex h-16 items-center justify-between border-b border-line px-4">
                <span className="flex items-center gap-2 text-base font-semibold">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-contrast">
                    <IconShield />
                  </span>
                  MdbUP
                </span>
                <button
                  type="button"
                  aria-label="Chiudi il menu"
                  className="rounded-md p-2 text-ink-muted hover:bg-surface-muted hover:text-ink"
                  onClick={() => {
                    setMobileOpen(false);
                    menuButtonRef.current?.focus();
                  }}
                >
                  <IconX />
                </button>
              </div>
              <nav aria-label="Navigazione principale" className="flex-1 overflow-y-auto p-3">
                <NavItems
                  collapsed={false}
                  firstLinkRef={firstDrawerLinkRef}
                  onNavigate={() => setMobileOpen(false)}
                />
              </nav>
              <div className="space-y-2 border-t border-line p-3">
                <p className="truncate text-xs text-ink-muted">{session.data?.user.email}</p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full"
                  onClick={onLogout}
                  busy={logout.isPending}
                >
                  <IconLogout />
                  Esci
                </Button>
              </div>
            </aside>
          </div>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-line bg-page/85 backdrop-blur">
            <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
              <button
                ref={menuButtonRef}
                type="button"
                aria-label="Apri il menu"
                aria-expanded={mobileOpen}
                aria-controls="app-nav-drawer"
                onClick={() => setMobileOpen(true)}
                className="rounded-md border border-line bg-surface p-2 text-ink-muted hover:text-ink lg:hidden"
              >
                <IconMenu />
              </button>

              <div className="min-w-0 flex-1">
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-ink-faint">
                  Control plane
                </p>
                <p className="truncate text-sm font-medium text-ink">{section}</p>
              </div>

              <HealthCluster className="hidden sm:flex" />

              <NavLink
                to="/app/runs?status=AWAITING_APPROVAL"
                data-testid="pending-approvals"
                title="Run in attesa di approvazione"
                className={cn(
                  "relative inline-flex h-9 items-center gap-2 rounded-md border px-2.5 text-xs font-medium",
                  pendingApprovals > 0
                    ? "border-warning/50 bg-warning-soft text-warning"
                    : "border-line bg-surface text-ink-muted hover:text-ink",
                )}
              >
                <IconActivity />
                <span className="tabular-nums">{pendingApprovals}</span>
                <span className="hidden md:inline">da approvare</span>
              </NavLink>

              <ThemeToggle />

              <div className="hidden items-center gap-2 border-l border-line pl-3 md:flex">
                <span className="max-w-[12rem] truncate text-xs text-ink-muted">
                  {session.data?.user.email}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onLogout}
                  busy={logout.isPending}
                  aria-label="Esci"
                >
                  <IconLogout />
                  <span className="hidden lg:inline">Esci</span>
                </Button>
              </div>
            </div>
          </header>

          <main
            id="main"
            ref={mainRef}
            tabIndex={-1}
            className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 focus:outline-none sm:px-6 lg:px-8"
          >
            <div aria-live="polite" className="sr-only">
              {location.pathname}
            </div>
            <Outlet />
          </main>

          <footer className="mt-8 border-t border-line">
            <div className="mx-auto w-full max-w-7xl space-y-1 px-4 py-4 text-xs text-ink-faint sm:px-6 lg:px-8">
              <p>
                Dati di disponibilità: TMDb (powered by JustWatch). This product uses the
                TMDB API but is not endorsed or certified by TMDB.
              </p>
              <p>
                Le collezioni &quot;Appena rilevati&quot; sono derivate dall&apos;osservazione
                dell&apos;app (<code className="font-mono">first_seen_at</code>), non da date
                ufficiali del provider.
              </p>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
