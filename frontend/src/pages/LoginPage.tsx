import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useLogin } from "../api/mutations";
import { useSession } from "../api/queries";
import { ErrorState } from "../components/ui/feedback";
import { Button, Field, Input } from "../components/ui/primitives";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { IconShield } from "../components/ui/icons";
import { safeNextPath } from "../lib/navigation";
import { loginSchema, type LoginValues } from "../lib/validation";

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const session = useSession();
  const login = useLogin();
  const next = safeNextPath(searchParams.get("next"));

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  if (session.data) {
    return <Navigate to={next} replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    try {
      await login.mutateAsync(values);
      navigate(next, { replace: true });
    } catch {
      // L'errore è mostrato dall'ErrorState sotto il form.
    }
  });

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-line bg-surface shadow-pop lg:grid-cols-2">
        <div className="hidden flex-col justify-between gap-8 border-r border-line bg-surface-muted p-8 lg:flex">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-accent-contrast">
              <IconShield />
            </span>
            <span className="text-lg font-semibold tracking-tight">MdbUP</span>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
              Control plane
            </p>
            <h2 className="mt-2 text-2xl font-semibold leading-tight text-ink">
              Sincronizza le collezioni dei provider con le tue liste MDBList.
            </h2>
            <p className="mt-3 text-sm text-ink-muted">
              Snapshot verificati, piani di sincronizzazione con soglie di rimozione e
              approvazione esplicita prima di ogni scrittura remota.
            </p>
          </div>
          <p className="text-xs text-ink-faint">
            Dati di disponibilità: TMDb (powered by JustWatch).
          </p>
        </div>

        <div className="p-6 sm:p-8">
          <h1 className="text-2xl font-semibold text-ink">Accedi a MdbUP</h1>
          <p className="mb-6 mt-1 text-sm text-ink-muted">
            Usa le credenziali dell&apos;amministratore configurato al primo avvio.
          </p>

          <div>
            <form
              onSubmit={onSubmit}
              noValidate
              className="space-y-4"
              data-testid="login-form"
            >
              <Field id="email" label="Email" required error={errors.email?.message}>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  autoFocus
                  data-testid="login-email"
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? "email-error" : undefined}
                  {...register("email")}
                />
              </Field>

              <Field
                id="password"
                label="Password"
                required
                error={errors.password?.message}
              >
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  data-testid="login-password"
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? "password-error" : undefined}
                  {...register("password")}
                />
              </Field>

              {login.isError ? <ErrorState error={login.error} /> : null}

              <Button
                type="submit"
                busy={isSubmitting || login.isPending}
                className="w-full"
                data-testid="login-submit"
              >
                Accedi
              </Button>
            </form>
          </div>

          <p className="mt-4 text-sm text-ink-muted">
            Primo avvio?{" "}
            <Link to="/bootstrap" className="font-medium text-accent underline">
              Configura l&apos;amministratore
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
