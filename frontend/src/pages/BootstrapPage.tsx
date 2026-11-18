import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { useBootstrap } from "../api/mutations";
import { ErrorState } from "../components/ui/feedback";
import { Button, Card, Field, Input } from "../components/ui/primitives";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { IconShield } from "../components/ui/icons";
import { bootstrapSchema, type BootstrapValues } from "../lib/validation";

export default function BootstrapPage() {
  const navigate = useNavigate();
  const bootstrap = useBootstrap();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<BootstrapValues>({
    resolver: zodResolver(bootstrapSchema),
    defaultValues: { token: "", email: "", password: "", confirmPassword: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    try {
      await bootstrap.mutateAsync({
        token: values.token,
        email: values.email,
        password: values.password,
      });
      navigate("/login", { replace: true });
    } catch {
      // L'errore è mostrato dall'ErrorState sotto il form.
    }
  });

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-accent-contrast">
            <IconShield />
          </span>
          <span className="text-lg font-semibold tracking-tight">MdbUP</span>
        </div>
        <h1 className="mb-1 text-2xl font-semibold text-ink">
          Configura l&apos;amministratore
        </h1>
        <p className="mb-6 text-sm text-ink-muted">
          Usa il token di bootstrap fornito dall&apos;installazione. Il token è monouso e
          non viene salvato nel browser.
        </p>

        <Card>
          <form onSubmit={onSubmit} noValidate className="space-y-4">
            <Field
              id="token"
              label="Token di bootstrap"
              required
              error={errors.token?.message}
              hint="Valore di BOOTSTRAP_TOKEN nella configurazione del server."
            >
              <Input
                id="token"
                type="password"
                autoComplete="one-time-code"
                aria-invalid={Boolean(errors.token)}
                aria-describedby={errors.token ? "token-error" : "token-hint"}
                {...register("token")}
              />
            </Field>

            <Field id="email" label="Email" required error={errors.email?.message}>
              <Input
                id="email"
                type="email"
                autoComplete="username"
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
              hint="Almeno 12 caratteri, diversa dall'email."
            >
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                aria-invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? "password-error" : "password-hint"}
                {...register("password")}
              />
            </Field>

            <Field
              id="confirmPassword"
              label="Conferma password"
              required
              error={errors.confirmPassword?.message}
            >
              <Input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                aria-invalid={Boolean(errors.confirmPassword)}
                aria-describedby={
                  errors.confirmPassword ? "confirmPassword-error" : undefined
                }
                {...register("confirmPassword")}
              />
            </Field>

            {bootstrap.isError ? <ErrorState error={bootstrap.error} /> : null}

            <Button
              type="submit"
              busy={isSubmitting || bootstrap.isPending}
              className="w-full"
            >
              Crea amministratore
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-sm text-ink-muted">
          Amministratore già creato?{" "}
          <Link to="/login" className="font-medium text-accent underline">
            Vai al login
          </Link>
        </p>
      </div>
    </main>
  );
}
