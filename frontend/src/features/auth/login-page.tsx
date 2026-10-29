import { useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, type Location } from "react-router";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api/client";
import { MOCK_CREDENTIALS } from "@/mocks/credentials";

import { useAuth } from "./auth-provider";

type FieldName = "email" | "password";
/** Every message the form can show: one per field, plus `form` for the alert above the fields. */
type FormErrors = Partial<Record<FieldName | "form", string>>;

/** Copy for a sign-in that failed for a reason other than wrong credentials. */
function signInFailureMessage(error: unknown) {
  // apiFetch throws ApiError for any HTTP response, so anything else means no response at all:
  // offline, DNS, or CORS (fetch rejects with a TypeError).
  if (!(error instanceof ApiError)) {
    return "Couldn't reach SolNexus. Check your connection and try again.";
  }
  if (error.status >= 500) {
    return "SolNexus is having trouble right now. Try again in a few minutes.";
  }
  return "Something went wrong signing in. Try again.";
}

interface LoginFieldProps {
  name: FieldName;
  label: string;
  type: "email" | "password";
  autoComplete: string;
  placeholder?: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}

/** One labelled input with its error message wired up for screen readers. */
function LoginField({ name, label, error, onChange, ...input }: LoginFieldProps) {
  const errorId = `${name}-error`;
  return (
    <Field data-invalid={!!error || undefined}>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Input
        id={name}
        name={name}
        {...input}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={!!error || undefined}
        aria-describedby={error ? errorId : undefined}
      />
      <FieldError id={errorId}>{error}</FieldError>
    </Field>
  );
}

function focusField(form: HTMLFormElement | null, name: FieldName) {
  (form?.elements.namedItem(name) as HTMLInputElement | null)?.focus();
}

/** Sign-in screen from wireframe 01 (FR-10). There is no sign-up: the team creates accounts. */
export function LoginPage() {
  const { user, isChecking, signIn } = useAuth();
  const location = useLocation();
  // Keep the query and hash too, so a filtered list or a lead's tab survives the trip through sign-in.
  const fromLocation = (location.state as { from?: Location } | null)?.from;
  const from = fromLocation
    ? `${fromLocation.pathname}${fromLocation.search}${fromLocation.hash}`
    : "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [pending, setPending] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  // Wait for the session check like RequireAuth does, so a signed-in user opening /login sees a
  // spinner and then the redirect, not the form flashing first.
  if (isChecking) {
    return (
      <div className="flex min-h-svh items-center justify-center" aria-label="Checking sign-in">
        <Spinner />
      </div>
    );
  }
  // The only redirect: a successful signIn sets the user, and this re-render sends them on.
  if (user) return <Navigate to={from} replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedEmail = email.trim();
    const missing: FormErrors = {
      email: trimmedEmail ? undefined : "Enter your email.",
      password: password ? undefined : "Enter your password.",
    };
    setErrors(missing);
    if (missing.email || missing.password) {
      focusField(formRef.current, missing.email ? "email" : "password");
      return;
    }

    setPending(true);
    try {
      await signIn({ email: trimmedEmail, password });
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) {
        // The API answers the same for an unknown email, a wrong password or a deactivated
        // account, so the form can't and shouldn't point at a field.
        setErrors({ form: "Email or password is incorrect." });
        setPassword("");
        focusField(formRef.current, "password");
      } else {
        // The credentials may be fine in every case below, so keep them for a retry.
        setErrors({ form: signInFailureMessage(error) });
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex items-center gap-3 font-semibold">
          <span aria-hidden className="size-9 rounded-sm bg-muted-foreground/30" />
          SolNexus
        </div>
        <div className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold tracking-tight">Sign in</h1>
          <p className="text-sm text-muted-foreground">Lead tracking for the SolTech sales team</p>
        </div>

        {/* Dev server only. VITE_USE_MOCKS defaults to true in .env.example and compose.yaml, so a
            built bundle could have it on too, and a sign-in page shouldn't print a password. */}
        {import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true" && (
          // role="note": this is a hint, not an error, so screen readers shouldn't announce it.
          <Alert role="note">
            <AlertDescription>
              Mock API: sign in with {MOCK_CREDENTIALS.email} / {MOCK_CREDENTIALS.password}
            </AlertDescription>
          </Alert>
        )}

        {/* noValidate: show our own messages instead of the browser's, which vary by browser. */}
        <form ref={formRef} noValidate onSubmit={handleSubmit}>
          <FieldGroup>
            {errors.form && (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            )}
            <LoginField
              name="email"
              label="Email"
              type="email"
              autoComplete="username"
              placeholder="name@example.test"
              value={email}
              error={errors.email}
              onChange={setEmail}
            />
            <LoginField
              name="password"
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              error={errors.password}
              onChange={setPassword}
            />
            <Button type="submit" size="lg" disabled={pending}>
              {/* aria-hidden: the label already says "Signing in…"; the spinner's own "Loading" would repeat it. */}
              {pending && <Spinner data-icon="inline-start" aria-hidden />}
              {pending ? "Signing in…" : "Sign in"}
            </Button>
          </FieldGroup>
        </form>

        <p className="text-sm text-muted-foreground">
          Accounts are created by the SolNexus team. Ask them if you need access.
        </p>
      </div>
    </main>
  );
}
